"""Host protocol/source tests only; memory doubles are never runtime artifacts."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from batch_system_calendar_runtime_project import FIX, ROLES, challenge, prepare, request, sha
from batch_system_calendar_runtime_sign import configure
import batch_system_calendar_runtime_protocol as p


class CalendarProtocolTests(unittest.TestCase):
    def setUp(self):
        self.identity = {'uid': 20015001, 'accessTokenId': 12345}
        self.request = {'schema_version': 1, 'run_id': 'd'*32, 'boot_id': '12345678-1234-1234-1234-123456789abc',
            'archive_sha256': 'a'*64, 'operation_id': 'b'*32, 'role': 'producer', 'action': 'read', 'case_id': 'read-before'}
        self.rows = [self.row('begin', 1, self.request), self.row('complete', 2, {})]

    def row(self, event, sequence, value):
        return {**self.request, 'sequence': sequence, 'timestamp_ms': 1800000000000+sequence,
            'uid': self.identity['uid'], 'token_id': self.identity['accessTokenId'],
            'event': event, 'api': 'request', 'value_json': json.dumps(value), 'error_code': 0, 'error_message': ''}

    def parse(self, rows):
        return p.parse(''.join(json.dumps(r)+'\n' for r in rows), self.request, self.identity)

    def test_bound_protocol_and_incomplete_not_success(self):
        self.assertEqual(len(self.parse(self.rows)[1]), 2)
        self.assertIsNone(self.parse(self.rows[:1])[1])
        with self.assertRaises(ValueError):
            p.parse(json.dumps(self.rows[0]), self.request, self.identity)

    def test_replay_identity_sequence_type_and_time_rejected(self):
        for field, value in [('boot_id', 'f'*36), ('archive_sha256', 'f'*64), ('run_id', '0'*32),
                             ('uid', 20015002), ('token_id', 3), ('sequence', 8), ('timestamp_ms', 1), ('error_code', False)]:
            rows = copy.deepcopy(self.rows); rows[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.parse(rows)
        with self.assertRaises(ValueError): self.parse([self.rows[0], self.rows[0], self.rows[1]])

    def test_substituted_request_and_duplicate_json_rejected(self):
        rows = copy.deepcopy(self.rows); value = dict(self.request, action='create'); rows[0]['value_json'] = json.dumps(value)
        with self.assertRaises(ValueError): self.parse(rows)
        with self.assertRaises(ValueError): p.decode('{"event":"begin","event":"complete"}')

    def test_profile_roles_cannot_raise_normal_caller_privilege(self):
        for role, policy in ROLES.items():
            profile = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
            module = {'app': {'bundleName': policy['bundle']}, 'module': {'requestPermissions': [{'name': n} for n in policy['permissions']],
                'abilities': [{'name': 'EntryAbility'}]}}
            result = configure(profile, role, 'a'*64, module)
            self.assertEqual(result['bundle-info']['apl'], policy['apl'])
            self.assertEqual(result['acls']['allowed-acls'], [] if role != 'observer' else ['ohos.permission.NOTIFICATION_CONTROLLER'])
            module['module']['requestPermissions'].append({'name': 'ohos.permission.MANAGE_MISSIONS'})
            with self.assertRaises(ValueError): configure(profile, role, 'a'*64, module)

    def test_metadata_only_actual_shape_and_unknown_version_rejected(self):
        ability = {'name': 'MainAbility', 'exported': True, 'srcEntry': './ets/MainAbility/MainAbility.ets'}
        for name in ('ohos', 'hmos'):
            for version in ('1', '2'):
                module = {'metadata': [{'name': name+'.calendardata.reminderDbVersion', 'value': version}], 'abilities': [ability]}
                self.assertFalse(p.schema(module)['alternate_keys_or_versions_tested'])
        with self.assertRaises(ValueError):
            p.schema({'metadata': [{'name': 'ohos.calendardata.reminderDbVersion', 'value': '3'}], 'abilities': [ability]})

    def test_request_role_scope_and_unique_nonces(self):
        with tempfile.TemporaryDirectory() as directory:
            source = challenge(Path(directory)/'challenge')
            first = request(source, self.request['boot_id'], 'a'*64, 'producer', 'create', 'create')
            second = request(source, self.request['boot_id'], 'a'*64, 'producer', 'create', 'create')
            self.assertNotEqual(first['operation_id'], second['operation_id'])
            for role, action in [('observer', 'create'), ('observer', 'routes'), ('denied', 'notifications'), ('producer', 'notifications')]:
                with self.subTest(role=role, action=action), self.assertRaises(ValueError):
                    request(source, self.request['boot_id'], 'a'*64, role, action, 'create')

    def test_notification_requires_real_preserved_want_and_id(self):
        seed = {'id': 400, 'event': {'title': 'QCAL_'+self.request['run_id']+'_cold-allow', 'startTime': 1800000120000, 'endTime': 1800001920000}}
        value = {'notification_id': 90400, 'title': seed['event']['title'], 'uid': 20015004, 'bundle': 'com.ohos.calendardata',
            'want': {'bundleName': 'com.ohos.calendardata', 'abilityName': 'MainAbility',
                'uri': 'calendar://com.ohos.calendar?event_id=400&start=1800000120000&end=1800001920000'}}
        rows = [self.row('notification-scan', 1, {}), self.row('notification-want', 2, value)]
        for index, row in enumerate(rows): row['timestamp_ms'] = seed['event']['startTime'] + index + 1
        rows[0]['api'] = 'notificationManager.getAllActiveNotifications'; rows[1]['api'] = 'wantAgent.getWant+getBundleName+getUid'
        self.assertEqual(p.notification(rows, seed)['uid'], 20015004)
        for name, changed in [('bundleName', 'com.ohos.calendar'), ('uri', ''), ('abilityName', 'Other')]:
            wrong = copy.deepcopy(rows); v = json.loads(wrong[1]['value_json']); v['want'][name] = changed; wrong[1]['value_json'] = json.dumps(v)
            with self.subTest(name=name), self.assertRaises(ValueError): p.notification(wrong, seed)

    def test_actual_qa_source_future_events_ownership_and_cleanup(self):
        result = subprocess.run(['node', '--unhandled-rejections=strict', str(FIX/'host.cjs'), str(FIX/'CalendarAudit.ets')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('PASS host-only', result.stdout)

    def test_fixture_has_no_direct_notification_publication_or_clock_mutation(self):
        source = (FIX/'CalendarAudit.ets').read_text()
        for forbidden in ('notificationManager.publish(', 'reminderAgentManager.publishReminder(', 'setTime(', 'SetAccessToken', 'grantUserGrantedPermission'):
            self.assertNotIn(forbidden, source)

    def test_empty_text_may_be_absent_or_zero_size_but_never_leak(self):
        tree = {'attributes': {'bundleName': 'com.ohos.calendardata'}, 'children': []}
        self.assertIsNone(p.viewer_field(tree, 'title', empty=True))
        tree['children'].append({'attributes': {'id': 'calendar-main-title', 'text': '', 'bounds': '[0,0][0,0]'}, 'children': []})
        self.assertEqual(p.viewer_field(tree, 'title', empty=True)['attributes']['text'], '')
        tree['children'][0]['attributes']['text'] = 'private retained event'
        with self.assertRaises(ValueError): p.viewer_field(tree, 'title', empty=True)

    def test_native_identity_requires_actual_current_permission_definitions(self):
        names = ['ohos.permission.'+v for v in ('READ_CALENDAR', 'WRITE_CALENDAR', 'READ_WHOLE_CALENDAR',
                 'WRITE_WHOLE_CALENDAR', 'NOTIFICATION_CONTROLLER')]
        value = {'schema_version': 1, 'run_id': self.request['run_id'], 'boot_id': self.request['boot_id'],
            'bundle': ROLES['producer']['bundle'], 'uid': self.identity['uid'], 'token_id': self.identity['accessTokenId'],
            'user_id': 100, 'permission_api': 'AccessTokenKit::VerifyAccessToken', 'permissions': {n: -1 for n in names},
            'definition_api': 'AccessTokenKit::GetDefPermission', 'definitions': {n: {'permissionName': n,
                'grantMode': 0, 'availableLevel': 1, 'availableType': 0, 'provisionEnable': False} for n in names},
            'process_api': 'AppMgrClient::GetAllRunningProcesses', 'processes': [],
            'before_ns': 10, 'after_ns': 11, 'realtime_ns': 100, 'boottime_ns': 12}
        self.assertEqual(p.token(value, self.request, ROLES['producer']['bundle'], self.identity)['uid'], self.identity['uid'])
        for field, replacement in [('definitions', {}), ('definition_api', 'hand-filled'), ('schema_version', True), ('boottime_ns', 0)]:
            altered = dict(value); altered[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                p.token(altered, self.request, ROLES['producer']['bundle'], self.identity)


if __name__ == '__main__':
    unittest.main()
