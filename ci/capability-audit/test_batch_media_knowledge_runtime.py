"""Host protocol/oracle counterexamples, never evidence of a guest/API result."""
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

import batch_media_knowledge_project as project
import batch_media_knowledge_runtime as runtime

BOOT = '132c45ef-1234-4567-8abc-123456789abc'
RUN = '123456789abcdef0123456789abcdef0'
SDK = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')


class KnowledgeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='knowledge-protocol-test-')
        self.root = Path(self.temp.name)
        self.calendar = self.root / 'holidays.ics'
        # External test dates ONLY; not represented as actual real-world holidays.
        self.calendar.write_text('BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:test-unicode\n'
            'DTSTART;VALUE=DATE:20260215\nDTEND;VALUE=DATE:20260224\nSUMMARY;LANGUAGE=zh-CN:测试节日\n'
            'END:VEVENT\nEND:VCALENDAR\n')
        self.provenance = self.root / 'provenance.json'
        project.write(self.provenance, {'asset': {'sha256': project.sha(self.calendar)},
            'makeup_workdays_not_in_holiday_ics': ['2026-02-14']})
        self.challenge = project.make_challenge(self.root / 'challenge', self.calendar, self.provenance, RUN)
        self.data = runtime.validate_challenge(self.challenge)
        self.uris = {c['case_id']: f'file://media/Photo/{index+1}/IMG_{index+1}.jpg'
                     for index, c in enumerate(self.data['cases'])}
        self.journals = self.make_host_oracle_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def make_host_oracle_fixture(self):
        """Synthesize ONLY unit-test inputs; none are saved as runtime evidence."""
        rows = {role: [] for role in project.ROLES}
        moment = 100000
        for step, (phase, role, action) in enumerate(runtime.STEPS):
            request = runtime.prepare_request(self.challenge, BOOT, phase, self.uris, f'{step+1:032x}')
            own = rows[role]
            def add(event, api, value, code=0):
                nonlocal moment
                moment += 1
                own.append({'schema_version': 1, 'run_id': RUN, 'boot_id': BOOT, 'operation_id': request['operation_id'],
                    'role': role, 'phase': phase, 'sequence': len(own)+1, 'timestamp_ms': moment,
                    'uid': 20010001+list(project.ROLES).index(role), 'token_id': 51+list(project.ROLES).index(role),
                    'event': event, 'api': api, 'value_json': json.dumps(value), 'error_code': code,
                    'error_message': 'real-error-placeholder-IN-UNIT-TEST-ONLY' if code else ''})
            add('begin', 'request', request)
            granted = role in ('query', 'curator') and action not in ('access', 'permission')
            add('access', 'abilityAccessCtrl.checkAccessTokenSync', {'read': 0 if granted else -1,
                'write': 0 if granted and role == 'curator' else -1})
            if phase in ('normal-denied', 'system-denied'):
                for method in ['getRelatedEntity', 'getSearchSuggestion'] if role == 'denied' else ['getRelatedEntity']:
                    add('access_error', 'KnowledgeContent.'+method, {}, 202 if role == 'denied' else 201)
            elif action == 'permission':
                names = [project.READ, project.WRITE] if role == 'curator' else [project.READ]
                add('permission', 'abilityAccessCtrl.requestPermissionsFromUser', {'permissions': names, 'authResults': [0]*len(names)})
                add('access', 'abilityAccessCtrl.checkAccessTokenSync', {'read': 0, 'write': 0 if role == 'curator' else -1})
            elif action == 'import':
                for c in self.data['cases']:
                    add('source', 'ImageSource.getImageProperty', {'case_id': c['case_id'], 'file_name': c['file_name'],
                        'bytes': project.checked(c['image']).stat().st_size, 'date_time_original': c['exif_datetime'],
                        'date_time_digitized': c['exif_datetime']})
                add('consent_request', 'PhotoAccessHelper.showAssetsCreationDialog', {})
                add('consent_result', 'PhotoAccessHelper.showAssetsCreationDialog', {'uris': list(self.uris.values())})
                for c in self.data['cases']:
                    add('created', 'fs.writeSync+closeSync', {'case_id': c['case_id'], 'uri': self.uris[c['case_id']],
                        'bytes': project.checked(c['image']).stat().st_size, 'title': c['title']})
            elif role == 'query':
                for c in self.data['cases']:
                    key = c['case_id']
                    absent = phase in ('baseline', 'cleanup') or (key == self.data['lifecycle_case'] and phase in ('hidden', 'trashed', 'deleted'))
                    if phase == 'baseline':
                        add('baseline_assets', 'PhotoAccessHelper.getAssets', {'case_id': key, 'count': 0})
                    else:
                        add('asset', 'PhotoAccessHelper.getAssets', {'case_id': key, 'count': 0 if absent else 1,
                            'requested_uri': self.uris[key], 'uri': '' if absent else self.uris[key],
                            'title': '' if absent else c['title'], 'date_day': '' if absent else c['day'],
                            'date_taken': 0 if absent else c['date_taken_utc_seconds']})
                    add('related', 'KnowledgeContent.getRelatedEntity', {'case_id': key, 'topic': c['day'], 'context': {'topicField': [6]},
                        'options': {'suggestionFields': [7], 'recommendationCount': 64}, 'entities': [] if absent else c['entities']})
                add('search', 'KnowledgeContent.getSearchSuggestion', {'types': [6], 'results': []})
                if phase == 'present':
                    add('zero_count', 'KnowledgeContent.getRelatedEntity', [])
                    for kind, code in [('negative-count', 13900020), ('none-field', 13900020), ('empty-search', 23800151)]:
                        add('boundary_error', kind, {}, code)
                if phase in ('deleted', 'cleanup'):
                    add('trash_album', 'PhotoAccessHelper.getAlbums', {'count': 1})
                    for c in self.data['cases']:
                        add('trash_asset', 'Album.getAssets', {'case_id': c['case_id'], 'uri': self.uris[c['case_id']], 'count': 0})
            elif action == 'prepare':
                for item in request['items']:
                    add('held', 'PhotoAccessHelper.getAssets', {k: item[k] for k in ('case_id', 'uri', 'title')})
            elif action in ('hide', 'unhide'):
                item = request['items'][0]
                add('mutation', 'MediaAssetChangeRequest.setHidden+PhotoAccessHelper.applyChanges',
                    {'case_id': item['case_id'], 'uri': item['uri'], 'hidden': action == 'hide'})
            elif action == 'remove-private':
                for item in request['items']:
                    add('private_removed', 'fs.unlinkSync', {'case_id': item['case_id'], 'file_name': item['file_name'], 'exists_after': False})
            else:
                uri_value = {'uris': [i['uri'] for i in request['items']]}
                if action in ('trash', 'cleanup'):
                    add('mutation', 'MediaAssetChangeRequest.deleteAssets', uri_value)
                if action in ('delete', 'cleanup', 'recover'):
                    api = 'MediaAlbumChangeRequest.'+('recoverAssetsWithUri' if action == 'recover' else 'deleteAssetsWithUri')+'+PhotoAccessHelper.applyChanges'
                    add('mutation', api, uri_value)
            add('complete', 'request', {})
        result = {}
        for role, own in rows.items():
            path = self.root / (role+'.jsonl')
            path.write_text(''.join(json.dumps(r)+'\n' for r in own))
            result[role] = path
        return result

    def verify(self):
        return runtime.verify_raw(self.challenge, self.journals, boot_id=BOOT)

    def mutate(self, role, phase, event, change, case=None):
        path = self.journals[role]
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        row = next(r for r in rows if r['phase'] == phase and r['event'] == event and
                   (case is None or json.loads(r['value_json']).get('case_id') == case))
        value = json.loads(row['value_json'])
        change(row, value)
        row['value_json'] = json.dumps(value)
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))

    def test_raw_positive_is_explicitly_not_guest_proof(self):
        result = self.verify()
        self.assertTrue(result['raw_semantics_passed'])
        self.assertFalse(result['guest_identity_verified'])
        self.assertFalse(result['ledger_closed'])
        self.assertFalse(result['account_isolation_verified'])

    def test_actual_exif_and_unique_random_inputs(self):
        again = project.make_challenge(self.root/'again', self.calendar, self.provenance)
        a = runtime.validate_challenge(again)
        self.assertNotEqual(a['cases'][0]['image']['sha256'], self.data['cases'][0]['image']['sha256'])
        with Image.open(project.checked(self.data['cases'][0]['image'])) as image:
            exif = image.getexif()
            self.assertEqual(exif.get_ifd(34665)[36881], '+00:00')
            self.assertNotIn(36867, exif)  # Real Exif sub-IFD, not mislocated IFD0.

    def test_application_root_files_keep_business_context_and_real_ui_failures(self):
        store = (project.FIX/'AuditStore.ets').read_text()
        self.assertIn('this.filesDir = context.getApplicationContext().filesDir;', store)
        self.assertIn("this.path = this.filesDir + '/knowledge-'", store)
        self.assertIn("const requestPath = this.filesDir + '/knowledge-request.json'", store)
        self.assertIn('requestPermissionsFromUser(this.context', store)
        self.assertNotIn('context.filesDir', store)
        importer = (project.FIX/'Importer.ets').read_text()
        self.assertNotIn('store.context.filesDir', importer)
        self.assertIn('store.filesDir', importer)
        for name in ('Importer', 'Denied', 'Curator', 'Query'):
            source = (project.FIX/(name+'.ets')).read_text()
            self.assertIn('Request initialization failed;', source)
            self.assertIn("Text(this.note).id('knowledge_status')", source)
            self.assertIn('actual.message ?? String(error)', source)

    def test_request_initialization_diagnostic_retains_real_ui_without_fabricating_journal(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import batch_media_knowledge_suite as suite
        tree = {'attributes': {'bundleName': project.ROLES['denied'][0]}, 'children': [{
            'attributes': {'id': 'knowledge_status', 'visible': 'true', 'bounds': '[0,0][600,100]',
                           'text': 'Request initialization failed; application filesDir=/actual; code=13900002; message=No such file'},
            'children': []}]}
        path = self.root/'diagnostic-tree.json'; path.write_text(json.dumps(tree))
        image = self.root/'diagnostic.png'; Image.new('RGB', (120, 120), 'red').save(image)
        ams = self.root/'ams.txt'; ams.write_text('HOST UNIT actual-byte placeholder')
        collector = object.__new__(suite.Collector)
        collector.persist = Mock()
        collector.value = {'commands': [{'argv': ['hdc', '-t', 'host-unit', 'file', 'recv', '/host-unit-screen.png', str(image)]}]}
        collector.ui = SimpleNamespace(layout=Mock(return_value=(tree,path)), screenshot=Mock(return_value=image))
        screen_hash = self.root/'screen-hash.txt'; screen_hash.write_text(project.sha(image)+'  /host-unit-screen.png')
        collector.observe = Mock(side_effect=[project.record(screen_hash), project.record(ams)])
        row = {'phase': 'normal-denied', 'role': 'denied'}
        result = collector.phase_diagnostic(row, 'waiting for actual journal')
        self.assertIs(result['diagnostic_only'], True)
        self.assertIs(result['journal_absence_proves_no_side_effect'], False)
        self.assertEqual(result['layout'], project.record(path))
        self.assertEqual(result['screenshot'], project.record(image))
        self.assertEqual(result['status']['attributes']['text'], tree['children'][0]['attributes']['text'])
        self.assertNotIn('journal', result)
        self.assertNotIn('complete', row)
        self.assertEqual(collector.observe.call_args_list[-1].args, ('aa dump -a -u 100', 'normal-denied-diagnostic-AMS'))
        collector.ui.layout.side_effect = ValueError('original UITest observation unavailable')
        second = collector.phase_diagnostic(row, 'actual journal timeout; side effects unknown')
        self.assertEqual(second['capture_error'], 'original UITest observation unavailable')
        self.assertNotIn('journal', second)

    def test_actual_sdk105_declarations_and_four_projects(self):
        if not SDK.is_dir():
            self.skipTest('actual SDK105 not present; root actual SDK build still required')
        for role, (bundle, apl, permissions, _) in project.ROLES.items():
            manifest = project.prepare_project(self.root/role, role, self.challenge, SDK)
            value = json.loads(manifest.read_text())
            module = json.loads((manifest.parent/'entry/src/main/module.json5').read_text())['module']
            self.assertEqual([p['name'] for p in module['requestPermissions']], permissions)
            self.assertEqual(value['bundle_name'], bundle)
            self.assertEqual(value['apl_required_at_signing'], apl)
            self.assertEqual(value['allowed_acls'], [])
            self.assertFalse(value['runtime_acceptance'])
            self.assertEqual(module['deviceTypes'], ['default'])
            self.assertEqual(value['sdk_device_types'], ['default'])
            self.assertEqual(value['acceptance_device'], 'phone')
            self.assertEqual(value['sdk']['device_default'], project.record(SDK/'ets/api/device-define/default.json'))

    def test_missing_real_device_capability_fails_before_preparation(self):
        sdk = self.root/'profile-unit-input'
        file = sdk/'ets/api/device-define/default.json'
        project.write(file, {'SysCaps': sorted(project.REQUIRED_SYSCAPS-{'SystemCapability.FileManagement.PhotoAccessHelper.Core'})})
        with self.assertRaisesRegex(ValueError, 'lacks a required caller capability'):
            project.check_device_profile(sdk)
        file.write_text(json.dumps({'SysCaps': sorted(project.REQUIRED_SYSCAPS)}))
        self.assertEqual(project.check_device_profile(sdk), project.record(file))

    def test_published_phase_contract_matches_actual_factory(self):
        contract = json.loads((project.FIX/'protocol.json').read_text())
        self.assertEqual(contract['steps'], [list(step) for step in runtime.STEPS])
        self.assertEqual(contract['sdk_device_types'], project.SDK_DEVICE_TYPES)
        self.assertEqual(contract['acceptance_device'], project.ACCEPTANCE_DEVICE)
        self.assertFalse(contract['acceptance']['ledger_closed'])

    def test_wrong_date_day_fails(self):
        self.mutate('query', 'present', 'asset', lambda r, v: v.update(date_day='20261017'))
        with self.assertRaisesRegex(ValueError, 'DATE_DAY'):
            self.verify()

    def test_date_taken_import_time_cannot_replace_exif(self):
        self.mutate('query', 'present', 'asset', lambda r, v: v.update(date_taken=123))
        with self.assertRaisesRegex(ValueError, 'DATE_TAKEN'):
            self.verify()

    def test_missing_holiday_entity_fails(self):
        path = self.journals['query']
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        row = next(r for r in rows if r['phase'] == 'present' and r['event'] == 'related' and json.loads(r['value_json'])['entities'])
        v = json.loads(row['value_json']); v['entities'] = []; row['value_json'] = json.dumps(v)
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        with self.assertRaisesRegex(ValueError, 'HOLIDAY relation'):
            self.verify()

    def test_hidden_cannot_keep_old_entity(self):
        lifecycle = next(c for c in self.data['cases'] if c['case_id'] == self.data['lifecycle_case'])
        self.mutate('query', 'hidden', 'related', lambda r, v: v.update(entities=lifecycle['entities']), case=lifecycle['case_id'])
        with self.assertRaisesRegex(ValueError, 'HOLIDAY relation'):
            self.verify()

    def test_missing_curator_is_not_partial_pass(self):
        del self.journals['curator']
        with self.assertRaisesRegex(ValueError, 'four'):
            self.verify()

    def test_normal_201_is_not_real_202(self):
        self.mutate('denied', 'normal-denied', 'access_error', lambda r, v: r.update(error_code=201))
        with self.assertRaisesRegex(ValueError, '202'):
            self.verify()

    def test_user_denial_is_not_empty_success(self):
        self.mutate('query', 'read-permission', 'permission', lambda r, v: v.update(authResults=[-1]))
        with self.assertRaisesRegex(ValueError, 'permission decision'):
            self.verify()

    def test_boolean_auth_result_is_not_grant(self):
        self.mutate('query', 'read-permission', 'permission', lambda r, v: v.update(authResults=[False]))
        with self.assertRaisesRegex(ValueError, 'permission decision'):
            self.verify()

    def test_other_api_cannot_supply_asset_result(self):
        self.mutate('query', 'present', 'asset', lambda r, v: r.update(api='fake.getAssets'))
        with self.assertRaisesRegex(ValueError, 'another API'):
            self.verify()

    def test_exclusive_end_cannot_be_a_holiday(self):
        self.mutate('query', 'present', 'related', lambda r, v:
                    v.update(entities=[{'id': 'wrong', 'name': 'wrong', 'field': 7, 'alias': []}]), case='d20260224')
        with self.assertRaisesRegex(ValueError, 'HOLIDAY relation'):
            self.verify()

    def test_source_date_cannot_be_written_by_asset_setter(self):
        for name in ('Importer.ets', 'Query.ets', 'Curator.ets', 'Denied.ets'):
            source = (project.FIX/name).read_text()
            self.assertNotIn('.set(photoAccessHelper.PhotoKeys.DATE', source)
            self.assertNotIn('executeSql', source)
            self.assertNotIn('rdbStore', source)
            self.assertNotIn('throw error', source)

    def test_trash_cleanup_must_be_actual_empty(self):
        self.mutate('query', 'cleanup', 'trash_asset', lambda r, v: v.update(count=1))
        with self.assertRaisesRegex(ValueError, 'remain in actual trash'):
            self.verify()

    def test_private_cleanup_must_be_actual(self):
        self.mutate('importer', 'cleanup-private', 'private_removed', lambda r, v: v.update(exists_after=True))
        with self.assertRaisesRegex(ValueError, 'private JPEG cleanup'):
            self.verify()

    def test_nonce_replay_fails(self):
        self.mutate('query', 'present', 'begin', lambda r, v: r.update(operation_id='f'*32))
        with self.assertRaises(ValueError):
            self.verify()

    def test_old_boot_fails(self):
        self.mutate('query', 'present', 'begin', lambda r, v: r.update(boot_id='e'*36))
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.verify()

    def test_bool_is_not_actual_asset_count(self):
        self.mutate('query', 'present', 'asset', lambda r, v: v.update(count=True))
        with self.assertRaisesRegex(ValueError, 'visibility'):
            self.verify()

    def test_real_call_error_cannot_be_disguised(self):
        self.mutate('query', 'present', 'asset', lambda r, v: r.update(error_code=201))
        with self.assertRaisesRegex(ValueError, 'hidden error'):
            self.verify()

    def test_source_image_tamper_fails(self):
        path = project.checked(self.data['cases'][0]['image'])
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.verify()

    def test_request_requires_public_uri_mapping(self):
        with self.assertRaisesRegex(ValueError, 'URI mapping'):
            runtime.prepare_request(self.challenge, BOOT, 'present')
        before = runtime.prepare_request(self.challenge, BOOT, 'baseline', self.uris)
        self.assertTrue(all(item['uri'] == '' for item in before['items']))
        present = runtime.prepare_request(self.challenge, BOOT, 'present', self.uris)
        self.assertEqual(present['items'][0]['case_id'], self.data['lifecycle_case'])

    def test_truncated_jsonl_fails(self):
        path = self.journals['query']; path.write_text(path.read_text().rstrip())
        with self.assertRaisesRegex(ValueError, 'complete bounded'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
