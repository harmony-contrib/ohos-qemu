#!/usr/bin/env python3
"""Compare ordinary USB host calls with raw sysfs/device and UI/socket records.

This proves only the named host-query/descriptor/right/attachment contracts.
UDC, configfs, MTP, bulk byte streams, process death and the full historical USB
aggregate are deliberately not closed by this limited verifier.
"""
import json
import hashlib
from pathlib import Path
import re

VENDOR, PRODUCT = 0x0403, 0x6001
OWNER_ORDER = (
    'begin', 'query_absent_initial', 'query_original', 'connect_denied_original',
    'query_before_deny', 'right_denied', 'connect_denied_after_user_denial',
    'query_before_allow', 'right_granted', 'descriptors_original', 'descriptors_original_close',
    'query_after_other_bundle', 'right_retained_after_other_bundle', 'right_removed',
    'connect_denied_after_revoke', 'query_before_live_pipe', 'right_granted_live',
    'descriptors_live', 'query_detached', 'stale_control_transfer', 'stale_pipe_close_rejected',
    'query_replug', 'connect_denied_replug', 'query_before_replug_deny', 'right_denied_replug',
    'connect_denied_replug_after_denial', 'query_before_replug_allow', 'right_granted_replug',
    'descriptors_replug', 'descriptors_replug_close', 'right_removed_final',
    'query_absent_final', 'completed',
)
PEER_ORDER = ('begin', 'query_peer_while_owner_granted', 'connect_denied_other_bundle', 'completed')
DENIED = frozenset(name for name in OWNER_ORDER + PEER_ORDER if name.startswith('connect_denied_'))
ABSENT = frozenset(('query_absent_initial', 'query_detached', 'query_absent_final'))
RIGHTS = {'right_denied': (False, False), 'right_granted': (True, True),
          'right_removed': (True, False), 'right_granted_live': (True, True),
          'right_denied_replug': (False, False), 'right_granted_replug': (True, True),
          'right_removed_final': (True, False)}
UI_ORDER = ('usb-trusted-deny', 'usb-trusted-allow', 'usb-trusted-allow-live',
            'usb-trusted-deny-replug', 'usb-trusted-allow-replug')
SOCKET_ORDER = ('begin', 'attach', 'detach', 'attach', 'detach', 'quit')
WITNESS_ORDER = ('initial', 'original', 'live', 'detached', 'replug', 'final')


def rows(text):
    # GuestUi keeps the original command log but strips terminal newlines from
    # its already exit-framed body. JSON parsing still rejects truncated rows.
    if type(text) is not str:
        raise ValueError('raw USB records required')
    result = [json.loads(line) for line in text.splitlines()]
    if not result or any(type(row) is not dict for row in result):
        raise ValueError('nonempty USB object records required')
    return result


def octets(value, name):
    if type(value) is not list or not value or any(type(item) is not int or not 0 <= item <= 255 for item in value):
        raise ValueError('invalid raw USB byte array: ' + name)
    return bytes(value)


def sysfs(text):
    lines = text.splitlines()
    if (len(lines) < 8 or not lines[0].startswith('/sys/devices/') or '/..' in lines[0] or
            not all(re.fullmatch(r'[0-9]+', item) for item in lines[1:3]) or
            lines[3:6] != ['0403', '6001', 'QEMUAPI26'] or
            re.fullmatch(r'[0-9]+', lines[6]) is None):
        raise ValueError('actual dedicated USB sysfs tuple/serial/configuration missing')
    words = ' '.join(lines[7:]).split()
    if not words or any(re.fullmatch(r'[0-9a-f]{2}', word) is None for word in words):
        raise ValueError('raw sysfs descriptor hex required')
    data = bytes(int(word, 16) for word in words)
    if (len(data) < 18 or data[:2] != b'\x12\x01' or
            int.from_bytes(data[8:10], 'little') != VENDOR or
            int.from_bytes(data[10:12], 'little') != PRODUCT or
            data[17] != int(lines[6]) or data[16] == 0):
        raise ValueError('sysfs device descriptor does not describe dedicated FTDI hardware')
    return {'path': lines[0], 'bus': int(lines[1]), 'address': int(lines[2]),
            'serial': lines[5], 'configs': int(lines[6]), 'raw': data}


def detail(row):
    value = json.loads(row['details'].split('\n', 1)[0])
    if type(value) is not dict:
        raise ValueError('structured raw USB result required')
    return value


