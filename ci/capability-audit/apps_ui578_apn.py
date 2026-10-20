"""Real APN dialog CRUD. Only the packaged UI writes; callers only query.

Requires a real registered/active SIM fixture. The no-SIM error is retained as
a failed positive case, never converted into capability support or closure.
"""
import json
import re
import time
from apps_ui578_contract import action_node, decode, json_ref, require, returned
from guest_ui import LayoutNotReady, NodeNotReady, select_node

BUNDLE = 'com.ohos.callsetting'


def canonical(value):
    value = dict(value)
    value['apns'] = sorted(value['apns'], key=lambda row: json.dumps(row, sort_keys=True))
    return value


def names(run):
    return {'name': 'apps578' + run[:16], 'edited': 'apps579' + run[:16],
            'cancelled': 'apps580' + run[:16], 'apn': 'apps578' + run[:16] + '.invalid'}


def control(tree, semantic, profile, plan):
    if semantic in ('select', 'edit'):
        require(type(profile) is int and profile >= 0, 'actual returned APN profile ID required')
        selector = {'bundle': BUNDLE, 'identifier': 'system-apn-' + semantic + '-' + str(profile)}
    elif semantic in ('save', 'back'):
        # The fixed real EditableTitleBar creates this ID from its unique ID.
        pending = list(tree if isinstance(tree, list) else [tree]); ids = []; count = 0
        while pending:
            node = pending.pop(); count += 1
            require(count <= 100000 and type(node) is dict, 'bounded actual hierarchy required')
            attrs = node.get('attributes', {})
            if (re.fullmatch(('Save' if semantic == 'save' else 'Back') + r'MenuItem_[0-9]+', attrs.get('id', '')) and
                    attrs.get('visible') == 'true'):
                ids.append(attrs['id'])
            pending.extend(node.get('children', []))
        require(len(ids) <= 1, 'ambiguous actual Save control')
        if not ids: raise NodeNotReady('real EditableTitleBar Save is not visible')
        selector = {'bundle': BUNDLE, 'identifier': ids[0]}
    else:
        require(semantic in plan['actions'] and len(plan['actions'][semantic]) == 1,
                'fixed source-backed APN selector required')
        selector = plan['actions'][semantic][0]
    if semantic == 'invalid-name':
        node = select_node(tree, **selector)
        return selector, node, node
    selected, matched = action_node(tree, selector)
    require(selected['attributes'].get('enabled') == 'true', 'actual APN control is disabled')
    return selector, selected, matched


