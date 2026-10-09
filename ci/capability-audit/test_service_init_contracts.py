"""Negative fixtures cannot replace actual new-package init/runtime evidence."""
from copy import deepcopy
import json
import unittest
from pathlib import Path
import tempfile
from run_root_probe import digest
from verify_service_init_contracts import FUSION,FUSION_CFG,I18N_CFG,I18N_DIRECTORIES,verify,verify_evidence,verify_load_results,verify_parameter_access,PARAMETER_DOMAINS,PARAMETER_CONTEXTS,PARTNER_PARAMETER

def fixture():
    passwd='i18n:x:3013:3013:::/bin/false\n'
    group='i18n:x:3013:\n'
    configs={}
    configs[PARAMETER_CONTEXTS]=PARTNER_PARAMETER+' u:object_r:fusion_partner_enable_param:s0\n'
    ownership={}
    serial=''
    hilog=''
    for index,(name,uid,sa) in enumerate(FUSION):
        passwd+=f'{name}:x:{uid}:{uid}:::/bin/false\n'
        group+=f'{name}:x:{uid}:\n'
        configs[FUSION_CFG[name]]=json.dumps({'services':[{'name':name,'uid':name,'gid':[name,'shell'],
            'path':['/system/bin/sa_main','/system/profile/'+name+'.json'],'ondemand':True,'secon':'u:r:'+name+':s0'}]})
        ownership['/data/service/el1/public/'+name]=f'{uid}:{uid}:711:directory'
        pid=1234+index
        serial+=f'[pid=1] ServiceStart started info {name}(pid {pid} uid {uid})\n'
        serial+=f'[pid={pid}] ServiceExec {name}\nSAMGR: Start dynamic proc:{name},{sa},0_4ms\n'
        serial+=f'SAMGR: insert SA:{sa}_{107+index}\n'
        hilog+=f'10-09 19:10:56.772  {pid}  2740 I C01810/SAFWK: Publish SA:{sa} result:0,spend:1ms\n'
    cmds=[]
    for leaf in I18N_DIRECTORIES:
        path='/data/service/el1/public/i18n/'+leaf
        mode='777' if leaf=='global' else '755'
        cmds.append('mkdir '+(path+'/' if leaf else path)+' 0'+mode+' i18n i18n')
        ownership[path.rstrip('/')]=f'3013:3013:{mode}:directory'
    cmds.append('exec /system/bin/icu72_dat_mount')
    configs[I18N_CFG]=json.dumps({'jobs':[{'name':'boot','cmds':cmds}],
        'services':[{'name':'i18n_service','uid':'i18n','gid':['i18n','shell']}]})
    serial+='ServiceStart started info i18n_service(pid 4567 uid 3013)\n'
    return [passwd,group,configs,ownership,serial,hilog]

