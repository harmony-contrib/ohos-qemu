"""Independent original-raw replay for real NetPolicy and DND provider flows."""
from apps_ui578_contract import bundle, decode, load_ref, qmp_wire, require, returned
from guest_ui import bounds, select_node


def mode_button(layout, selector):
    """Resolve the real DND mode card, never another visible Swiper card."""
    require(selector == {'bundle': 'com.ohos.intelligentscene', 'text': selector['text'],
                         'within_mode': 'Do not disturb'} and selector['text'] in ('Turn on', 'Turn off'),
            'fixed real mode Button relation required')
    anchor = select_node(layout, selector['bundle'], text='Do not disturb')
    roots = layout if isinstance(layout, list) else [layout]
    pending = [(r, '', []) for r in roots]; paths = []
    while pending:
        node, inherited, parents = pending.pop()
        attrs = node['attributes']; owner = attrs.get('bundleName') or inherited
        if owner == selector['bundle'] and attrs.get('text') == 'Do not disturb' and attrs.get('visible') == 'true':
            paths.append(parents)
        pending += [(r, owner, parents + [(node, owner)]) for r in node.get('children', [])]
    require(len(paths) == 1, 'one actual visible DND mode label required')
    for parent, owner in reversed(paths[0][-8:]):
        if owner != selector['bundle']:
            break
        queue = [(r, owner) for r in parent.get('children', [])]; found = []
        while queue:
            node, inherited = queue.pop(); attrs = node['attributes']
            actual_owner = attrs.get('bundleName') or inherited
            if (actual_owner == owner and attrs.get('text') == selector['text'] and attrs.get('visible') == 'true' and
                    attrs.get('enabled') == 'true' and attrs.get('clickable') == 'true'):
                found.append({'attributes': attrs, 'bundle': owner, 'rect': list(bounds(attrs.get('bounds')))})
            queue += [(r, actual_owner) for r in node.get('children', [])]
        if found:
            require(len(found) == 1, 'mode card must contain one actual enabled semantic Button')
            return found[0], anchor
    raise ValueError('actual DND card Button is not present in the real hierarchy')


def checkbox(tree, role, run):
    wanted = 'intelligent-scene-app-' + bundle(role)
    row = select_node(tree, 'com.ohos.settings', identifier=wanted, clickable=True)
    pending = [(r, '') for r in (tree if isinstance(tree, list) else [tree])]; checks = []; labels=[]
    while pending:
        node, inherited = pending.pop(); attrs = node['attributes']; owner = attrs.get('bundleName') or inherited
        if owner == 'com.ohos.settings' and attrs.get('id') == wanted:
            queue = list(node.get('children', []))
            while queue:
                item = queue.pop(); a = item['attributes']
                if a.get('type')=='Text' and a.get('visible')=='true': labels.append(a.get('text'))
                if a.get('type') in ('Checkbox', 'CheckBox') and a.get('visible') == 'true':
                    checks.append(a)
                queue += item.get('children', [])
        pending += [(r, owner) for r in node.get('children', [])]
    require(len(checks) == 1 and checks[0].get('checked') in ('true', 'false'), 'one actual Row Checkbox required')
    require(labels==['apps578'+role+run[:8]], 'actual Settings row label is not this nonce compiled caller')
    return row, checks[0]['checked'] == 'true'


