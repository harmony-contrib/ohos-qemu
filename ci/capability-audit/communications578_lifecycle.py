"""Cross-environment observer/revocation/queued-off/exit/recovery callback stage.

All three callers use the same fixed guest source. The root must use three
separately signed, real system bundles and its existing complete PID/UID scans.
No component here owns a VM, host process, token tool, HDC instance or lease.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
import time
import traceback
from communications578_contract import case, URC, OBSERVER
from communications578_raw import decode, peer_rows, receipt, require, rows_from_text, terminal_ok

ROLES = ('system', 'system_peer', 'system_replacement')


def run_lifecycle(guest, root_callbacks, *, run_id, boot_id, output, executables):
    from communications578_runtime import CALLBACKS
    require(set(root_callbacks) == CALLBACKS and all(callable(v) for v in root_callbacks.values()), 'Original callbacks missing')
    require(re.fullmatch('[a-f0-9]{32}', run_id) and re.fullmatch('[a-f0-9-]{36}', boot_id), 'Original Owner identities missing')
    output = Path(output); output.mkdir(exist_ok=False)
    report = {'schema': 'communications578-observer-lifecycle/v1', 'run_id': run_id, 'boot_id': boot_id,
              'receipts': [], 'raw_captures': [], 'requests': [], 'cleanup_errors': [],
              'status': 'incomplete', 'actual_new_image_pass': False}
    journals = {}; identities = {}; texts = {}; counter = 0; windows = []; issued = {}; cached_windows = []

    def keep(name, value):
        raw = value.encode() if type(value) is str else (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
        path = output / name; path.write_bytes(raw)
        return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

    def save(): keep('result.json', report)

    def checked(value):
        require(type(value) is dict and type(value.get('receipts')) is list and value['receipts'], 'Actual callback receipts absent')
        for row in value['receipts']: receipt(row, boot_id, executables)
        report['receipts'].extend(value['receipts']); save(); return value

    def collect(role, op):
        nonlocal counter
        result = checked(root_callbacks['collect'](guest, role, op)); raw = result.get('raw')
        require(type(raw) is str and raw.startswith(texts.get(role, '')), 'Journal replaced/truncated')
        counter += 1; report['raw_captures'].append(keep(role + '-' + str(counter).zfill(5) + '.jsonl', raw))
        if not raw: return []
        first = decode(raw.splitlines()[0]); identity = (first['pid'], first['uid'])
        require(type(identity[0]) is int and identity[0] > 0 and type(identity[1]) is int and identity[1] > 0, 'Real PID/UID missing')
        if role not in identities:
            require(type(result.get('bms_raw')) is str and type(result.get('process_identity_raw')) is str and
                    result['process_identity_raw'] and type(result.get('module_files_raw')) is str and result['module_files_raw'], 'Real BMS/process/files identity absent')
            app = decode(result['bms_raw'])['applicationInfo']
            require(app['uid'] == identity[1] and app.get('isSystemApp') is True, 'Actual lifecycle system role mismatch')
            identities[role] = identity; report.setdefault('identities', {})[role] = result
        require(identities[role] == identity, 'Caller process generation changed')
        texts[role] = raw; journals[role] = rows_from_text(raw, run_id, boot_id, *identity)
        save(); return journals[role]

    def command(role, name, api='', *, action='invoke', form='callback', listener='a', expected='return', wait_ms=5000):
        c = case(name, api, form)
        c.update(action=action, listener=listener, wait_ms=wait_ms, run_id=run_id, boot_id=boot_id,
                 operation_id=secrets.token_hex(16)); c.pop('expect')
        issued[c['operation_id']] = (role, c, expected)
        report['requests'].append(dict(role=role, request=c)); save()
        checked(root_callbacks['start'](guest, role, 'EntryAbility', c)); return c

    def wait(role, request, kind='end'):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            rows = collect(role, request['operation_id'])
            matching = [r for r in rows if r['operation_id'] == request['operation_id'] and r['kind'] == kind]
            if matching:
                require(len(matching) == 1, 'Repeated actual acknowledgement')
                return matching[0]
            time.sleep(.1)
        raise ValueError('Actual lifecycle acknowledgement missing: ' + request['case_id'] + '/' + kind)

    def invoke(role, name, api, **kw):
        c = command(role, name, api, **kw); wait(role, c); return c

    def register(role, name, listener, known, active):
        # Registration can request the genuinely known cached registry value.
        # Bound it separately so late callbacks cannot disappear between pulses.
        c = invoke(role, name, OBSERVER[0], listener=listener)
        settled = command(role, name + '-cached-settle', action='quiet')
        wait(role, settled)
        cached_windows.append(dict(role=role, request=c, settled=settled,
                                   known=known, active=list(active)))
        return c

    def pulse(name, kind, active, expected, queue=None):
        opened = {}
        for role in active:
            if queue is not None and role == 'system': continue
            c = command(role, name + '-' + role, action='quiet')
            wait(role, c, 'begin'); opened[role] = c
        op = queue['operation_id'] if queue is not None else next(iter(opened.values()))['operation_id']
        checked(root_callbacks['network'](guest, 'communications-at-write', {'operation_id': op, 'kind': kind}))
        if queue is not None:
            wait('system', queue)
            opened['system'] = command('system', name + '-drain', action='quiet')
        for role, c in opened.items(): wait(role, c)
        windows.append(dict(name=name, kind=kind, operation_id=op, opened=opened, expected=expected, queue=queue))

    try:
        checked(root_callbacks['prepare_callers'](guest, 'communications578', run_id, ROLES))
        for role in ROLES[:2]:
            checked(root_callbacks['install'](guest, role))
            c = command(role, role + '-exports', action='exports'); wait(role, c)
        checked(root_callbacks['network'](guest, 'communications-at-open', {'run_id': run_id, 'boot_id': boot_id}))
        baseline_op = secrets.token_hex(16)
        checked(root_callbacks['network'](guest, 'communications-at-write', {'operation_id': baseline_op, 'kind': 'zero'}))
        register('system', 'main-on-a', 'a', False, ('a',))
        register('system', 'main-on-b', 'b', False, ('a', 'b'))
        register('system_peer', 'peer-on', 'peer', False, ('peer',))
        pulse('both-one', 'one', ROLES[:2], {'system': [('a', True), ('b', True)], 'system_peer': [('peer', True)]})
        invoke('system', 'main-off-a', OBSERVER[1])
        pulse('other-env-zero', 'zero', ROLES[:2], {'system': [('b', False)], 'system_peer': [('peer', False)]})
        checked(root_callbacks['network'](guest, 'communications-queue-native-begin', {'role': 'system'}))
        queued = command('system', 'queued-generation-on-off', OBSERVER[0], form='queued-off', listener='queued')
        wait('system', queued, 'armed')
        pulse('queued-one', 'one', ROLES[:2], {'system': [('b', True)], 'system_peer': [('peer', True)]}, queue=queued)
        native = checked(root_callbacks['network'](guest, 'communications-queue-native-end', {'role': 'system'}))
        # This cut must be produced by the root's existing bounded native capture
        # around this exact queue attempt, filtered to actual main caller PID.
        require(native.get('pid') == identities['system'][0] and type(native.get('raw')) is str and
                native['raw'].count('OnCommunicationStateUpdated slotId = 0, activeStateResult = 1') == 1,
                'No actual bounded native receive cut for queued-generation challenge')
        queue_cached_count = native['raw'].count('OnCommunicationStateUpdated slotId = 0, activeStateResult = 0')
        require(queue_cached_count in (0, 1), 'Duplicate native cached update during queued registration')
        report['queued_native'] = keep('queued-native.json', native)
        revoke = checked(root_callbacks['input'](guest, 'communications-revoke-network-info', {'role': 'system'}))
        rejection = decode(revoke['raw'])
        require(rejection['kind'] == 'fixed-permission-revoke-attempt' and rejection['run_id'] == run_id and
                rejection['boot_id'] == boot_id and rejection['target_pid'] == identities['system'][0] and
                rejection['kill_process'] is False and rejection['flag_before'] & 4 and rejection['revoke_result'] != 0 and
                rejection['flag_before'] == rejection['flag_after'] == rejection['flag_final'] and
                rejection['status_before'] == rejection['status_after'] == rejection['status_final'] == 0 and
                rejection['target_start_ticks_before'] == rejection['target_start_ticks_after'] > 0,
                'Actual SYSTEM_FIXED rejection/unchanged live token proof differs')
        report['live_permission_revocation'] = {'support': 'unsupported_platform_SYSTEM_FIXED',
            'raw': keep('real-fixed-permission-attempt.json', rejection),
            'note': 'The real revoke was rejected. No successful revocation or denied delivery is claimed; observer-denied separately requires actual public 201.'}
        register('system', 'on-after-rejected-revoke', 'revokeprobe', True, ('b', 'revokeprobe'))
        invoke('system', 'off-after-rejected-revoke', OBSERVER[1], listener='revokeprobe')
        pulse('fixed-permission-zero', 'zero', ROLES[:2], {'system': [('b', False)], 'system_peer': [('peer', False)]})
        exited = checked(root_callbacks['network'](guest, 'communications-caller-exit', {'role': 'system'}))
        require(type(exited.get('raw')) is str and exited['raw'], 'Original Owner complete caller-exit scans missing')
        report['exited'] = keep('caller-exit.json', exited)
        pulse('surviving-env-one', 'one', ('system_peer',), {'system_peer': [('peer', True)]})
        checked(root_callbacks['install'](guest, 'system_replacement'))
        register('system_replacement', 'replacement-on', 'replacement', True, ('replacement',))
        pulse('replacement-zero', 'zero', ROLES[1:], {'system_peer': [('peer', False)], 'system_replacement': [('replacement', False)]})
        invoke('system_replacement', 'replacement-off', OBSERVER[1], listener='replacement')
        invoke('system_peer', 'peer-off', OBSERVER[1], listener='peer')
        pulse('all-off-one', 'one', ROLES[1:], {'system_peer': [], 'system_replacement': []})
        pulse('reset-zero', 'zero', ROLES[1:], {'system_peer': [], 'system_replacement': []})
        for role in ROLES[1:]:
            c = command(role, role + '-cleanup', action='cleanup'); wait(role, c)
        evidence = checked(root_callbacks['network'](guest, 'communications-at-evidence', {}))
        wire, path = peer_rows(evidence.get('peer_raw'), run_id, boot_id)
        require(evidence.get('binding_raw', '').splitlines() == [path, path], 'Actual AT/RIL reader PTY binding differs')
        baseline = [r for r in wire if r['kind'] == 'tx' and r['operation_id'] == baseline_op]
        require(len(baseline) == 1 and baseline[0]['bytes'] == URC['zero'], 'Real initial zero update missing')
        for role, rows in journals.items():
            for op, (which, request, expected) in issued.items():
                if which != role: continue
                own = [r for r in rows if r['operation_id'] == op]
                begins = [r for r in own if r['kind'] == 'begin']; ends = [r for r in own if r['kind'] == 'end']
                terminals = [r for r in own if r['kind'] in ('return', 'throw', 'reject')]
                require(len(begins) == len(ends) == len(terminals) == 1 and begins[0]['value'] == request and
                        begins[0]['seq'] < terminals[0]['seq'] < ends[0]['seq'], 'Incomplete/unbound lifecycle command')
                terminal_ok(terminals[0], expected)
        accounted = {role: set() for role in ROLES}
        for cached in cached_windows:
            role = cached['role']; rs = journals[role]
            begin = next(r for r in rs if r['kind'] == 'begin' and r['operation_id'] == cached['request']['operation_id'])
            settled = next(r for r in rs if r['kind'] == 'end' and r['operation_id'] == cached['settled']['operation_id'])
            actual = [r for r in rs if r['kind'] == 'callback' and begin['seq'] < r['seq'] < settled['seq']]
            require(all(type(r['value']) is dict and set(r['value']) == {'listener', 'slot', 'payload'} and
                        r['value']['listener'] in cached['active'] and r['value']['slot'] == 0 and
                        r['value']['payload'] is cached['known'] for r in actual), 'Foreign/unknown state in cached registration interval')
            names = [r['value']['listener'] for r in actual]
            require(len(names) == len(set(names)), 'Duplicate public cached registration delivery')
            # A cached callback is allowed only here; successful later wire
            # pulses independently require every registered listener to fire.
            accounted[role].update(r['seq'] for r in actual)
        for window in windows:
            transmitted = [r for r in wire if r['kind'] == 'tx' and r['operation_id'] == window['operation_id']]
            require(len(transmitted) == 1 and transmitted[0]['bytes'] == URC[window['kind']], 'Exact lifecycle wire/nonce differs')
            at = transmitted[0]['monotonic_ms']
            for role, expected in window['expected'].items():
                c = window['opened'][role]; rs = journals[role]
                begin = next(r for r in rs if r['kind'] == 'begin' and r['operation_id'] == c['operation_id'])
                end = next(r for r in rs if r['kind'] == 'end' and r['operation_id'] == c['operation_id'])
                require(end['monotonic_ms'] - begin['monotonic_ms'] >= c['wait_ms'], 'Lifecycle quiet shortened')
                if window['queue'] is not None and role == 'system':
                    armed = next(r for r in rs if r['kind'] == 'armed' and r['operation_id'] == window['operation_id'])
                    terminal = next(r for r in rs if r['kind'] == 'return' and r['operation_id'] == window['operation_id'])
                    require(armed['monotonic_ms'] <= at < terminal['monotonic_ms'] and
                            terminal['monotonic_ms'] - armed['monotonic_ms'] >= 5000, 'URC did not arrive during actual blocked generation')
                    lower = armed['seq']
                else:
                    require(begin['monotonic_ms'] <= at <= end['monotonic_ms'], 'Wire outside live callback interval')
                    lower = begin['seq']
                actual = [r for r in rs if r['kind'] == 'callback' and lower < r['seq'] < end['seq']]
                require(all(r['value']['slot'] == 0 and type(r['value']['payload']) is bool and r['monotonic_ms'] >= at for r in actual), 'Foreign/type/early lifecycle callback')
                if window['queue'] is not None and role == 'system' and queue_cached_count:
                    cached = [r for r in actual if r['value'] == {'listener': 'b', 'slot': 0, 'payload': False}]
                    require(len(cached) == 1, 'Actual native cached generation did not reach surviving listener exactly once')
                    accounted[role].add(cached[0]['seq']); actual.remove(cached[0])
                require(sorted((r['value']['listener'], r['value']['payload']) for r in actual) == sorted(expected), 'Cross-env/revoke/queue/exit semantics differ: ' + window['name'] + '/' + role)
                accounted[role].update(r['seq'] for r in actual)
        require(len(set(identities.values())) == 3, 'Fresh distinct environment identities missing')
        require(not [r for rs in journals.values() for r in rs if r['kind'] == 'callback' and r['value'].get('listener') == 'queued'],
                'Removed native queued generation reached its public callback')
        require(all({r['seq'] for r in journals[role] if r['kind'] == 'callback'} == accounted[role] for role in ROLES),
                'Uncorrelated/late lifecycle callback outside actual wire or cached registration intervals')
        for role in ROLES: keep(role + '-final.jsonl', texts.get(role, ''))
        report['status'] = 'raw_lifecycle_matched_NOT_capability_closure'
        report['windows'] = windows; report['cached_windows'] = cached_windows
        report['wire'] = keep('at-evidence.json', evidence)
    except Exception as error:
        report['status'] = 'fail_raw_preserved'; report['error'] = type(error).__name__ + ': ' + str(error)
        report['traceback'] = traceback.format_exc()
    finally:
        try:
            cleanup = checked(root_callbacks['cleanup'](guest)); require(cleanup.get('raw'), 'Original Owner cleanup raw missing')
            report['cleanup'] = cleanup
        except Exception as error:
            report['cleanup_errors'].append(str(error)); report['status'] = 'fail_raw_preserved'
        for role, raw in texts.items(): keep(role + '-final.jsonl', raw)
        save()
    return report
