#!/usr/bin/env python3
"""Strict raw Calendar QA protocol and host checks. Never emits guest journals."""
import json
from pathlib import Path
import re
from hap_identity_binding import verify_hap_token_identity
from batch_system_calendar_runtime_project import CONTRACT, FIX, ROLES, checked, record, require, sha

KEYS = {'schema_version', 'run_id', 'boot_id', 'archive_sha256', 'operation_id', 'role', 'action', 'case_id',
        'sequence', 'timestamp_ms', 'uid', 'token_id', 'event', 'api', 'value_json', 'error_code', 'error_message'}


def unique(pairs):
    value = {}
    for name, item in pairs:
        require(name not in value, 'duplicate JSON key')
        value[name] = item
    return value


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique)


def parse(raw, request, identity):
    require(isinstance(raw, str) and 0 < len(raw.encode()) <= 4194304 and raw.endswith('\n'),
            'complete bounded original journal required')
    rows = []
    last = 0
    for line in raw.splitlines():
        row = decode(line)
        require(set(row) == KEYS and type(row['schema_version']) is int and row['schema_version'] == 1,
                'unknown journal schema')
        require(all(row[key] == request[key] for key in ('run_id', 'boot_id', 'archive_sha256', 'role')) and
                re.fullmatch('[a-f0-9]{32}', row['operation_id']), 'foreign journal identity')
        require(type(row['sequence']) is int and row['sequence'] == len(rows) + 1 and
                type(row['timestamp_ms']) is int and row['timestamp_ms'] >= last > -1 and
                row['timestamp_ms'] > 0, 'reordered/stale journal sequence/time')
        require(type(row['uid']) is int and row['uid'] == identity['uid'] and row['uid'] // 200000 == 100 and
                type(row['token_id']) is int and row['token_id'] == identity['accessTokenId'], 'actual BMS UID/token differs')
        require(type(row['error_code']) is int and isinstance(row['error_message'], str) and
                isinstance(row['event'], str) and isinstance(row['api'], str) and
                isinstance(row['value_json'], str), 'raw API outcome fields required')
        decode(row['value_json'])
        last = row['timestamp_ms']; rows.append(row)
    own = [r for r in rows if r['operation_id'] == request['operation_id']]
    if not own or own[-1]['event'] != 'complete':
        return rows, None
    require(own[0]['event'] == 'begin' and sum(r['event'] == 'begin' for r in own) == 1 and
            sum(r['event'] == 'complete' for r in own) == 1 and
            all(r['action'] == request['action'] and r['case_id'] == request['case_id'] for r in own) and
            decode(own[0]['value_json']) == request, 'duplicate or substituted operation')
    return rows, own


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def bms(raw, bundle, policy=None):
    if raw.startswith(bundle + ':\n'):
        raw = raw[len(bundle) + 2:]
    value = decode(raw)
    app = value.get('applicationInfo')
    require(isinstance(app, dict) and (app.get('name') or app.get('bundleName')) == bundle and
            type(app.get('uid')) is int and app['uid'] // 200000 == 100 and
            type(app.get('accessTokenId')) is int and 0 < app['accessTokenId'] < 2**32, 'actual unique BMS application required')
    if policy:
        require(app.get('isSystemApp') is policy['system_app'] and app.get('appPrivilegeLevel') == policy['apl'],
                'BMS actual normal/system role differs')
    paths = {v['hapPath'] for v in objects(value) if isinstance(v.get('hapPath'), str) and v['hapPath'].endswith('.hap')}
    require(len(paths) == 1 and all(p.startswith(('/data/app/', '/system/', '/vendor/', '/product/')) and
            '..' not in Path(p).parts for p in paths), 'actual unique installed HAP path required')
    return value, app, paths.pop()


