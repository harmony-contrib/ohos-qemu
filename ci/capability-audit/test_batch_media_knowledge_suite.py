"""Narrow host counterexamples; no SDK, signer, HDC, compiled helper or VM."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import batch_media_knowledge_artifacts as artifacts
import batch_media_knowledge_suite as suite
from batch_media_knowledge_project import ROLES, READ, WRITE, record
from guest_ui import NodeNotReady


class KnowledgeCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='knowledge-wrapper-host-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'source.txt'; self.source.write_text('reviewed source selector bytes\n')
        self.plan = dict(schema_version=1, source_evidence=[record(self.source)], permissions={
            role: [dict(bundle='com.ohos.permissionmanager', title={'text': 'Allow Knowledge audit ' + role + ' to access images and videos on your device?'},
                        allow={'text': 'Allow'})] for role in ('query', 'curator')},
            photo_consent=dict(bundle=ROLES['importer'][0], title={'text': '允许“Knowledge audit importer”保存 33 张图片？'},
                               allow={'text': '允许'}))

    def raw(self, text, name='raw'):
        path = self.root / name; path.write_text(text); return record(path)

    def command(self, script='id -u', text='0', *, code=0, marker=True):
        nonce = '__UITEST_EXIT_' + 'a' * 32 + '__='
        argv = ['/hdc', '-t', '127.0.0.1:47001', 'shell', script + '; task_ui_rc=$?; printf "\\n' + nonce + '%s\\n" "$task_ui_rc"']
        return dict(argv=argv, label='synthetic-host-only', exit_code=0, timed_out=False,
                    raw=self.raw(text + ('\n' + nonce + str(code) + '\n' if marker else ''), 'command.log'))

    def test_exact_reviewed_plan(self):
        self.assertEqual(artifacts.validate_plan(self.plan, {'cases': [None] * 33}), self.plan)

    def test_real_source_plural_allow_text_does_not_depend_on_dynamic_widget_id(self):
        plan = copy.deepcopy(self.plan)
        artifacts.validate_plan(plan, {'cases': [None]*33})
        plan['photo_consent']['allow'] = {'identifier': 'advanced_dialog_button_1'}
        with self.assertRaises(ValueError): artifacts.validate_plan(plan, {'cases': [None]*33})

    def test_ui_plan_refuses_coordinates_wrong_owner_generic_title_and_count(self):
        changes = [lambda p: p['photo_consent'].update(allow={'x': 1, 'y': 2}),
                   lambda p: p['permissions']['query'][0].update(bundle=ROLES['query'][0]),
                   lambda p: p['permissions']['query'][0].update(title={'text': 'Allow'}),
                   lambda p: p['photo_consent'].update(title={'text': 'Allow Knowledge audit importer to save 5 images?'}),
                   lambda p: p.update(source_evidence=[]),
                   lambda p: p['photo_consent'].update(allow={'identifier': 'arbitrary_button'}),
                   lambda p: p['permissions'].update(curator=[])]
        for change in changes:
            candidate = copy.deepcopy(self.plan); change(candidate)
            with self.subTest(change=changes.index(change)), self.assertRaises(ValueError):
                artifacts.validate_plan(candidate, {'cases': [None] * 33})

    def test_plan_source_hash_is_rechecked(self):
        self.source.write_text('changed')
        with self.assertRaises(ValueError): artifacts.validate_plan(self.plan, {'cases': [None] * 33})

    def test_profile_preserves_only_legitimate_exact_roles(self):
        base = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
        for role in ('query', 'curator'):
            bundle, apl, permissions, _ = ROLES[role]
            value = suite.profile(copy.deepcopy(base), role, 'a' * 64,
                                  {'app': {'bundleName': bundle}, 'module': {'requestPermissions': [{'name': p} for p in permissions]}})
            self.assertEqual(value['bundle-info'], {'bundle-name': bundle, 'apl': apl, 'app-feature': 'hos_system_app'})
            self.assertEqual(value['acls']['allowed-acls'], [])
            self.assertEqual(value['permissions']['restricted-permissions'], [])
            self.assertEqual(value['debug-info']['device-ids'], ['a' * 64])

    def test_profile_rejects_extra_permission_bundle_or_stale_udid(self):
        for role, bundle, permissions, udid in [('query', ROLES['query'][0], [READ, WRITE], 'a' * 64),
                ('curator', ROLES['query'][0], [READ, WRITE], 'a' * 64), ('query', ROLES['query'][0], [READ], 'stale'),
                ('importer', ROLES['importer'][0], [], 'a' * 64)]:
            with self.subTest(role=role, permissions=permissions), self.assertRaises(ValueError):
                suite.profile({}, role, udid, {'app': {'bundleName': bundle}, 'module': {'requestPermissions': [{'name': p} for p in permissions]}})

    def bms(self, role):
        bundle, apl, _, _ = ROLES[role]
        return {'applicationInfo': {'name': bundle, 'uid': 20010001, 'accessTokenId': 123,
            'isSystemApp': apl != 'normal', 'appPrivilegeLevel': apl}, 'hapPath': '/data/app/el1/bundle/public/' + bundle + '/entry.hap'}

    def test_actual_bms_distinguishes_normal_and_system_roles(self):
        for role in ROLES:
            value = self.bms(role)
            result = suite.bms_identity(ROLES[role][0] + ':\n' + json.dumps(value), role)
            self.assertEqual((result['uid'], result['token_id']), (20010001, 123))

    def test_native_identity_joins_actual_at_tuple_to_stable_raw_bms(self):
        bundle = ROLES['importer'][0]; boot = 'host-only-boot'; run = 'd' * 32
        token = dict(schema_version=2, api='AccessTokenKit::VerifyAccessToken', run_id=run, boot_id=boot,
            bundle=bundle, token_id=123, identity_schema='hap-bms-access-token/v1', expected_uid=20010001,
            at_reported_uid=0, at_query_rc=0, at_token_id=123, at_user_id=100, at_inst_index=0, at_bundle=bundle)
        def collector(value, *, changed_after=False):
            c = object.__new__(suite.Collector); c.data = {'run_id': run}; c.env = {'boot_id': boot}; c.remote = '/owned'
            c.identities = {'importer': suite.bms_identity(json.dumps(self.bms('importer')), 'importer')}
            c.roles = {'importer': {}}; c.persist = lambda: None; scripts = []
            after = self.bms('importer')
            if changed_after: after['applicationInfo']['accessTokenId'] = 124
            values = [json.dumps(self.bms('importer')), json.dumps(value), json.dumps(after)]
            def observe(script, label):
                scripts.append(script); return self.raw(values.pop(0), label + '.json')
            c.observe = observe
            return c, scripts
        c, scripts = collector(token); c.token('importer', 'initial')
        self.assertEqual(len(scripts), 3)
        self.assertEqual(scripts[1], 'unset LD_LIBRARY_PATH LD_PRELOAD; /owned/observer ' + run + ' 20010001 ' + bundle)
        self.assertEqual(set(c.roles['importer']['token_bms_initial']), {'before', 'after'})
        for mutation in ({'at_token_id': 124}, {'expected_uid': 1}, {'at_bundle': 'foreign'}, {'uid': 20010001}, {'schema_version': 1}):
            c, _ = collector(dict(token, **mutation))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): c.token('importer', 'initial')
        c, _ = collector(token, changed_after=True)
        with self.assertRaises(ValueError): c.token('importer', 'initial')

    def test_bms_rejects_wrong_identity_uid_token_or_ambiguous_hap(self):
        changes = [lambda v: v['applicationInfo'].update(uid=10001), lambda v: v['applicationInfo'].update(uid=True),
                   lambda v: v['applicationInfo'].update(isSystemApp=True), lambda v: v['applicationInfo'].update(appPrivilegeLevel='system_basic'),
                   lambda v: v['applicationInfo'].update(accessTokenId=0), lambda v: v.update(other={'hapPath': '/data/app/other.hap'})]
        for change in changes:
            value = self.bms('importer'); change(value)
            with self.subTest(change=changes.index(change)), self.assertRaises(ValueError): suite.bms_identity(json.dumps(value), 'importer')

    def test_guest_command_requires_transport_boot_target_and_actual_remote_exit(self):
        row = self.command()
        suite.verify_commands([row], '/hdc', '127.0.0.1:47001')
        with self.assertRaises(ValueError): suite.verify_commands([row], '/hdc', '127.0.0.1:47002')
        for bad in [self.command(code=1), self.command(marker=False), dict(row, timed_out=True), dict(row, exit_code=1)]:
            with self.subTest(bad=bad), self.assertRaises(ValueError): suite.verify_commands([bad], '/hdc', '127.0.0.1:47001')

    def test_forbidden_grants_sql_or_power_never_count_as_real_transport(self):
        for script in ['pm grant app permission', 'bm grant app permission', 'sqlite3 /data/media.db', 'power-shell timeout -r', 'system_powerdown']:
            with self.subTest(script=script), self.assertRaises(ValueError):
                suite.verify_commands([self.command(script)], '/hdc', '127.0.0.1:47001')

    def test_normalization_cannot_change_original_guest_output(self):
        row = self.command('cat exact-file', 'raw bytes')
        self.assertEqual(suite.exact_script(row, 'cat exact-file'), 'raw bytes')
        with self.assertRaises(ValueError): suite.exact_script(row, 'cat another-file')
        row['raw']['sha256'] = '0' * 64
        with self.assertRaises(ValueError): suite.shell_body(row)

    def test_only_documented_layout_transition_can_be_tolerated(self):
        path = '/data/local/tmp/qemu-capability-ui-' + 'b'*32 + '-1.json'
        row = self.command('test ! -e ' + path + ' && uitest dumpLayout -p ' + path,
                           'DumpLayout failed:Get window nodes failed', code=1)
        row['layout_transition'] = True
        suite.verify_commands([row], '/hdc', '127.0.0.1:47001')
        row = self.command('cat permission-error', 'DumpLayout failed:Get window nodes failed', code=1)
        row['layout_transition'] = True
        with self.assertRaises(ValueError): suite.verify_commands([row], '/hdc', '127.0.0.1:47001')

    def test_photos_host_requires_real_source_grammar_provider_record(self):
        raw = ('    uri [/com.ohos.photos/phone/SaveUIExtensionAbility]\n'
               '      bundle name [com.ohos.photos]\n      ability type [UIEXTENSION]\n'
               '      root host bundle name [' + ROLES['importer'][0] + ']\n'
               '      AbilityRecord ID #42  state #FOREGROUND\n')
        suite.photos_connection(raw)
        for bad in [raw + raw, raw.replace('UIEXTENSION', 'PAGE'), raw.replace('FOREGROUND', 'BACKGROUND'),
                    raw.replace(ROLES['importer'][0], ROLES['denied'][0]), 'PID 123 com.ohos.photos']:
            with self.subTest(bad=bad), self.assertRaises(ValueError): suite.photos_connection(bad)

    def test_not_ready_can_retry_disabled_but_never_ambiguous_nodes(self):
        attrs = {'id': 'knowledge_run', 'bundleName': ROLES['query'][0], 'visible': 'true', 'enabled': 'false',
                 'clickable': 'true', 'bounds': '[0,0][20,20]'}
        node = {'attributes': attrs, 'children': []}
        with self.assertRaises(NodeNotReady): suite.ready_node(node, ROLES['query'][0], identifier='knowledge_run', clickable=True)
        attrs['enabled'] = 'true'
        with self.assertRaises(ValueError): suite.ready_node([node, node], ROLES['query'][0], identifier='knowledge_run', clickable=True)

    def test_nested_allow_text_selects_actual_dynamic_button_in_titled_dialog(self):
        from photos_dialog_contract import select_dialog
        bundle = ROLES['importer'][0]
        def text(value):
            return {'attributes': {'type': 'Text', 'text': value, 'visible': 'true', 'enabled': 'true', 'clickable': 'false',
                                   'bounds': '[0,0][20,20]'}, 'children': []}
        def button(identifier, value):
            return {'attributes': {'type': 'Button', 'id': identifier, 'visible': 'true', 'enabled': 'true', 'clickable': 'true',
                                   'bounds': '[0,0][20,20]'}, 'children': [text(value)]}
        allow = button('advanced_dialog_button_42', '允许')
        tree = {'attributes': {'type': 'Column', 'bundleName': bundle, 'visible': 'true', 'bounds': '[0,0][100,100]'},
                'children': [text('允许“Knowledge audit importer”保存 33 张图片？'), allow, button('advanced_dialog_button_43', '禁止')]}
        node, contract = select_dialog(tree, bundle, 'save', label='Knowledge audit importer', count=33)
        self.assertEqual(node['attributes'], allow['attributes'])
        self.assertEqual(contract['allow'], '允许')
        tree['children'][-1] = button('advanced_dialog_button_43', 'Allows unrelated operation')
        with self.assertRaises(NodeNotReady): select_dialog(tree, bundle, 'save', label='Knowledge audit importer', count=33)

    def test_bms_absence_is_not_empty_or_transport_failure(self):
        suite.assert_bundles_absent('bundle name [com.ohos.settings]', [ROLES['query'][0]])
        for text in ['', '[Fail]', 'bundle name [com.ohos.settings]\n' + ROLES['query'][0]]:
            with self.subTest(text=text), self.assertRaises(ValueError): suite.assert_bundles_absent(text, [ROLES['query'][0]])

    def test_ams_absence_requires_actual_live_system_records(self):
        raw = '  AppRunningRecords:\n    AppRunningRecord ID #0\n      process name [com.ohos.sceneboard]\n'
        suite.assert_ams_absent(raw, [ROLES['importer'][0]])
        for invalid in ['', 'error: dump failed', raw + 'root host bundle name [' + ROLES['importer'][0] + ']']:
            with self.subTest(raw=invalid), self.assertRaises(ValueError): suite.assert_ams_absent(invalid, [ROLES['importer'][0]])

    def cleanup(self, active=0, trash=0):
        request = {'operation_id': 'a'*32}
        request_path = self.root / 'request.json'; request_path.write_text(json.dumps(request))
        row = lambda event, value: {'operation_id': 'a'*32, 'event': event, 'value_json': json.dumps(value)}
        rows = [row('begin', {}), row('asset', {'case_id': 'd20260101', 'count': active, 'requested_uri': 'file://media/Photo/1/a.jpg'}),
                row('trash_album', {'count': 1}), row('trash_asset', {'case_id': 'd20260101', 'count': trash, 'uri': 'file://media/Photo/1/a.jpg'}), row('complete', {})]
        journal = self.raw(''.join(json.dumps(v)+'\n' for v in rows), 'cleanup.jsonl')
        return {'request': record(request_path), 'journal': journal}, {'cases': [{'case_id': 'd20260101'}]}, {'d20260101': 'file://media/Photo/1/a.jpg'}

    def test_cleanup_requires_real_active_and_trash_absence(self):
        result = suite.cleanup_observation(*self.cleanup())
        self.assertTrue(result['owned_assets_absent'])
        for active, trash in [(1, 0), (0, 1), (True, 0), (0, False)]:
            with self.subTest(active=active, trash=trash), self.assertRaises(ValueError): suite.cleanup_observation(*self.cleanup(active, trash))

    def test_helper_cannot_be_missing_or_self_reported_pass(self):
        path = self.root / 'build.json'; path.write_text(json.dumps({'status': 'pass', 'helpers': {}}))
        with self.assertRaises((ValueError, KeyError)):
            artifacts.helper_binding({'build': record(path), 'output_directory': str(self.root)})

    def test_summary_cannot_replace_independent_raw_verification(self):
        evidence = self.root / 'evidence.json'; evidence.write_text(json.dumps({'status': 'pass', 'all_phases_verified': True}))
        archive = self.root / 'archive.tar.gz'; archive.write_bytes(b'synthetic-host-only')
        boot = self.root / 'boot.json'; boot.write_text('{}')
        with self.assertRaises(ValueError): suite.verify_evidence(evidence, archive, boot)

    def test_real_phase_method_launches_before_staging_and_waits_for_actual_operation(self):
        collector = suite.Collector.__new__(suite.Collector)
        collector.args = SimpleNamespace(output=self.root)
        collector.env = {'boot_id': '11111111-1111-1111-1111-111111111111'}
        collector.value = {'artifacts_data': {'challenge': record(self.source)}, 'phases': [], 'ui_plan_data': self.plan}
        collector.identities = {'query': {'uid': 20010001}}
        collector.roles = {'query': {}}; collector.curator_pid = None
        collector.data = {'run_id': 'b'*32}; collector.uris = {}
        calls = []; request = {'schema_version': 1, 'role': 'query', 'phase': 'system-denied', 'action': 'access',
                              'operation_id': 'a'*32, 'items': []}
        collector.identity = lambda label: self.raw(collector.env['boot_id'], label)
        collector.persist = lambda: None
        collector.shell = lambda script, label: calls.append(('launch', script))
        collector.wait_control = lambda *args, **kwargs: calls.append(('ready', args))
        def stage(raw, remote, uid, **options):
            self.assertEqual(json.loads(suite.checked(raw).read_text()), request)
            self.assertEqual(uid, 20010001); self.assertEqual(options, {'replace': True})
            self.assertTrue(remote.endswith('/knowledge-request.json')); calls.append(('stage', remote))
        collector.stage = stage
        collector.click = lambda *args, **kwargs: calls.append(('click', args))
        collector.journal = lambda role, name: self.raw(json.dumps({'operation_id': 'a'*32, 'event': 'complete'})+'\n', 'phase-result.jsonl')
        with mock.patch.object(suite.runtime, 'prepare_request', return_value=request):
            phase = collector.phase('system-denied')
        self.assertEqual([call[0] for call in calls], ['launch', 'ready', 'stage', 'click'])
        self.assertTrue(phase['complete'])
        self.assertEqual(collector.roles['query']['journal'], phase['journal'])

    def test_retained_curator_pid_changes_fail(self):
        collector = suite.Collector.__new__(suite.Collector)
        collector.curator_pid = None
        collector.observe = lambda *args: self.raw('123', 'pid.txt')
        collector.pid(); collector.pid()
        collector.observe = lambda *args: self.raw('124', 'pid.txt')
        with self.assertRaises(ValueError): collector.pid()

    def test_ui_click_binds_original_dump_screenshot_and_click_coordinates(self):
        from PIL import Image
        nonce = 'a'*32; target = '127.0.0.1:47001'; prefix = '/data/local/tmp/qemu-capability-ui-' + nonce
        node = {'attributes': {'id': 'advanced_dialog_button_19', 'text': '允许', 'bundleName': ROLES['importer'][0],
                'visible': 'true', 'enabled': 'true', 'clickable': 'true', 'bounds': '[0,0][20,20]'}, 'children': []}
        layout = self.root / 'layout.json'; layout.write_text(json.dumps(node))
        picture = self.root / 'screen.png'; Image.new('RGB', (100, 100)).save(picture)
        def command(script, text=''):
            row = self.command(script, text)
            raw = self.root / ('raw-' + str(len(commands)) + '.log'); raw.write_bytes(suite.checked(row['raw']).read_bytes())
            row['raw'] = record(raw); commands.append(row)
        commands = []
        command('test ! -e ' + prefix + '-1.json && uitest dumpLayout -p ' + prefix + '-1.json')
        command('cat ' + prefix + '-1.json', json.dumps(node))
        command('test ! -e ' + prefix + '-2.png && uitest screenCap -p ' + prefix + '-2.png')
        commands.append(dict(argv=['/hdc', '-t', target, 'file', 'recv', prefix+'-2.png', str(picture)], exit_code=0, timed_out=False,
                             raw=self.raw('FileTransfer finish', 'transfer.log')))
        command('uitest uiInput click 10 10')
        row = dict(kind='run', layout=record(layout), selector={'text': '允许'}, title=None, bundle=ROLES['importer'][0],
                   selected_node=suite.select_node(node, ROLES['importer'][0], text='允许', clickable=True),
                   layout_command=1, screenshot_command=3, command=4, screenshot=record(picture),
                   screenshot_guest_hash=self.raw(suite.sha(picture)+'  '+prefix+'-2.png', 'screen-sha.txt'))
        observed = lambda raw, script: suite.checked(raw).read_text()
        suite.verify_click(row, commands, '/hdc', target, observed)
        # The dynamic id was accepted via actual Allow text; modified transport
        # dump or screenshot bytes cannot be replaced with a normalized claim.
        changed = copy.deepcopy(node); changed['attributes']['id'] = 'forged'
        layout.write_text(json.dumps(changed)); row['layout'] = record(layout)
        with self.assertRaises(ValueError): suite.verify_click(row, commands, '/hdc', target, observed)

    def test_cleanup_failure_cannot_certify_safe_vm_reuse(self):
        collector = suite.Collector.__new__(suite.Collector)
        collector.value = {'cleanup_errors': [], 'commands': []}
        collector.installed = [ROLES['importer'][0]]; collector.remote = '/data/local/tmp/knowledge-'+'a'*32
        collector.remote_created = False; collector.ui = SimpleNamespace(challenge='b'*32)
        collector.args = SimpleNamespace(hdc=Path('/hdc'))
        collector.guest = SimpleNamespace(report={'commands': []}, close=mock.Mock())
        collector.guest.target = '127.0.0.1:47001'
        collector.emergency_cleanup = lambda: {'owned_assets_absent': True}
        collector.persist = lambda: None
        def command(*args): raise ValueError('actual uninstall failed')
        collector.command = command
        def observe(script, label):
            if script == 'bm dump -a': raw = 'bundle name [com.ohos.settings]'
            else: raw = '  AppRunningRecords:\n      process name [com.ohos.sceneboard]\n'
            return self.raw(raw, label)
        collector.observe = observe
        collector.identity = lambda *args: self.raw('boot', 'final-boot')
        collector.cleanup()
        self.assertFalse(collector.value['cleanup_complete'])
        self.assertTrue(any('uninstall' in error for error in collector.value['cleanup_errors']))
        collector.guest.close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
