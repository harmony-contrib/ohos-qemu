"""Strict same-guest raw semantics. No resource creation or capability ledger write."""
import json
import re
from communications578_contract import plan, RTT, OBSERVER, URC

FIELDS = {'schema', 'run_id', 'boot_id', 'operation_id', 'case_id', 'action', 'api', 'seq', 'files_dir',
          'monotonic_ms', 'pid', 'uid', 'kind', 'code', 'phase', 'value'}
PEER_FIELDS = {'schema', 'run_id', 'boot_id', 'pid', 'uid', 'seq', 'monotonic_ms', 'kind', 'operation_id', 'hex'}


def require(condition, message):
    if not condition: raise ValueError(message)


def decode(value):
    def pairs(items):
        result = {}
        for key, item in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def receipt(item, boot, executables):
    require(type(item) is dict and {'argv', 'exit_code', 'stdout', 'stderr', 'boot_id'} <= set(item), 'Actual command receipt missing')
    require(item['boot_id'] == boot and type(item['argv']) is list and item['argv'] and
            item['argv'][0] in executables and all(type(s) is str and '\x00' not in s for s in item['argv']) and
            type(item['exit_code']) is int and type(item['stdout']) is str and type(item['stderr']) is str,
            'Command identity/raw/exit missing')
    require(item['exit_code'] == 0, 'Actual command failed: ' + repr(item['argv']))
    return item['stdout']


def rows_from_text(raw, run, boot, pid, uid):
    require(type(raw) is str and raw.endswith('\n') and 0 < len(raw.encode()) <= 16 * 1024 * 1024, 'Raw missing/truncated/oversized')
    rows = []; previous = -1
    for line in raw.splitlines():
        require(0 < len(line) <= 262144, 'Raw line limit')
        row = decode(line)
        require(type(row) is dict and set(row) == FIELDS, 'Raw field set')
        require(row['schema'] == 1 and row['run_id'] == run and row['boot_id'] == boot and
                row['pid'] == pid and row['uid'] == uid, 'Foreign raw run/boot/process/UID')
        require(type(row['seq']) is int and row['seq'] == len(rows) + 1 and
                type(row['monotonic_ms']) is int and row['monotonic_ms'] >= previous, 'Raw sequence/time regression')
        require(row['kind'] in ('begin', 'return', 'reject', 'throw', 'end', 'callback', 'state', 'bt-sample', 'bt-callback', 'cleanup-step', 'sms-send', 'sms-delivery', 'armed') and
                row['phase'] in ('sync', 'settled', 'promise', 'callback') and type(row['code']) is int and
                re.fullmatch('[a-f0-9]{32}', row['operation_id']), 'Unrecognized raw event')
        previous = row['monotonic_ms']; rows.append(row)
    return rows


def peer_rows(raw, run, boot):
    require(type(raw) is str and raw.endswith('\n') and len(raw.encode()) <= 8 * 1024 * 1024, 'Peer raw absent/truncated')
    result = []; previous = -1; identity = None
    for line in raw.splitlines():
        row = decode(line)
        require(type(row) is dict and set(row) == PEER_FIELDS and row['schema'] == 1 and
                row['run_id'] == run and row['boot_id'] == boot and type(row['pid']) is int and row['pid'] > 0 and
                row['uid'] == 0 and row['seq'] == len(result) + 1 and type(row['monotonic_ms']) is int and
                row['monotonic_ms'] >= previous and row['kind'] in ('ready', 'rx', 'tx', 'control', 'closed') and
                re.fullmatch('[a-f0-9]{32}', row['operation_id']) and re.fullmatch('([a-f0-9]{2})*', row['hex']), 'Invalid peer journal')
        if identity is None: identity = (row['pid'], row['uid'])
        require(identity == (row['pid'], row['uid']), 'Peer generation changed')
        previous = row['monotonic_ms']; row['bytes'] = bytes.fromhex(row['hex']); result.append(row)
    require(result and result[0]['kind'] == 'ready', 'No actual PTY ready')
    path = result[0]['bytes'].decode('ascii')
    require(re.fullmatch('/dev/pts/[0-9]+', path), 'Foreign PTY path')
    # Proves actual read-loop command traffic, not just successful writes to an unopened PTY.
    received = b''.join(r['bytes'] for r in result if r['kind'] == 'rx')
    require(b'ATE0Q0V1\r' in received and b'AT+CFUN=1,0\r' in received, 'Actual RIL ModemInit traffic missing')
    return result, path


