"""Pure boundary/replay fixtures are not new-guest acceptance."""
from copy import deepcopy
import json
import unittest
from pathlib import Path
import tempfile
from run_root_probe import digest
from verify_huks_compatibility_results import BINARY, CFG, SCOPE, remote_output, verify, verify_evidence

RUN='a'*32


def fixture():
    cfg={'jobs':[{'name':'post-fs-data','cmds':[
        'mkdir /data/data/huks_service 0711 huks_server huks_server',
        'mkdir /data/data/huks_service/maindata 0711 huks_server huks_server',
        'exec '+BINARY,'start huks_service']}],
        'services':[{'name':'huks_service','uid':'huks_server','gid':['huks_server'],
                     'path':['/system/bin/sa_main','/system/profile/huks_service.json']}]}
    serial='[ 1.001] HUKS_COMPATIBILITY pid=200 uid=0 status=0 directories=1 files=0\n'
    serial+='[pid=1] ServiceStart started info huks_service(pid 201 uid 3510)\n'
    serial+='[pid=201] ServiceExec huks_service\n'
    observations={'before_directory':'0:0:755:directory','before_file':'0:0:644:regular file',
        'after_directory':'3510:3510:700:directory','after_file':'3510:3510:600:regular file',
        'base_before':'3510:3510:711:directory','base_after':'3510:3510:711:directory',
        'payload_before':RUN,'payload_after':RUN,'fixture_cleaned':'absent',
        'helper':'HUKS_COMPATIBILITY pid=999 uid=0 status=0 directories=2 files=1'}
    return ['Inode: 123 Type: regular Mode: 0755\n',json.dumps(cfg),
            'huks_server:x:3510:3510:::/bin/false\n','huks_server:x:3510:\n',serial,observations,RUN]


def evidence_fixture(directory):
    runtime=Path(directory)
    root=runtime/'huks-compatibility';root.mkdir()
    image=runtime/'boot/extract/package/images/system.img'
    image.parent.mkdir(parents=True);image.write_bytes(b'host fixture NOT guest image')
    binary,config,passwd,group,serial,observations,run_id=fixture()
    doc={'status':'pass','persona':'huks-compatibility','scope':SCOPE,
         'archive_sha256':'archive','boot_id':'boot','run_id':run_id,
         'owned_fixture':'/data/data/huks_service/.qemu-compatibility-'+run_id,
         'system_image':str(image),'system_image_sha256':digest(image),
         'verifier_sha256':digest(Path(__file__).with_name('verify_huks_compatibility_results.py')),
         'image_contract_files':{},'observation_files':{},'observations':observations,
         'result':verify(*fixture())}
    for index,(name,value) in enumerate({BINARY:binary,CFG:config,'/etc/passwd':passwd,'/etc/group':group}.items()):
        path=root/('image-'+str(index));path.write_text(value)
        doc['image_contract_files'][name]={'file':str(path),'sha256':digest(path)}
    for index,(name,value) in enumerate(observations.items()):
        nonce=run_id+'_'+str(index)
        path=root/(name+'.txt');path.write_text(value+'\n__HUKS_EXIT_'+nonce+'=0\n')
        doc['observation_files'][name]={'file':str(path),'sha256':digest(path),'remote_exit_nonce':nonce}
    path=root/'serial.log';path.write_text(serial)
    doc.update(serial=str(path),serial_sha256=digest(path))
    boot={'status':'pass','purpose':'acceptance','archive_sha256':'archive',
          'initial_package_file_sha256':{'images/system.img':digest(image)},
          'test_environment':{'boot_id':'boot','external_keepalive':False,
                              'freshly_extracted_directory':str(image.parent.parent)}}
    return doc,root,boot


