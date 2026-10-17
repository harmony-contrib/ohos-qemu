#!/usr/bin/env python3
"""Recompute raw Calendar chain semantics; retain unsupported lifecycle gaps."""
import argparse
import json
from pathlib import Path
import re

from batch_system_calendar_runtime_project import CONTRACT, ROLES, checked, load_challenge, record, require, sha, write
import batch_system_calendar_runtime_protocol as protocol
from enclosing_acceptance_guest import validate_binding
from guest_ui import select_node


def raw_bound(capture, item):
    path = checked(item)
    match = re.match(r'raw-([0-9]+)-', path.name)
    require(match is not None, 'collector-owned raw guest artifact required')
    row = capture['guest_commands'][int(match[1])-1]
    log = checked({'path': row['log'], 'sha256': row['sha256']}).read_text().replace('\r', '')
    marker = re.search(r'__QEMU_CHILD_EXIT_[a-f0-9]{32}__=', row['argv'][-1])
    require(row['exit_code'] == 0 and marker is not None and log.count(marker[0]) == 1 and
            log.endswith('\n'+marker[0]+'0\n') and log.rsplit('\n'+marker[0], 1)[0] == path.read_text(),
            'raw observation is not the preserved actual marked guest command output')
    return path.read_text()


def layout_bound(capture, item):
    value = protocol.decode(checked(item).read_text())
    found = []
    for row in capture['commands']:
        if not row['label'].endswith('-read') or len(row['argv']) < 5 or row['argv'][3] != 'shell':
            continue
        raw = checked({'path': row['path'], 'sha256': row['sha256']}).read_text().replace('\r', '')
        marker = re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=', row['argv'][-1])
        if marker and raw.count(marker[0]) == 1 and raw.rstrip().endswith(marker[0]+'0'):
            try:
                if protocol.decode(raw.rsplit('\n'+marker[0], 1)[0]) == value:
                    found.append(row)
            except (ValueError, json.JSONDecodeError):
                pass
    require(found, 'actual UITest hierarchy transport binding missing')
    return value


def pixels_bound(capture, item):
    from PIL import Image
    path = checked(item)
    transfers = [r for r in capture['commands'] if len(r['argv']) >= 7 and r['argv'][3:5] == ['file', 'recv'] and
                 Path(r['argv'][-1]).resolve() == path and r['exit_code'] == 0]
    require(len(transfers) == 1, 'actual compositor screenshot transfer required')
    with Image.open(path) as image:
        require(image.format == 'PNG' and min(image.size) >= 100 and
                any(high > low for low, high in image.convert('RGB').getextrema()), 'empty/unusable compositor pixels')
        return image.size


def operation(capture):
    role = capture['request']['role']
    info = capture['artifacts'][role]
    app = {'uid': info['uid'], 'accessTokenId': info['token_id']}
    _, rows = protocol.parse(raw_bound(capture, capture['journal']), capture['request'], app)
    require(rows is not None, 'actual operation incomplete')
    return rows


