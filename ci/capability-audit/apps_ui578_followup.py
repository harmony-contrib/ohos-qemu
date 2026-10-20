"""Real current-provider flows. Runs only inside the parent's held guest stage."""
import time

from apps_ui578_contract import bundle, decode, json_ref, require, returned
from guest_ui import select_node, NodeNotReady, LayoutNotReady


def policy_pair(value):
    require(isinstance(value, dict) and set(value) == {'allowWiFi', 'allowCellular'} and
            all(type(v) is bool for v in value.values()), 'actual public own-UID network policy required')
    return value


def policy_read(session, role, operation, wanted):
    deadline = time.monotonic() + 25
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        current = policy_pair(session.api(role, operation + '.' + str(attempt), 'read'))
        if current == wanted:
            return current
        time.sleep(.2)
    raise ValueError('real own-UID policy did not reach the user-selected state')


def network_policy(session):
    session.bind_provider()
    roles = ('normal', 'system-denied', 'a', 'b')
    baseline = {role: policy_pair(session.api(role, 'net.before', 'read')) for role in roles}
    session.value['network_policy'] = {'baseline': baseline, 'cycles': [], 'restored': False}
    session.api('normal', 'net.normal.denied', 'privileged', 202)
    session.api('system-denied', 'net.system.denied', 'privileged', 201)
    # The current PUBLIC launcher resolves immediately after modal creation.
    # It is not a with-result API and a normal caller needs no system grant.
    for role in ('normal', 'system-denied'):
        session.api(role, 'net.public.open', 'invoke')
        session.visible(role, 'net.public.open')
        session.system('cancel')
        require(policy_pair(session.api(role, 'net.public.cancelled', 'read')) == baseline[role],
                'public launcher cancellation mutated the real caller policy')
    session.api('a', 'net.invalid', 'invalid', -1)
    # Caller records the actual native null rejection, not an invented 401.
    invalid = returned(session.rows('a'), 'net.invalid', 'invalid', -1)
    require(invalid == {'errorKind': 'null', 'raw': None}, 'current native invalid-context rejection changed')
    peer = session.value['roles']['b']['identity']['uid']
    own = session.value['roles']['a']['identity']['uid']
    require(peer != own, 'independent actual BMS UIDs required')
    # B is a separate system consumer; snapshot the real privileged policy too.
    peer_before = session.api('b', 'net.peer.before', 'privileged')
    session.value['network_policy']['privileged_baseline'] = session.api('a','net.own.privileged.before','privileged')
    for role in ('normal', 'system-denied', 'a'):
        # Both forged reserved callerUid/hostUid and appUid carry another UID.
        # AMS must replace the reserved identity and provider must refuse it.
        session.api(role, 'net.spoof.foreign', 'spoof', number=peer)
        session.wait(role, lambda rows: any(r['operation'] == 'net.spoof.foreign' and
            r['event'] in ('network.extension.terminated', 'network.extension.error') for r in rows), 'foreign_uid_rejected')
        require(session.api('b', 'net.peer.after.spoof.' + role.replace('-', ''), 'privileged') == peer_before,
                'forged Want altered another application policy')
    for role in ('normal', 'system-denied', 'a'):
        # A legitimate own-UID request still works when untrusted reserved
        # identity parameters name B. Neither normal nor system caller can use
        # those forged fields as authority over B.
        session.api(role, 'net.spoof.self', 'spoof-self', number=peer)
        session.visible(role, 'net.spoof.self')
        session.system('cancel')
        require(session.api(role, 'net.spoof.self.read', 'read') == baseline[role],
                'own-UID public modal cancellation changed the real policy')
    choices = [('deny', {'allowWiFi': False, 'allowCellular': False})]
    env = session.api('a', 'net.environment', 'network-environment')
    require(type(env['maxSimCount']) is int and env['maxSimCount'] >= 0, 'real advertised SIM count required')
    if env['maxSimCount'] == 0:
        choices += [('allow', {'allowWiFi': True, 'allowCellular': True})]
    else:
        choices += [('wifi-only', {'allowWiFi': True, 'allowCellular': False}),
                    ('wifi-cellular', {'allowWiFi': True, 'allowCellular': True})]
    for choice, wanted in choices:
        operation = 'net.choice.' + choice
        session.api('a', operation, 'invoke')
        session.visible('a', operation)
        session.system(choice)
        observed = policy_read(session, 'a', operation + '.read', wanted)
        require(session.api('b', operation + '.peer', 'privileged') == peer_before,
                'real user action changed the independent peer policy')
        session.value['network_policy']['cycles'].append({'choice': choice, 'expected': wanted,
                                                        'observed': observed, 'operation': operation})
    current = policy_pair(session.api('a', 'net.before.death', 'read'))
    session.api('a', 'net.death.open', 'invoke')
    session.visible('a', 'net.death.open')
    old = session.stop('a')
    session.provider_gone()
    require(session.api('a', 'net.recreated', 'read') == current and any(
        r['operation'] == 'net.recreated' and r['pid'] != old for r in session.rows('a')),
        'caller death/recreation lost the committed policy or retained a stale process')
    # Restoration uses the public user-consent dialog; direct privileged root
    # policy writes are never a substitute for this original provider flow.
    restore_network(session)