def dnd(value, rows, records, original_qmp_replay):
    item = value['dnd']
    require(item['restored'] is True and set(item['original_selection']) == {'a', 'b'} and item['searches'],
            'actual original picker state/restoration and physical searches are mandatory')
    require(value['baseline'] == {r: returned(rows[r], 'baseline', 'read') for r in ('a', 'b')} and
            all(not v[0] for v in value['baseline'].values()), 'fresh DND-disabled baseline required')
    returned(rows['a'],'dnd.prime','prime-settings')
    for role in ('normal', 'system-denied'):
        returned(rows[role], 'denied', 'read', 201)
    require(callable(original_qmp_replay), 'original held-guest QMP raw binding required')
    for proof in item['searches']:
        parameters = proof['parameters']; role = parameters['role']
        require(role in ('a', 'b') and parameters == {'role': role, 'text': 'apps578' + role + value['run'][:8]} and
                proof['action'] == 'dnd-search' and proof['boot_id'] == value['boot_id'] and
                proof['archive_sha256'] == value['archive_sha256'], 'actual finite caller-label search differs')
        wire = proof['qmp']
        require(wire and wire[0]['execute'] == 'query-qmp-schema' and
                any(x.get('name') == 'send-key' and x.get('meta-type') == 'command' for x in wire[0]['reply']),
                'actual owned QEMU keyboard capability missing')
        expected = [[{'type': 'qcode', 'data': 'ctrl'}, {'type': 'qcode', 'data': 'a'}],
                    [{'type': 'qcode', 'data': 'backspace'}]] + [
                        [{'type': 'qcode', 'data': letter}] for letter in parameters['text']]
        require(len(wire) == 1 + len(expected), 'actual clear/search physical key count differs')
        for event, keys in zip(wire[1:], expected):
            require(event['execute'] == 'send-key' and event['arguments'] == {'keys': keys, 'hold-time': 60} and
                    event['reply'] == {}, 'actual search QMP wire differs')
        for event in wire:
            qmp_wire(event)
        original_qmp_replay(proof, value['archive_sha256'], value['boot_id'])
    first = {}
    for observation in item['checkboxes']:
        selected = observation['commands']
        require(len(selected) == 2 and selected == list(range(selected[0], selected[0] + 2)),
                'actual Checkbox observation must retain its original dump/read')
        dump, read = [records[i] for i in selected]
        require(dump.get('script', '').startswith('test ! -e ') and
                dump.get('script', '').endswith(' -b com.ohos.settings') and
                read.get('script', '').startswith('cat '), 'actual Settings hierarchy record missing')
        tree = decode(read['body'])
        require(tree == decode(load_ref(observation['layout'])), 'saved actual picker hierarchy differs')
        node, actual = checkbox(tree, observation['role'], value['run'])
        require(node == observation['node'] and actual is observation['checked'], 'actual Checkbox raw state differs')
        first.setdefault(observation['role'], actual)
    require(first == item['original_selection'], 'initial actual picker state was replaced by inferred API state')
    edits = {e['operation']: e for e in item['edits']}
    for name, desired, committed in [('allowed.open', {'a': True, 'b': False}, True),
                                     ('cancelled.open', {'a': False}, False),
                                     ('denied.open', {'a': False, 'b': False}, True)]:
        require(edits[name]['desired'] == desired and edits[name]['committed'] is committed,
                'actual whitelist allow/deny/cancel sequence differs')
    for role, expected in [('a', [True, True]), ('b', [True, False])]:
        candidates = [r for r in rows[role] if r['operation'].startswith('allowed.read.') and r['event'] == 'return.read']
        require(candidates and decode(candidates[-1]['value']) == expected and candidates[-1]['code'] == 0,
                'real independent ANS query did not observe global DND/per-UID allowlist')
    require(returned(rows['a'], 'cancelled.read', 'read') == [True, True] and
            returned(rows['a'], 'denied.read', 'read') == returned(rows['b'], 'denied.read', 'read') == [True, False],
            'actual cancel/deny policy consumers differ')
    recreated = [r for r in rows['a'] if r['operation'] == 'restart.read' and r['event'] == 'return.read']
    before = [r for r in rows['a'] if r['operation'] == 'death.open' and r['event'] == 'return.open-settings']
    require(len(before) == len(recreated) == 1 and before[0]['pid'] != recreated[0]['pid'] and
            returned(rows['a'], 'restart.read', 'read') == [True, False], 'real DND caller death/recreation missing')
    require('death.open' in {a['visible'] for a in value['actions'] if 'visible' in a},
            'caller death must occur with the real provider still displayed')
    restore = [e for e in item['edits'] if e['operation'] == 'dnd.restore.selection']
    require(restore and all(e['desired'] == item['original_selection'] and e['committed'] for e in restore),
            'finally must restore only the two actual original caller selections')
    for role in ('a', 'b'):
        require(returned(rows[role], 'cleanup.read', 'read') == value['baseline'][role],
                'actual original DND public state was not restored')