def validate_capture(path, challenge, archive):
    capture = protocol.decode(Path(path).read_text())
    here = Path(__file__).with_name('batch_system_calendar_runtime_capture.py')
    require(capture['collector'] == record(here) and capture['schema_version'] == 1 and
            capture['run_id'] == challenge['run_id'] and capture['archive'] == archive and
            capture['status'] == 'captured' and not capture['failures'] and
            capture['ledger_closed'] is False and capture['first_artifact_behavior_gate_passed'] is False,
            'original current collector successful raw stage required')
    boot = protocol.decode(checked(capture['boot']).read_text())
    env = validate_binding(boot, archive['sha256'])
    require(env['boot_id'] == capture['boot_id'], 'actual enclosing boot identity differs')
    for row in capture['commands']:
        require(row['exit_code'] == 0, 'collector contains failed actual command')
        checked({'path': row['path'], 'sha256': row['sha256']})
    plan = protocol.decode(checked(capture['plan']).read_text())
    from batch_system_calendar_runtime_capture import helper_proof
    helper_proof(plan['helper'])
    require(capture['helper']['binary'] == plan['helper']['binary'] and capture['helper']['receipt'] == plan['helper']['receipt'] and
            raw_bound(capture, capture['helper']['guest_sha']).split()[0] == sha(checked(plan['helper']['binary'])),
            'actual guest helper differs from compiled product artifact')
    require(set(capture['helper']['dsos']) == set(plan['helper']['guest_dsos']), 'complete actual runtime DSO observations required')
    for name, item in plan['helper']['guest_dsos'].items():
        require(raw_bound(capture, capture['helper']['dsos'][name]).split()[0] == sha(checked(item['artifact'])),
                'actual running helper DSO differs from linked product artifact')
    identities = []
    apps = {}
    for role, policy in ROLES.items():
        item = capture['artifacts'][role]
        _, app, _ = protocol.bms(raw_bound(capture, item['bms']), policy['bundle'], policy)
        require(item['uid'] == app['uid'] and item['token_id'] == app['accessTokenId'], 'role UID/token substituted')
        token = protocol.token(protocol.decode(raw_bound(capture, item['token'])),
            {'run_id': challenge['run_id'], 'boot_id': env['boot_id']}, policy['bundle'], app)
        profile = protocol.decode(checked(item['signature']['verified_profile']).read_text())
        require(profile['bundle-info']['bundle-name'] == policy['bundle'] and profile['bundle-info']['apl'] == policy['apl'] and
                profile['acls']['allowed-acls'] == policy['allowed_acls'] and
                profile['permissions']['restricted-permissions'] == policy['allowed_acls'], 'captured exact profile role/ACL mismatch')
        require(sha(checked(item['installed_hap'])) == sha(checked(item['signature']['signed_hap'])), 'actual installed QA signed bytes changed')
        if role in ('producer', 'denied'):
            require(all(token['permissions'][p] == -1 for p in ('ohos.permission.READ_WHOLE_CALENDAR',
                'ohos.permission.WRITE_WHOLE_CALENDAR', 'ohos.permission.NOTIFICATION_CONTROLLER')), 'normal caller elevated')
        else:
            require(token['permissions']['ohos.permission.NOTIFICATION_CONTROLLER'] == 0,
                    'observer exact configured ACL did not confer the actual required notification permission')
        identities.append((app['uid'], app['accessTokenId']))
        apps[policy['bundle']] = app
    require(len(set(identities)) == 3, 'producer/observer identity overlap')
    provider = capture['artifacts']['provider']
    _, app, _ = protocol.bms(raw_bound(capture, provider['bms']), CONTRACT['provider'])
    require(app['isSystemApp'] is True and app['appPrivilegeLevel'] == 'system_core', 'provider actual BMS identity differs')
    apps[CONTRACT['provider']] = app
    protocol.token(protocol.decode(raw_bound(capture, provider['token'])),
        {'run_id': challenge['run_id'], 'boot_id': env['boot_id']}, CONTRACT['provider'], app)
    if 'provider_token_after' in capture:
        protocol.token(protocol.decode(raw_bound(capture, capture['provider_token_after'])),
            {'run_id': challenge['run_id'], 'boot_id': env['boot_id']}, CONTRACT['provider'], app)
    source = protocol.decode(checked(provider['archive_binding']).read_text())
    require(source['archive'] == archive and source['signed_hap']['sha256'] == sha(checked(provider['installed_hap'])) and
            source['collector'] == record(Path(__file__).with_name('batch_system_calendar_runtime_archive.py')),
            'provider bytes are not derived from the current archive')
    import batch_apps_contact_picker_coordinator as signatures
    module, payload = signatures.hap_contents(checked(provider['installed_hap']))
    require(protocol.schema(module) == provider['schema'] and payload == source['module_payload'], 'actual provider metadata/ABC changed')
    if capture['stage'] == 'public-operation':
        operation(capture)
        role = capture['request']['role']
        protocol.token(protocol.decode(raw_bound(capture, capture['token_after'])),
            {'run_id': challenge['run_id'], 'boot_id': env['boot_id']}, ROLES[role]['bundle'], apps[ROLES[role]['bundle']])
    for decision in capture.get('permission_clicks', []):
        layout = layout_bound(capture, decision['layout']); pixels_bound(capture, decision['screenshot'])
        text = decision['selected_text']
        allowed = plan.get('allow_texts', ['允许', 'Allow']) if decision['decision'] == 'allow' else plan.get('deny_texts', ['不允许', 'Deny'])
        require(text in allowed, 'actual permission label does not match requested user decision')
        from batch_apps_run_contact_picker_runtime import clickable_for_text
        node = clickable_for_text(layout, plan.get('permission_bundle', 'com.ohos.permissionmanager'), text)
        require(node == decision['selected_node'], 'permission choice is not the observed permissionmanager UI node')
        x, y, w, h = node['rect']; command = f'uitest uiInput click {x+w//2} {y+h//2}'
        require(any(row['label'] == 'permission-actual-node' and command in row['argv'][-1] for row in capture['commands']),
                'actual user permission click command missing')
    if 'view' in capture:
        view = capture['view']
        layout = layout_bound(capture, view['layout'])
        size = pixels_bound(capture, view['screenshot'])
        for name, node in view['nodes'].items():
            empty = view['expected_blank'] and name != 'status'
            actual = protocol.viewer_field(layout, name, empty=empty)
            require(actual == node, 'actual viewer node differs')
            if not empty:
                require(actual['rect'][0]+actual['rect'][2] <= size[0] and
                        actual['rect'][1]+actual['rect'][3] <= size[1], 'actual viewer pixel geometry differs')
        if view['expected_blank']:
            require(view['nodes']['status']['attributes'].get('text'), 'denied/invalid/deleted UI needs real visible status')
        elif view['expected_persisted']:
            provider_token = protocol.decode(raw_bound(capture, capture['provider_token_after']))
            require(provider_token['permissions']['ohos.permission.READ_WHOLE_CALENDAR'] == 0,
                    'persisted viewer data appeared without the actual required whole-calendar grant')
            require('readback_capture' in capture, 'independent public readback required')
            independent = protocol.decode(checked(capture['readback_capture']).read_text())
            require(independent['request']['role'] == 'observer' and independent['request']['action'] == 'read' and
                    independent['boot_id'] == capture['boot_id'] and independent['archive'] == archive, 'independent same-boot observer required')
            rows = operation(independent)
            expected = view['expected_persisted']
            matches = [(event, value) for value in protocol.values(rows, 'events', 'Calendar.getEvents')
                for event in value['events'] if event.get('id') == expected['event']['id']]
            require(len(matches) == 1 and matches[0][0] == expected['event'] and
                    expected['display'] in matches[0][1]['display'], 'UI expected values were not independently publicly read')
            for key in ('title', 'description'):
                require(view['nodes'][key]['attributes'].get('text') == expected['event'][key], 'UI does not show actual persisted event')
            for key in ('start', 'end'):
                require(view['nodes'][key]['attributes'].get('text') == expected['display'][key], 'UI does not show actual persisted time')
    return capture