def restore_network(session):
    item = session.value['network_policy']
    if item['restored']:
        actual={r: policy_pair(session.api(r,'net.final.read','read')) for r in item['baseline']}
        require(actual==item['baseline'],'actual final network state changed before original cleanup')
        return actual
    desired = item['baseline']['a']
    if policy_pair(session.api('a', 'net.cleanup.before', 'read')) != desired:
        choices = {(False, False): 'deny', (True, True): 'allow', (True, False): 'wifi-only'}
        key = desired['allowWiFi'], desired['allowCellular']
        require(key in choices, 'original policy is not representable by the actual public provider UI')
        choice = choices[key]
        if choice == 'allow' and session.api('a', 'net.cleanup.environment', 'network-environment')['maxSimCount'] > 0:
            choice = 'wifi-cellular'
        session.api('a', 'net.cleanup.open', 'invoke'); session.visible('a', 'net.cleanup.open')
        session.system(choice)
        policy_read(session, 'a', 'net.cleanup.await', desired)
    restored = {r: policy_pair(session.api(r, 'net.cleanup.read', 'read')) for r in item['baseline']}
    require(restored == item['baseline'], 'all four real caller policies must be restored exactly')
    if 'privileged_baseline' in item:
        require(session.api('a','net.own.privileged.final','privileged')==item['privileged_baseline'],
                'real full privileged own-policy state was not restored')
    item['restored'] = True
    return restored


def dnd_selection(session, role):
    # The parent has already bound both actual built HAPs. These nodes belong
    # to Settings' real app picker, not the disposable caller or a test page.
    identifier = 'intelligent-scene-app-' + bundle(role)
    begin=len(session.value['commands'])
    tree, path = session.ui.layout(bundle='com.ohos.settings', label='actual_dnd_selection')
    node = select_node(tree, 'com.ohos.settings', identifier=identifier, clickable=True)
    roots = tree if isinstance(tree, list) else [tree]
    pending = [(r, '') for r in roots]; found = []
    while pending:
        current, inherited = pending.pop()
        attrs = current['attributes']; owner = attrs.get('bundleName') or inherited
        if owner == 'com.ohos.settings' and attrs.get('id') == identifier:
            queue = list(current.get('children', [])); checks = []
            while queue:
                child = queue.pop(); a = child['attributes']
                if a.get('type') in ('Checkbox', 'CheckBox') and a.get('visible') == 'true':
                    checks.append(a)
                queue += child.get('children', [])
            found += checks
        pending += [(r, owner) for r in current.get('children', [])]
    require(len(found) == 1 and found[0].get('checked') in ('true', 'false'),
            'actual source Row must expose one real Checkbox state')
    observation = {'role': role, 'layout': json_ref(path), 'node': node,
                   'checked': found[0]['checked'] == 'true','commands':list(range(begin,len(session.value['commands'])))}
    session.value['dnd']['checkboxes'].append(observation)
    return observation['checked']


def dnd_search(session, role):
    session.system('search')
    text = 'apps578' + role + session.run[:8]
    proof = session.callbacks['business_boundary'](session.guest, session, 'dnd-search', {'role': role, 'text': text})
    session.value['dnd']['searches'].append(proof)
    deadline = time.monotonic() + 25
    while True:
        try:
            return dnd_selection(session, role)
        except (NodeNotReady, LayoutNotReady):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.15)