def token(value, request, bundle, app):
    verify_hap_token_identity(value, bundle=bundle, uid=app['uid'], token_id=app['accessTokenId'])
    require(type(value.get('schema_version')) is int and value.get('schema_version') == 2 and value.get('run_id') == request['run_id'] and
            value.get('boot_id') == request['boot_id'] and value.get('bundle') == bundle and
            value.get('user_id') == 100 and value.get('permission_api') == 'AccessTokenKit::VerifyAccessToken' and
            value.get('process_api') == 'AppMgrClient::GetAllRunningProcesses', 'raw product token/process identity mismatch')
    expected = {'ohos.permission.' + name for name in ('READ_CALENDAR', 'WRITE_CALENDAR', 'READ_WHOLE_CALENDAR',
                'WRITE_WHOLE_CALENDAR', 'NOTIFICATION_CONTROLLER')}
    require(set(value.get('permissions', {})) == expected and all(type(v) is int and v in (0, -1)
            for v in value['permissions'].values()), 'actual bounded token grants required')
    definitions = value.get('definitions', {})
    require(value.get('definition_api') == 'AccessTokenKit::GetDefPermission' and set(definitions) == expected and
            all(row.get('permissionName') == name and type(row.get('availableLevel')) is int and
                row['availableLevel'] in (1, 2, 3) and type(row.get('grantMode')) is int and row['grantMode'] in (0, 1) and
                type(row.get('availableType')) is int and type(row.get('provisionEnable')) is bool
                for name, row in definitions.items()), 'actual current-image permission definitions required')
    require(type(value.get('before_ns')) is int and type(value.get('after_ns')) is int and
            0 < value['before_ns'] <= value['after_ns'] and type(value.get('realtime_ns')) is int and
            value['realtime_ns'] > 0 and type(value.get('boottime_ns')) is int and value['boottime_ns'] > 0,
            'real observer clocks required')
    return value


def schema(module):
    actual = module.get('module', module)
    rows = [v for v in actual.get('metadata', []) if v.get('name') in
            ('ohos.calendardata.reminderDbVersion', 'hmos.calendardata.reminderDbVersion')]
    require(rows and len({r['name'] for r in rows}) == len(rows) and
            all(r.get('value') in ('1', '2') for r in rows) and len({r['value'] for r in rows}) == 1,
            'installed provider actual reminder schema missing/unsupported/ambiguous')
    require(len([a for a in actual.get('abilities', []) if a.get('name') == 'MainAbility' and
            a.get('exported') is True and a.get('srcEntry') == './ets/MainAbility/MainAbility.ets']) == 1,
            'actual compiled provider MainAbility contract missing')
    return {'observed_metadata': rows, 'alternate_keys_or_versions_tested': False}


def values(rows, event, api=None):
    selected = [r for r in rows if r['event'] == event and (api is None or r['api'] == api)]
    return [decode(r['value_json']) for r in selected]


def viewer_field(layout, name, *, empty=False):
    from guest_ui import select_node
    if not empty:
        return select_node(layout, CONTRACT['provider'], identifier='calendar-main-' + name)
    # ArkUI may omit or give zero-size bounds to Text(''). That is a real
    # empty UI outcome, not a synthetic visible node. Status must separately
    # be visible. Any retained nonempty sensitive field still fails closed.
    from batch_apps_run_contact_picker_runtime import walk
    matches = [node['attributes'] for node, bundle, _ in walk(layout) if bundle == CONTRACT['provider'] and
               node['attributes'].get('id') == 'calendar-main-' + name]
    require(len(matches) <= 1 and all(not row.get('text') for row in matches), 'blank viewer retains event text or ambiguous instances')
    return {'attributes': matches[0], 'bundle': CONTRACT['provider']} if matches else None


TERMINAL_STATUSES = {'请从日程提醒打开对应日程', '日程已删除或当前帐号不可见', '无法读取日程，请检查日历权限后重试'}


def viewer_nodes(layout, blank):
    from guest_ui import NodeNotReady, select_node
    nodes = {name: viewer_field(layout, name, empty=blank) for name in ('title', 'description', 'start', 'end')}
    if blank:
        nodes['status'] = select_node(layout, CONTRACT['provider'], identifier='calendar-main-status')
        if nodes['status']['attributes'].get('text') not in TERMINAL_STATUSES:
            raise NodeNotReady('blank viewer is still pending or has no recognized actual terminal status')
    else:
        # Successful production reads intentionally render Text(''). It may
        # have zero area or be absent; no synthetic visible node is invented.
        try:
            nodes['status'] = viewer_field(layout, 'status', empty=True)
        except ValueError as error:
            raise NodeNotReady('viewer has not reached the actual empty success status') from error
    return nodes


def permission_windows(layout, bundle):
    from batch_apps_run_contact_picker_runtime import walk
    result = []
    for node, actual, ancestors in walk(layout):
        if actual != bundle or node['attributes'].get('bundleName') != bundle or any(
                p['attributes'].get('bundleName') == bundle for p in ancestors):
            continue
        if any(v['attributes'].get('visible') == 'true' for v, owner, _ in walk(node) if owner == bundle):
            result.append(node)
    return result


