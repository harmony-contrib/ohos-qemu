"""Tiny host protocol fixtures; not native build, image or guest evidence."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_media_wallpaper_native as native
from batch_media_wallpaper_runtime import record
from test_batch_media_wallpaper_suite import boot_value


HDC = '/host-only/pinned-hdc'  # Explicit host fixture pin; never a real guest executor.

def checksum(value): return hashlib.sha256(value).hexdigest()


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve()
        self.guard=SimpleNamespace(__file__=__file__,check_inventory=lambda *args:args[0],image=self.image)
        self.image_calls=0

    def image(self,system,directory,product):
        self.image_calls+=1
        self.assertEqual(b'HOST IMAGE FIXTURE ONLY',system.read_bytes())
        self.assertEqual('arm64_virt',product)
        self.assertEqual({'host_fixture':True},json.loads((directory/'inventory.json').read_text()))
        return self.image_value

    def package(self,mutate=None,extras=()):
        payload={'wallpaper-native/'+name:(b'HOST NATIVE FIXTURE ONLY'if name!= 'inventory.json'else b'{"host_fixture":true}')
                 for name in native.PAYLOADS}
        payload['manifest.json']=b'{}';payload['build-inputs.json']=b'{}'
        payload['contacts-theme-provider-evidence.json']=b'{"host_fixture":true}'
        payload['images/system.img']=b'HOST IMAGE FIXTURE ONLY'
        self.image_value={'status':'pass','scope':'fixture_only','product':'arm64_virt',
            'system_image_sha256':checksum(payload['images/system.img']),
            'inventory_sha256':checksum(payload['wallpaper-native/inventory.json']),
            'library_sha256':checksum(payload['wallpaper-native/'+native.LIBRARY]),
            'image_entry':{'image_path':'/lib64/'+native.LIBRARY,'image_inode':23},
            'first_artifact_behavior_gate_passed':False}
        payload['wallpaper-native-image-evidence.json']=json.dumps(self.image_value).encode()
        if mutate:mutate(payload)
        payload['SHA256SUMS']=''.join(checksum(data)+'  '+name+'\n'for name,data in payload.items()).encode()
        archive=self.root/'fixture.tar.gz'
        with tarfile.open(archive,'w:gz')as stream:
            for name,data in list(payload.items())+list(extras):
                item=tarfile.TarInfo('fixture/'+name);item.size=len(data);stream.addfile(item,io.BytesIO(data))
        extracted=self.root/'boot-extracted';(extracted/'images').mkdir(parents=True)
        (extracted/'images/system.img').write_bytes(b'HOST IMAGE FIXTURE ONLY')
        boot=boot_value(native.digest(archive));boot['initial_package_file_sha256']={k:checksum(v)for k,v in payload.items()}
        boot['test_environment'].update(freshly_extracted_directory=str(extracted))
        boot['test_environment']['qemu_command']+=' '+str(extracted/'images/system.img')
        boot_path=self.root/'boot.json';boot_path.write_text(json.dumps(boot))
        return archive,boot_path,payload

    def verify(self,archive,boot,output='native'):
        with patch.object(native,'native_guard',return_value=self.guard):
            return native.archive_native(archive,boot,self.root/output)

    def test_public_inventory_and_image_are_called_again_on_each_replay(self):
        archive,boot,_=self.package();calls=[]
        self.guard.check_inventory=lambda *args:calls.append(args[1])or args[0]
        actual=self.verify(archive,boot);self.assertEqual(actual,self.verify(archive,boot,'native-replay'))
        self.assertEqual(['arm64_virt','arm64_virt'],calls);self.assertEqual(2,self.image_calls)
        self.assertFalse(actual['service_token_to_pid_directly_observed'])

    def test_missing_native_payload_cannot_use_summary_pass(self):
        archive,boot,_=self.package(lambda p:p.pop('wallpaper-native/witness.json'))
        with self.assertRaises(ValueError):self.verify(archive,boot)
        self.assertEqual(0,self.image_calls)

    def test_payload_contract_matches_public_guard_with_both_query_receipts(self):
        self.assertEqual(native.PAYLOADS, native.native_guard().PAYLOADS | {'inventory.json'})

    def test_missing_original_build_stdout_is_rejected_before_image_replay(self):
        archive,boot,_=self.package(lambda p:p.pop('wallpaper-native/build-theme-service-args.txt'))
        with self.assertRaises(ValueError):self.verify(archive,boot)
        self.assertEqual(0,self.image_calls)

    def test_missing_package_query_receipt_is_rejected_before_image_replay(self):
        archive,boot,_=self.package(lambda p:p.pop('wallpaper-native/theme-service-query.json'))
        with self.assertRaises(ValueError):self.verify(archive,boot)
        self.assertEqual(0,self.image_calls)

    def test_old_extracted_image_rejected_before_public_image_checker(self):
        archive,boot,_=self.package();(self.root/'boot-extracted/images/system.img').write_bytes(b'OLD')
        with self.assertRaises(ValueError):self.verify(archive,boot)
        self.assertEqual(0,self.image_calls)

    def test_old_initial_boot_checksums_rejected(self):
        archive,boot,_=self.package();value=json.loads(boot.read_text())
        value['initial_package_file_sha256']['wallpaper-native/witness.json']='0'*64;boot.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.verify(archive,boot)

    def test_image_not_in_qemu_argv_rejected(self):
        archive,boot,_=self.package();value=json.loads(boot.read_text())
        value['test_environment']['qemu_command']='qemu -qmp unix:/tmp/fixture-qmp';boot.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.verify(archive,boot)

    def test_similarly_named_qemu_image_cannot_borrow_original_image_hash(self):
        archive,boot,_=self.package();value=json.loads(boot.read_text())
        value['test_environment']['qemu_command']+='.old';boot.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.verify(archive,boot)

    def test_public_guard_failure_cannot_fall_back_to_packaged_status(self):
        archive,boot,_=self.package();self.guard.check_inventory=lambda *args:(_ for _ in ()).throw(ValueError('CFI/GN rejected'))
        with self.assertRaisesRegex(ValueError,'CFI/GN'):self.verify(archive,boot)

    def test_packaged_image_summary_must_equal_actual_redump(self):
        archive,boot,_=self.package();self.image_value['image_entry']['image_inode']=24
        with self.assertRaisesRegex(ValueError,'re-dump'):self.verify(archive,boot)

    def test_extra_payload_or_alias_is_rejected(self):
        archive,boot,_=self.package(extras=[('wallpaper-native/another.so',b'wrong')])
        with self.assertRaises(ValueError):self.verify(archive,boot)

    def test_symlink_archive_is_rejected(self):
        archive,boot,_=self.package();link=self.root/'linked.tar.gz';link.symlink_to(archive)
        with self.assertRaises(ValueError):self.verify(link,boot)

    def map_fixture(self):
        from test_batch_runtime_process_snapshots import BOOT, frame, hx, queries
        request={'nonce':'a'*32,'sequence':6,'boot_id':BOOT,'action':'show-real-desktop','details':{'case':'desktop-1'}}
        proof={'boot_id':BOOT,'library_guest_path':'/system/lib64/'+native.LIBRARY,'image':{'library_sha256':'b'*64}}
        maps=('7f000000-7f001000 r--p 00000000 08:01 23      '+proof['library_guest_path']+'\n'+
              '7f001000-7f002000 r-xp 00001000 08:01 23      '+proof['library_guest_path']+'\n')
        records={1:queries(1,mode='maps',ppid=0),21:queries(21,mode='maps',exe='/system/bin/sa_main',
            uid=1000,start=12345,argv=['/system/bin/sa_main','/system/profile/wallpaper.json'],maps=maps)}
        direct={stage+'-'+kind:(0,hx('2049 23 65536' if kind=='stat' else 'b'*64+'  '+proof['library_guest_path']))
                for stage in ('file-before','file-after') for kind in ('stat','hash')}
        return request,proof,frame(mode='maps',records=records,direct=direct).removesuffix('\n')

    def test_maps_actual_inode_device_executable_uid_and_process_generation(self):
        request,proof,raw=self.map_fixture(); actual=native.parse_maps(raw,request,proof)
        self.assertEqual((21,1000,12345),(actual['pid'],actual['uid'],actual['process_start_ticks']))
        self.assertEqual(2,len(actual['mappings'])); self.assertFalse(actual['service_token_to_pid_directly_observed'])
        script=native.maps_script(request,proof)
        self.assertNotIn('| tr',script); self.assertNotIn('tr "',script)
        # Parsing only, never the actual host /proc scan.
        checked=subprocess.run(['/bin/sh','-n'],input=script,text=True,capture_output=True)
        self.assertEqual(0,checked.returncode,checked.stderr)

    def test_maps_adapter_matches_actual_guestui_raw_and_rejects_suffixes(self):
        import guest_ui
        request,proof,raw=self.map_fixture(); ui=guest_ui.GuestUi.__new__(guest_ui.GuestUi)
        ui.hdc='/host-only/hdc'; ui.target='bound-target'; marker='__UITEST_EXIT_'+'d'*32+'__='
        argv=[]
        def command(values,label):
            argv.append(values)
            return raw+'\n\n'+marker+'0\n'
        ui.command=command
        with patch.object(guest_ui.secrets,'token_hex',return_value='d'*32):
            observed=ui.shell(native.maps_script(request,proof),'host-transport-fixture')
        self.assertEqual(observed,raw)
        self.assertEqual(native.parse_maps(observed,request,proof)['pid'],21)
        self.assertEqual(argv[0][1:4],['-t','bound-target','shell'])
        for suffix in ('\n','\n\n','\r',' ','\t','\v'):
            with self.subTest(suffix=repr(suffix)),self.assertRaises(ValueError):
                native.parse_maps(raw+suffix,request,proof)
        with self.assertRaises(ValueError): native.parse_maps(raw[:-1],request,proof)

    def test_bad_maps_nonce_boot_hash_inode_device_uid_noexec_deleted_rejected(self):
        from test_batch_runtime_process_snapshots import replace_payload
        request,proof,raw=self.map_fixture()
        for old,new in [('b'*64,'c'*64),('08:01 23','08:01 24'),('08:01 23','08:02 23'),
                        ('Uid:\t1000\t1000\t1000\t1000','Uid:\t20000000\t20000000\t20000000\t20000000'),
                        ('r-xp','r--p'),(proof['library_guest_path']+'\n',proof['library_guest_path']+' (deleted)\n')]:
            with self.subTest(new=new),self.assertRaises(ValueError): native.parse_maps(replace_payload(raw,old,new).removesuffix('\n'),request,proof)
        for value in (raw.replace(request['nonce'],'c'*32,1),raw.replace(request['boot_id'],'22222222-2222-2222-2222-222222222222'),raw.rsplit('END|',1)[0]):
            with self.assertRaises(ValueError): native.parse_maps(value,request,proof)

    def test_native_process_cannot_change_generation_during_mapping_read(self):
        request,proof,raw=self.map_fixture(); lines=raw.splitlines()
        for i,line in enumerate(lines):
            if line.startswith('Q|21|stat_after|0|'):
                fields=line.split('|'); fields[4]=bytes.fromhex(fields[4]).replace(b'12345',b'12346').hex(); lines[i]='|'.join(fields)
        with self.assertRaisesRegex(ValueError,'generation changed'): native.parse_maps('\n'.join(lines),request,proof)

    def test_only_two_public_challenge_desktop_requests_collect_read_only_witnesses(self):
        import batch_media_wallpaper_coordinator as coordinator
        owner=coordinator.Coordinator.__new__(coordinator.Coordinator); calls=[]; owner.home=lambda:calls.append('home')
        with (patch.object(native,'observe_maps',side_effect=lambda *args:calls.append('maps')),
              patch.object(native,'observe_renderer_hap',side_effect=lambda *args:calls.append('HAP'))):
            for case in ('desktop-1','desktop-2','desktop-restore'):
                owner.dispatch({'action':'show-real-desktop','details':{'case':case}})
        self.assertEqual(['home','maps','HAP','home','maps','HAP','home'],calls)

    def test_two_mapped_processes_are_not_arbitrarily_selected(self):
        request,proof,raw=self.map_fixture(); block=raw[raw.index('PID|21\n'):raw.index('TERMINAL|21|')]
        with self.assertRaises(ValueError): native.parse_maps(raw.replace(block,block+block),request,proof)

    def mapping_protocol(self):
        request,proof,raw=self.map_fixture();rows=[];actions=[];commands=[]
        for sequence,case in enumerate(('desktop-1','desktop-2'),6):
            item=copy.deepcopy(request);item.update(sequence=sequence,nonce=format(sequence,'032x'));item['details']['case']=case
            path=self.root/(case+'.request.json');path.write_text(json.dumps(item))
            actual_raw=raw.replace(request['nonce'],item['nonce']);artifact=self.root/(case+'.txt');artifact.write_text(actual_raw)
            marker='__UITEST_EXIT_'+format(sequence,'032x')+'__='
            log=self.root/(case+'.log');log.write_text(actual_raw+'\n\n'+marker+'0\n')
            commands.append({'label':case+'-native-maps-scan-0','argv':[HDC,'-t','127.0.0.1:12345','shell',
                native.maps_script(item,proof)+'; task_ui_rc=$?; printf "\\n'+marker+'%s\\n" "$task_ui_rc"'],
                'exit_code':0,**record(log)})
            rows.append({'case':case,'nonce':item['nonce'],'sequence':sequence,'began_ns':20,'finished_ns':30,
                'capture_label':case+'-native-maps-scan-0','raw':record(artifact),'parsed':native.parse_maps(actual_raw,item,proof)})
            actions.append({'sequence':sequence,'request':record(path),'began_ns':10,'finished_ns':40})
        return {'hdc':HDC,'native_mappings':rows,'commands':commands,'actions':actions},proof

    def installed_protocol(self,coo):
        image=self.root/'image-provider.hap';image.write_bytes(b'HOST HAP FIXTURE ONLY')
        rows=[];remote='/system/app/com.ohos.wallpaper/Wallpaper.hap';uid=20010012
        def raw(label,script,text):
            path=self.root/(label+'.txt');path.write_text(text)
            log=self.root/(label+'.log');marker='__UITEST_EXIT_'+'d'*32+'__='
            log.write_text(text+'\n'+marker+'0\n')
            coo['commands'].append({'label':label,'exit_code':0,**record(log),
                'argv':[HDC,'-t','127.0.0.1:12345','shell',script+'; task_ui_rc=$?; printf "\\n'+marker+'%s\\n" "$task_ui_rc"']})
            return record(path)
        for index,case in enumerate(('desktop-1','desktop-2'),6):
            label=case+'-renderer-installed';copied=self.root/(case+'.hap');copied.write_bytes(image.read_bytes())
            bms=raw(label+'-BMS','bm dump -n com.ohos.wallpaper',json.dumps({'appInfo':{
                'bundleName':'com.ohos.wallpaper','isSystemApp':True,'uid':uid},'hapModuleInfos':[{'hapPath':remote}]}))
            stat='1000 1000 644 '+str(image.stat().st_size)+' 1 5\n'+native.digest(image)+'  '+remote
            transfer={'remote':remote,'file':record(copied),'before':raw(label+'-HAP-stat',native.hap_stat_script(remote),stat),
                'after':raw(label+'-HAP-stat-after',native.hap_stat_script(remote),stat)}
            log=self.root/(label+'-recv.log');log.write_text('FileTransfer finish')
            coo['commands'].append({'label':label+'-HAP-recv','exit_code':0,**record(log),
                'argv':[HDC,'-t','127.0.0.1:12345','file','recv',remote,str(copied)]})
            rows.append({'case':case,'sequence':index,'nonce':format(index,'032x'),'began_ns':20,'finished_ns':30,
                'BMS':bms,'uid':uid,'transfer':transfer})
        coo['renderer_installed_haps']=rows
        return image

    def test_installed_renderer_hap_actual_bms_path_transfer_and_image_bytes(self):
        coo,proof=self.mapping_protocol();image=self.installed_protocol(coo)
        result=native.verify_renderer_haps(coo,proof,image,target='127.0.0.1:12345')
        self.assertEqual(['desktop-1','desktop-2'],[r['case']for r in result])
        self.assertEqual(20010012,result[0]['uid'])
        for change in (lambda v:v['renderer_installed_haps'][0].update(uid=20010013),
                       lambda v:v['renderer_installed_haps'][0].update(began_ns=9),
                       lambda v:v['renderer_installed_haps'][0].update(nonce='f'*32),
                       lambda v:v['renderer_installed_haps'][0]['transfer'].update(remote='/data/app/wrong.hap'),
                       lambda v:v.update(renderer_installed_haps=v['renderer_installed_haps'][:1])):
            bad=copy.deepcopy(coo);change(bad)
            with self.assertRaises(ValueError):native.verify_renderer_haps(bad,proof,image,target='127.0.0.1:12345')
        image.write_bytes(b'ANOTHER SIGNED IMAGE')
        with self.assertRaisesRegex(ValueError,'source-bound image'):native.verify_renderer_haps(coo,proof,image,target='127.0.0.1:12345')

    def test_installed_renderer_does_not_accept_another_bundle_or_ordinary_bms(self):
        for path in ('/data/app/el1/bundle/public/other/entry.hap','/system/app/com.ohos.wallpaper/../other.hap',
                     '/system/app/com.ohos.wallpaper//Wallpaper.hap'):
            raw=json.dumps({'appInfo':{'bundleName':'com.ohos.wallpaper','isSystemApp':True,'uid':20010012},'hapPath':path})
            with self.assertRaises(ValueError):native.renderer_path(raw)
        with self.assertRaises(ValueError):native.renderer_path(json.dumps({'appInfo':{'bundleName':'com.ohos.wallpaper',
            'isSystemApp':False,'uid':20010012},'hapPath':'/system/app/com.ohos.wallpaper/Wallpaper.hap'}))

    def test_mapping_ack_interval_and_exact_real_transport_replay(self):
        coo,proof=self.mapping_protocol();actual=native.verify_mappings(coo,proof,target='127.0.0.1:12345')
        self.assertEqual(2,len(actual['stages']))
        for bad in (lambda c:c['native_mappings'][0].update(began_ns=9),
                    lambda c:c['native_mappings'][0].update(finished_ns=41),
                    lambda c:c['native_mappings'][0].update(nonce='f'*32),
                    lambda c:c['native_mappings'][0]['parsed'].update(pid=22),
                    lambda c:c['commands'][0]['argv'].__setitem__(2,'127.0.0.1:54321'),
                    lambda c:c['commands'][0].update(exit_code=1),
                    lambda c:c.update(native_mappings=c['native_mappings'][:1])):
            value=copy.deepcopy(coo);bad(value)
            with self.assertRaises(ValueError):native.verify_mappings(value,proof,target='127.0.0.1:12345')

    def test_wrapper_composes_actual_connection_parser_and_native_mapping_oracles(self):
        import batch_media_wallpaper_suite as suite
        import batch_apps_wallpaper_connection as connections
        coo,proof=self.mapping_protocol();runtime={'hdc':HDC,'commands':[],'stages':[]};target='127.0.0.1:12345'
        provider_hap=self.installed_protocol(coo)
        def raw(label,script,text):
            path=self.root/(label+'.raw');path.write_text(text)
            log=self.root/(label+'.transport');marker='__UITEST_EXIT_'+'c'*32+'__='
            log.write_text(text+'\n'+marker+'0\n')
            runtime['commands'].append({'label':label,'exit_code':0,**record(log),
                'argv':[HDC,'-t',target,'shell',script+'; task_ui_rc=$?; printf "\\n'+marker+'%s\\n" "$task_ui_rc"']})
            return record(path)
        runtime['renderer_identity']=raw('renderer-BMS','bm dump -n com.ohos.wallpaper',json.dumps({
            'appInfo':{'bundleName':'com.ohos.wallpaper','isSystemApp':True,'uid':20010012}}))
        ams='''  ExtensionRecords:
    uri [/com.ohos.wallpaper/phone_wallpaper/WallpaperExtAbility]
      AbilityRecord ID #0   state #INACTIVE   start time [1234]
      main name [WallpaperExtAbility]
      bundle name [com.ohos.wallpaper]
      ability type [SERVICE]
      Connections: 1
       > com.ohos.wallpaper/WallpaperExtAbility   connectionState #CONNECTED
  AppRunningRecords:
    AppRunningRecord ID #0
      process name [com.ohos.wallpaper]
      pid #2345  uid #20010012'''
        for case in ('desktop-1','desktop-2'):
            runtime['stages'].append({'name':case,'started_ns':50,'finished_ns':60,
                'ams':raw(case+'-AMS','aa dump -a -u 100',ams),
                'renderer_pids':raw(case+'-renderer-pid','pidof com.ohos.wallpaper','2345')})
        runtime_path=self.root/'runtime.json';runtime_path.write_text(json.dumps(runtime))
        connection_path=self.root/'connections.json';connection_path.write_text(json.dumps(connections.verify_runtime_connections(runtime_path,target=target)))
        mapping_path=self.root/'mappings.json';mapping_path.write_text(json.dumps(native.verify_mappings(coo,proof,target=target)))
        value={'runtime':record(runtime_path),'connection_verifier':record(connections.__file__),
            'native_connections':record(connection_path),'native_mappings':record(mapping_path),
            'renderer_provider':{'hap':record(provider_hap)}}
        actual=suite.verify_native_runtime(value,coo,proof,{'target':target,'device_type':'phone'})
        # Actual service-host PID and renderer PID are distinct observations.
        self.assertEqual(21,actual['mappings']['stages'][0]['pid'])
        self.assertEqual(2345,actual['connections']['stages'][0]['pid'])
        self.assertFalse(actual['connections']['service_token_to_pid_directly_observed'])
        bad=copy.deepcopy(coo);bad['native_mappings'][0]['parsed']['pid']=2345
        with self.assertRaises(ValueError):suite.verify_native_runtime(value,bad,proof,{'target':target,'device_type':'phone'})
        runtime['stages'].pop();runtime_path.write_text(json.dumps(runtime));value['runtime']=record(runtime_path)
        with self.assertRaises(ValueError):suite.verify_native_runtime(value,coo,proof,{'target':target,'device_type':'phone'})

    def test_source_provider_proof_cannot_borrow_another_archive_guard_or_sdk(self):
        import batch_media_wallpaper_suite as suite
        image=self.root/'source-image.hap';image.write_bytes(b'host-source-image')
        profile=self.root/'profile.p7b';profile.write_bytes(b'host-profile')
        native_proof={'system_image':{'path':'/fixture/system.img','sha256':'a'*64},
            'files_sha256':{'contacts-theme-provider-evidence.json':'b'*64}}
        actual={'hap':record(image),'embedded_profile':record(profile),'system_image':native_proof['system_image'],
            'archive_guard':{'path':'/fixture/provider.json','sha256':'b'*64},'sdk':{'fixture':'bound source inventory'},
            'image_identity':{'image_inode':23},'signer_inputs':{'fixed':'crypto input'},
            'production':{'scope':'HOST-ONLY actual native unsigned/signed lineage fixture'}}
        suite.verify_provider_proof(actual,copy.deepcopy(actual),native_proof)
        for key in ('system_image','archive_guard','sdk','production','image_identity','signer_inputs'):
            bad=copy.deepcopy(actual);bad[key]={}
            with self.assertRaises(ValueError):suite.verify_provider_proof(bad,actual,native_proof)
        changed=copy.deepcopy(native_proof);changed['files_sha256']['contacts-theme-provider-evidence.json']='c'*64
        with self.assertRaises(ValueError):suite.verify_provider_proof(actual,actual,changed)


if __name__=='__main__':unittest.main()