def click(session, semantic, profile=None):
    deadline = time.monotonic() + 20; scrolls = 0
    while True:
        try:
            begin = len(session.value['commands'])
            tree, path = session.ui.layout(bundle=BUNDLE, label='actual_apn_control')
            selector, selected, matched = control(tree, semantic, profile, session.plan)
            x, y, width, height = selected['rect']
            if semantic != 'invalid-name': session.ui.shell('uitest uiInput click ' + str(x + width // 2) + ' ' + str(y + height // 2),
                             'actual_apn_node_center')
            session.value['apn']['ui'].append({'semantic': semantic, 'profile': profile,
                'layout': json_ref(path), 'selector': selector, 'selected': selected, 'matched': matched,
                'commands': list(range(begin, len(session.value['commands'])))})
            return
        except (LayoutNotReady, NodeNotReady):
            if semantic in ('select', 'edit') and scrolls < 12:
                begin = len(session.value['commands'])
                tree, path = session.ui.layout(bundle=BUNDLE, label='actual_apn_list_geometry')
                node = select_node(tree, BUNDLE, identifier='system-apn-list')
                x, y, width, height = node['rect']; require(height >= 80, 'actual APN list is too small')
                points = [x + width // 2, y + height * 3 // 4, x + width // 2, y + height // 4]
                session.ui.shell('uitest uiInput swipe ' + ' '.join(map(str, points)) + ' 500',
                                 'actual_apn_list_scroll')
                session.value['apn']['ui'].append({'semantic': 'scroll', 'layout': json_ref(path),
                    'node': node, 'points': points, 'commands': list(range(begin, len(session.value['commands'])))})
                scrolls += 1
            if time.monotonic() >= deadline: raise
            time.sleep(.15)


def snapshot(session, operation):
    b = canonical(session.api('b', operation, 'read'))
    a = canonical(session.api('a', operation, 'read'))
    require(a == b, 'independent APN callers read different actual catalogs/preference')
    require(a['active'] is True and type(a['simId']) is int and a['simId'] >= 0 and
            re.fullmatch(r'[0-9]{5,6}', a['numeric']) and
            all(type(row['id']) is int and row['id'] >= 0 for row in a['rows']) and
            len({row['id'] for row in a['rows']}) == len(a['rows']), 'real active SIM/catalog required')
    session.value['apn']['snapshots'].append({'operation': operation, 'value': a})
    return a


def open_list(session, operation, role='a'):
    session.invoke(role, operation, 'invoke', wait=False)
    session.visible(role, operation)
    accepted = session.wait(role, lambda rows: any(row['operation'] == operation and row['event'] == 'return.invoke' for row in rows), 'actual_apn_modal_result')
    returned(accepted, operation, 'invoke')
    session.api(role, operation + '.accepted', 'environment')


def type_field(session, field, text):
    require(field in ('name', 'apn') and text in names(session.run).values(), 'fixed nonce APN field only')
    click(session, 'field-' + field); click(session, 'field-input')
    raw = session.callbacks['business_boundary'](session.guest, session, 'apn-type', {'field': field, 'text': text})
    session.value['apn']['input'].append(raw)
    click(session, 'accept-field')


def own_row(value, run):
    expected = names(run)
    found = [row for row in value['rows'] if row['apn'] == expected['apn'] and
             row['name'] in (expected['name'], expected['edited'], expected['cancelled'])]
    require(len(found) == 1, 'exact one actual nonce APN row required')
    return found[0]


def unchanged_originals(value, baseline, run):
    ids = {row['id'] for row in baseline['rows']}
    require([row for row in value['rows'] if row['id'] in ids] == baseline['rows'],
            'the real UI changed an original APN row')
    require(value['slot'] == baseline['slot'] and value['simId'] == baseline['simId'] and
            value['numeric'] == baseline['numeric'], 'active SIM/default slot changed during APN mutation')
    extra = [row for row in value['rows'] if row['id'] not in ids]
    require(len(extra) == 1 and extra[0] == own_row(value, run), 'APN UI created an unrelated row')


def apn_case(session):
    session.bind_provider()
    require(session.value['roles']['a']['identity']['uid'] != session.value['roles']['b']['identity']['uid'],
            'APN independent consumers require distinct actual BMS UIDs')
    session.value['apn'] = {'ui': [], 'input': [], 'snapshots': [], 'positive_completed': False}
    for role in ('normal', 'system-denied'):
        session.api(role, 'apn.denied.read', 'read', 201)
    session.api('a', 'apn.invalid-context', 'invalid', -1)
    environment = session.api('a', 'apn.environment', 'environment')
    session.value['apn']['environment'] = environment
    if environment['active'] is not True:
        session.api('a', 'apn.no-sim', 'invoke', -1)
        session.value['apn']['no_sim_boundary'] = True
        raise ValueError('real active default SIM is missing; APN CRUD positive remains pending')
    baseline = snapshot(session, 'apn.baseline')
    require(baseline['preferred'] >= 0 and any(row['id'] == baseline['preferred'] for row in baseline['rows']),
            'original preferred APN must be restorable before any UI write')
    require(not any(row['apn'] == names(session.run)['apn'] for row in baseline['rows']), 'nonce APN already exists')
    session.value['apn']['baseline'] = baseline
    for role in ('normal', 'system-denied'):
        open_list(session, 'apn.public.' + role, role); session.system('cancel')
        require(snapshot(session, 'apn.cancel.' + role) == baseline, 'public menu cancellation wrote APN state')
    open_list(session, 'apn.create.open'); session.system('create')
    click(session, 'save'); click(session, 'invalid-name'); click(session, 'dismiss-warning')
    require(snapshot(session, 'apn.invalid.read') == baseline, 'blank APN name changed the actual catalog')
    labels = names(session.run)
    type_field(session, 'name', labels['name']); type_field(session, 'apn', labels['apn']); click(session, 'save')
    created = snapshot(session, 'apn.created'); unchanged_originals(created, baseline, session.run)
    owned = own_row(created, session.run); session.value['apn']['owned_id'] = owned['id']
    require(owned['name'] == labels['name'] and any(row['apnName'] == labels['name'] and
        row['apn'] == labels['apn'] for row in created['apns']), 'public APN consumer did not receive new actual data')
    click(session, 'select', owned['id'])
    selected = snapshot(session, 'apn.selected'); unchanged_originals(selected, baseline, session.run)
    require(selected['preferred'] == owned['id'], 'actual preferred APN did not change')
    click(session, 'edit', owned['id']); type_field(session, 'name', labels['edited']); click(session, 'save')
    edited = snapshot(session, 'apn.edited'); unchanged_originals(edited, baseline, session.run)
    require(own_row(edited, session.run)['id'] == owned['id'] and own_row(edited, session.run)['name'] == labels['edited'],
            'actual edit changed the row identity or lost its value')
    click(session, 'edit', owned['id']); type_field(session, 'name', labels['cancelled'])
    click(session, 'back'); session.system('discard-edit')
    require(snapshot(session, 'apn.cancelled-edit') == edited, 'cancelled UI edit committed data')
    # The public function returns void when its real modal is accepted. A killed
    # caller still must release the modal; a new process must re-read the DB.
    session.system('cancel'); open_list(session, 'apn.death.open')
    previous = session.stop('a'); session.provider_gone()
    require(snapshot(session, 'apn.after-death') == edited and any(row['operation'] == 'apn.after-death' and
        row['pid'] != previous for row in session.rows('a')), 'APN caller recreation used stale process state')
    final = restore_apn(session, 'apn.complete')
    require(final == baseline, 'real APN CRUD cleanup did not restore all original state')
    session.value['apn']['positive_completed'] = True


def restore_apn(session, prefix='apn.finally'):
    baseline = session.value['apn']['baseline']
    current = snapshot(session, prefix + '.before')
    extra = [row for row in current['rows'] if row['id'] not in {row['id'] for row in baseline['rows']}]
    if current != baseline:
        unchanged_originals(current, baseline, session.run)
        owned = own_row(current, session.run)
        require(extra == [owned], 'finally may only remove this nonce-created row')
        # Always reopen a real root menu so list scrolling starts in its normal
        # source lifecycle; no root/DataShare mutation bypass exists here.
        session.system('cancel'); open_list(session, prefix + '.open')
        if current['preferred'] != baseline['preferred']:
            click(session, 'select', baseline['preferred'])
            require(snapshot(session, prefix + '.preference')['preferred'] == baseline['preferred'],
                    'original preferred APN was not restored by actual UI')
        session.system('cancel'); open_list(session, prefix + '.delete')
        click(session, 'edit', owned['id']); click(session, 'delete')
    final = snapshot(session, prefix + '.read')
    require(final == baseline, 'finally retained nonce APN or changed original public/preference data')
    session.system('cancel')
    return final
