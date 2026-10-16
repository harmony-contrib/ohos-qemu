#!/usr/bin/env python3
"""Host-only recorder and independent-verifier challenges; no HAP/runtime claim."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('runtime', ROOT / 'ci/capability-audit/batch_apps_contact_picker_runtime.py')
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class RuntimeVerifier(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='contacts-runtime-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = 'host_unit_only'
        self.rows = []
        self.ui = {'run_id': self.run, 'boot_session_id': 'unit-not-a-real-boot', 'events': []}
        self.records = [{'id': 1000 + i, 'key': 'key-' + str(i), 'name': {'fullName': self.run + '-seed-' + str(i)},
                         'phoneNumbers': [{'phoneNumber': '+1555000' + str(i).zfill(4)}]} for i in range(205)]
        runtime.prepare_project(self.root / 'project')
        with zipfile.ZipFile(self.root / 'caller.hap', 'w') as archive:
            archive.writestr('module.json', json.dumps({'module': {'name': 'entry', 'requestPermissions': []}}))
        (self.root / 'installed.hap').write_bytes((self.root / 'caller.hap').read_bytes())
        (self.root / 'package.img').write_bytes(b'host fixture only, not a package')
        (self.root / 'provider.hap').write_bytes(b'host fixture only, not a provider')
        (self.root / 'screen.png').write_bytes(b'\x89PNG\r\n\x1a\nHOST_TEST_FIXTURE')
        self.build = {'run_id': self.run, 'architecture': 'arm64', 'device_profile': 'phone',
                      'boot_session_id': self.ui['boot_session_id'], 'representative_package': self.desc('package.img'),
                      'booted_package_sha256': runtime.sha(self.root / 'package.img'), 'caller_hap': self.desc('caller.hap'),
                      'provider_hap': self.desc('provider.hap'),
                      'caller_fixture_hashes': {p.name: runtime.sha(p) for p in sorted(runtime.FIX.iterdir()) if p.is_file()},
                      'caller_source_manifest': self.desc('project/caller-source-manifest.json')}
        self.identity = {'run_id': self.run, 'hap_sha256': runtime.sha(self.root / 'caller.hap'),
                         'installed_caller_hap': self.desc('installed.hap'),
                         'bms_dump': self.json_artifact('bms.json', {'appInfo': {'bundleName': runtime.BUNDLE,
                             'uid': 20000100, 'accessTokenId': 12345, 'isSystemApp': False, 'appPrivilegeLevel': 'normal'}}),
                         'permission_probe': self.json_artifact('token.json', {'api': 'abilityAccessCtrl.verifyAccessTokenSync',
                             'token_id': 12345, 'READ_CONTACTS': -1, 'WRITE_CONTACTS': -1}),
                         'decoded_profile': self.json_artifact('profile.json', {'bundle-info': {'bundle-name': runtime.BUNDLE,
                             'apl': 'normal', 'app-feature': 'normal_app'}, 'acls': {'allowed-acls': []}})}
        self.identity['signature_verification'] = self.json_artifact('signature.json', {'command': ['unit-signer', 'verify-app'],
                         'exit_code': 0, 'hap_sha256': self.identity['hap_sha256'],
                         'decoded_profile_sha256': self.identity['decoded_profile']['sha256']})
        self.seed = {'run_id': self.run, 'create_api': 'contact.addContacts', 'read_api': 'contact.queryContacts',
                     'contacts': self.records,
                     'raw_create': self.json_artifact('create.json', {'run_id': self.run, 'api': 'contact.addContacts', 'ids': [r['id'] for r in self.records]}),
                     'raw_readback': self.json_artifact('seed-read.json', {'run_id': self.run, 'api': 'contact.queryContacts', 'contacts': self.records})}
        self.cleanup = {'run_id': self.run, 'delete_api': 'contact.deleteContact', 'read_api': 'contact.queryContacts',
                        'deleted_keys': [r['key'] for r in self.records], 'remaining_contacts': [],
                        'raw_delete': self.json_artifact('delete.json', {'run_id': self.run, 'api': 'contact.deleteContact', 'keys': [r['key'] for r in self.records]}),
                        'raw_readback': self.json_artifact('cleanup-read.json', {'run_id': self.run, 'api': 'contact.queryContacts', 'contacts': []})}
        self.ui['caller_processes'] = {}
        for phase, processes in [('before_exit', [{'pid': 111, 'bundleNames': [runtime.BUNDLE]}]),
                                 ('after_exit', []), ('after_reopen', [{'pid': 222, 'bundleNames': [runtime.BUNDLE]}])]:
            self.ui['caller_processes'][phase] = self.json_artifact(phase + '.json',
                {'api': 'appManager.getRunningProcessInformation', 'processes': processes})

    def desc(self, name):
        return {'path': str(self.root / name), 'sha256': runtime.sha(self.root / name)}

    def json_artifact(self, name, value):
        (self.root / name).write_text(json.dumps(value))
        return self.desc(name)

    def bytes(self):
        return b''.join((json.dumps(row) + '\n').encode() for row in self.rows)

    def make_case(self, case_id):
        case = runtime.MATRIX[case_id]
        launch = case_id.replace('-', '_')
        for slot in case['slots']:
            invocation = launch + '/' + slot
            self.rows.append({'schema_version': 1, 'run_id': self.run, 'case_id': case_id, 'launch_id': launch,
                              'invocation_id': invocation, 'event': 'begin', 'timestamp_ms': 100,
                              'callback_count': 0})
            if case.get('error_kind') != 'throw':
                callback = 'callback' in case['api'] and (case_id != 'dual-session' or slot == 'b')
                self.rows.append({**self.rows[-1], 'event': 'return', 'value_type': 'undefined' if callback else 'object',
                                  'raw_json': 'undefined' if callback else 'Promise'})
        for slot in case['slots']:
            invocation = launch + '/' + slot
            caller_layout = self.json_artifact(invocation.replace('/', '_') + '-caller.json',
                {'attributes': {'bundleName': runtime.BUNDLE, 'id': 'contact_case_start'}})
            self.ui['events'].append({'kind': 'caller_start', 'invocation_id': invocation,
                                      'layout': caller_layout, 'screenshot': self.desc('screen.png')})
            expected = runtime.selected_records(case, slot, self.records)
            if case['ui'] == 'provider-launch':
                (self.root / 'provider.log').write_text(runtime.CONTRACT['provider_bundle'] + ' ' + runtime.CONTRACT['provider_ability'])
                self.ui['events'].append({'kind': 'provider_launch', 'invocation_id': invocation,
                                          'raw_log': self.desc('provider.log')})
            elif case['ui'] != 'none':
                action = 'cancel' if 'cancel' in case['ui'] else 'force_stop' if 'force-stop' in case['ui'] and 'after' not in case['ui'] else 'done'
                node = 'close_click_btn' if action == 'cancel' else 'doneButton'
                layout = self.json_artifact(invocation.replace('/', '_') + '-layout.json', {'attributes': {
                    'bundleName': runtime.CONTRACT['provider_bundle'], 'id': node},
                    'children': [{'id': 'selectedText', 'text': '205 selected' if len(expected) == 205 else 'selection'},
                                 *[{'text': record['name']['fullName']} for record in self.records[:4]]]})
                self.ui['events'].append({'kind': 'picker_visible', 'invocation_id': invocation})
                snapshot = invocation.replace('/', '_') + '-before.jsonl'
                (self.root / snapshot).write_bytes(self.bytes())
                self.ui['events'].append({'kind': action, 'invocation_id': invocation, 'node_id': node,
                                          'layout': layout, 'screenshot': self.desc('screen.png'), 'journal_before': self.desc(snapshot)})
                after = self.json_artifact(invocation.replace('/', '_') + '-after.json',
                    {'attributes': {'bundleName': runtime.BUNDLE, 'id': 'contact_case_status'}})
                self.ui['events'].append({'kind': 'picker_absent', 'invocation_id': invocation,
                                          'layout': after, 'screenshot': self.desc('screen.png')})
                if case_id == 'cancel-default':
                    self.ui['events'] += [{'kind': 'unselect', 'invocation_id': invocation, 'contact_id': self.records[0]['id'], 'layout': layout},
                                          {'kind': 'select', 'invocation_id': invocation, 'contact_id': self.records[3]['id'], 'layout': layout}]
            if case.get('no_terminal_expected'):
                continue
            result = {'schema_version': 1, 'run_id': self.run, 'case_id': case_id, 'launch_id': launch,
                      'invocation_id': invocation, 'timestamp_ms': 200, 'callback_count': 0}
            if 'error_code' in case:
                event = 'reject' if case['error_kind'] == 'reject-or-throw' else case['error_kind']
                result.update(event=event, error_type='object', error_code=case['error_code'], raw_json='undefined')
            else:
                callback = 'callback' in case['api'] and (case_id != 'dual-session' or slot == 'b')
                result.update(event='callback' if callback else 'resolve', value_type='object', error_type='undefined',
                              raw_json=json.dumps(expected))
            result['callback_count'] = 1 if result['event'] == 'callback' else 0
            self.rows.append(result)

    def verify(self, case=None):
        (self.root / 'journal.jsonl').write_bytes(self.bytes())
        for name, value in [('seed', self.seed), ('cleanup', self.cleanup), ('ui', self.ui),
                            ('identity', self.identity), ('build', self.build)]:
            (self.root / (name + '.json')).write_text(json.dumps(value))
        return runtime.verify_runtime(self.root / 'journal.jsonl', self.root / 'seed.json', self.root / 'cleanup.json',
                                      self.root / 'ui.json', self.root / 'identity.json', self.root / 'build.json', case)

    def test_complete_synthetic_verifier_fixture_does_not_close_runtime_gate(self):
        for case in runtime.MATRIX.values():
            if case['required']: self.make_case(case['id'])
        result = self.verify()
        self.assertTrue(result['raw_results_verified'])
        self.assertFalse(result['first_artifact_behavior_gate_passed'])
        self.assertFalse(result['ledger_closed'])

    def test_partial_or_wrong_205_result_is_rejected_even_with_pass_or_expected_fields(self):
        for mode in ['partial', 'wrongkey', 'wrongname', 'wrongphone', 'duplicate']:
            with self.subTest(mode=mode):
                self.rows = []; self.ui['events'] = []; self.make_case('options-promise-205')
                row = self.rows[-1]; actual = json.loads(row['raw_json'])
                if mode == 'partial': actual = actual[:100]
                elif mode == 'wrongkey': actual[0]['key'] = 'forged-key'
                elif mode == 'wrongname': actual[0]['name']['fullName'] = 'wrong'
                elif mode == 'wrongphone': actual[0]['phoneNumbers'] = []
                else: actual[1] = actual[0]
                row.update(raw_json=json.dumps(actual), passed=True, expected=self.records)
                with self.assertRaises(runtime.EvidenceError): self.verify('options-promise-205')

    def test_bare_number_failure_missing_callback_and_duplicate_callback_fail(self):
        self.make_case('invalid-filter-callback')
        self.rows[-1]['error_type'] = 'number'
        with self.assertRaisesRegex(runtime.EvidenceError, 'BusinessError'): self.verify('invalid-filter-callback')
        self.rows[-1]['error_type'] = 'object'
        self.rows.append(copy.deepcopy(self.rows[-1]))
        with self.assertRaisesRegex(runtime.EvidenceError, 'repeated'): self.verify('invalid-filter-callback')
        self.rows = [row for row in self.rows if row['event'] != 'callback']
        with self.assertRaisesRegex(runtime.EvidenceError, 'missing'): self.verify('invalid-filter-callback')

    def test_return_before_real_input_or_wrong_ui_and_unmodified_default_cancel_fail(self):
        self.make_case('cancel-default')
        result = self.verify('cancel-default')
        self.assertEqual(result['scope'], 'one_case_only')
        self.ui['events'] = [event for event in self.ui['events'] if event['kind'] != 'unselect']
        with self.assertRaisesRegex(runtime.EvidenceError, 'change selection'): self.verify('cancel-default')
        self.ui['events'] = []; self.rows = []; self.make_case('select-promise')
        action = next(event for event in self.ui['events'] if event['kind'] == 'done')
        (self.root / 'premature.jsonl').write_bytes(self.bytes())
        action['journal_before'] = self.desc('premature.jsonl')
        with self.assertRaisesRegex(runtime.EvidenceError, 'before real UI'): self.verify('select-promise')

    def test_normal_signing_bms_token_and_installed_payload_are_independent_requirements(self):
        self.make_case('select-promise')
        self.identity['permission_probe'] = self.json_artifact('token-granted.json', {
            'api': 'abilityAccessCtrl.verifyAccessTokenSync', 'token_id': 12345, 'READ_CONTACTS': 0, 'WRITE_CONTACTS': -1})
        with self.assertRaisesRegex(runtime.EvidenceError, 'broad contacts permission'): self.verify('select-promise')
        self.identity['permission_probe'] = self.desc('token.json')
        self.identity['bms_dump'] = self.json_artifact('bms-system.json', {'appInfo': {'bundleName': runtime.BUNDLE,
            'uid': 20000100, 'accessTokenId': 12345, 'isSystemApp': True, 'appPrivilegeLevel': 'normal'}})
        with self.assertRaisesRegex(runtime.EvidenceError, 'non-system'): self.verify('select-promise')
        self.identity['bms_dump'] = self.desc('bms.json')
        self.identity['installed_caller_hap'] = self.desc('provider.hap')
        with self.assertRaisesRegex(runtime.EvidenceError, 'installed HAP'): self.verify('select-promise')

    def test_old_image_scope_and_missing_cleanup_cannot_pass(self):
        self.make_case('select-promise')
        with self.assertRaises(runtime.EvidenceError): self.verify()
        self.build['booted_package_sha256'] = '0' * 64
        with self.assertRaisesRegex(runtime.EvidenceError, 'fresh ARM64'): self.verify('select-promise')
        self.build['booted_package_sha256'] = self.build['representative_package']['sha256']
        self.cleanup['remaining_contacts'] = [self.records[0]]
        with self.assertRaisesRegex(runtime.EvidenceError, 'cleanup'): self.verify('select-promise')

    def test_prepare_is_normal_permissionless_and_preserves_prior_output(self):
        module = runtime.document(self.root / 'project/entry/src/main/module.json5')['module']
        self.assertEqual(module['requestPermissions'], [])
        self.assertEqual(module['deviceTypes'], ['default', 'tablet', '2in1'])
        self.assertNotIn('extensionAbilities', module)
        with self.assertRaises(runtime.EvidenceError): runtime.prepare_project(self.root / 'project')
        self.assertEqual(len(runtime.document(self.root / 'project/caller-source-manifest.json')['fixture_hashes']), 6)

    def test_actual_recorder_classes_preserve_raw_late_and_duplicate_observations(self):
        program = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {stripTypeScriptTypes}=require('node:module');
const root=process.argv[1], files=new Map(),timers=new Map(), callbacks=[],promises=[];let serial=0;
const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}};
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve()};
let behavior='pending';
const api=(...args)=>{if(behavior==='throw')throw {code:401,message:'actual failure'};
 const cb=args.find(x=>typeof x==='function');if(cb){callbacks.push(cb);return undefined}
 const pending=defer();promises.push(pending);return behavior==='undefined'?undefined:pending.promise;};
const box=vm.createContext({console,JSON,Map,Set,Date,String,Number,Array,Error,
 fs:{OpenMode:{CREATE:1,READ_WRITE:2,APPEND:4},openSync:p=>({fd:p}),writeSync:(p,s)=>{if(!files.has(p))files.set(p,[]);files.get(p).push(JSON.parse(s))},closeSync(){}},
 setTimeout:fn=>{timers.set(++serial,fn);return serial},clearTimeout:id=>timers.delete(id),
 contact:{selectContacts:api,selectContact:api,queryContact:api,FilterType:{SHOW_FILTER_AND_DEFAULT_SELECT:2,DEFAULT_SELECT:1},FilterCondition:{IN:3}}});
for(const [name,expose] of [['ResultJournal.ets','this.ResultJournal=ResultJournal;this.Observation=Observation;'],
 ['PickerCases.ets','this.PickerCases=PickerCases;this.LaunchInput=LaunchInput;']]){
 let code=fs.readFileSync(root+'/'+name,'utf8').replace(/^import .*;\n/gm,'').replace(/\bexport (?:default )?/g,'');
 vm.runInContext(stripTypeScriptTypes(code,{mode:'transform'})+'\n'+expose,box);
}
function run(caseId,launchId){const input=new box.LaunchInput();Object.assign(input,{runId:'raw',launchId,caseId,
 seedIds:Array.from({length:205},(_,i)=>1000+i),queryKey:'real'});const value=new box.PickerCases(input,{filesDir:'/unit'},()=>{});value.start();return value}
const rows=()=>files.get('/unit/contact-picker-raw.jsonl')||[];
(async()=>{
 const first=run('select-promise','first');promises[0].resolve([{id:42,key:'returned-not-seed',name:{fullName:'raw'}}]);await tick();
 assert.deepEqual(JSON.parse(rows().find(x=>x.event==='resolve').raw_json),[{id:42,key:'returned-not-seed',name:{fullName:'raw'}}]);
 run('select-callback','old');run('select-callback','new');callbacks[1](undefined,[{id:222}]);callbacks[0](-1,undefined);await tick();
 const old=rows().find(x=>x.invocation_id==='old/a'&&x.event==='callback');assert.equal(old.error_type,'number');assert.equal(old.error_code,undefined);
 assert.equal(JSON.parse(rows().find(x=>x.invocation_id==='new/a'&&x.event==='callback').raw_json)[0].id,222);
 callbacks[1](undefined,[{id:333}]);assert.deepEqual(rows().filter(x=>x.invocation_id==='new/a'&&x.event==='callback').map(x=>x.callback_count),[1,2]);
 const dying=run('exit-pending','dying');dying.dispose();dying.dispose();promises[1].reject({code:16700001,message:'cancel'});await tick();
 assert.equal(rows().find(x=>x.invocation_id==='dying/a'&&x.event==='reject').after_dispose,true);
 behavior='throw';run('invalid-limit-callback','bad');assert.equal(rows().find(x=>x.invocation_id==='bad/a'&&x.event==='throw').error_code,401);
 behavior='pending';const waiting=run('select-promise','waiting');const timer=[...timers.entries()].at(-1);timers.delete(timer[0]);timer[1]();
 assert(rows().some(x=>x.invocation_id==='waiting/a'&&x.event==='observer_watchdog'));
 assert(!rows().some(x=>x.invocation_id==='waiting/a'&&['resolve','reject','throw','callback'].includes(x.event)));
 waiting.dispose();assert.equal(timers.size,0);assert(rows().every(x=>!('passed'in x)&&!('expected'in x)));
 console.log('actual caller recorder raw/late/duplicate/dispose/watchdog checks passed');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run(['node', '--unhandled-rejections=strict', '-e', program, str(runtime.FIX)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('actual caller recorder', result.stdout)


if __name__ == '__main__':
    unittest.main()