def query(row, witness, absent=False):
    value = detail(row)
    devices = value.get('devices')
    if type(devices) is not list or type(value.get('matching_count')) is not int:
        raise ValueError('raw getDevices result/count missing')
    keys = []
    selected = []
    for device in devices:
        if (type(device) is not dict or
                any(type(device.get(key)) is not int for key in ('busNum', 'devAddress', 'vendorId', 'productId')) or
                type(device.get('name')) is not str or not device['name']):
            raise ValueError('getDevices contains malformed device identity')
        keys.append((device['busNum'], device['devAddress']))
        if (device['vendorId'], device['productId']) == (VENDOR, PRODUCT):
            selected.append(device)
    if len(set(keys)) != len(keys) or value['matching_count'] != len(selected) or len(selected) != (0 if absent else 1):
        raise ValueError('duplicate/wrong attachment state in actual getDevices result')
    if absent:
        return None
    device = selected[0]
    if ((device['busNum'], device['devAddress']) != (witness['bus'], witness['address']) or
            type(device.get('configs')) is not list or len(device['configs']) != witness['configs']):
        raise ValueError('public USB tuple/configuration does not match independent sysfs')
    # A normal caller must obtain the serial through the authorized control path.
    if device.get('serial') != '':
        raise ValueError('ordinary getDevices leaked a serial identifier')
    return device


def descriptors(row, witness, device):
    value = detail(row)
    control = octets(value.get('control_bytes'), row['case'])
    raw = octets(value.get('raw_bytes'), row['case'])
    languages = octets(value.get('language_bytes'), row['case'])
    serial = octets(value.get('serial_bytes'), row['case'])
    if (value.get('name') != device['name'] or value.get('pipe') !=
            {'busNum': witness['bus'], 'devAddress': witness['address']} or
            type(value.get('control_count')) is not int or value['control_count'] != 18 or
            len(control) != 18 or control != witness['raw'][:18] or raw != witness['raw']):
        raise ValueError('GET_DESCRIPTOR/raw descriptor differs from physical sysfs bytes')
    if (type(value.get('language_count')) is not int or value['language_count'] != len(languages) or
            len(languages) < 4 or languages[0] != len(languages) or languages[1] != 3 or
            len(languages) % 2 or int.from_bytes(languages[2:4], 'little') == 0):
        raise ValueError('real LANGID descriptor missing or malformed')
    if (type(value.get('serial_count')) is not int or value['serial_count'] != len(serial) or
            len(serial) < 2 or serial[0] != len(serial) or serial[1] != 3 or len(serial) % 2 or
            serial[2:].decode('utf-16-le') != witness['serial']):
        raise ValueError('authorized control transfer did not read the actual USB serial bytes')


