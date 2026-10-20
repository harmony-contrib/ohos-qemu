"""Independent actual raw replay for the public APN dialog and DB consumer."""
import re
from apps_ui578_contract import decode, load_ref, qmp_wire, require, returned
from apps_ui578_apn import BUNDLE, canonical, control, names, own_row, unchanged_originals
from guest_ui import select_node


def replay_ui(value, records, plan, original_qmp_replay):
    item = value['apn']
    for entry in item['ui']:
        observed = [records[i] for i in entry['commands']]
        require(len(observed) in (2, 3), 'actual APN dump/read/input required')
        dump, read = observed[:2]
        match = re.fullmatch(r'test ! -e (\S+) && uitest dumpLayout -p (\S+) -b com.ohos.callsetting',
                             dump.get('script', ''))
        require(match and match[1] == match[2] and read.get('script') == 'cat ' + match[1],
                'APN selection is not the actual packaged UITest dump/read')
        tree = decode(read['body']); require(tree == decode(load_ref(entry['layout'])), 'actual APN tree differs')
        if entry['semantic'] == 'scroll':
            node = select_node(tree, BUNDLE, identifier='system-apn-list')
            x, y, width, height = node['rect']; points = [x + width // 2, y + height * 3 // 4,
                                                        x + width // 2, y + height // 4]
            require(height >= 80 and entry['node'] == node and entry['points'] == points and len(observed) == 3 and
                    observed[2].get('script') == 'uitest uiInput swipe ' + ' '.join(map(str, points)) + ' 500',
                    'APN list input did not use actual observed geometry')
            continue
        selector, node, matched = control(tree, entry['semantic'], entry['profile'], plan)
        require(selector == entry['selector'] and node == entry['selected'] and matched == entry['matched'],
                'actual APN node does not match the source-backed finite action')
        if entry['semantic'] == 'invalid-name':
            require(len(observed) == 2, 'validation-message observation must not synthesize an input')
        else:
            x, y, width, height = node['rect']
            require(len(observed) == 3 and observed[2].get('script') ==
                    'uitest uiInput click ' + str(x + width // 2) + ' ' + str(y + height // 2),
                    'APN action did not click the observed actual control')
    require(callable(original_qmp_replay), 'original same-boot actual QMP wire binding required')
    typed = []
    for proof in item['input']:
        require(proof['schema'] == 'actual-apps578-input/v1' and proof['action'] == 'apn-type' and
                proof['boot_id'] == value['boot_id'] and proof['archive_sha256'] == value['archive_sha256'],
                'APN physical input escaped the actual package/boot')
        parameters = proof['parameters']
        require(set(parameters) == {'field', 'text'} and parameters['field'] in ('name', 'apn') and
                parameters['text'] in names(value['run']).values(), 'APN input is not this nonce field value')
        expected = [('query-qmp-schema', {})]
        expected += [('send-key', {'keys': [{'type': 'qcode', 'data': 'ctrl'},
                                          {'type': 'qcode', 'data': 'a'}], 'hold-time': 60}),
                     ('send-key', {'keys': [{'type': 'qcode', 'data': 'backspace'}], 'hold-time': 60})]
        expected += [('send-key', {'keys': [{'type': 'qcode', 'data': 'dot' if char == '.' else char}],
                                  'hold-time': 60}) for char in parameters['text']]
        require(len(proof['qmp']) == len(expected), 'actual APN physical input sequence missing or extended')
        for row, (execute, arguments) in zip(proof['qmp'], expected):
            require(row['execute'] == execute and row['arguments'] == arguments and row['boot_id'] == value['boot_id'],
                    'actual APN physical key or boot differs')
            qmp_wire(row)
        original_qmp_replay(proof, value['archive_sha256'], value['boot_id'])
        typed.append((parameters['field'], parameters['text']))
    labels = names(value['run'])
    require(typed == [('name', labels['name']), ('apn', labels['apn']),
                      ('name', labels['edited']), ('name', labels['cancelled'])],
            'actual APN create/edit/cancel field inputs incomplete')


def verify_apn(value, rows, records, plan, original_qmp_replay):
    item = value['apn']; require(item['positive_completed'] is True and not item.get('no_sim_boundary'),
                               'APN positive cannot be replaced with a no-SIM error')
    for role in ('normal', 'system-denied'):
        returned(rows[role], 'apn.denied.read', 'read', 201)
        returned(rows[role], 'apn.public.' + role, 'invoke')
    returned(rows['a'], 'apn.invalid-context', 'invalid', -1)
    for operation in ('apn.create.open','apn.death.open','apn.complete.open','apn.complete.delete'):
        returned(rows['a'], operation, 'invoke')
    require(value['roles']['a']['identity']['uid'] != value['roles']['b']['identity']['uid'],
            'actual independent APN UIDs are identical')
    environment = returned(rows['a'], 'apn.environment', 'environment')
    require(environment == item['environment'] and environment['active'] is True and
            type(environment['slot']) is int and 0 <= environment['slot'] < environment['max'],
            'actual active default SIM unavailable')
    snapshots = {}
    for entry in item['snapshots']:
        operation = entry['operation']; require(operation not in snapshots, 'duplicated APN snapshot operation')
        actual = canonical(returned(rows['a'], operation, 'read'))
        require(actual == canonical(returned(rows['b'], operation, 'read')) == entry['value'],
                'actual independent public/readonly DataShare consumers differ')
        snapshots[operation] = actual
    baseline = snapshots['apn.baseline']; require(baseline == item['baseline'] and baseline['active'] is True and
        baseline['slot'] == environment['slot'] and baseline['preferred'] >= 0 and
        any(row['id'] == baseline['preferred'] for row in baseline['rows']), 'original APN state was not restorable')
    for operation in ('apn.cancel.normal', 'apn.cancel.system-denied', 'apn.invalid.read'):
        require(snapshots[operation] == baseline, 'cancel/invalid UI input changed real APN data')
    created, selected, edited = [snapshots[operation] for operation in ('apn.created', 'apn.selected', 'apn.edited')]
    labels = names(value['run']); owned = own_row(created, value['run'])
    require(owned['id'] == item['owned_id'] and owned['name'] == labels['name'] and
        any(row['apnName'] == labels['name'] and row['apn'] == labels['apn'] for row in created['apns']),
        'public APN result is not the real UI-created nonce profile')
    for state in (created, selected, edited): unchanged_originals(state, baseline, value['run'])
    require(selected['preferred'] == owned['id'] and own_row(edited, value['run'])['id'] == owned['id'] and
        own_row(edited, value['run'])['name'] == labels['edited'] and
        snapshots['apn.cancelled-edit'] == snapshots['apn.after-death'] == edited,
        'actual selection/edit/cancel/recreation state differs')
    before = [row for row in rows['a'] if row['operation'] == 'apn.death.open' and row['event'] == 'call.invoke']
    after = [row for row in rows['a'] if row['operation'] == 'apn.after-death' and row['event'] == 'return.read']
    require(len(before) == len(after) == 1 and before[0]['pid'] != after[0]['pid'],
            'APN public consumer did not recreate after its real caller death')
    require(snapshots['apn.complete.read'] == snapshots['apn.finally.read'] == baseline,
            'actual UI deletion/finally retained a nonce profile or changed original data')
    semantics = [entry['semantic'] for entry in item['ui']]
    require(semantics.count('save') == 3 and semantics.count('invalid-name') == 1 and
            semantics.count('delete') == 1 and semantics.count('back') == 1 and
            semantics.count('select') == 2 and semantics.count('edit') == 3,
            'one actual APN CRUD/lifecycle UI boundary was omitted')
    replay_ui(value, records, plan, original_qmp_replay)


def verify_no_sim_boundary(value, rows):
    """Use only after the parent's original raw/role/boot binding. Never pass."""
    environment = returned(rows['a'], 'apn.environment', 'environment')
    require(value['status'] == 'fail' and value['failures'] and value['formally_closed'] == [] and
        value['apn']['no_sim_boundary'] is True and value['apn']['positive_completed'] is False and
        environment == value['apn']['environment'] and environment['active'] is False,
        'actual no-active-SIM boundary required')
    returned(rows['a'], 'apn.no-sim', 'invoke', -1)
    return {'boundary': 'actual_no_active_default_sim', 'runtime_pass': False,
            'formally_closed': [], 'positive_apn_crud_verified': False}