def network(value, rows):
    from apps_ui578_followup import policy_pair
    item = value['network_policy']; baseline = item['baseline']
    require(set(baseline) == {'normal', 'system-denied', 'a', 'b'} and item['restored'] is True,
            'all real role policies and completed restoration required')
    for role in baseline:
        require(policy_pair(returned(rows[role], 'net.before', 'read')) == baseline[role] ==
                returned(rows[role], 'net.cleanup.read', 'read'), 'actual network baseline/final restoration differs')
    returned(rows['normal'], 'net.normal.denied', 'privileged', 202)
    returned(rows['system-denied'], 'net.system.denied', 'privileged', 201)
    for role in ('normal', 'system-denied'):
        returned(rows[role], 'net.public.open', 'invoke')
        require(returned(rows[role], 'net.public.cancelled', 'read') == baseline[role],
                'public normal/system-denied launch/cancel mutated real policy')
    require(returned(rows['a'], 'net.invalid', 'invalid', -1) == {'errorKind': 'null', 'raw': None},
            'actual current native null rejection differs')
    peer = returned(rows['b'], 'net.peer.before', 'privileged')
    for role in ('normal', 'system-denied', 'a'):
        returned(rows[role], 'net.spoof.foreign', 'spoof')
        require(any(r['operation'] == 'net.spoof.foreign' and r['event'] in
                    ('network.extension.terminated', 'network.extension.error') for r in rows[role]),
                'forged foreign-UID modal did not terminate with actual callback evidence')
        require(returned(rows['b'], 'net.peer.after.spoof.' + role.replace('-', ''), 'privileged') == peer,
                'forged caller/host UID changed the independent privileged consumer')
        returned(rows[role], 'net.spoof.self', 'spoof-self')
        require(returned(rows[role], 'net.spoof.self.read', 'read') == baseline[role],
                'own-UID public modal with forged reserved fields was not preserved/cancelled')
    count = returned(rows['a'], 'net.environment', 'network-environment')['maxSimCount']
    expected = ['deny', 'allow'] if count == 0 else ['deny', 'wifi-only', 'wifi-cellular']
    require([r['choice'] for r in item['cycles']] == expected, 'actual advertised-network UI branches incomplete')
    for cycle in item['cycles']:
        require(policy_pair(cycle['observed']) == cycle['expected'], 'actual public independent network policy differs')
        results = [r for r in rows['a'] if r['operation'].startswith(cycle['operation'] + '.read.') and r['event'] == 'return.read']
        require(results and results[-1]['code'] == 0 and decode(results[-1]['value']) == cycle['expected'],
                'source UI choice lacks the actual own-UID policy consumer')
        require(returned(rows['b'], cycle['operation'] + '.peer', 'privileged') == peer,
                'selected own-UID policy changed its peer')
    require(returned(rows['a'], 'net.before.death', 'read') == returned(rows['a'], 'net.recreated', 'read'),
            'real network state did not survive caller death/recreation')
    require(returned(rows['a'],'net.own.privileged.before','privileged')==returned(rows['a'],'net.own.privileged.final','privileged'),
            'full actual privileged policy flags were not restored')
    prior=[r for r in rows['a'] if r['operation']=='net.death.open' and r['event']=='return.invoke']
    recreated=[r for r in rows['a'] if r['operation']=='net.recreated' and r['event']=='return.read']
    require(len(prior)==len(recreated)==1 and prior[0]['pid']!=recreated[0]['pid'],
            'actual network caller generation did not change after scoped death')
    require('net.death.open' in {a['visible'] for a in value['actions'] if 'visible' in a},
            'real network modal must be displayed at caller death')