def verify(owner, peer, host, run_id, owner_bundle, peer_bundle):
    """Consume raw records; the enclosing original runner binds archive/boot/UID."""
    errors = []
    try:
        if (re.fullmatch('[0-9a-f]{32}', run_id) is None or owner_bundle == peer_bundle or
                type(host) is not dict or [row.get('label') for row in host['witnesses']] != list(WITNESS_ORDER)):
            raise ValueError('fresh distinct ordinary caller identity and complete physical witnesses required')
        witnesses = {}
        for row in host['witnesses']:
            absent = row['label'] in ('initial', 'detached', 'final')
            if type(row.get('raw')) is not str or (absent and row['raw'] != 'ABSENT'):
                raise ValueError('physical attachment witness incomplete')
            witnesses[row['label']] = None if absent else sysfs(row['raw'])
        if witnesses['original']['raw'] != witnesses['replug']['raw'] or witnesses['live'] != witnesses['original']:
            raise ValueError('replacement did not preserve the actual public physical descriptor tuple')
        identities = host['normal_uids']
        uids = [identities[bundle] for bundle in (owner_bundle, peer_bundle)]
        if any(type(uid) is not int or uid < 10000 for uid in uids) or uids[0] == uids[1]:
            raise ValueError('two different genuine ordinary application UIDs required')
        actors = {}
        for actor, records, order, bundle in (('owner', owner, OWNER_ORDER, owner_bundle),
                                               ('peer', peer, PEER_ORDER, peer_bundle)):
            if [row.get('case') for row in records] != list(order):
                raise ValueError('missing/duplicate/reordered USB ' + actor + ' calls')
            cases = {}
            for row in records:
                name = row['case']
                expected = (14400001 if name in DENIED else -1 if name == 'stale_control_transfer'
                            else 22 if name == 'stale_pipe_close_rejected' else 0)
                if (row.get('kind') != 'usb_manager_case' or row.get('run_id') != run_id or
                        row.get('actor') != actor or row.get('bundle') != bundle or row.get('passed') is not True or
                        row.get('code_type') != 'number' or type(row.get('code')) is not int or
                        row['code'] != expected or type(row.get('details')) is not str):
                    raise ValueError('wrong/stale/failed actual USB record: ' + name)
                cases[name] = row
            actors[actor] = cases
        owner_cases, peer_cases = actors['owner'], actors['peer']
        devices = {}
        for actor, cases in actors.items():
            for name, row in cases.items():
                if name.startswith('query_'):
                    slot = 'replug' if 'replug' in name else 'original'
                    devices[(actor, name)] = query(row, witnesses[slot], name in ABSENT)
        original = devices['owner', 'query_original']
        replacement = devices['owner', 'query_replug']
        if devices['peer', 'query_peer_while_owner_granted'] != original:
            raise ValueError('second bundle did not query the same actual original USB device')
        for actor, cases in actors.items():
            for name, row in cases.items():
                device = replacement if 'replug' in name or name == 'right_removed_final' else original
                if name in DENIED:
                    value = detail(row)
                    if value != {'name': device['name'], 'result': False, 'has_right': False}:
                        raise ValueError('unauthorized caller/other bundle unexpectedly has a right')
                elif name in RIGHTS:
                    expected, right = RIGHTS[name]
                    if detail(row) != {'name': device['name'], 'result': expected, 'has_right': right}:
                        raise ValueError('actual dialog/revoke result or subsequent hasRight differs')
        if owner_cases['right_retained_after_other_bundle']['details'] != original['name']:
            raise ValueError('owner right was not rechecked after independent ordinary peer')
        for name, slot, device in (('descriptors_original', 'original', original),
                                   ('descriptors_live', 'live', original),
                                   ('descriptors_replug', 'replug', replacement)):
            descriptors(owner_cases[name], witnesses[slot], device)
        journal = host['socket_journal']
        if [row.get('operation') for row in journal] != list(SOCKET_ORDER):
            raise ValueError('actual private endpoint attach/detach sequence incomplete')
        for index, row in enumerate(journal, 1):
            expected_connected = row['operation'] == 'attach'
            if (row.get('kind') != 'serial_host_attachment' or row.get('run_id') != run_id or
                    type(row.get('sequence')) is not int or row['sequence'] != index or
                    row.get('host_operation_completed') is not True or
                    row.get('host_socket_connected') is not expected_connected):
                raise ValueError('stale/failed/contradictory raw host socket operation')
        actions = host['ui_actions']
        if [row.get('label') for row in actions] != list(UI_ORDER):
            raise ValueError('actual five trusted UI decisions required')
        for index, row in enumerate(actions):
            decision = 'notAllowButton' if index in (0, 3) else 'allowButton'
            if (row.get('trusted_bundle') != 'com.usb.right' or row.get('decision') != decision or
                    row.get('clicked') is not True or row.get('selected_node', {}).get('bundle') != 'com.usb.right'):
                raise ValueError('USB authorization did not use the actual trusted dialog control')
        if set(host['cleanup']) != {owner_bundle, peer_bundle} or 'endpoint_cleanup_error' in host:
            raise ValueError('both own ordinary bundles and the private endpoint require cleanup')
        for row in host['cleanup'].values():
            if (row.get('stop_reply') != 'force stop process successfully.' or row.get('pidof') != '' or
                    type(row.get('absence_observations')) is not int or row['absence_observations'] < 2 or
                    type(row.get('uninstall_reply')) is not str or
                    re.search(r'\bsuccess\b', row['uninstall_reply'], re.I) is None or 'error' in row):
                raise ValueError('owned USB caller cleanup was not established by actual commands')
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError) as error:
        errors.append(str(error))
    return errors