def evidence_fixture(directory):
    runtime=Path(directory)
    root=runtime/'service-init-contracts';root.mkdir()
    image=runtime/'boot/extract/package/images/system.img'
    image.parent.mkdir(parents=True);image.write_bytes(b'host fixture NOT guest image')
    passwd,group,configs,ownership,serial,hilog=fixture()
    doc={'status':'pass','persona':'service-init-contracts',
        'scope':'Fusion_init_accounts_and_I18n_init_paths_only','archive_sha256':'archive','boot_id':'boot',
        'verifier_sha256':digest(Path(__file__).with_name('verify_service_init_contracts.py')),
        'system_image':str(image),'system_image_sha256':digest(image),
        'ownership':ownership,'image_contract_files':{},'ownership_files':{},
        'result':verify(passwd,group,configs,ownership,serial,hilog)}
    for index,(name,value) in enumerate({'/etc/passwd':passwd,'/etc/group':group,**configs}.items()):
        path=root/('image-'+str(index));path.write_text(value)
        doc['image_contract_files'][name]={'file':str(path),'sha256':digest(path)}
    for index,(name,value) in enumerate(ownership.items()):
        path=root/('stat-'+str(index));path.write_text(value+'\n')
        doc['ownership_files'][name]={'file':str(path),'sha256':digest(path)}
    path=root/'serial.log';path.write_text(serial)
    doc.update(serial=str(path),serial_sha256=digest(path))
    path=root/'publication-hilog.log';path.write_text(hilog)
    doc.update(publication_hilog=str(path),publication_hilog_sha256=digest(path))
    loader=root/'loader';loader.mkdir()
    binary=loader/'service-load';binary.write_bytes(b'explicit host fixture, not an executable')
    build=loader/'build.json'
    build.write_text(json.dumps({'status':'pass','scope':'actual_product_SAMGR_caller_build_NOT_guest',
        'arch':'arm64','probe_sha256':digest(binary),
        'source_sha256':digest(Path(__file__).with_name('probes')/'service_load.cpp')}))
    rows=[{'ability':ability,'round':round,'loaded':True} for round in (1,2) for _,_,ability in FUSION]
    raw=root/'samgr-load.log';raw.write_text('\n'.join(map(json.dumps,rows))+'\nLOAD_EXIT=0\n')
    doc['samgr_load']={'build':str(build),'build_sha256':digest(build),'binary':str(binary),
        'binary_sha256':digest(binary),'results':rows,'file':str(raw),'sha256':digest(raw)}
    parameter_root=root/'parameter-loader';parameter_root.mkdir()
    parameter_binary=parameter_root/'fusion-parameter-access'
    parameter_binary.write_bytes(b'host fixture NOT loaded kernel proof')
    parameter_build=parameter_root/'build.json'
    parameter_build.write_text(json.dumps({'status':'pass',
        'scope':'actual_product_Fusion_parameter_AV_caller_build_NOT_guest','arch':'arm64',
        'probe_sha256':digest(parameter_binary),
        'source_sha256':digest(Path(__file__).with_name('probes')/'fusion_parameter_access.cpp')}))
    parameter_rows=[{'domain':domain,'compute_rc':0,'errno':0,'allowed':allowed,'expected':allowed}
                    for domain,allowed in PARAMETER_DOMAINS]
    parameter_raw=root/'parameter-access.log'
    parameter_raw.write_text('\n'.join(map(json.dumps,parameter_rows))+'\nPOLICY_EXIT=0\n')
    doc['parameter_access']={'scope':'kernel_allowed_bits_NOT_permissive_AVC_return_or_identity_change',
        'build':str(parameter_build),'build_sha256':digest(parameter_build),
        'binary':str(parameter_binary),'binary_sha256':digest(parameter_binary),
        'results':parameter_rows,'file':str(parameter_raw),'sha256':digest(parameter_raw)}
    boot={'status':'pass','purpose':'acceptance','archive_sha256':'archive',
          'initial_package_file_sha256':{'images/system.img':digest(image)},
          'test_environment':{'boot_id':'boot','external_keepalive':False,'guest_arch':'arm64',
                              'freshly_extracted_directory':str(image.parent.parent)}}
    return doc,root,boot