def permission_control(layout, panel, target_bundle, target_label, texts):
    """Fail closed on a foreign/ambiguous actual prompt; never click by Allow alone."""
    from batch_apps_run_contact_picker_runtime import clickable_for_text
    from guest_ui import NodeNotReady, select_node
    windows = permission_windows(layout, panel)
    if not windows:
        return None
    require(len(windows) == 1, 'foreign or ambiguous permission windows; preserve their state')
    window = windows[0]
    requester = select_node(window, panel, text=target_label)
    matches = []
    for text in texts:
        try:
            matches.append((text, clickable_for_text(window, panel, text)))
        except NodeNotReady:
            pass
    require(len(matches) == 1, 'actual owned prompt decision is missing or ambiguous')
    text, button = matches[0]
    return {'requester_bundle': target_bundle, 'requester_label': target_label, 'requester_node': requester,
            'window_attributes': window['attributes'], 'selected_text': text, 'selected_node': button}


def bind_seed(rows, request, supplied, run):
    require(request.get('role') == 'producer' and request.get('action') == 'create', 'original normal producer create required')
    cases = created(rows, run)
    require(isinstance(supplied, dict) and supplied.get('case_id') in cases and
            cases[supplied['case_id']] == supplied, 'derived clicked event differs from original public create journal')
    return cases[supplied['case_id']]


def created(rows, run):
    require(not values(rows, 'error'), 'producer public API failed')
    accounts = values(rows, 'calendar-created', 'CalendarManager.createCalendar')
    require(len(accounts) == 1 and accounts[0]['account']['name'] == 'qcal_' + run and
            type(accounts[0]['id']) is int and accounts[0]['id'] > 0, 'public unique calendar create missing')
    events = values(rows, 'event-created', 'Calendar.addEvent')
    require(len(events) == 4 and {e['case_id'] for e in events} == set(CONTRACT['case_ids']) and
            len({e['id'] for e in events}) == 4, 'four independent public event IDs required')
    for e in events:
        require(type(e['id']) is int and 0 < e['id'] <= 2147483647 and e['event']['title'] == 'QCAL_' + run + '_' + e['case_id'] and
                e['event']['description'] == 'QNOTE_' + run + '_' + e['case_id'] and e['event']['reminderTime'] == [0] and
                e['event']['endTime'] > e['event']['startTime'] > rows[0]['timestamp_ms'] + 119000,
                'actual future owned Calendar reminder differs')
    return {e['case_id']: e for e in events}


def notification(rows, seed):
    require(not values(rows, 'error'), 'notification observer failed')
    expected = seed['event']
    scans = values(rows, 'notification-scan', 'notificationManager.getAllActiveNotifications')
    require(len(scans) == 1, 'complete actual notification scan required')
    records = values(rows, 'notification-want', 'wantAgent.getWant+getBundleName+getUid')
    # The notification service owns notification IDs. Its ID need not equal
    # the calendar's public event ID; bind the event through the real Want URI.
    chosen = [r for r in records if r['title'] == expected['title']]
    require(len(chosen) == 1, 'unique actual reminder notification/WantAgent required')
    value = chosen[0]
    require(type(value.get('notification_id')) is int and value['notification_id'] >= 0 and
            all(r['timestamp_ms'] >= expected['startTime'] for r in rows if r['event'] == 'notification-want' and
            decode(r['value_json']).get('notification_id') == value['notification_id']), 'real reminder was observed before its scheduled wall clock')
    uri = f"calendar://com.ohos.calendar?event_id={seed['id']}&start={expected['startTime']}&end={expected['endTime']}"
    require(value.get('bundle') == 'com.ohos.calendardata' and value['want'].get('bundleName') == 'com.ohos.calendardata' and value['want'].get('abilityName') == 'MainAbility' and
            value['want'].get('uri') == uri and type(value['uid']) is int and value['uid'] > 0,
            'actual notification target/legacy URI mismatch')
    return value


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-check', action='store_true', required=True)
    args = parser.parse_args()
    # Tests are deliberately imported only by this opt-in host path. They never
    # install a fake runtime journal in an acceptance evidence directory.
    import unittest
    from batch_system_calendar_runtime_tests import CalendarProtocolTests
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CalendarProtocolTests))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