def verify_saved(directory, run_id, owner_bundle, peer_bundle):
    """Recompute from the original runner's saved raw child files."""
    directory = Path(directory)
    host = json.loads((directory / 'host-witnesses.json').read_text())
    errors = verify(rows((directory / 'owner-results.jsonl').read_text()),
                    rows((directory / 'peer-results.jsonl').read_text()), host,
                    run_id, owner_bundle, peer_bundle)
    if errors:
        return errors
    try:
        from guest_ui import select_node, command_exit
        from run_normal_hap_probe import require_normal_identity

        def command_body(record, shell=True):
            path = Path(record['log'])
            if (path.is_symlink() or not path.is_file() or
                    not path.resolve().is_relative_to(directory.parent.resolve()) or
                    hashlib.sha256(path.read_bytes()).hexdigest() != record.get('sha256') or
                    type(record.get('exit_code')) is not int or record['exit_code'] != 0):
                raise ValueError('original USB command log missing, changed, failed or outside enclosing runner')
            text = path.read_text().replace('\r', '')
            if not shell:
                return text
            markers = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', record['argv'][-1])
            if len(markers) != 1:
                raise ValueError('original command-bound UITest exit marker required')
            body, code = command_exit(text, markers[0])
            if code != 0:
                raise ValueError('actual USB guest command failed')
            return body.rstrip('\n')

        if rows((directory / 'host-attachment.jsonl').read_text()) != host['socket_journal']:
            raise ValueError('embedded USB socket sequence differs from original raw journal')
        for witness in host['witnesses']:
            if command_body(witness['command']) != witness['raw']:
                raise ValueError('USB physical witness differs from its original command log')
        for bundle in (owner_bundle, peer_bundle):
            record = host['normal_identity_commands'][bundle]
            if (not record['argv'][-1].startswith('bm dump -n ' + bundle + ';') or
                    require_normal_identity(command_body(record), bundle) != host['normal_uids'][bundle]):
                raise ValueError('USB caller UID differs from actual ordinary application identity')
        for action in host['ui_actions']:
            layout = Path(action['layout'])
            if (layout.is_symlink() or not layout.is_file() or
                    not layout.resolve().is_relative_to(directory.parent.resolve() / 'ui') or
                    hashlib.sha256(layout.read_bytes()).hexdigest() != action.get('layout_sha256')):
                raise ValueError('actual trusted USB layout file is missing, changed or outside original runner')
            node = action['selected_node']
            actual = select_node(json.loads(layout.read_text()), 'com.usb.right',
                                 text=node['attributes']['text'], clickable=True)
            if actual != node:
                raise ValueError('selected trusted USB control differs from actual captured layout')
            left, top, width, height = node['rect']
            prefix = 'uitest uiInput click ' + str(left + width // 2) + ' ' + str(top + height // 2) + ';'
            if not action['click_command']['argv'][-1].startswith(prefix):
                raise ValueError('actual USB click command targets a different UI location')
            command_body(action['click_command'])
        for bundle, cleanup in host['cleanup'].items():
            for field in ('stop', 'pid'):
                prefix = ('aa force-stop ' + bundle + ';' if field == 'stop' else
                          'pidof ' + bundle + ' || true;')
                if not cleanup[field + '_command']['argv'][-1].startswith(prefix):
                    raise ValueError('actual cleanup command targets another application')
                observed = command_body(cleanup[field + '_command'])
                if observed != cleanup['stop_reply' if field == 'stop' else 'pidof']:
                    raise ValueError('owned USB process cleanup differs from actual command')
            absent = cleanup['absence_commands']
            if (len(absent) != 2 or any(not record['argv'][-1].startswith('pidof ' + bundle + ' || true;') or
                    command_body(record) != '' for record in absent)):
                raise ValueError('two raw consecutive own USB process absence observations required')
            if (cleanup['uninstall_command']['argv'][-2:] != ['uninstall', bundle] or
                    command_body(cleanup['uninstall_command'], shell=False) != cleanup['uninstall_reply']):
                raise ValueError('own USB bundle uninstall differs from actual command')
            result = directory / ('owner-results.jsonl' if bundle == owner_bundle else 'peer-results.jsonl')
            remote = '/data/app/el2/100/base/' + bundle + '/files/usb-manager-results.log'
            retained = cleanup['retained_result_command']
            if (not retained['argv'][-1].startswith('if test -f ' + remote + '; then cat ' + remote + '; fi;') or
                    command_body(retained) != result.read_text()):
                raise ValueError('ordinary USB raw result differs from its final captured command')
    except (ValueError, KeyError, TypeError, OSError) as error:
        errors.append(str(error))
    return errors