def terminal_ok(row, expected):
    if type(expected) is int:
        require(row['kind'] in ('throw', 'reject') and row['code'] == expected, 'Exact public BusinessError differs')
    elif expected in ('telephony-failure', 'capability-local', 'sms-result'):
        if expected in ('capability-local', 'sms-result') and row['kind'] == 'return':
            require(row['code'] == 0, 'Local capability return code')
        else:
            require(row['kind'] in ('throw', 'reject') and 8300001 <= row['code'] <= 8499999 and
                    type(row['value']) is dict and type(row['value'].get('message')) is str and row['value']['message'],
                    'Actual telephony service failure required; no session success/JS/permission/unsupported substitute')
    elif expected in ('bt-enable', 'bt-disable'):
        require((row['kind'] == 'return' and row['code'] == 0) or
                (row['kind'] in ('throw', 'reject') and row['code'] in (2900003, 2900099)), 'Unexpected Bluetooth transition result')
    else:
        require(row['kind'] == 'return' and row['code'] == 0, 'Public success missing')
    if row['kind'] in ('throw', 'reject'):
        require(type(row['value']) is dict and set(row['value']) == {'message'} and
                type(row['value']['message']) is str and row['value']['message'], 'Error raw message missing')


def review(rows, profile, commands, *, peer_raw=None, at_binding_raw=None, run=None, boot=None):
    spec = plan(profile); begins = [r for r in rows if r['kind'] == 'begin']
    require(len(begins) == len(commands) == len(spec) and [r['case_id'] for r in begins] == [c['case_id'] for c in spec],
            'Finite profile incomplete/reordered/extra')
    require(len({r['operation_id'] for r in begins}) == len(begins), 'Replayed operation')
    mapping = {r['operation_id']: r for r in begins}; operations = {}
    for i, (begin, request, expected) in enumerate(zip(begins, commands, spec)):
        require(begin['value'] == request and begin['operation_id'] == request['operation_id'] and
                begin['case_id'] == request['case_id'] and begin['api'] == request['api'], 'Raw request binding differs')
        own = [r for r in rows if r['operation_id'] == begin['operation_id']]
        ends = [r for r in own if r['kind'] == 'end']; terms = [r for r in own if r['kind'] in ('return', 'throw', 'reject')]
        require(len(ends) == len(terms) == 1 and begin['seq'] < terms[0]['seq'] < ends[0]['seq'], 'Operation did not complete exactly once')
        require(all(r['case_id'] == begin['case_id'] and r['api'] == begin['api'] and r['action'] == begin['action'] for r in own), 'Event origin identity drift')
        if i + 1 < len(begins): require(ends[0]['seq'] < begins[i + 1]['seq'], 'Concurrent commands')
        terminal_ok(terms[0], expected['expect'])
        if request['action'] == 'consent':
            require(terms[0]['value'] == {'permissions': ['ohos.permission.ACCESS_BLUETOOTH'], 'authResults': [0]},
                    'Actual Bluetooth user grant missing')
        if begin['action'] == 'quiet':
            require(ends[0]['monotonic_ms'] - begin['monotonic_ms'] >= request['wait_ms'], 'Quiet window shortened')
        operations[begin['case_id']] = (begin, terms[0], ends[0])
    require(all(r['operation_id'] in mapping for r in rows), 'Foreign callback/row')
    require(all(r['code'] == 0 for r in rows if r['kind'] in ('begin', 'end', 'callback', 'bt-sample', 'bt-callback', 'cleanup-step')), 'Control/release event failed')
    exports = operations['exports'][1]['value']
    require(type(exports) is dict and set(exports) == set(RTT + OBSERVER + ('startPairOutOfBand',)) and
            set(exports.values()) == {'function'}, 'One or more actual guest public exports missing')
    events = [r for r in rows if r['kind'] == 'callback']
    if profile.startswith('rtt') or profile in ('no-modem', 'observer-denied'):
        require(not events, 'Invented no-session/unauthorized callback')
    if profile == 'observer':
        wire, path = peer_rows(peer_raw, run, boot)
        require(type(at_binding_raw) is str and at_binding_raw.splitlines() == [path, path],
                'Configured AT device and actual RIL reader fd are not the same PTY')
        windows = {'invalid-urc': [], 'one-urc': [('a', True), ('b', True)],
                   'zero-urc': [('a', False), ('b', False)], 'one-after-off-a': [('b', True)],
                   'zero-after-off-all': [], 'one-next-generation': [('a2', True)], 'final-zero': []}
        cached_begin = operations['on-a-next-generation'][0]
        cached_end = operations['next-generation-cached-zero'][2]
        cached = [r for r in events if cached_begin['seq'] < r['seq'] < cached_end['seq']]
        require(len(cached) == 1 and cached[0]['value'] == {'listener': 'a2', 'slot': 0, 'payload': False},
                'Actual known zero cache was not delivered once to the new generation')
        for expected in spec:
            if 'stimulus' not in expected: continue
            name = expected['case_id']; begin, _, end = operations[name]
            tx = [r for r in wire if r['kind'] == 'tx' and r['operation_id'] == begin['operation_id']]
            require(len(tx) == 1 and tx[0]['bytes'] == URC[expected['stimulus']] and
                    begin['monotonic_ms'] <= tx[0]['monotonic_ms'] <= end['monotonic_ms'], 'Wire bytes/nonce/window differ')
            actual = [r for r in events if begin['seq'] < r['seq'] < end['seq']]
            require(all(type(r['value']) is dict and set(r['value']) == {'listener', 'slot', 'payload'} and
                        r['value']['slot'] == 0 and type(r['value']['payload']) is bool and
                        r['monotonic_ms'] >= tx[0]['monotonic_ms'] for r in actual), 'Callback type/slot/wire causality differs')
            require(sorted((r['value']['listener'], r['value']['payload']) for r in actual) == sorted(windows[name]),
                    'Boolean/listener/on-off/generation semantics differ: ' + name)
        require(all(e in cached or any(operations[name][0]['seq'] < e['seq'] < operations[name][2]['seq'] for name in windows)
                    for e in events), 'Uncorrelated/late observer callback')
    if profile == 'bluetooth':
        require(not [r for r in rows if r['kind'] == 'bt-callback' and r['value'] not in (0, 1, 3)], 'False ON/BLE_ON callback')
        for name in ('off-baseline', 'failed-enable-0', 'final-off-0', 'failed-enable-1', 'final-off-1'):
            begin, _, end = operations[name]
            samples = [r for r in rows if r['kind'] == 'bt-sample' and begin['seq'] < r['seq'] < end['seq']]
            require(len(samples) >= 20 and all(type(r['value']) is dict and set(r['value']) == {'state', 'paired'} and
                    r['value']['state'] in (0, 1, 3) and r['value']['paired'] == [] for r in samples), 'False ON/paired state or missing state samples')
            require(all(r['value']['state'] == 0 for r in samples[-10:]) and
                    samples[-1]['monotonic_ms'] - samples[-10]['monotonic_ms'] >= 800, 'Bluetooth did not settle stably OFF')
    if profile == 'no-modem':
        states = [r for r in rows if r['kind'] == 'state']
        require(len(states) == 36, 'Complete before/during/after SIM/network/radio/data/service queries missing')
        for row in states:
            api = row['value']['api']; value = row['value'].get('value')
            if row['code']:
                require(8300001 <= row['code'] <= 8499999 and api != 'hasCall', 'No-device query hid permission/JS error')
            elif api in ('hasSimCard', 'hasCall'): require(value is False, 'Manufactured SIM/call')
            elif api == 'getSimState': require(value in (0, 1), 'Unexpected active/ready SIM')
            elif api == 'getNetworkState':
                require(type(value) is dict and type(value.get('isEmergency')) is bool and value.get('regState') in (0, 2, 3), 'Manufactured registered network')
            elif api == 'getCellularDataState': require(value in (-1, 0), 'Manufactured cellular data connection')
            elif api == 'getCellularDataFlowType': require(value == 0, 'Manufactured cellular data traffic')
            elif api == 'isRadioOn': require(type(value) is bool, 'Radio status not a public bool')
            elif api == 'isCellularDataEnabled': require(type(value) is bool, 'Data policy getter not boolean')
        sms = operations['sms-no-modem'][1]
        sent = [r for r in rows if r['kind'] == 'sms-send']
        delivered = [r for r in rows if r['kind'] == 'sms-delivery']
        require(not delivered, 'Invented no-modem SMS delivery')
        require(len(sent) <= 1, 'Duplicate SMS result')
        if sms['kind'] == 'return': require(len(sent) == 1, 'SMS enqueue success has no real failure callback')
        for row in sent:
            require(row['operation_id'] == sms['operation_id'] and type(row['value']) is dict and
                    ((row['code'] != 0 and 8300001 <= row['code'] <= 8499999) or
                     (row['code'] == 0 and type(row['value'].get('info')) is dict and
                      row['value']['info'].get('result') in (1, 2, 3))), 'Invented SMS success or malformed failure')
        restore = [r for r in rows if r['kind'] == 'cleanup-step' and r['value'].get('api') == 'restoreCellularDataPolicy']
        require(len(restore) == 1 and type(restore[0]['value']['baseline']) is bool and
                restore[0]['value']['actual'] is restore[0]['value']['baseline'], 'Data policy was not restored to actual baseline')
    return {'status': 'raw_behavior_matched_NOT_capability_closure', 'profile': profile,
            'operations': len(operations), 'callbacks': len(events), 'raw_rows': len(rows),
            'unverified_positive': ['IMS_RTT_peer_session', 'Bluetooth_controller_peer_pairing'],
            'not_proved_by_this_profile': ['cross_env', 'permission_revocation', 'native_queued_generation', 'service_restart']}