class HuksCompatibilityTests(unittest.TestCase):
    def test_ledger_closes_only_the_original_helper_finding_from_replayed_current_boot(self):
        from verify_gap_closure import behavior_results
        with tempfile.TemporaryDirectory() as directory:
            doc, root, boot = evidence_fixture(directory)
            (root.parent / 'boot/boot.json').write_text(json.dumps(boot))
            path = root / 'evidence.json'
            path.write_text(json.dumps(doc))
            closed = behavior_results(root.parent, 'boot', 'archive')
            self.assertEqual(set(closed), {'behavior:huks-compatibility-helper-missing'})
            self.assertIn('legacy_encrypted_key_conversion_TEE',
                          closed['behavior:huks-compatibility-helper-missing']['not_claimed'])
            doc['archive_sha256'] = 'stale'
            path.write_text(json.dumps(doc))
            self.assertEqual(behavior_results(root.parent, 'boot', 'archive'), {})

    def test_transport_success_cannot_replace_actual_guest_exit(self):
        nonce=RUN+'_42'
        self.assertEqual(remote_output('actual output\n__HUKS_EXIT_'+nonce+'=0\n',nonce),'actual output')
        for value in ('actual output', 'actual output\n__HUKS_EXIT_'+nonce+'=1\n',
                      'actual output\n__HUKS_EXIT_'+nonce+'=255\n',
                      'actual output\n__HUKS_EXIT_'+nonce+'=256\n',
                      'actual output\n__HUKS_EXIT_'+nonce+'=00\n',
                      'actual output\n__HUKS_EXIT_'+RUN+'_41=0\n',
                      '__HUKS_EXIT_'+nonce+'=0\n__HUKS_EXIT_'+nonce+'=0\n'):
            with self.subTest(value=value),self.assertRaises(ValueError):remote_output(value,nonce)

    def test_replay_reads_exact_original_image_init_and_fixture_files(self):
        with tempfile.TemporaryDirectory() as directory:
            doc,root,boot=evidence_fixture(directory)
            self.assertEqual(verify_evidence(doc,root,boot,'archive','boot'),doc['result'])

    def test_stale_or_altered_report_image_capture_or_fixture_is_rejected(self):
        for kind in ('status','scope','archive','boot','diagnostic','keepalive','image','verifier','fixture-path',
                     'config','stat','payload','serial','missing-image','missing-observation','result',
                     'reported-observation','escaped-file','symlink'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                doc,root,boot=evidence_fixture(directory)
                if kind=='status':doc['status']='fail'
                elif kind=='scope':doc['scope']='other'
                elif kind=='archive':doc['archive_sha256']='stale'
                elif kind=='boot':boot['test_environment']['boot_id']='stale'
                elif kind=='diagnostic':boot['purpose']='diagnostic'
                elif kind=='keepalive':boot['test_environment']['external_keepalive']=True
                elif kind=='image':Path(doc['system_image']).write_bytes(b'changed')
                elif kind=='verifier':doc['verifier_sha256']='stale'
                elif kind=='fixture-path':doc['owned_fixture']='/data/data/huks_service'
                elif kind=='config':Path(doc['image_contract_files'][CFG]['file']).write_text('{}')
                elif kind=='stat':(root/'after_file.txt').write_text('0:0:777:regular file')
                elif kind=='payload':(root/'payload_after.txt').write_text('stale')
                elif kind=='serial':(root/'serial.log').write_text('stale')
                elif kind=='missing-image':doc['image_contract_files'].pop(BINARY)
                elif kind=='missing-observation':doc['observation_files'].pop('helper')
                elif kind=='result':doc['result']['actual_owned_payload_preserved']=False
                elif kind=='reported-observation':doc['observations']['after_file']='0:0:777:regular file'
                elif kind=='escaped-file':
                    path=root.parent/'escape.txt';path.write_text(doc['observations']['after_file'])
                    doc['observation_files']['after_file']={'file':str(path),'sha256':digest(path)}
                elif kind=='symlink':
                    path=root/'after_file.txt';value=path.read_text();path.unlink()
                    target=root.parent/'elsewhere.txt';target.write_text(value);path.symlink_to(target)
                with self.assertRaises(ValueError):verify_evidence(doc,root,boot,'archive','boot')

    def test_actual_narrow_init_and_permission_contract(self):
        result=verify(*fixture())
        self.assertTrue(result['actual_owned_payload_preserved'])
        self.assertTrue(result['legacy_crypto_not_claimed'])
        self.assertEqual(result['normal_service_pids'],[201])

    def test_wrong_binary_account_job_service_or_boot_fails(self):
        for kind in ('binary','uid','gid','alias','job','exec-order','service-root','service-pid',
                     'helper-failure','helper-duplicate','helper-missing','helper-uid','helper-no-directory'):
            with self.subTest(kind=kind):
                args=fixture()
                if kind=='binary':args[0]=args[0].replace('0755','0644')
                elif kind=='uid':args[2]=args[2].replace(':3510:3510',':0:3510')
                elif kind=='gid':args[3]=args[3].replace(':3510:',':0:')
                elif kind=='alias':args[2]+='alias:x:3510:3510:::/bin/false\n'
                elif kind in ('job','exec-order','service-root'):
                    cfg=json.loads(args[1])
                    if kind=='job':cfg['jobs']*=2
                    elif kind=='exec-order':cfg['jobs'][0]['cmds'][-2:]=['start huks_service','exec '+BINARY]
                    else:cfg['services'][0]['uid']='root'
                    args[1]=json.dumps(cfg)
                elif kind=='service-pid':args[4]=args[4].replace('[pid=201]','[pid=200]')
                elif kind=='helper-failure':args[4]=args[4].replace('status=0','status=-13')
                elif kind=='helper-duplicate':args[4]+=args[4].splitlines()[0]+'\n'
                elif kind=='helper-missing':args[4]='\n'.join(args[4].splitlines()[1:])
                elif kind=='helper-uid':args[4]=args[4].replace('uid=0','uid=3510')
                elif kind=='helper-no-directory':args[4]=args[4].replace('directories=1','directories=0')
                with self.assertRaises(ValueError):verify(*args)

    def test_every_fixture_observation_and_fresh_challenge_required(self):
        for field in fixture()[5]:
            for value in ('stale','', '0:0:777:regular file'):
                with self.subTest(field=field,value=value):
                    args=fixture();args[5][field]=value
                    with self.assertRaises(ValueError):verify(*args)
        for field in fixture()[5]:
            args=fixture();del args[5][field]
            with self.subTest(missing=field),self.assertRaises(ValueError):verify(*args)
        for run in ('','f'*31,'A'*32,'stale'):
            args=fixture();args[6]=run
            with self.subTest(run=run),self.assertRaises(ValueError):verify(*args)
        args=fixture();args[5]['helper']=args[5]['helper'].replace('pid=999','pid=200')
        with self.assertRaises(ValueError):verify(*args)


if __name__=='__main__':unittest.main()