class ServiceInitContractTests(unittest.TestCase):
    def test_parameter_label_and_actual_denials_are_not_waived(self):
        for value in ('',PARTNER_PARAMETER+' u:object_r:persist_param:s0\n',
                      2*(PARTNER_PARAMETER+' u:object_r:fusion_partner_enable_param:s0\n')):
            args=fixture();args[2][PARAMETER_CONTEXTS]=value
            with self.assertRaises(ValueError):verify(*args)
        for index in (4,5):
            args=fixture();args[index]+='avc:  denied  { set } for parameter='+PARTNER_PARAMETER+' pid=1235\n'
            with self.assertRaises(ValueError):verify(*args)

    def test_parameter_build_and_AV_evidence_cannot_be_replaced(self):
        for change in ('missing','binary','source','ABI','results','raw','scope'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                doc,root,boot=evidence_fixture(directory)
                row=doc['parameter_access']
                if change=='missing':doc.pop('parameter_access')
                elif change=='binary':Path(row['binary']).write_bytes(b'changed')
                elif change in ('source','ABI'):
                    path=Path(row['build']);data=json.loads(path.read_text())
                    data['source_sha256' if change=='source' else 'arch']='wrong'
                    path.write_text(json.dumps(data));row['build_sha256']=digest(path)
                elif change=='results':row['results'][2]['allowed']=True
                elif change=='raw':
                    path=Path(row['file']);path.write_text('POLICY_EXIT=0\n');row['sha256']=digest(path)
                elif change=='scope':row['scope']='permissive_WRAPPER_only'
                with self.assertRaises(ValueError):verify_evidence(doc,root,boot,'archive','boot')

    def test_parameter_AV_requires_actual_success_and_all_negative_domains(self):
        rows=[{'domain':domain,'compute_rc':0,'errno':0,'allowed':allowed,'expected':allowed}
              for domain,allowed in PARAMETER_DOMAINS]
        render=lambda data:'\n'.join(map(json.dumps,data))+'\nPOLICY_EXIT=0\n'
        self.assertEqual(verify_parameter_access(render(rows)),rows)
        for index in range(len(rows)):
            for key,value in (('compute_rc',-1),('allowed',not rows[index]['allowed']),
                              ('domain','unrelated'),('expected',not rows[index]['expected']),
                              ('compute_rc',False)):
                bad=deepcopy(rows);bad[index][key]=value
                with self.subTest(index=index,key=key),self.assertRaises(ValueError):
                    verify_parameter_access(render(bad))
        for text in (render(rows[:-1]),render(rows+[rows[0]]),render(rows).replace('POLICY_EXIT=0','POLICY_EXIT=1')):
            with self.assertRaises(ValueError):verify_parameter_access(text)

    def test_loader_requires_two_real_rounds_and_successful_exit(self):
        rows=[{'ability':ability,'round':round,'loaded':True} for round in (1,2) for _,_,ability in FUSION]
        value='\n'.join(map(json.dumps,rows))+'\nLOAD_EXIT=0\n'
        self.assertEqual(verify_load_results(value),rows)
        for bad in (value.replace('LOAD_EXIT=0','LOAD_EXIT=1'),value.replace('8631','9999'),
                    value.replace('true','false',1),value.split('\n',1)[1],value+'extra\n'):
            with self.assertRaises(ValueError):verify_load_results(bad)

    def test_loader_tampering_and_missing_real_artifact_are_rejected(self):
        for change in ('missing','binary','build','results','raw','ABI','source','domain'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                doc,root,boot=evidence_fixture(directory)
                if change=='missing':doc.pop('samgr_load')
                elif change=='binary':Path(doc['samgr_load']['binary']).write_bytes(b'changed')
                elif change=='build':Path(doc['samgr_load']['build']).write_text('{}')
                elif change=='results':doc['samgr_load']['results'].pop()
                elif change=='raw':Path(doc['samgr_load']['file']).write_text('LOAD_EXIT=0\n')
                elif change=='ABI':boot['test_environment']['guest_arch']='x86_64'
                elif change=='source':
                    path=Path(doc['samgr_load']['build']);data=json.loads(path.read_text())
                    data['source_sha256']='stale';path.write_text(json.dumps(data))
                    doc['samgr_load']['build_sha256']=digest(path)
                elif change=='domain':
                    row=doc['image_contract_files'][FUSION_CFG['fusion_ranging']]
                    path=Path(row['file']);data=json.loads(path.read_text())
                    data['services'][0]['secon']='u:r:init:s0';path.write_text(json.dumps(data));row['sha256']=digest(path)
                with self.assertRaises(ValueError):verify_evidence(doc,root,boot,'archive','boot')

    def test_evidence_rechecks_original_image_stat_and_init_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            doc,root,boot=evidence_fixture(directory)
            self.assertEqual(verify_evidence(doc,root,boot,'archive','boot'),doc['result'])
            from verify_gap_closure import behavior_results
            (root/'evidence.json').write_text(json.dumps(doc))
            (root.parent/'boot/boot.json').write_text(json.dumps(boot))
            closed=behavior_results(root.parent,'boot','archive','phone')
            self.assertEqual(set(closed),{'behavior:fusion-connectivity-init-accounts'})
            # Initialization alone must not claim data or full Fusion behavior.
            self.assertNotIn('behavior:i18n-core-and-customization-paths',closed)

    def test_stale_image_or_boot_unrecorded_stat_and_changed_payload_fail(self):
        for change in ('archive','boot','diagnostic','keepalive','image','verifier','stat','serial',
                       'config','reported-stat','reported-result','missing-config','missing-stat','hilog','hilog-path'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                doc,root,boot=evidence_fixture(directory)
                if change=='archive':doc['archive_sha256']='stale'
                elif change=='boot':boot['test_environment']['boot_id']='stale'
                elif change=='diagnostic':boot['purpose']='diagnostic'
                elif change=='keepalive':boot['test_environment']['external_keepalive']=True
                elif change=='image':Path(doc['system_image']).write_bytes(b'changed')
                elif change=='verifier':doc['verifier_sha256']='stale'
                elif change=='stat':Path(next(iter(doc['ownership_files'].values()))['file']).write_text('0:0:777:directory')
                elif change=='serial':(root/'serial.log').write_text('stale')
                elif change=='hilog':(root/'publication-hilog.log').write_text('stale')
                elif change=='hilog-path':doc['publication_hilog']=str(root/'serial.log')
                elif change=='config':Path(doc['image_contract_files'][I18N_CFG]['file']).write_text('{}')
                elif change=='reported-stat':doc['ownership'][next(iter(doc['ownership']))]='0:0:777:directory'
                elif change=='reported-result':doc['result']['fusion'].clear()
                elif change=='missing-config':doc['image_contract_files'].pop(I18N_CFG)
                elif change=='missing-stat':doc['ownership_files'].pop(next(iter(doc['ownership_files'])))
                with self.assertRaises(ValueError):verify_evidence(doc,root,boot,'archive','boot')

    def test_i18n_closure_also_requires_fresh_normal_data_and_numeric_errors(self):
        from test_i18n_data import results,render,RUN
        from verify_i18n_data import verify as verify_i18n
        from verify_gap_closure import behavior_results
        with tempfile.TemporaryDirectory() as directory:
            doc,root,boot=evidence_fixture(directory)
            (root/'evidence.json').write_text(json.dumps(doc))
            (root.parent/'boot/boot.json').write_text(json.dumps(boot))
            i18n=root.parent/'i18n';i18n.mkdir()
            raw=i18n/'results.log';raw.write_text(render(results()))
            identity=i18n/'application-identity.json'
            identity.write_text(json.dumps({'applicationInfo':{'appPrivilegeLevel':'normal',
                                'isSystemApp':False,'uid':20010000}}))
            verification=i18n/'verified-result.json'
            verification.write_text(json.dumps({'status':'pass','archive_sha256':'archive','run_id':RUN,
                'results_sha256':digest(raw),'results':verify_i18n(raw.read_text(),RUN)}))
            (i18n/'evidence.json').write_text(json.dumps({'status':'pass','persona':'i18n',
                'archive_sha256':'archive','boot_id':'boot','run_id':RUN,
                'raw_results_sha256':digest(raw),'ordinary_identity_sha256':digest(identity),
                'result':str(verification),'result_sha256':digest(verification)}))
            closed=behavior_results(root.parent,'boot','archive','phone')
            self.assertEqual(set(closed),{'behavior:fusion-connectivity-init-accounts',
                                          'behavior:i18n-core-and-customization-paths'})
            raw.write_text('stale or incomplete data')
            closed=behavior_results(root.parent,'boot','archive','phone')
            self.assertEqual(set(closed),{'behavior:fusion-connectivity-init-accounts'})

    def test_exact_narrow_scopes(self):
        result=verify(*fixture())
        self.assertEqual(set(result),{'fusion','i18n'})
        self.assertEqual(len(result['fusion']),2)
        self.assertTrue(result['i18n']['ordinary_data_probe_required_separately'])

    def test_bad_or_aliased_accounts_and_duplicate_rows_fail(self):
        cases=[(0,'fusion_ranging:x:6067:6067:::/bin/false','fusion_ranging:x:6067:0:::/bin/false'),
               (1,'partner_device_agent:x:6068:','partner_device_agent:x:0:'),
               (0,'i18n:x:3013:3013:::/bin/false','i18n_service:x:3013:3013:::/bin/false')]
        for index,old,new in cases:
            args=fixture();args[index]=args[index].replace(old,new)
            with self.subTest(index=index,new=new),self.assertRaises(ValueError):verify(*args)
        for index,new in ((0,'other:x:6067:6067:::/bin/false\n'),(1,'other:x:6068:\n'),
                          (0,'fusion_ranging:x:6067:6067:::/bin/false\n')):
            args=fixture();args[index]+=new
            with self.subTest(index=index,new=new),self.assertRaises(ValueError):verify(*args)

    def test_actual_init_identity_execution_and_publication_required(self):
        for old,new in (('uid 6067','uid 0'),('[pid=1234] ServiceExec','[pid=5555] ServiceExec'),
                        ('insert SA:8630_108','insert SA:8639_108'),
                        ('SAMGR: Start dynamic proc:partner_device_agent,8630,','SAMGR: wrong process,'),
                        ('i18n_service(pid 4567 uid 3013)','i18n_service(pid 4567 uid 0)')):
            args=fixture();args[4]=args[4].replace(old,new)
            with self.subTest(old=old),self.assertRaises(ValueError):verify(*args)
        for old,new in (('  1234  2740','  9999  2740'),('result:0','result:1'),
                        ('C01810/SAFWK:','C01800/SAMGR:'),('Publish SA:8630','Publish SA:8639')):
            args=fixture();args[5]=args[5].replace(old,new)
            with self.subTest(hilog=old),self.assertRaises(ValueError):verify(*args)
        args=fixture();args[4]+=args[5];args[5]=''
        with self.assertRaises(ValueError):verify(*args)
        for path in fixture()[3]:
            args=fixture();args[3][path]='0:0:777:directory'
            with self.subTest(path=path),self.assertRaises(ValueError):verify(*args)

    def test_config_cannot_bypass_init_or_use_absent_i18n_helpers(self):
        for name,_,_ in FUSION:
            for key,value in (('uid','root'),('gid',['root']),('path',['/system/bin/sa_main']),('ondemand',False)):
                args=fixture();cfg=json.loads(args[2][FUSION_CFG[name]])
                cfg['services'][0][key]=value;args[2][FUSION_CFG[name]]=json.dumps(cfg)
                with self.subTest(name=name,key=key),self.assertRaises(ValueError):verify(*args)
        for helper in ('timezone','libphonenumber','taboo'):
            args=fixture();cfg=json.loads(args[2][I18N_CFG])
            cfg['jobs'][0]['cmds'].append('exec /system/bin/hmos_cust_'+helper+'_mount')
            args[2][I18N_CFG]=json.dumps(cfg)
            with self.subTest(helper=helper),self.assertRaises(ValueError):verify(*args)
            args=fixture();args[4]+='exec failed hmos_cust_'+helper+'_mount'
            with self.assertRaises(ValueError):verify(*args)
        args=fixture();cfg=json.loads(args[2][I18N_CFG]);cfg['jobs'][0]['cmds'].pop()
        args[2][I18N_CFG]=json.dumps(cfg)
        with self.assertRaises(ValueError):verify(*args)

if __name__=='__main__':unittest.main()