def verify(challenge_path, captures):
    data = load_challenge(challenge_path)
    paths = [Path(p).resolve() for p in captures]
    require(paths and len(paths) == len(set(paths)), 'nonempty unique actual captures required')
    first = protocol.decode(paths[0].read_text())
    archive = first['archive']; checked(archive)
    values = [validate_capture(path, data, archive) for path in paths]
    clocks = {}
    for c in values:
        observed = [item['token'] for item in c['artifacts'].values() if 'token' in item]
        observed += [c[k] for k in ('token_after', 'provider_token_after') if k in c]
        for item in observed:
            token = protocol.decode(raw_bound(c, item))
            clocks.setdefault(c['boot_id'], []).append(token)
        if c['stage'] == 'public-operation':
            rows = operation(c)
            first = protocol.decode(raw_bound(c, c['artifacts'][c['request']['role']]['token']))
            last = protocol.decode(raw_bound(c, c['token_after']))
            require(all(first['realtime_ns']//1_000_000 <= r['timestamp_ms'] <= last['realtime_ns']//1_000_000 for r in rows),
                    'public journal timestamp lies outside actual native observer capture clocks')
    for boot, rows in clocks.items():
        offsets = [r['realtime_ns']-r['boottime_ns'] for r in rows]
        require(max(offsets)-min(offsets) <= 2_000_000_000, 'guest wall clock changed between captured stages')
    by_path = {str(path): value for path, value in zip(paths, values)}
    core = []
    coverage = {case: 'gap' for case in CONTRACT['mandatory_coverage']}
    coverage['normal-identities'] = 'observed'
    coverage['provider-identity-schema'] = 'observed-installed-shape-only'
    for c in values:
        if c['stage'] == 'public-operation':
            rows = operation(c); request = c['request']; action = request['action']; role = request['role']
            errors = [r for r in rows if r['event'] == 'error']
            if action == 'permission' and role == 'producer':
                permissions = protocol.values(rows, 'permission', 'abilityAccessCtrl.requestPermissionsFromUser')
                decisions = c.get('permission_clicks', [])
                require(len(permissions) == 1, 'actual user permission outcome missing')
                native = protocol.decode(raw_bound(c, c['token_after']))['permissions']
                for choice, wanted, key in [('deny', -1, 'producer-user-deny'), ('allow', 0, 'producer-user-allow')]:
                    if decisions and decisions[-1]['decision'] == choice and permissions[0]['authResults'] == [wanted, wanted] and all(
                            native[p] == wanted for p in ROLES['producer']['permissions']):
                        coverage[key] = 'observed'
            if action == 'create' and role == 'producer' and not errors:
                native = protocol.decode(raw_bound(c, c['token_after']))['permissions']
                require(all(native[p] == 0 for p in ROLES['producer']['permissions']), 'ordinary public creation lacks actual user READ/WRITE grants')
                protocol.created(rows, data['run_id']); coverage['public-create-readback'] = 'observed'
            if action == 'read' and role == 'observer' and not errors and protocol.values(rows, 'events', 'Calendar.getEvents'):
                require(protocol.decode(raw_bound(c, c['token_after']))['permissions']['ohos.permission.READ_WHOLE_CALENDAR'] == 0,
                        'independent observer read lacks actual whole-calendar grant')
                coverage['independent-whole-read'] = 'observed'
            if action == 'cleanup' and role == 'producer' and not errors:
                deleted = protocol.values(rows, 'calendar-deleted', 'CalendarManager.deleteCalendar')
                accounts = protocol.values(rows, 'accounts', 'CalendarManager.getAllCalendars+Calendar.getAccount')
                require(len(deleted) == 1 and deleted[0]['account_name'] == data['account_name'] and accounts == [[]], 'public owned cleanup not complete')
                coverage['owned-cleanup'] = 'producer-observed; independent-final-read-required'
        if c['stage'] == 'notification-click':
            require(c['notification_capture']['path'] in by_path and c['seed_capture']['path'] in by_path,
                    'supply original create and notification captures alongside click capture')
            observed = by_path[c['notification_capture']['path']]
            rows = operation(observed); seed = c['seed_event']; want = protocol.notification(rows, seed)
            require(want == c['observed_want'] and want['uid'] == c['artifacts']['provider']['uid'], 'actual notification owner UID differs')
            raw = protocol.values(rows, 'notification', 'notificationManager.getAllActiveNotifications')
            chosen = [r for r in raw if r.get('id') == want['notification_id'] and r.get('creatorBundleName') == CONTRACT['provider'] and
                      r.get('creatorUid') == c['artifacts']['provider']['uid']]
            require(len(chosen) == 1, 'actual native-consumer notification creator identity missing')
            require(not any('aa start ' in row['argv'][-1] for row in c['guest_commands']), 'direct launch cannot substitute notification click')
            click = c['notification_click']; layout = layout_bound(c, click['layout']); pixels_bound(c, click['screenshot'])
            from batch_apps_run_contact_picker_runtime import clickable_for_text
            node = clickable_for_text(layout, click['selected_node']['bundle'], seed['event']['title'])
            require(node == click['selected_node'], 'notification selected actual UI node differs')
            x, y, w, h = node['rect']; command = f'uitest uiInput click {x+w//2} {y+h//2}'
            require(any(row['label'] == 'actual-notification-node-click' and command in row['argv'][-1] for row in c['commands']), 'actual notification click command missing')
            key = {'cold-deny': 'notification-cold-deny', 'cold-allow': 'notification-cold-allow', 'warm': 'notification-warm'}.get(seed['case_id'])
            if key:
                if seed['case_id'] == 'cold-deny':
                    require(c['view']['expected_blank'] and any(d['decision'] == 'deny' for d in c.get('permission_clicks', [])),
                            'denied notification case lacks actual user Deny')
                    observed_token = protocol.decode(raw_bound(c, c['provider_token_after']))
                    require(observed_token['permissions']['ohos.permission.READ_WHOLE_CALENDAR'] == -1, 'MainAbility token was not actually denied')
                coverage[key] = 'actual-click/UI-observed; launch-mode-unproven'
            if c['view']['expected_persisted']:
                require(c['readback_capture']['path'] in by_path, 'supply original independent read capture')
                core.append({'case': seed['case_id'], 'click_capture': record(paths[values.index(c)]),
                    'public_event_id': seed['id'], 'independent_ui_values_verified': True,
                    'pixels_captured_not_OCR_verified': True})
        if c['stage'] == 'direct-uri-boundary':
            key = {'valid': 'legacy-uri', 'bad-uri': 'bad-uri', 'missing-id': 'missing-id', 'bad-id': 'bad-uri', 'deleted-id': 'deleted-refresh'}[c['uri_case']]
            coverage[key] = 'direct-URI-observed-only'
    gaps = [key for key, value in coverage.items() if value != 'observed']
    # Cold/warm instance lifecycle and reboot continuity are never inferred from
    # a stage name, two starts, two processes or an ACK. Raw AMS/hilog are kept
    # for the root's actual product lifecycle witness integration.
    return {'schema_version': 1, 'scope': 'actual_calendar_public_API_notification_UI_chain_AND_explicit_remaining_gaps',
        'run_id': data['run_id'], 'archive': archive, 'captures': [record(p) for p in paths],
        'core_chain_verified': bool(core) and coverage['public-create-readback'] == 'observed' and
            coverage['independent-whole-read'] == 'observed' and coverage['producer-user-allow'] == 'observed',
        'verified_notification_chains': core, 'coverage': coverage, 'remaining_required_gaps': gaps,
        'full_calendar_lifecycle_verified': False, 'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--challenge', type=Path, required=True)
    parser.add_argument('--capture', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.challenge, args.capture)
    write(args.output, result)
    print(json.dumps({'core_chain_verified': result['core_chain_verified'], 'remaining_required_gaps': result['remaining_required_gaps']}))
    raise SystemExit(0 if result['core_chain_verified'] else 1)
