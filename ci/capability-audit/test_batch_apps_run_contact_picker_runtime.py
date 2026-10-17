#!/usr/bin/env python3
"""Host orchestration/actual-ETS checks. These are not QEMU runtime evidence."""
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from test_batch_apps_contact_picker_runtime import ams_fixture, provider_fixture

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location('driver', HERE / 'batch_apps_run_contact_picker_runtime.py')
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def node(bundle, identifier, text='', y=0, clickable=True, children=None):
    return {'attributes': {'bundleName': bundle, 'id': identifier, 'text': text,
            'visible': 'true', 'enabled': 'true', 'clickable': str(clickable).lower(),
            'bounds': '[0,' + str(y) + '][200,' + str(y + 30) + ']'}, 'children': children or []}


class ModelGuest:
    """Explicit host model at guest transport boundary, never a runtime receipt."""
    def __init__(self, root, records):
        self.env = {'boot_id': 'host-model-not-boot'}
        self.root, self.records = root, records
        self.rows, self.commands = [], []
        self.case, self.launch = '', ''
        self.provider, self.caller = False, False
        self.pid = 100
        self.generation = 0
        self.count = 0
        self.pending = []
        self.result_ids = []
        self.clicks = []

    def terminal(self, invocation, raw=None, error=None):
        case = driver.verifier.MATRIX[self.case]
        slot = invocation.rsplit('/', 1)[1]
        callback = 'callback' in case['api'] and (self.case != 'dual-session' or slot == 'b')
        row = {'schema_version': 1, 'run_id': 'host_model', 'launch_id': self.launch, 'case_id': self.case,
               'invocation_id': invocation, 'event': 'callback' if callback else 'resolve',
               'timestamp_ms': 200, 'callback_count': 1 if callback else 0,
               'error_type': 'undefined', 'value_type': 'object', 'raw_json': json.dumps(raw or [])}
        if error:
            row.update(event=case['error_kind'] if case['error_kind'] != 'reject-or-throw' else 'reject',
                       error_type='object', error_code=error, raw_json='undefined')
        self.rows.append(row)

    def begin(self):
        self.generation += 1
        case = driver.verifier.MATRIX[self.case]
        for slot in case['slots']:
            invocation = self.launch + '/' + slot
            self.rows.append({'schema_version': 1, 'run_id': 'host_model', 'launch_id': self.launch,
                'case_id': self.case, 'invocation_id': invocation, 'event': 'begin', 'timestamp_ms': 100, 'callback_count': 0})
        if case['ui'] in ('none', 'provider-launch'):
            self.terminal(self.launch + '/a', error=case['error_code'])
            return
        self.provider = True
        if self.case == 'dual-session':
            self.pending = [(2, self.launch + '/b'), (1, self.launch + '/a')]
            self.count = 2
        else:
            offsets = case.get('selected_offsets', [[]])
            self.result_ids = list(range(205)) if offsets == 'first205' else (list(offsets[0]) if offsets else [])
            self.count = len(self.result_ids)

    def shell(self, script, label):
        self.commands.append(script)
        argv = shlex.split(script)
        if argv[:2] == ['aa', 'start']:
            bundle = argv[argv.index('-b') + 1]
            if bundle == driver.CALLER:
                values = {argv[i + 1]: argv[i + 2] for i, value in enumerate(argv) if value == '--ps'}
                self.case, self.launch = values['caseId'], values['launchId']
                if not self.caller: self.pid += 1
                self.caller = True
            return 'start ability successfully'
        if argv[:2] == ['aa', 'force-stop']:
            if argv[-1] == driver.CALLER: self.caller, self.provider = False, False
            return 'force stop process successfully'
        if 'contact-picker-' in script:
            return ''.join(json.dumps(row) + '\n' for row in self.rows)
        if argv[:2] == ['/observer', 'processes']:
            return json.dumps({'api': 'AppMgrClient::GetAllRunningProcesses', 'error_code': 0,
                'processes': [{'pid': self.pid, 'bundleNames': [driver.CALLER]}] if self.caller else []})
        if script == 'aa dump -a -u 100':
            sessions = ([self.generation * 10 + (2 if inv.endswith('/b') else 1) for _, inv in self.pending]
                        if self.provider and self.pending else [self.generation * 10 + 1] if self.provider else [])
            return ams_fixture(sessions, self.pid)
        if script == 'hilog -x':
            return driver.PROVIDER + ' ' + driver.verifier.CONTRACT['provider_ability'] + ' ' + self.case + '\n'
        return ''


