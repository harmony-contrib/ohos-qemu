"""In-memory synthetic host protocol cases. Never guest receipts or SDK proof."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import batch_apps_select375_project as p
import batch_apps_select375_project_build as b
import batch_apps_select375_project_verify as v
REQ=dict(schema_version=1,run_id='1'*32,boot_id='11111111-2222-3333-4444-555555555555',archive_sha256='2'*64,operation_id='3'*32,case_id='read-a',phase='run',kind='caller')
IDS={r:dict(uid=20010001+i,token_id=77+i) for i,r in enumerate(p.ROLES)}
API='UIAbilityContext.startAbilityForResult'
def js(x):return json.dumps(x,separators=(',',':'))
def fixture(case='read-a'):
    q=dict(REQ,case_id=case);out={r:[] for r in p.ROLES}
    def add(role,kind,stage,event,api,value,t,code=0):
        out[role].append(dict(v.phase(q,kind,stage),role=role,uid=IDS[role]['uid'],token_id=IDS[role]['token_id'],pid=121+list(p.ROLES).index(role),sequence=len(out[role])+1,timestamp_ms=t,event=event,api=api,value_json=js(value),error_code=code,error_message='Permission denied' if code else ''))
    def c(event,api,value,t,code=0):add('caller','caller','run',event,api,value,t,code)
    c('begin','request',q,1000);c('incoming','UIAbility.Want',dict(parameters=dict(request=js(q))),1001)
    if case in ('private-start','forged-sid'):
        w=dict(bundleName='com.ohos.settings',abilityName='PickerDialog')
        if case=='forged-sid':w['parameters']=dict(dialogSessionId='legacy_picker_'+q['operation_id'])
        c('private_call','UIAbilityContext.startAbility',w,1002);c('private_reject','UIAbilityContext.startAbility',None,1003,16000004);c('complete','',None,1004);return q,out
    suffix='/select375-'+q['run_id']+'-'+q['operation_id']+'.txt';uri='file://'+p.ROLES['caller']['bundle']+'/data/storage/el2/base/files'+suffix
    c('owned','fileUri.getUriFromPath',uri,1002);c('owner_before','fileIo.openSync/readSync',v.payload(q,'original'),1003)
    selected=p.CONTRACT['cases'][case]['target'];other='target_b' if selected=='target_a' else 'target_a'
    def target(role,kind,stage,t):
        r=v.phase(q,kind,stage);w=dict(bundleName=p.ROLES[role]['bundle'],moduleName='entry',abilityName='EntryAbility',flags=0,parameters=dict(request=js(r)))
        if kind=='probe':w['parameters']['probe_uri']=uri
        else:w.update(uri=uri,action='',type=p.CONTRACT['mime'],entities=[p.CONTRACT['entity']],flags=p.CONTRACT['cases'][case]['flags'])
        add(role,kind,stage,'begin','request',r,t);add(role,kind,stage,'incoming','UIAbility.Want',w,t+1)
        for i,event,flag in [(2,'read',1),(3,'write',2)]:
            ok=kind=='select' and p.CONTRACT['cases'][case]['flags']&flag
            add(role,kind,stage,event,'fileIo.openSync/'+('readSync' if event=='read' else 'writeSync'),v.payload(q,'original' if event=='read' else 'modified') if ok else None,t+i,0 if ok else 13900012)
        z=v.result(q,role,stage);add(role,kind,stage,'return','UIAbilityContext.terminateSelfWithResult',z,t+4);add(role,kind,stage,'complete','',None,t+5);return z
    def probe(stage,t,tt,rt):
        w=dict(bundleName=p.ROLES[other]['bundle'],moduleName='entry',abilityName='EntryAbility',flags=0,parameters=dict(request=js(v.phase(q,'probe',stage)),probe_uri=uri))
        c('probe_call',API,w,t);z=target(other,'probe',stage,tt);c('probe_result',API,z,rt)
    if case!='cancel':probe('before',1004,1005,1020)
    w=dict(action=p.CONTRACT['action'],uri=uri,type=p.CONTRACT['mime'],entities=[p.CONTRACT['entity']],flags=p.CONTRACT['cases'][case]['flags'],parameters=dict(request=js(v.phase(q,'select','choose'))))
    c('select_call',API,w,1021);z={'resultCode':-1} if case=='cancel' else target(selected,'select','choose',1022)
    c('select_result',API,z,1040);c('owner_after','fileIo.openSync/readSync',v.payload(q,'modified' if case=='write-a' else 'original'),1041)
    if case!='cancel':probe('after',1042,1043,1060)
    c('deleted','fileIo.unlinkSync/accessSync',dict(path='/data/storage/el2/base/files'+suffix,exists_after=False),1061);c('complete','',None,1062);return q,out

def raw(rows):return {r:''.join(js(x)+'\n' for x in a) for r,a in rows.items()}
def check(q,rows,before=None):return v.verify_operation(q,before or {r:'' for r in p.ROLES},raw(rows),IDS)

class Protocol(unittest.TestCase):
    def test_seven_outcome_shapes(self):
        for case in p.CONTRACT['cases']:
            q,rows=fixture(case)
            with self.subTest(case=case):self.assertEqual(check(q,rows)['case_id'],case)
    def test_missing_duplicate_extra_reordered_records(self):
        q,original=fixture()
        for role in p.ROLES:
            for i in range(len(original[role])):
                for kind in ['missing','duplicate','reorder']:
                    rows=copy.deepcopy(original)
                    if kind=='missing':rows[role].pop(i)
                    elif kind=='duplicate':rows[role].insert(i,rows[role][i])
                    else:rows[role][i]['sequence']+=1
                    with self.subTest(role=role,i=i,kind=kind),self.assertRaises(ValueError):check(q,rows)
    def test_nonce_identity_boot_metadata_bool_and_unknown_event(self):
        q,original=fixture()
        for role in p.ROLES:
            for field,bad in [('run_id','9'*32),('operation_id','9'*32),('uid',0),('token_id',0),('pid',0),('boot_id','0'*36),('archive_sha256','9'*64),('event','pass'),('schema_version',True),('error_code',False),('sequence',True),('phase','replaced')]:
                rows=copy.deepcopy(original);rows[role][0][field]=bad
                with self.subTest(role=role,field=field),self.assertRaises(ValueError):check(q,rows)
            rows=copy.deepcopy(original);rows[role][0]['pass']=True
            with self.assertRaises(ValueError):check(q,rows)
    def test_payload_uri_grants_and_nonpermission_errors(self):
        q,original=fixture()
        for role,i,field,bad in [('target_a',2,'value_json',js('fake')),('target_a',3,'error_code',13900002),('target_b',2,'error_code',13900002),('target_b',8,'error_code',0),('caller',3,'value_json',js('fake')),('caller',8,'value_json',js('foreign'))]:
            rows=copy.deepcopy(original);rows[role][i][field]=bad
            with self.subTest(role=role,i=i),self.assertRaises(ValueError):check(q,rows)
        for role,i,key,bad in [('caller',6,'action','ohos.want.action.choose'),('caller',6,'bundleName',p.ROLES['target_a']['bundle']),('target_b',1,'uri','file://foreign/x'),('target_b',1,'flags',1)]:
            rows=copy.deepcopy(original);w=v.value(rows[role][i]);w[key]=bad;rows[role][i]['value_json']=js(w)
            with self.assertRaises(ValueError):check(q,rows)
    def test_result_cancel_known_empty_napi_defaults_preserve_metadata_rejection(self):
        q,rows=fixture('cancel');rows['caller'][5]['value_json']=js(dict(resultCode=-1,want=dict(flags=0,entities=[],parameters={},uri='')));check(q,rows)
        for key,bad in [('uri','file://stale'),('abilityName','foreign'),('parameters',{'stale':'secret'}),('unknown','')]:
            changed=copy.deepcopy(rows);z=v.value(changed['caller'][5]);z['want'][key]=bad;changed['caller'][5]['value_json']=js(z)
            with self.assertRaises(ValueError):check(q,changed)
        q,rows=fixture();z=v.value(rows['caller'][7]);z['want'].update(flags=0,entities=[],uri='');rows['caller'][7]['value_json']=js(z);check(q,rows)
        z['want']['parameters']['operation_id']='9'*32;rows['caller'][7]['value_json']=js(z)
        with self.assertRaises(ValueError):check(q,rows)
    def test_replay_truncation_duplicate_keys_and_foreign_append(self):
        q,rows=fixture()
        with self.assertRaises(ValueError):check(q,rows,before=raw(rows))
        changed=raw(rows);changed['target_a']=changed['target_a'][:-1]
        with self.assertRaises(ValueError):v.verify_operation(q,{r:'' for r in p.ROLES},changed,IDS)
        changed=raw(rows);changed['caller']=changed['caller'].replace('"pid":121','"pid":121,"pid":121',1)
        with self.assertRaises(ValueError):v.verify_operation(q,{r:'' for r in p.ROLES},changed,IDS)
    def test_direct_private_success_missing_provider_or_internal_error_fails(self):
        for case in ['private-start','forged-sid']:
            q,original=fixture(case)
            for event,code in [('private_resolve',0),('private_reject',16000050),('private_reject',16000001)]:
                rows=copy.deepcopy(original);rows['caller'][3].update(event=event,error_code=code)
                with self.assertRaises(ValueError):check(q,rows)
    def test_guest_footer_hdc_and_transport(self):
        script='cat /proc/sys/kernel/random/boot_id';argv,marker=v.wrapped(script,REQ['operation_id'])
        with tempfile.TemporaryDirectory(prefix='select375-raw-host-') as temp:
            path=Path(temp).resolve()/'raw.txt'
            def record(body):
                path.write_text(body);return dict(argv=['/owned/hdc','-t','127.0.0.1:1234','shell',argv],host_exit_code=0,raw=p.record(path),started_ns=1,finished_ns=2)
            body=REQ['boot_id']+'\n\n'+marker+'0\n';self.assertEqual(v.command(record(body),script,REQ,'/owned/hdc','127.0.0.1:1234'),REQ['boot_id']+'\n')
            for bad in [body+'late\n',body.replace(marker+'0',marker+'1'),body+marker+'0\n',body.replace(REQ['boot_id'],'[Fail]')]:
                with self.assertRaises(ValueError):v.command(record(bad),script,REQ,'/owned/hdc','127.0.0.1:1234')
            for key,bad in [('host_exit_code',1),('host_exit_code',False),('argv',['/wrong/hdc']),('started_ns',True)]:
                row=record(body);row[key]=bad
                with self.assertRaises(ValueError):v.command(row,script,REQ,'/owned/hdc','127.0.0.1:1234')

class Sources(unittest.TestCase):
    def test_three_ordinary_projects_storage_cold_newwant_and_exact_target_skills(self):
        for role in p.ROLES:
            files=p.expected_sources({'run_id':REQ['run_id']},role,'/owned/official-sdk/26.0.0');m=json.loads(files['entry/src/main/module.json5'])['module'];a=m['abilities'][0]
            self.assertEqual(m['requestPermissions'],[]);self.assertEqual(m['deviceTypes'],['default']);self.assertTrue(a['exported'])
            self.assertEqual(a['launchType'],'singleton' if role=='caller' else 'standard')
            self.assertEqual(json.loads(files['AppScope/app.json5'])['app']['bundleName'],p.ROLES[role]['bundle'])
            if role=='caller':self.assertNotIn('skills',a)
            else:self.assertEqual(a['skills'][0]['uris'],[{'type':p.CONTRACT['mime']}])
            page=files['entry/src/main/ets/pages/Index.ets'];entry=files['entry/src/main/ets/entryability/EntryAbility.ets']
            self.assertIn('@Entry({ useSharedStorage: true })',page);self.assertIn("@Watch('wantChanged')",page)
            self.assertIn('onNewWant(want: Want): void { this.publish(want); }',entry);self.assertIn("stage.loadContent('pages/Index', this.storage)",entry)
    def test_actual_calls_grant_avoidance_and_owned_cleanup_guard(self):
        text=(p.FIX/'SelectAudit.ets').read_text()
        for s in ['getApplicationContext().filesDir','this.context.startAbilityForResult(want)','this.context.terminateSelfWithResult(result)',"action: 'ohos.want.action.select'",'finalStat.ino !== originalStat.ino','Duplicate owned operation/phase',"this.foreign(uri, 'before')","this.foreign(uri, 'after')"]:self.assertIn(s,text)
        for s in ['grantUriPermission','uriPermissionManager','OpenMode.EXCL','AppStorage.','system_basic','hos_system_app']:self.assertNotIn(s,text)
        self.assertLess(text.index('finalStat.ino !== originalStat.ino'),text.index('fs.unlinkSync(path)'))
    def test_build_requires_root_optin_before_any_process(self):
        class Args:execute_sdk_build=False
        with mock.patch.object(subprocess,'Popen',side_effect=AssertionError('no process')):
            with self.assertRaisesRegex(ValueError,'explicitly'):b.build(Args())
    def test_execute_flag_alone_cannot_acquire_sdk_resources(self):
        class Args:execute_sdk_build=True
        with self.assertRaisesRegex(ValueError,'callback'):b.build(Args())
        self.assertNotIn('subprocess',Path(b.__file__).read_text().replace('# No subprocess, nested lock, owner JSON assertion or fallback exists.',''))
    def test_untracked_or_different_producer_cannot_borrow_a_git_commit(self):
        def observation(argv,**kw):
            if argv[-1]=='HEAD':return 'a'*40+'\n'
            if 'status' in argv:return ''
            name=argv[-1].split(':',1)[1]
            return (p.ROOT/name).read_bytes()
        with mock.patch.object(p.subprocess,'check_output',side_effect=observation):p.repository('a'*40)
        def wrong(argv,**kw):
            if 'show' in argv:return b'old committed producer'
            return observation(argv,**kw)
        with mock.patch.object(p.subprocess,'check_output',side_effect=wrong):
            with self.assertRaisesRegex(ValueError,'committed source'):p.repository('a'*40)

if __name__=='__main__':unittest.main()
