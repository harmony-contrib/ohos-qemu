"""Host protocol/source tests only; memory doubles are never runtime artifacts."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from batch_system_calendar_runtime_project import FIX, ROLES, challenge, prepare, request, sha, record
from batch_system_calendar_runtime_sign import configure
import batch_system_calendar_runtime_protocol as p
import batch_system_calendar_runtime_binding as binding


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

    def test_success_empty_status_and_negative_loading_are_distinct(self):
        def node(name, text):
            return {'attributes': {'id': 'calendar-main-'+name, 'text': text, 'visible': 'true', 'bounds': '[1,1][80,40]'}, 'children': []}
        tree = {'attributes': {'bundleName': 'com.ohos.calendardata'}, 'children': [node(n, n) for n in ('title', 'description', 'start', 'end')]}
        self.assertIsNone(p.viewer_nodes(tree, False)['status'])
        tree['children'].append(node('status', '')); tree['children'][-1]['attributes']['bounds'] = '[0,0][0,0]'
        self.assertEqual(p.viewer_nodes(tree, False)['status']['attributes']['text'], '')
        negative = {'attributes': {'bundleName': 'com.ohos.calendardata'}, 'children': [node('status', '正在读取日程')]}
        with self.assertRaises(ValueError): p.viewer_nodes(negative, True)
        for status in p.TERMINAL_STATUSES:
            negative['children'][0]['attributes']['text'] = status
            self.assertEqual(p.viewer_nodes(negative, True)['status']['attributes']['text'], status)
        negative['children'].append(node('title', 'retained sensitive event'))
        with self.assertRaises(ValueError): p.viewer_nodes(negative, True)

    def test_permission_button_is_bound_to_one_actual_requester_window(self):
        panel = 'com.ohos.permissionmanager'; bundle = ROLES['producer']['bundle']
        label = binding.permission_label(bundle, {}, self.request['run_id'])
        def node(text, clickable=False):
            return {'attributes': {'text': text, 'visible': 'true', 'enabled': 'true', 'clickable': str(clickable).lower(),
                'bounds': '[1,1][80,40]'}, 'children': []}
        tree = {'attributes': {'bundleName': panel, 'visible': 'true'}, 'children': [node(label), node('Allow', True)]}
        self.assertEqual(p.permission_control(tree, panel, bundle, label, ['Allow'])['requester_bundle'], bundle)
        foreign = copy.deepcopy(tree); foreign['children'][0]['attributes']['text'] = 'Unrelated application'
        with self.assertRaises(ValueError): p.permission_control(foreign, panel, bundle, label, ['Allow'])
        with self.assertRaises(ValueError): p.permission_control([tree, foreign], panel, bundle, label, ['Allow'])
        self.assertIsNone(p.permission_control({'attributes': {'bundleName': bundle}, 'children': []}, panel, bundle, label, ['Allow']))
        with self.assertRaises(ValueError): binding.permission_label('com.ohos.calendardata', {'com.ohos.calendardata': {}}, self.request['run_id'])

    def test_foreign_prompt_preflight_prevents_first_request(self):
        from types import SimpleNamespace
        from batch_system_calendar_runtime_capture import Collector
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); challenge_path = challenge(root/'challenge'); archive = root/'archive.test'
            archive.write_bytes(b'HOST-TEST-ONLY not a package')
            caller = Collector.__new__(Collector)
            caller.args = SimpleNamespace(challenge=challenge_path, archive=archive, lead_minutes=2, spacing_minutes=2)
            caller.boot = self.request['boot_id']; caller.report = {}
            caller.permission_preflight = lambda: (_ for _ in ()).throw(ValueError('actual foreign prompt'))
            caller.raw = lambda *args: self.fail('must not send aa/start or any guest request')
            with self.assertRaisesRegex(ValueError, 'foreign prompt'):
                caller.operation('producer', 'permission', 'permission')

    def test_clicked_seed_must_equal_original_public_create(self):
        run = self.request['run_id']; cases = p.CONTRACT['case_ids']
        rows = [self.row('calendar-created', 1, {'id': 10, 'account': {'name': 'qcal_'+run}})]
        rows[0]['api'] = 'CalendarManager.createCalendar'
        for index, case in enumerate(cases):
            event = {'case_id': case, 'id': 400+index, 'event': {'title': 'QCAL_'+run+'_'+case,
                'description': 'QNOTE_'+run+'_'+case, 'reminderTime': [0], 'startTime': 1800000200000+index*60000,
                'endTime': 1800002000000+index*60000}}
            row = self.row('event-created', index+2, event); row['api'] = 'Calendar.addEvent'; rows.append(row)
        supplied = json.loads(rows[1]['value_json']); request = dict(self.request, role='producer', action='create')
        self.assertEqual(p.bind_seed(rows, request, supplied, run), supplied)
        changed = copy.deepcopy(supplied); changed['id'] = 999
        with self.assertRaises(ValueError): p.bind_seed(rows, request, changed, run)
        with self.assertRaises(ValueError): p.bind_seed(rows, dict(request, role='observer'), supplied, run)

    def test_shared_signing_payload_contract_is_delegated_without_fallback(self):
        with patch.object(binding.shared, 'verify_signed_payload', create=True) as shared:
            binding.signed_payload(Path('/host-test/unsigned'), Path('/host-test/signed'))
            shared.assert_called_once_with(Path('/host-test/unsigned'), Path('/host-test/signed'))
            shared.side_effect = ValueError('extra signed member')
            with self.assertRaisesRegex(ValueError, 'extra signed member'):
                binding.signed_payload(Path('/host-test/unsigned'), Path('/host-test/signed'))

    def test_exact_role_recipe_rejects_manifest_claiming_current_fixture_for_changed_source(self):
        sdk = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); c = challenge(root/'challenge')
            for role in ROLES:
                manifest_path = prepare(root/role, role, c, sdk)
                manifest, _ = binding.prepared(root/role, role, c)
                self.assertEqual(manifest['role'], role)
                target = root/role/'entry/src/main/ets/model/CalendarAudit.ets'
                target.write_text(target.read_text()+'\n// foreign source\n')
                altered = json.loads(manifest_path.read_text())
                altered['source_hashes']['entry/src/main/ets/model/CalendarAudit.ets'] = sha(target)
                manifest_path.write_text(json.dumps(altered))
                with self.subTest(role=role), self.assertRaises(ValueError): binding.prepared(root/role, role, c)

    def test_challenge_parent_alias_is_canonical_but_leaf_symlink_is_rejected(self):
        sdk = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); c = challenge(root/'challenge')
            prepare(root/'producer', 'producer', c, sdk)
            alias = root/'alias'; alias.symlink_to(c.parent, target_is_directory=True)
            value, _ = binding.prepared(root/'producer', 'producer', alias/c.name)
            self.assertEqual(value['challenge'], record(c.resolve()))
            leaf = root/'leaf.json'; leaf.symlink_to(c)
            with self.assertRaises(ValueError): binding.prepared(root/'producer', 'producer', leaf)

    def test_dedicated_SDK_receipt_rejects_foreign_failed_commands_and_sources(self):
        # Synthetic protocol inputs in a disposable host-test directory only.
        # No compiler is executed and these are never acceptance artifacts.
        sdk = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); c = challenge(root/'challenge'); source = root/'producer'
            manifest = prepare(source, 'producer', c, sdk); value, hashes = binding.prepared(source, 'producer', c)
            output = root/'host-test-only-sdk'; output.mkdir()
            tools = {}
            for name in ('node', 'ohpm', 'hvigor'):
                path = output/name; path.write_text('HOST-TEST-ONLY non executable tool protocol fixture'); tools[name] = record(path)
            cpu = output/'cpu-cap.cjs'; cpu.write_bytes((FIX/'cpu-cap.cjs').read_bytes()); tools['cpu_cap'] = record(cpu)
            hap = source/'entry/build/default/outputs/default/entry-default-unsigned.hap'; hap.parent.mkdir(parents=True)
            with zipfile.ZipFile(hap, 'w') as z:
                z.writestr('module.json', json.dumps({'app': {'bundleName': ROLES['producer']['bundle']}, 'module': {'name': 'entry'}}))
                z.writestr('ets/modules.abc', b'HOST-TEST-ONLY not compiled ABC')
                z.writestr('resources.index', b'HOST-TEST-ONLY not compiled resources')
            report = {'schema_version': 1, 'scope': binding.SDK_SCOPE, 'exit_code': 0, 'failures': [],
                'node_version': 'v18.20.1', 'source_commit': 'a'*40, 'runner_sha256': sha(binding.HERE/'batch_system_calendar_runtime_build.py'),
                'source_tools': binding.source_tools(), 'source_files': {'producer': hashes}, 'sdk': value['sdk'], 'tools': tools,
                'commands': [], 'haps': [{'project': 'producer', **record(hap), 'bytes': hap.stat().st_size}]}
            for label, argv in binding.sdk_commands(tools):
                log = output/(label+'.log'); log.write_text('HOST-TEST-ONLY protocol fixture\nBUILD SUCCESSFUL\n')
                report['commands'].append({'project': 'producer', 'label': label, 'argv': argv, 'cwd': str(source),
                    'exit_code': 0, 'log': str(log), 'sha256': sha(log)})
            evidence = output/'evidence.json'
            def run(report):
                evidence.write_text(json.dumps(report))
                spec = {'sdk_evidence': record(evidence), 'sdk_project': 'producer', 'source_project': str(source), 'unsigned_hap': record(hap)}
                return binding.sdk_binding(spec, record(manifest), 'producer', c)
            self.assertEqual(run(report)['sdk_project'], 'producer')
            for change in ('scope', 'runner', 'tools', 'SDK', 'failed', 'cwd', 'argv', 'inventory', 'timed-out'):
                wrong = copy.deepcopy(report)
                if change == 'scope': wrong['scope'] = 'foreign builder'
                elif change == 'runner': wrong['runner_sha256'] = 'f'*64
                elif change == 'tools': wrong['source_tools'] = {}
                elif change == 'SDK': wrong['sdk'] = {}
                elif change == 'failed': wrong['exit_code'] = 1
                elif change == 'cwd': wrong['commands'][1]['cwd'] = str(root/'foreign')
                elif change == 'argv': wrong['commands'][1]['argv'].append('--foreign')
                elif change == 'inventory': wrong['source_files']['producer'].pop('entry/src/main/ets/model/CalendarAudit.ets')
                elif change == 'timed-out': wrong['commands'][1]['timed_out'] = True
                with self.subTest(change=change), self.assertRaises(ValueError): run(wrong)


if __name__ == '__main__':
    unittest.main()