class ModelUi:
    def __init__(self, root, guest):
        self.root, self.guest, self.sequence = root, guest, 0
        self.targets = {}
        self.host_owned = False

    def layout(self, label):
        self.sequence += 1
        g = self.guest
        if not g.provider:
            layout = node(driver.CALLER, 'root', children=[
                node(driver.CALLER, 'contact_case_status', 'Ready: ' + g.launch, 0, False),
                node(driver.CALLER, 'contact_case_start', 'Start case', 40)])
        else:
            children = [node(driver.PROVIDER, 'selectedText', 'Selected ' + str(g.count) + '/205', 0, False),
                        node(driver.PROVIDER, 'doneButton', 'Done', 40),
                        node(driver.PROVIDER, 'close_click_btn', 'Cancel', 80),
                        node(driver.PROVIDER, 'all_select_message', 'Select all', 120)]
            children += [node(driver.PROVIDER, 'row-' + str(i), '', 160 + i * 40, children=[
                node(driver.PROVIDER, 'name', r['name']['fullName'], 160 + i * 40, False)])
                for i, r in enumerate(g.records[:5])]
            layout = node(driver.PROVIDER, 'root', clickable=False, children=children)
            if self.host_owned:
                for index, child in enumerate(children):
                    for nested in driver.verifier.objects(child):
                        attrs = nested.get('attributes')
                        if isinstance(attrs, dict):
                            attrs.pop('bundleName', None)
                            attrs.update(hostWindowId='42', accessibilityId=str(100000000100 + index))
                session = g.generation * 10 + (2 if g.pending and g.pending[0][1].endswith('/b') else 1)
                extension = node(driver.CALLER, '', clickable=False, children=children)
                extension['attributes'].update(type='UIExtensionComponent', hostWindowId='42', accessibilityId=str(session))
                layout = node(driver.CALLER, 'root', clickable=False, children=[extension])
        self.targets = {}
        for current, bundle, ancestors in driver.walk(layout):
            attrs = current['attributes']
            if attrs['clickable'] == 'true':
                x, y, w, h = driver.bounds(attrs['bounds'])
                self.targets[(x + w // 2, y + h // 2)] = attrs['id']
        path = self.root / ('model-layout-' + str(self.sequence) + '.json')
        path.write_text(json.dumps(layout))
        return layout, path

    def screenshot(self, label):
        self.sequence += 1
        path = self.root / ('model-screen-' + str(self.sequence) + '.png')
        path.write_bytes(b'\x89PNG\r\n\x1a\nHOST_MODEL_NOT_RUNTIME')
        return path

    def shell(self, script, label):
        words = shlex.split(script)
        if words[:3] == ['uitest', 'uiInput', 'click']:
            identifier = self.targets[tuple(map(int, words[3:5]))]
            g = self.guest
            g.clicks.append(identifier)
            if identifier == 'contact_case_start': g.begin()
            elif identifier == 'all_select_message': g.count = 0 if g.count else 205
            elif identifier.startswith('row-'):
                offset = int(identifier[4:])
                if offset in g.result_ids: g.result_ids.remove(offset)
                else: g.result_ids.append(offset)
                g.count = len(g.result_ids)
            elif identifier in ('doneButton', 'close_click_btn'):
                if g.pending:
                    _, invocation = g.pending.pop(0)
                    selected = [0] if invocation.endswith('/a') else [1, 2]
                    g.terminal(invocation, [g.records[i] for i in selected])
                    if g.pending: g.count = g.pending[0][0]
                    else: g.provider = False
                else:
                    selected = (driver.verifier.MATRIX[g.case].get('selected_offsets') or [[]])
                    selected = list(range(205)) if selected == 'first205' else selected[0]
                    g.terminal(g.launch + '/a', [g.records[i] for i in selected])
                    g.provider = False
            return ''
        raise AssertionError('unexpected UI model command ' + script)


class RuntimeDriver(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='contacts-driver-host-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.records = [{'id': 1000 + i, 'key': 'k' + str(i), 'name': {'fullName': 'QCP_host_model_' + str(i).zfill(3)},
                         'phoneNumbers': [{'phoneNumber': '+1555' + str(i).zfill(7)}]} for i in range(205)]
        self.guest = ModelGuest(self.root, self.records)
        self.ui = ModelUi(self.root, self.guest)
        self.driver = driver.Driver(self.guest, self.ui, self.root, 'host_model', '/observer', sleep=lambda _: None)
        self.driver.caller_uid = 20000100
        bms = self.root / 'provider-bms.log'
        bms.write_text(driver.PROVIDER + ':\n' + json.dumps(provider_fixture()))
        self.driver.provider_bms = driver.descriptor(bms)
        self.seed = {'contacts': self.records}

    def test_seed_project_only_two_user_permissions_and_real_startup_resources(self):
        project = self.root / 'project'
        manifest = driver.prepare_seed(project)
        module = json.loads((project / 'entry/src/main/module.json5').read_text())['module']
        self.assertEqual([p['name'] for p in module['requestPermissions']], driver.PERMISSIONS)
        self.assertEqual(module['deviceTypes'], ['default', 'tablet', '2in1'])
        self.assertEqual(module['abilities'][0]['startWindowIcon'], '$media:app_icon')
        self.assertEqual(module['abilities'][0]['startWindowBackground'], '$color:start_window_background')
        self.assertNotIn('extensionAbilities', module)
        self.assertEqual(manifest['apl_required_at_signing'], 'system_basic')
        self.assertTrue(manifest['system_app_required_at_install'])
        self.assertFalse(manifest['runtime_acceptance'])
        with self.assertRaises(driver.verifier.EvidenceError): driver.prepare_seed(project)
        self.assertEqual(set(manifest['source_hashes']), {str(p.relative_to(project)) for p in project.rglob('*')
                                                        if p.is_file() and p.name != 'seed-source-manifest.json'})

    def test_only_seed_can_have_system_basic_bms_identity(self):
        for bundle in (driver.CALLER, driver.SEED):
            seed = bundle == driver.SEED
            app = {'bundleName': bundle, 'isSystemApp': seed, 'appPrivilegeLevel': 'system_basic' if seed else 'normal',
                   'uid': 20010001, 'accessTokenId': 123}
            self.assertEqual(driver.application_info(json.dumps({'applicationInfo': app}), bundle)['accessTokenId'], 123)
            app.update(isSystemApp=not seed)
            with self.assertRaises(driver.verifier.EvidenceError): driver.application_info(json.dumps({'applicationInfo': app}), bundle)

    def test_caller_and_seed_still_require_account100(self):
        for bundle in (driver.CALLER, driver.SEED):
            seed = bundle == driver.SEED
            for uid in (10004, 10040, 20210040, True):
                app = {'bundleName': bundle, 'isSystemApp': seed,
                       'appPrivilegeLevel': 'system_basic' if seed else 'normal', 'uid': uid, 'accessTokenId': 123}
                with self.subTest(bundle=bundle, uid=uid), self.assertRaises(driver.verifier.EvidenceError):
                    driver.application_info(json.dumps({'applicationInfo': app}), bundle)

    def test_failure_tree_error_still_collects_png_without_changing_failure(self):
        calls = []
        proof = self.root / 'failure-observation'; proof.write_text('host observation only')
        self.driver.raw = lambda script, stem: (self.guest.env['boot_id'], driver.descriptor(proof))
        self.driver.layout = lambda stem: (_ for _ in ()).throw(driver.LayoutNotReady('no window nodes'))
        self.driver.screen = lambda stem: (calls.append(stem) or driver.descriptor(proof))
        result = self.driver.failure_diagnostics('host-failure')
        self.assertTrue(result['same_boot_verified'])
        self.assertIn('screenshot', result)
        self.assertNotIn('layout', result)
        self.assertEqual(['layout'], [row['observation'] for row in result['errors']])
        self.assertEqual(['host-failure-pixels'], calls)
        self.assertNotIn('passed', result)

    def test_failure_capture_other_boot_does_not_read_ui(self):
        self.driver.raw = lambda script, stem: ('different-boot', {})
        self.driver.screen = lambda stem: self.fail('must not observe a replacement boot')
        self.driver.layout = lambda stem: self.fail('must not observe a replacement boot')
        result = self.driver.failure_diagnostics('host-failure')
        self.assertEqual(['boot_before'], [row['observation'] for row in result['errors']])
        self.assertNotIn('same_boot_verified', result)

    def test_real_ui_flow_205_clears_and_selects_all_before_done(self):
        self.driver.case('options-promise-205', self.seed)
        self.assertEqual(self.guest.clicks, ['contact_case_start', 'all_select_message', 'all_select_message', 'doneButton'])
        done = next(r for r in self.driver.evidence['events'] if r['kind'] == 'done')
        before = Path(done['journal_before']['path']).read_text()
        self.assertIn('begin', before)
        self.assertNotIn('resolve', before)
        self.assertEqual(len(json.loads(self.guest.rows[-1]['raw_json'])), 205)

    def test_cancel_modifies_actual_selection_but_keeps_original_defaults(self):
        self.driver.case('cancel-default', self.seed)
        self.assertEqual(self.guest.clicks, ['contact_case_start', 'row-0', 'row-3', 'close_click_btn'])
        changes = [(r['kind'], r['contact_id']) for r in self.driver.evidence['events'] if r['kind'] in ('select', 'unselect')]
        self.assertEqual(changes, [('unselect', 1000), ('select', 1003)])
        self.assertEqual([r['id'] for r in json.loads(self.guest.rows[-1]['raw_json'])], [1000, 1001, 1002])

    def test_dual_session_uses_actual_count_and_records_absence_after_both_close(self):
        self.driver.case('dual-session', self.seed)
        events = self.driver.evidence['events']
        done = [r for r in events if r['kind'] == 'done']
        self.assertTrue(done[0]['invocation_id'].endswith('/b'))
        self.assertTrue(done[1]['invocation_id'].endswith('/a'))
        second_before = Path(done[1]['journal_before']['path']).read_text()
        self.assertIn('callback', second_before)
        self.assertNotIn('resolve', second_before)
        absent = [r for r in events if r['kind'] == 'picker_absent']
        self.assertEqual(len(absent), 2)
        self.assertEqual(absent[0]['layout'], absent[1]['layout'])
        begins = [i for i, row in enumerate(self.guest.rows) if row['event'] == 'begin']
        self.assertLess(max(begins), next(i for i, row in enumerate(self.guest.rows) if row['event'] == 'callback'))

    def test_force_stop_and_reopen_are_measured_by_actual_observer_outputs(self):
        self.driver.case('exit-pending', self.seed)
        self.driver.case('reopen', self.seed)
        driver.verifier.verify_process_restart(self.driver.evidence)
        self.assertEqual(len([r for r in self.guest.rows if r['case_id'] == 'exit-pending' and r['event'] in driver.verifier.TERMINAL]), 0)
        self.assertIn('aa force-stop ' + driver.CALLER, self.guest.commands)

    def test_all_six_overloads_and_early_rejections_get_real_start_inputs(self):
        cases = ['select-promise', 'select-callback', 'options-promise-205', 'options-callback-205',
                 'legacy-promise', 'legacy-callback', 'invalid-limit-promise', 'invalid-limit-callback', 'query-no-read']
        for case in cases: self.driver.case(case, self.seed)
        self.assertEqual(self.guest.clicks.count('contact_case_start'), len(cases))
        self.assertEqual(self.guest.clicks.count('doneButton'), 6)

    def test_host_owned_driver_uses_bound_remote_tree_for_six_overloads_cancel_and_dual(self):
        self.ui.host_owned = True
        for case in ['select-promise', 'select-callback', 'options-promise-205', 'options-callback-205',
                     'legacy-promise', 'legacy-callback', 'cancel-default', 'dual-session']:
            self.driver.case(case, self.seed)
        actions = [row for row in self.driver.evidence['events'] if row['kind'] in ('done', 'cancel')]
        self.assertEqual(len(actions), 9)
        for action in actions:
            binding = driver.verifier.closed_session(action, self.driver.provider_bms, 20000100)
            self.assertEqual(binding['host_pid'], self.guest.pid)
            view = driver.verifier.picker_view(json.loads(Path(action['layout']['path']).read_text()))
            self.assertTrue(view['host_owned'])
            after = json.loads(Path(action['layout_after']['path']).read_text())
            self.assertFalse(any(row.get('type') == 'UIExtensionComponent' and row.get('accessibilityId') == view['extension_id']
                                 for row in driver.verifier.objects(after)))

    def test_list_root_scoping_preserves_provider_inherited_owner(self):
        roots = [node(driver.PROVIDER, 'root', children=[node(driver.PROVIDER, 'selectedText', 'Selected 0/205'),
                                                      node(driver.PROVIDER, 'doneButton')])]
        self.assertEqual(driver.selected_count(roots), 0)

    def test_ambiguous_duplicate_names_and_malformed_counts_fail(self):
        layout = node(driver.PROVIDER, 'root', children=[node(driver.PROVIDER, 'row', children=[
            node(driver.PROVIDER, 'name', 'duplicate', clickable=False), node(driver.PROVIDER, 'name', 'duplicate', clickable=False)])])
        with self.assertRaises(driver.verifier.EvidenceError): driver.clickable_for_text(layout, driver.PROVIDER, 'duplicate')
        for text in ['Selected 205', 'Selected 206/205', 'Selected 1/2 and 3/4']:
            with self.assertRaises(driver.verifier.EvidenceError):
                driver.selected_count(node(driver.PROVIDER, 'selectedText', text))
        self.assertEqual(driver.selected_count(node(driver.PROVIDER, 'root', children=[node(driver.PROVIDER, 'selectedText', 'Selected 0/205'), node(driver.PROVIDER, 'doneButton')])), 0)

    def test_completion_before_real_input_fails_without_clicking_done(self):
        self.driver.caller_ready('select-promise', 'early', self.seed)
        self.guest.terminal('early/a', [self.records[0]])
        with self.assertRaisesRegex(driver.verifier.EvidenceError, 'immediately before'):
            self.driver.terminal_input('early/a', 'done')
        self.assertNotIn('doneButton', self.guest.clicks)

    def test_cleanup_runs_after_case_failure_and_retains_cleanup_failure(self):
        outer = self
        class FaultDriver(driver.Driver):
            def permissions(self, *args): return {'READ_CONTACTS': -1 if 'before' in args[-1] else 0,
                                                  'WRITE_CONTACTS': -1 if 'before' in args[-1] else 0}, {}
            def seed_operation(self, mode):
                self.evidence['seed_user_permission_inputs'] = [{}]
                if mode == 'cleanup':
                    outer.cleaned = True
                    raise ValueError('actual deletion failed')
                return outer.seed
            def case(self, case, seed):
                outer.attempted.append(case)
                if case == 'first': raise ValueError('picker result failed')
        self.cleaned, self.attempted = False, []
        subject = FaultDriver(self.guest, self.ui, self.root, 'host_model', '/observer')
        errors = subject.execute(123, ['first', 'second'])
        self.assertTrue(self.cleaned)
        self.assertEqual(self.attempted, ['first', 'second'])
        self.assertTrue(any(r.get('case_id') == 'first' for r in errors))
        self.assertTrue(any(r.get('phase') == 'public-CRUD-cleanup' and 'deletion failed' in r['error'] for r in errors))
        self.assertTrue((self.root / 'ui.json').is_file())

    def test_permission_allow_uses_its_actual_clickable_button_ancestor(self):
        bundle = 'com.ohos.permissionmanager'
        layout = node(bundle, 'grant_button', y=80, children=[node(bundle, 'label', 'Allow', 90, False)])
        selected = driver.clickable_for_text(layout, bundle, 'Allow')
        self.assertEqual(selected['attributes']['id'], 'grant_button')
        self.assertEqual(selected['rect'], [0, 80, 200, 30])
        with self.assertRaises(driver.NodeNotReady): driver.clickable_for_text(layout, driver.CALLER, 'Allow')

    def test_hilog_difference_cannot_reuse_old_provider_launch(self):
        old = driver.PROVIDER + ' ' + driver.verifier.CONTRACT['provider_ability']
        self.assertEqual(driver.fresh_lines(old + '\n', old + '\nnew unrelated log\n'), 'new unrelated log\n')

    def test_actual_seed_store_public_crud_and_failure_recovery(self):
        program = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
let source=fs.readFileSync(process.argv[1]+'/SeedStore.ets','utf8').replace(/^import .*;\n/gm,'').replace(/export default /g,'').replace(/export /g,'');
source=stripTypeScriptTypes(source,{mode:'strip'})+'\nglobalThis.Store=SeedStore;globalThis.Request=SeedRequest';
const files=new Map(), db=[],calls=[];
const abilityContext={filesDir:'/haps/entry/files',getApplicationContext:()=>({filesDir:'/files'})};let next=1,grant=true,failAt=0,deleteFail=false,queryFail=false;
const ctx={console,JSON,Date,Number,Set,Error,Promise,fs:{OpenMode:{CREATE:1,READ_WRITE:2,APPEND:4},openSync:p=>({fd:p}),
writeSync:(p,s)=>files.set(p,(files.get(p)||'')+s),closeSync:()=>{}},
abilityAccessCtrl:{createAtManager:()=>({requestPermissionsFromUser:async(c,p)=>{
assert.equal(c,abilityContext);assert.deepEqual(Array.from(p),['ohos.permission.READ_CONTACTS','ohos.permission.WRITE_CONTACTS']);return{authResults:grant?[0,0]:[-1,-1]}}})},
contact:{queryContacts:async(c)=>{assert.equal(c,abilityContext);calls.push('query');if(queryFail)throw new Error('query failed');return JSON.parse(JSON.stringify(db))},
addContact:async(c,info)=>{assert.equal(c,abilityContext);calls.push('add');if(failAt&&next===failAt)throw new Error('add failed');const id=next++;
db.push({...JSON.parse(JSON.stringify(info)),id,key:'real-key-'+id});return id},
deleteContact:async(c,key)=>{assert.equal(c,abilityContext);calls.push('delete');if(deleteFail)throw new Error('delete failed');const i=db.findIndex(r=>r.key===key);assert.ok(i>=0);db.splice(i,1)}}};
vm.createContext(ctx);vm.runInContext(source,ctx);
let serial=0;
async function run(mode,runId='actual_store_host'){const r=new ctx.Request();r.runId=runId;r.mode=mode;r.operationId='op_'+(++serial);
const store=new ctx.Store(abilityContext,r);await store.execute();return files.get('/files/contact-seed-'+runId+'.jsonl').trim().split('\n').map(JSON.parse).filter(x=>x.operation_id===r.operationId)};
(async()=>{
let rows=await run('create');assert.equal(db.length,205);assert.equal(rows.filter(x=>x.event==='created').length,205);
assert.equal(JSON.parse(rows.find(x=>x.event==='readback').raw_json).length,205);assert.equal(rows.at(-1).event,'complete');
rows=await run('create');assert.equal(db.length,205);assert.ok(rows.some(x=>x.event==='error'));
db.push({id:99999,key:'foreign',name:{fullName:'Keep user contact'},phoneNumbers:[{phoneNumber:'1'}]});
rows=await run('cleanup');assert.equal(rows.filter(x=>x.event==='deleted').length,205);assert.equal(db.length,1);assert.equal(db[0].key,'foreign');
assert.deepEqual(JSON.parse(rows.find(x=>x.event==='readback').raw_json),[]);
failAt=next+3;rows=await run('create','partial');assert.ok(rows.some(x=>x.event==='error'));assert.equal(db.length,4);
failAt=0;rows=await run('cleanup','partial');assert.equal(rows.filter(x=>x.event==='deleted').length,3);assert.equal(db.length,1);
grant=false;const old=calls.length;rows=await run('create','denied');assert.equal(calls.length,old);assert.ok(rows.some(x=>x.event==='error'));grant=true;
rows=await run('create','delete_failure');deleteFail=true;rows=await run('cleanup','delete_failure');assert.ok(rows.some(x=>x.event==='error'));assert.ok(!rows.some(x=>x.event==='readback'));deleteFail=false;
rows=await run('cleanup','delete_failure');assert.equal(db.length,1);
queryFail=true;rows=await run('cleanup','query_failure');assert.ok(rows.some(x=>x.event==='error'));assert.ok(!rows.some(x=>x.event==='readback'));
console.log('actual SeedStore host public-API adapter scenarios passed; NOT runtime evidence');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', program, str(driver.FIX)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('NOT runtime evidence', result.stdout)


if __name__ == '__main__': unittest.main()
