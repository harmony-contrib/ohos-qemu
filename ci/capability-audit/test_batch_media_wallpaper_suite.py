"""Light host negative/protocol tests, never guest/native/signature evidence."""
import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import batch_media_wallpaper_suite as suite
import batch_media_wallpaper_artifacts as artifacts
import batch_media_wallpaper_coordinator as coordinator
from batch_media_wallpaper_runtime import record,sha


def boot_value(archive_sha):
    return {'status':'pass','purpose':'acceptance','scope':'fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
        'archive_sha256':archive_sha,'test_environment':{'external_keepalive':False,'guest_arch':'arm64','device_type':'phone',
        'qemu_pid':123,'qemu_command':'qemu-system-aarch64 -qmp unix:/tmp/fixture-qmp','target':'127.0.0.1:12345',
        'boot_id':'11111111-1111-1111-1111-111111111111','udid':'a'*64,'qmp_socket':'/tmp/fixture-qmp'}}


class PowerTransport:
    def __init__(self,output,override=86400000):self.output=output;self.override=override;self.commands=[]
    def shell(self,command,label):
        self.commands.append(command)
        if command.startswith('hidumper'):return 'ScreenOffTime: Timeout=30000ms'+('  OverrideTimeout='+str(self.override)+'ms'if self.override else'')
        if command=='power-shell timeout -r':self.override=None;return 'Restore screen off time'
        if command=='power-shell timeout -o 86400000':self.override=86400000;return 'Override screen off time to 86400000'
        raise AssertionError(command)
    def text(self,raw,label):
        path=self.output/(label+'.txt');path.write_text(raw);return record(path)
    def home(self):self.commands.append('actual home gesture fixture');self.override=None


