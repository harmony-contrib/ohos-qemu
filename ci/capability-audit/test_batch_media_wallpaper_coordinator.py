"""Host orchestration/receipt/oracle tests. No VM, HDC, SDK build or native run."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import batch_media_wallpaper_coordinator as coordinator
import batch_media_wallpaper_runtime as runtime
from batch_media_verify_wallpaper_runtime import NodeNotReady


class CoordinatorTests(unittest.TestCase):
    def request(self,index=1):
        return {'schema_version':1,'run_id':'a'*32,'boot_id':'11111111-1111-1111-1111-111111111111',
                'sequence':index,'nonce':format(index,'032x'),'action':coordinator.ordered_actions()[index-1],'details':{}}

    def test_actual_21_requests_and_atomic_single_link_ack(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp)
            for sequence in range(1,22):
                request=self.request(sequence);path=root/f'{request["run_id"]}-{sequence:03}-{request["nonce"]}.request.json'
                path.write_text(json.dumps(request)+'\n');path.chmod(0o600)
                value=coordinator.request_file(path,request['run_id'],request['boot_id'],sequence)
                reply=path.with_name(path.name.replace('.request.','.ack.'))
                coordinator.publish_ack(reply,value)
                self.assertEqual(1,reply.stat().st_nlink);self.assertEqual(0o600,reply.stat().st_mode&0o777)
                self.assertEqual({k:v for k,v in request.items()if k!='details'},json.loads(reply.read_text()))
                with self.assertRaises(FileExistsError):coordinator.publish_ack(reply,value)
            self.assertEqual(21,len(coordinator.ordered_actions()))

    def test_bad_request_partial_replay_mode_link_and_unsafe_path(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);request=self.request();path=root/f'{request["run_id"]}-001-{request["nonce"]}.request.json'
            path.write_text('{');path.chmod(0o600)
            with self.assertRaises(NodeNotReady):coordinator.request_file(path,request['run_id'],request['boot_id'],1)
            path.write_text(json.dumps(request))
            with self.assertRaises(NodeNotReady):coordinator.request_file(path,request['run_id'],request['boot_id'],1)
            original=copy.deepcopy(request)
            for key,value in [('run_id','b'*32),('boot_id','2'*36),('sequence',True),('schema_version',True),
                              ('action','remove-owned-seed-private-inputs'),('nonce','x'*32)]:
                bad=copy.deepcopy(original);bad[key]=value;path.write_text(json.dumps(bad)+'\n')
                with self.subTest(key=key):
                    with self.assertRaises(ValueError):coordinator.request_file(path,original['run_id'],original['boot_id'],1)
            path.write_text(json.dumps(original)+'\n');path.chmod(0o644)
            with self.assertRaises(ValueError):coordinator.request_file(path,original['run_id'],original['boot_id'],1)
            path.chmod(0o600);link=root/'hardlink';os.link(path,link)
            with self.assertRaises(ValueError):coordinator.request_file(path,original['run_id'],original['boot_id'],1)
            link.unlink();path.unlink();path.symlink_to(link)
            with self.assertRaises(OSError):coordinator.request_file(path,original['run_id'],original['boot_id'],1)

    def test_actual_sdk_schema_adaptation_rejects_zero_without_real_compile(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);page=root/'Index.ets';page.write_text('source');hap=root/'real.hap';hap.write_bytes(b'host oracle HAP')
            log=root/'compile.log';log.write_text('hvigor BUILD SUCCESSFUL in 2s\n')
            evidence={'exit_code':0,'source_commit':'a'*40,'archive_sha256':'b'*64,'runner_sha256':'c'*64,
                'first_artifact_behavior_gate_passed':False,'source_files':{'entry/src/main/ets/pages/Index.ets':runtime.sha(page)},
                'commands':[{'label':'compile','argv':['node','hvigorw.js','assembleHap'],'exit_code':0,
                             'log':str(log),'sha256':runtime.sha(log)}],
                'haps':[{'path':'linux/output.hap','sha256':runtime.sha(hap),'bytes':hap.stat().st_size}]}
            path=root/'evidence.json';path.write_text(json.dumps(evidence))
            inputs={'sdk_evidence':runtime.record(path),'source_key':'entry/src/main/ets/pages/Index.ets'}
            adapter=coordinator.adapt_sdk_build(inputs,page,hap,root/'adapted.json')
            self.assertEqual('pass',json.loads(Path(adapter['path']).read_text())['status'])
            modifications=[lambda v:v.update(exit_code=255),lambda v:v.update(haps=[]),
                           lambda v:v['commands'][0].update(exit_code=255),lambda v:v['source_files'].clear(),
                           lambda v:v['commands'][0].update(argv=['echo','success'])]
            for index,change in enumerate(modifications):
                value=copy.deepcopy(evidence);change(value);path.write_text(json.dumps(value));inputs['sdk_evidence']=runtime.record(path)
                with self.assertRaises(ValueError):coordinator.adapt_sdk_build(inputs,page,hap,root/(str(index)+'.json'))
            log.write_text('process exited 0; compile was never run\n');path.write_text(json.dumps(evidence))
            value=copy.deepcopy(evidence);value['commands'][0]['sha256']=runtime.sha(log);path.write_text(json.dumps(value));inputs['sdk_evidence']=runtime.record(path)
            with self.assertRaises(ValueError):coordinator.adapt_sdk_build(inputs,page,hap,root/'no-completion.json')

    def test_real_query_empty_requires_before_positive_and_exact_cursor_contract(self):
        uris=[f'file://media/Photo/{i+1}/fresh.png'for i in range(5)]
        for phase in ('before','after'):
            value={'run_id':'a'*32,'nonce':'b'*32,'phase':phase,'queried_uris':uris,
                'active_uris':uris if phase=='before'else[],
                'entries':[{'uri':uri,'count':1 if phase=='before'else 0,'actualUri':uri if phase=='before'else''}for uri in uris],
                'began_ms':1000,'ended_ms':1001}
            self.assertEqual(value['active_uris'],coordinator.actual_query(json.dumps(value),'a'*32,'b'*32,phase,uris)['active_uris'])
            for change in ('stale','error','wrong_count','missing_uri','fake_summary','reordered'):
                bad=copy.deepcopy(value)
                if change=='stale':bad['nonce']='c'*32
                elif change=='error':bad={'run_id':'a'*32,'error_code':201,'active_uris':[]}
                elif change=='wrong_count':bad['entries'][0]['count']=2
                elif change=='missing_uri':bad['entries'].pop()
                elif change=='reordered':bad['queried_uris']=uris[::-1]
                else:bad['active_uris']=[]if phase=='before'else uris
                with self.subTest(phase=phase,change=change):
                    with self.assertRaises(ValueError):coordinator.actual_query(json.dumps(bad),'a'*32,'b'*32,phase,uris)

    def test_minimal_signed_HAP_role_source_and_original_build_receipt(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);challenge=json.loads(runtime.prepare(root/'challenge',360,640).read_text())
            project=root/'project';page=project/'entry/src/main/ets/pages/Index.ets';page.parent.mkdir(parents=True)
            page.write_bytes(Path(challenge['generated_page']['path']).read_bytes())
            label=project/'AppScope/resources/base/element/string.json';label.parent.mkdir(parents=True)
            label.write_text(json.dumps({'string':[{'name':'app_name','value':'Actual caller label'}]}))
            module={'app':{'bundleName':runtime.SEED,'label':'$string:app_name'},
                    'module':{'requestPermissions':[],'abilities':[{'name':'EntryAbility'}]}}
            unsigned=root/'unsigned.hap'
            with zipfile.ZipFile(unsigned,'w')as hap:
                hap.writestr('module.json',json.dumps(module));hap.writestr('ets/modules.abc',b'SYNTHETIC HOST ORACLE ONLY')
            signed=root/'signed.hap';signed.write_bytes(unsigned.read_bytes())
            sign={'status':'pass','scope':'actual_signature_profile_and_codesign_NOT_guest','unsigned_sha256':runtime.sha(unsigned),
                  'signed_sha256':runtime.sha(signed),'verified_profile':{'bundle-info':{'bundle-name':runtime.SEED,
                  'apl':'normal','app-feature':'hos_normal_app'},'debug-info':{'device-ids':['a'*64]},
                  'acls':{'allowed-acls':[]},'permissions':{'restricted-permissions':[]}}}
            signpath=root/'signing.json';signpath.write_text(json.dumps(sign))
            log=root/'compile.log';log.write_text('BUILD SUCCESSFUL\n')
            evidence={'exit_code':0,'source_commit':'a'*40,'archive_sha256':'b'*64,'runner_sha256':'c'*64,
                'first_artifact_behavior_gate_passed':False,'source_files':{'entry/src/main/ets/pages/Index.ets':runtime.sha(page),
                    'AppScope/resources/base/element/string.json':runtime.sha(label)},
                'commands':[{'label':'compile','argv':['node','assembleHap'],'exit_code':0,'log':str(log),'sha256':runtime.sha(log)}],
                'haps':[{'path':'host','sha256':runtime.sha(unsigned),'bytes':unsigned.stat().st_size}]}
            ep=root/'SDK.json';ep.write_text(json.dumps(evidence));out=root/'output';out.mkdir()
            value={'compiled_page':runtime.record(page),'unsigned_hap':runtime.record(unsigned),'signed_hap':runtime.record(signed),
                'signing_receipt':runtime.record(signpath),'sdk_evidence':runtime.record(ep),'source_key':'entry/src/main/ets/pages/Index.ets',
                'ability':'EntryAbility'}
            self.assertEqual('Actual caller label',coordinator.validate_hap(value,'seed',challenge,'a'*64,out)['app_label'])
            for index,mutate in enumerate([lambda v:v['verified_profile']['bundle-info'].update(apl='system_core'),
                lambda v:v['verified_profile']['acls'].update({'allowed-acls':['ohos.permission.SET_WALLPAPER']}),
                lambda v:v['verified_profile']['debug-info'].update({'device-ids':['b'*64]}),lambda v:v.update(status='fail')]):
                bad=copy.deepcopy(sign);mutate(bad);signpath.write_text(json.dumps(bad));value['signing_receipt']=runtime.record(signpath)
                target=root/str(index);target.mkdir()
                with self.assertRaises(ValueError):coordinator.validate_hap(value,'seed',challenge,'a'*64,target)
            # Actual compiled user-grant declarations carry reason/usedScene
            # metadata. It must not make the legitimate read-only role fail.
            page.write_text((coordinator.FIXTURE/'Query.ets').read_text().replace('__WALLPAPER_RUN__',challenge['run_id']))
            module['app']['bundleName']=coordinator.QUERY
            module['module']['requestPermissions']=[{'name':coordinator.READ,'reason':'$string:permission_reason',
                'reasonId':16777217,'usedScene':{'abilities':['EntryAbility'],'when':'inuse'}}]
            def query_role():
                with zipfile.ZipFile(unsigned,'w')as hap:
                    hap.writestr('module.json',json.dumps(module));hap.writestr('ets/modules.abc',b'SYNTHETIC HOST QUERY ORACLE ONLY')
                signed.write_bytes(unsigned.read_bytes());actual=copy.deepcopy(sign)
                actual['verified_profile']['bundle-info'].update({'bundle-name':coordinator.QUERY,'apl':'system_basic','app-feature':'hos_system_app'})
                actual.update(unsigned_sha256=runtime.sha(unsigned),signed_sha256=runtime.sha(signed))
                signpath.write_text(json.dumps(actual));value.update(compiled_page=runtime.record(page),
                    unsigned_hap=runtime.record(unsigned),signed_hap=runtime.record(signed),signing_receipt=runtime.record(signpath))
                evidence['source_files']['entry/src/main/ets/pages/Index.ets']=runtime.sha(page)
                evidence['haps'][0].update(sha256=runtime.sha(unsigned),bytes=unsigned.stat().st_size)
                ep.write_text(json.dumps(evidence));value['sdk_evidence']=runtime.record(ep)
            query_role();target=root/'query';target.mkdir()
            self.assertEqual('Actual caller label',coordinator.validate_hap(value,'query',challenge,'a'*64,target)['app_label'])
            module['module']['requestPermissions'].append({'name':coordinator.SET});query_role()
            target=root/'extra-permission';target.mkdir()
            with self.assertRaises(ValueError):coordinator.validate_hap(value,'query',challenge,'a'*64,target)

    def test_actual_permission_resources_bind_the_query_app_label(self):
        def item(text,click=False):return {'attributes':{'bundleName':'com.ohos.permissionmanager','text':text,
            'visible':'true','enabled':'true','clickable':'true'if click else'false','bounds':'[0,0][100,100]'},'children':[]}
        tree=[item('允许“Independent query”访问图片和视频？'),item('允许',True)]
        node,locale=coordinator.read_permission_node(tree,'Independent query');self.assertEqual('允许',locale['allow'])
        with self.assertRaises(NodeNotReady):coordinator.read_permission_node(tree,'Another app')

    def test_preserve_actual_file_newlines_and_reject_partial_log(self):
        value=coordinator.Coordinator.__new__(coordinator.Coordinator)
        def shell(script,label):
            marker=re.search(r'__WALLPAPER_EOF_[a-f0-9]{32}__',script).group()
            return '{"line":1}\n\n'+marker
        value.shell=shell
        self.assertEqual('{"line":1}\n',value.read_complete('/private/path','read'))
        def partial(script,label):
            marker=re.search(r'__WALLPAPER_EOF_[a-f0-9]{32}__',script).group()
            return '{"line":\n'+marker
        value.shell=partial;self.assertFalse(value.read_complete('/private/path','read').endswith('\n'))

    def test_wait_disabled_is_not_duplicate_and_no_settings_back_in_other_app(self):
        from guest_ui import select_node
        tree={'attributes':{'bundleName':runtime.SEED,'id':'button','visible':'true','enabled':'false',
                             'clickable':'false','bounds':'[0,0][100,100]'},'children':[]}
        with self.assertRaises(NodeNotReady):coordinator.ready_node(tree,runtime.SEED,identifier='button',clickable=True)
        tree['attributes'].update(enabled='true',clickable='true')
        self.assertEqual(runtime.SEED,coordinator.ready_node(tree,runtime.SEED,identifier='button',clickable=True)['bundle'])
        with self.assertRaises(ValueError):coordinator.ready_node([tree,tree],runtime.SEED,identifier='button',clickable=True)
        self.assertFalse(coordinator.settings_foreground('    AppRunningRecord ID #1\n      process name [com.other]\n      pid #1  uid #20010001\n      state #FOREGROUND\n',20010001))

    def test_no_ack_after_actual_handler_failure(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);request=self.request();path=root/f'{request["run_id"]}-001-{request["nonce"]}.request.json'
            path.write_text(json.dumps(request)+'\n');path.chmod(0o600)
            value=coordinator.Coordinator.__new__(coordinator.Coordinator)
            value.args=SimpleNamespace(actions=root,idle_seconds=1,action_seconds=1)
            value.guest=SimpleNamespace(start=lambda:None);value.run=request['run_id'];value.boot_id=request['boot_id']
            value.value={'actions':[]};value.wake_if_asleep=lambda _:False;value.identity=lambda _:None
            value.power_state=lambda _:{'host_fixture':True}
            value.dispatch=lambda _:(_ for _ in()).throw(ValueError('real UI failed'));value.save=lambda:None
            with self.assertRaisesRegex(ValueError,'real UI failed'):value.run_requests()
            self.assertEqual([],list(root.glob('*.ack.json')))

    def test_query_actual_API26_declarations_and_read_only_sources(self):
        sdk=Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
        with tempfile.TemporaryDirectory()as temp:
            result=subprocess.run(['node',str(runtime.FIXTURE/'sdk-types.cjs'),str(coordinator.FIXTURE/'Query.ets'),
                str(sdk/'ets/build-tools/ets-loader/node_modules/typescript'),temp,str(sdk/'ets/api')],capture_output=True,text=True,timeout=30)
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        native=(coordinator.FIXTURE/'token_query.cpp').read_text();query=(coordinator.FIXTURE/'Query.ets').read_text()
        self.assertNotRegex(native,r'AccessTokenKit::(?:Grant|Revoke|Set|Update|Delete|Alloc)')
        self.assertIn('helper.getAssets',query);self.assertNotRegex(query,r'deleteAssets|executeSql|insert\(|update\(')
        self.assertIn('requestPermissionsFromUser',query)


if __name__=='__main__':unittest.main()