def dnd_open(session, operation):
    session.api('a', operation, 'open-settings')
    session.visible('a', operation)


def dnd_edit(session, operation, desired, commit=True):
    dnd_open(session, operation)
    session.system('open-apps')
    states = {}
    for role, wanted in desired.items():
        actual = dnd_search(session, role)
        states[role] = actual
        if actual is not wanted:
            session.system('toggle-' + role)
            require(dnd_selection(session, role) is wanted, 'real Settings Checkbox did not follow its real row click')
    session.system('finish' if commit else 'cancel-selection')
    session.value['dnd']['edits'].append({'operation': operation, 'before': states,
                                        'desired': desired, 'committed': commit})
    return states


def intelligent_scene(session):
    session.bind_provider()
    session.bind_aux_provider('intelligent-scene-settings')
    baseline = {r: session.api(r, 'baseline', 'read') for r in ('a', 'b')}
    require(all(isinstance(v, list) and len(v) == 2 and all(type(x) is bool for x in v) and not v[0]
                for v in baseline.values()), 'fresh owned guest must begin with DND disabled; no other user mode may be overwritten')
    session.value['baseline'] = baseline
    session.value['dnd'] = {'checkboxes': [], 'searches': [], 'edits': [], 'original_selection': None,
                            'restored': False}
    for role in ('normal', 'system-denied'):
        session.api(role, 'denied', 'read', 201)
    # The original Settings entry initializes its real AppListLoader, which the
    # nested official picker consumes. Opening it is a prerequisite, never the
    # business oracle; only later actual rows/Checkboxes/ANS queries count.
    session.api('a','dnd.prime','prime-settings')
    # Capture each real original picker state before the first mutation.
    dnd_open(session, 'dnd.initial.open'); session.system('open-apps')
    original = {r: dnd_search(session, r) for r in ('a', 'b')}
    session.value['dnd']['original_selection'] = original
    session.system('cancel-selection')
    dnd_open(session, 'dnd.enable.open'); session.system('dnd-enable')
    dnd_edit(session, 'allowed.open', {'a': True, 'b': False})
    for role, wanted in (('a', [True, True]), ('b', [True, False])):
        deadline = time.monotonic() + 25; attempt = 0
        while True:
            attempt += 1
            observed = session.api(role, 'allowed.read.' + str(attempt), 'read')
            if observed == wanted:
                break
            require(time.monotonic() < deadline, 'ANS did not reflect real DND global/per-UID selected state')
            time.sleep(.2)
    dnd_edit(session, 'cancelled.open', {'a': False}, commit=False)
    require(session.api('a', 'cancelled.read', 'read') == [True, True], 'picker cancellation persisted an uncommitted edit')
    dnd_edit(session, 'denied.open', {'a': False, 'b': False})
    require(session.api('a', 'denied.read', 'read') == session.api('b', 'denied.read', 'read') == [True, False],
            'independent public ANS consumers did not observe denial')
    dnd_open(session, 'death.open')
    old = session.stop('a'); session.provider_gone()
    require(session.api('a', 'restart.read', 'read') == [True, False] and any(
        r['operation'] == 'restart.read' and r['pid'] != old for r in session.rows('a')),
        'caller recreation retained stale per-process DND result')
    restore_dnd(session)


def restore_dnd(session):
    item = session.value['dnd']
    if item['restored']:
        after={r:session.api(r,'dnd.final.read','read') for r in ('a','b')}
        require(after==session.value['baseline'],'actual final DND state changed before original cleanup')
        return after
    if item['original_selection'] is not None:
        dnd_edit(session, 'dnd.restore.selection', item['original_selection'])
    current = session.api('a', 'dnd.restore.before', 'read')
    if current[0]:
        dnd_open(session, 'dnd.restore.open'); session.system('dnd-disable')
    after = {r: session.api(r, 'cleanup.read', 'read') for r in ('a', 'b')}
    require(after == session.value['baseline'], 'DND/global and per-UID public state restoration failed')
    item['restored'] = True
    return after