class WallpaperSuiteTests(unittest.TestCase):
    def test_project_success_in_failed_batch_is_local_and_keeps_original_failure(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);page=root/'Index.ets';page.write_text('source');hap=root/'unsigned.hap';hap.write_bytes(b'UNIT ONLY')
            good=root/'wallpaper-query-compile.log';good.write_text('BUILD SUCCESSFUL\n');bad=root/'other-compile.log';bad.write_text('BUILD FAILED\n')
            value={'exit_code':1,'first_artifact_behavior_gate_passed':False,'source_commit':'a'*40,'archive_sha256':'b'*64,
                'runner_sha256':'c'*64,'source_files':{'wallpaper-query/entry/src/main/ets/pages/Index.ets':sha(page)},
                'haps':[{'project':'wallpaper-query','sha256':sha(hap),'bytes':hap.stat().st_size}],
                'commands':[{'project':name,'label':'compile','argv':['node','assembleHap'],'exit_code':rc,'log':str(log),'sha256':sha(log)}
                    for name,rc,log in [('wallpaper-query',0,good),('other',255,bad)]]}
            path=root/'evidence.json';path.write_text(json.dumps(value));spec={'sdk_evidence':record(path),'source_key':'wallpaper-query/entry/src/main/ets/pages/Index.ets'}
            result=coordinator.adapt_sdk_build(spec,page,hap,root/'adapted.json')
            self.assertEqual(1,json.loads(Path(result['path']).read_text())['actual_batch_exit_code'])
            value['commands'][0]['exit_code']=255;path.write_text(json.dumps(value));spec['sdk_evidence']=record(path)
            with self.assertRaises(ValueError):coordinator.adapt_sdk_build(spec,page,hap,root/'bad.json')

    def test_source_manifest_hashes_every_selected_project_source(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);project=root/'project';rows={}
            for name in ('entry/src/main/ets/pages/Index.ets','entry/src/main/module.json5','AppScope/resources/base/element/string.json','hvigorfile.ts'):
                path=project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name);rows['query/'+name]=sha(path)
            evidence=root/'evidence.json';evidence.write_text(json.dumps({'source_files':rows}))
            spec={'source_project':str(project),'source_key':'query/entry/src/main/ets/pages/Index.ets','sdk_evidence':record(evidence)}
            self.assertEqual(sha(project/'entry/src/main/ets/pages/Index.ets'),artifacts.caller_sources(spec)['compiled_page']['sha256'])
            (project/'hvigorfile.ts').write_text('changed after compile')
            with self.assertRaises(ValueError):artifacts.caller_sources(spec)

    def test_query_signer_exact_role_keeps_empty_acl(self):
        profile={'bundle-info':{},'debug-info':{},'acls':{'allowed-acls':['unrelated']},'permissions':{'restricted-permissions':['unrelated']}}
        module={'app':{'bundleName':coordinator.QUERY},'module':{'requestPermissions':[{'name':coordinator.READ,'reason':'actual'}]}}
        actual=suite.query_profile(copy.deepcopy(profile),'query','a'*64,module)
        self.assertEqual('system_basic',actual['bundle-info']['apl']);self.assertEqual([],actual['acls']['allowed-acls'])
        for mutate in (lambda v:v['app'].update(bundleName=coordinator.SEED),lambda v:v['module']['requestPermissions'].append({'name':coordinator.SET})):
            bad=copy.deepcopy(module);mutate(bad)
            with self.assertRaises(ValueError):suite.query_profile(copy.deepcopy(profile),'query','a'*64,bad)

    def test_source_plan_uses_dynamic_nodes_and_actual_bms_ability(self):
        plan={'settings_ability':'MainAbility','photos_ability':'MainAbility','photos_main':{'identifier':'actual-source-gallery-marker'},
              'screens':{'desktop':{'bundle':'com.ohos.sceneboard','identifier':'SCBDesktop_Flex_Desktop'},
                         'lock':{'bundle':'com.ohos.sceneboard','identifier':'ScreenLockRootComponent'}}}
        actual=suite.validate_plan(plan);self.assertEqual('theme_settings',actual['settings_navigation'][0]['identifier'])
        bad=copy.deepcopy(plan);bad['photos_main']={'x':120,'y':42}
        with self.assertRaises(ValueError):suite.validate_plan(bad)
        dump={'applicationInfo':{'name':coordinator.PHOTOS},'hapModuleInfos':[{'abilityInfos':[{'name':'MainAbility'}]}]}
        suite.declared_ability(json.dumps(dump),coordinator.PHOTOS,'MainAbility')
        with self.assertRaises(ValueError):suite.declared_ability(json.dumps(dump),coordinator.PHOTOS,'InventedAbility')

    def test_first_phone_plan_is_bound_to_frozen_source_ids_not_coordinates(self):
        root=coordinator.FIXTURE;plan=suite.validate_plan(json.loads((root/'phone-ui-plan.json').read_text()))
        source=json.loads((root/'ui-source-contract.json').read_text());text=json.dumps(source)
        self.assertEqual('com.ohos.photos.MainAbility',plan['photos_ability']);self.assertEqual('TabPhotos',plan['photos_main']['identifier'])
        self.assertIn(".id('TabPhotos')",text);self.assertIn("THEME_ENTRY = 'theme_settings'",text)
        transport=PowerTransport(Path(tempfile.gettempdir()),None)
        # Invoke the real coordinator getter/parser path on explicit host
        # PowerMgr unit text; this remains a unit test, not actual guest state.
        with tempfile.TemporaryDirectory()as temp:
            transport.output=Path(temp);value=coordinator.Coordinator.power_state(transport,'actual-getter-fixture')
            self.assertEqual({'base_ms':30000,'override_ms':None},value['state'])

    def test_only_owned_power_override_paused_and_exactly_resumed(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);boot=root/'main-boot.json';boot.write_text(json.dumps(boot_value('a'*64)))
            snapshot=root/'stable-boot.json';snapshot.write_bytes(boot.read_bytes())
            owner=root/'parent.json';before={'base_ms':30000,'override_ms':None};setup=dict(before,override_ms=86400000)
            value={'scope':'new_packaged_qemu_behavior','package':{'sha256':'a'*64},'checks':{'boot':{'evidence':str(boot),'sha256':sha(boot)}},
                'application_test_setup':{'method':'existing_power-shell_development_override','restored':False,'policy_states':{'before':before,'setup':setup}}}
            owner.write_text(json.dumps(value));transport=PowerTransport(root);report={};policy=suite.OwnedPolicy(transport,owner,report)
            policy.suspend('a'*64,boot_value('a'*64)['test_environment']['boot_id'],snapshot)
            self.assertIsNone(transport.override);owner.write_text('parent continues updating report')
            self.assertEqual(value,json.loads(Path(report['owner']['path']).read_text()))
            policy.restore();self.assertEqual(86400000,transport.override);self.assertTrue(report['restored'])
            transport=PowerTransport(root,1234);policy=suite.OwnedPolicy(transport,None,{})
            with self.assertRaises(ValueError):policy.suspend('a'*64,'boot',snapshot)
            self.assertFalse(policy.restorable);self.assertFalse(any(c.startswith('power-shell')for c in transport.commands))

    def test_pair_actual_host_success_and_peer_cancellation_retains_logs(self):
        # These are tiny real host processes, not fake guest execution.
        for fail in (False,True):
            with tempfile.TemporaryDirectory()as temp:
                root=Path(temp);script="from pathlib import Path; import time; p=Path("+repr(str(root/'runtime'))+"); p.mkdir(); (p/'runtime.json').write_text('{}'); print('host caller started',flush=True); time.sleep("+('10'if fail else'.15')+")"
                runtime=[sys.executable,'-c',script];peer=[sys.executable,'-c','raise SystemExit('+('7'if fail else'0')+')']
                if fail:
                    with self.assertRaises(ValueError):suite.run_pair(runtime,peer,root,3)
                    rows=json.loads((root/'child-processes.json').read_text());self.assertEqual(7,rows[1]['exit_code']);self.assertNotEqual(0,rows[0]['exit_code'])
                else:self.assertEqual([0,0],[r['exit_code']for r in suite.run_pair(runtime,peer,root,3)])
                self.assertIn('host caller started',(root/'runtime-process.log').read_text())

    @staticmethod
    def elf():
        # Constructed parser unit bytes only. Never executed or compile evidence.
        data=bytearray(512);data[:7]=b'\x7fELF\x02\x01\x01';struct.pack_into('<HH',data,16,3,183)
        struct.pack_into('<Q',data,32,64);struct.pack_into('<HH',data,54,56,3)
        struct.pack_into('<IIQQQQQQ',data,64,1,4,0,0x100000,0,512,512,4096)
        interpreter=b'/lib/ld-musl-aarch64.so.1\0';data[240:240+len(interpreter)]=interpreter
        struct.pack_into('<IIQQQQQQ',data,120,3,4,240,0,0,len(interpreter),len(interpreter),1)
        struct.pack_into('<IIQQQQQQ',data,176,2,4,288,0,0,64,64,8)
        strings=b'\0libaccesstoken_sdk.z.so\0';data[400:400+len(strings)]=strings
        for i,(tag,value)in enumerate([(1,1),(5,0x100000+400),(10,len(strings)),(0,0)]):struct.pack_into('<qQ',data,288+i*16,tag,value)
        return data

    def test_actual_elf_dependency_parser_rejects_wrong_machine_and_truncation(self):
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp)/'elf';data=self.elf();path.write_bytes(data)
            self.assertEqual(['libaccesstoken_sdk.z.so'],artifacts.elf_dependencies(path))
            data[18:20]=(62).to_bytes(2,'little');path.write_bytes(data)
            with self.assertRaises(ValueError):artifacts.elf_dependencies(path)
            path.write_bytes(self.elf()[:480])
            with self.assertRaises(ValueError):artifacts.elf_dependencies(path)

    def test_bare_helper_and_status_only_receipt_never_pass(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);path=root/'fake.json';path.write_text(json.dumps({'status':'pass'}))
            binary=root/'elf';binary.write_bytes(self.elf());source=root/'source';source.write_text('unit fixture')
            with self.assertRaises((KeyError,ValueError)):artifacts.verify_helper_receipt('token',binary,source,record(path))
            archive=root/'archive';archive.write_bytes(b'unit archive');boot=root/'boot';boot.write_text(json.dumps(boot_value(sha(archive))))
            with self.assertRaises((KeyError,ValueError)):suite.verify_evidence(path,archive,boot)

    def test_mutable_journal_updates_but_never_overwrites_raw_signing_receipt(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);path=root/'evidence.json'
            suite.save_report(path,{'status':'running'});suite.save_report(path,{'status':'fail','cleanup_complete':True})
            self.assertEqual('fail',json.loads(path.read_text())['status'])
            linked=root/'hardlink';os.link(path,linked)
            with self.assertRaises(ValueError):suite.save_report(path,{})
            linked.unlink();path.unlink();path.symlink_to(linked)
            with self.assertRaises(ValueError):suite.save_report(path,{})
            # Existing query sign_certificate receipt is retained; adapter has
            # its own name and the shared raw writer stays exclusive.
            original=root/'query-signed.signing.json';original.write_text('original actual receipt fixture')
            before=sha(original);adapter=root/'query-coordinator-signing.json'
            suite.write_json(adapter,{'actual_original':record(original)})
            self.assertEqual(before,sha(original))

    def test_private_artifact_path_map_preserves_hash_and_never_maps_linux_source(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);path=root/'compile.log';path.write_text('unit log')
            old={'path':'/evidence/helpers/compile.log','sha256':sha(path)}
            actual=artifacts.mapped_record(old,{'/evidence/helpers':str(root)})
            self.assertEqual(record(path),actual);self.assertEqual('/evidence/helpers/compile.log',old['path'])
            path.write_text('tampered')
            with self.assertRaises(ValueError):artifacts.mapped_record(old,{'/evidence/helpers':str(root)})
            with self.assertRaises(ValueError):artifacts.mapped_record(old,{'/ohos':str(root)})

    def test_complete_helper_receipt_binds_binary_logs_and_recorded_dso_inputs(self):
        # Constructed source/ELF/logs exercise the adapter only, never a real
        # compiler, CFI implementation, product library or guest capability.
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);builder=root/'batch_system_build_runtime_helpers.py';builder.write_text('# host receipt oracle only')
            source=root/'fixtures/batch_media/wallpaper_receipts/token_query.cpp';source.parent.mkdir(parents=True);source.write_text('unit fixture')
            binary=root/'wallpaper_token_query';binary.write_bytes(self.elf());commands=[]
            for kind in ('compile','link','actual-ELF-ABI'):
                log=root/(kind+'.log');log.write_text('unit observation '+kind)
                commands.append({'label':'wallpaper_token_query-'+kind,'argv':['fixture-tool',kind],
                    'exit_code':0,'log':str(log),'sha256':sha(log)})
            dso={'path':'/ohos/out/arm64_virt/security/libaccesstoken_sdk.z.so','sha256':'d'*64}
            row={'status':'pass_compile_link_ONLY','fixture':'batch_media/wallpaper_receipts/token_query.cpp',
                'source':record(source),'private_source_sha256':sha(source),'binary_sha256':sha(binary),
                'CFI_preserved':True,'runtime_validated':False,'DT_NEEDED':['libaccesstoken_sdk.z.so'],
                'elf':{'sha256':sha(binary)},'linked_libraries':[dso],'actual_link_inputs':[dso],
                'compile_command':commands[0]['argv'],'link_command':commands[1]['argv']}
            original={'scope':'diagnostic_new_helpers_using_existing_actual_product_GN_flags_NOT_fresh_GN_target_selection_or_runtime',
                'product':'arm64_virt','plan_only':False,'changed_inputs':[],'builder_sha256':sha(builder),
                'first_artifact_behavior_gate_passed':False,'helpers':{'wallpaper_token_query':row},'commands':commands,'inputs':{dso['path']:dso}}
            report=root/'build.json'
            with patch.object(artifacts,'HERE',root):
                report.write_text(json.dumps(original))
                self.assertEqual('d'*64,artifacts.helper_binding('token',binary,source,record(report),root)['product_DSOs'][0]['sha256'])
                changes=[lambda v:v.update(changed_inputs=['changed']),lambda v:v['helpers']['wallpaper_token_query'].update(status='fail'),
                         lambda v:v['helpers']['wallpaper_token_query'].update(private_source_sha256='0'*64),
                         lambda v:v['commands'][0].update(exit_code=1),lambda v:v['inputs'].clear()]
                for change in changes:
                    value=copy.deepcopy(original);change(value);report.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):artifacts.helper_binding('token',binary,source,record(report),root)
                original['status']='fail';original['helpers']['wallpaper_token_query']['status']='fail'
                report.write_text(json.dumps(original));original_hash=sha(report)
                recheck=copy.deepcopy(original);recheck.update(verify_existing=True,
                    scope='read_only_recheck_of_prior_compile_link_artifacts_and_actual_product_DSO_ELF_ONLY_NOT_runtime',
                    original_report={**record(report),'status':'fail','builder_sha256':original['builder_sha256'],'rewritten':False},
                    original_commands=[dict(c,verified_log={'path':c['log'],'sha256':c['sha256']})for c in commands],
                    commands=[commands[2]])
                recheck['helpers']['wallpaper_token_query'].update(status='pass_compile_link_ONLY',
                    reused_artifacts={'binary':record(binary),'source':record(source)})
                path=root/'recheck.json';path.write_text(json.dumps(recheck))
                self.assertEqual('fail',artifacts.helper_binding('token',binary,source,record(path),root)['original_build_status'])
                self.assertEqual(original_hash,sha(report))
                recheck['original_report']['rewritten']=True;path.write_text(json.dumps(recheck))
                with self.assertRaises(ValueError):artifacts.helper_binding('token',binary,source,record(path),root)

    def test_exact_layout_transition_only_and_cleanup_failure_markers(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);marker='__UITEST_EXIT_'+'a'*32+'__='
            remote='/data/local/tmp/qemu-capability-ui-'+'b'*32+'-1.json'
            script='test ! -e '+remote+' && uitest dumpLayout -p '+remote+'; task_ui_rc=$?; printf trailing'
            # Exact nonce text still must be present in actual command argv.
            script+=' '+marker
            path=root/'actual.log';path.write_text('DumpLayout failed:Get window nodes failed\n'+marker+'1\n')
            row={'argv':['hdc','-t','127.0.0.1:12','shell',script],'exit_code':0,**record(path)}
            suite.verify_guest_commands([row],'127.0.0.1:12')
            for text in ('another failure','DumpLayout failed:Get window nodes failed\nextra output'):
                path.write_text(text+'\n'+marker+'1\n');row.update(record(path))
                with self.assertRaises(ValueError):suite.verify_guest_commands([row],'127.0.0.1:12')
            path.write_text('cleanup failed\n'+marker+'7\n');row.update(record(path));row['argv'][4]='rm /only-owned; '+marker
            with self.assertRaises(ValueError):suite.verify_guest_commands([row],'127.0.0.1:12')


if __name__=='__main__':unittest.main()
