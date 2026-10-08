"""Actual HUKS helper init and legacy owner/mode contract, not key crypto."""
import json
import re

SCOPE = 'packaged_HUKS_init_and_legacy_UID_mode_migration_NOT_legacy_crypto_or_TEE'
CFG = '/etc/init/huks_service.cfg'
BINARY = '/system/bin/hks_compatibility_bin'


def remote_output(text, nonce):
    """HDC transport success is not the guest shell/process exit status."""
    if not isinstance(nonce, str) or re.fullmatch('[0-9a-f]{32}_[0-9]+', nonce) is None:
        raise ValueError('fresh exact guest exit challenge required')
    match = re.fullmatch(r'([\s\S]*)\n__HUKS_EXIT_' + re.escape(nonce) + r'=(0|[1-9][0-9]{0,2})\n?',
                         text.replace('\r', ''))
    if not match or int(match[2]) != 0 or '__HUKS_EXIT_' in match[1]:
        raise ValueError('missing, mixed, stale or unsuccessful actual guest exit')
    return match[1]


def account(passwd, group):
    for text, size in ((passwd, 7), (group, 4)):
        rows=[line.split(':') for line in text.splitlines() if line and not line.startswith('#')]
        if any(len(row)!=size for row in rows):
            raise ValueError('malformed packaged HUKS account table')
        owned=[row for row in rows if row[0]=='huks_server']
        aliases=[row for row in rows if row[2]=='3510']
        if len(owned)!=1 or aliases!=owned or owned[0][2]!='3510':
            raise ValueError('HUKS service account is missing, duplicate or aliased')
        if size==7 and owned[0][3]!='3510':
            raise ValueError('HUKS service group differs')


def helper(text):
    rows=re.findall(r'(?m)^(?:\[\s*\d+\.\d+\]\s*)?HUKS_COMPATIBILITY '
        r'pid=(\d+) uid=(\d+) status=(-?\d+) directories=(\d+) files=(\d+)\s*$',text)
    if len(rows)!=1:
        raise ValueError('missing/duplicate actual helper completion')
    pid,uid,status,dirs,files=map(int,rows[0])
    if pid<=1 or uid!=0 or status!=0 or dirs<1:
        raise ValueError('actual helper execution/legacy directory migration failed')
    return {'pid':pid,'uid':uid,'status':status,'directories':dirs,'files':files}


def image_and_boot(binary_stat, config, passwd, group, serial):
    if not re.search(r'(?m)^Inode: \d+\s+Type: regular\s+Mode:\s+0?755\b',binary_stat):
        raise ValueError('actual image helper is not a regular executable')
    account(passwd,group)
    cfg=json.loads(config)
    jobs=[row for row in cfg.get('jobs',[]) if row.get('name')=='post-fs-data']
    if len(jobs)!=1:
        raise ValueError('HUKS post-fs-data init job missing/duplicated')
    cmds=jobs[0].get('cmds',[])
    if (cmds.count('exec '+BINARY)!=1 or cmds.count('start huks_service')!=1 or
        cmds.index('exec '+BINARY)>cmds.index('start huks_service') or
        cmds.count('mkdir /data/data/huks_service 0711 huks_server huks_server')!=1 or
        cmds.count('mkdir /data/data/huks_service/maindata 0711 huks_server huks_server')!=1):
        raise ValueError('packaged init must invoke migration before invoking service start; exec is asynchronous')
    services=[row for row in cfg.get('services',[]) if row.get('name')=='huks_service']
    if (len(services)!=1 or services[0].get('uid')!='huks_server' or
        services[0].get('gid')!=['huks_server'] or services[0].get('path')!=
            ['/system/bin/sa_main','/system/profile/huks_service.json']):
        raise ValueError('HUKS service identity/protocol changed')
    boot=helper(serial)
    starts=re.findall(r'ServiceStart started info huks_service\(pid (\d+) uid 3510\)',serial)
    pids=[int(pid) for pid in starts if re.search(r'\[pid='+pid+r'\].*ServiceExec huks_service\b',serial)]
    if not pids or boot['pid'] in pids or any(pid<=1 for pid in pids):
        raise ValueError('normal isolated HUKS service did not execute independently of helper')
    return boot,pids


def verify(binary_stat, config, passwd, group, serial, observations, run_id):
    if re.fullmatch('[0-9a-f]{32}',run_id) is None:
        raise ValueError('fresh migration fixture challenge required')
    boot,pids=image_and_boot(binary_stat,config,passwd,group,serial)
    expected={'before_directory':'0:0:755:directory','before_file':'0:0:644:regular file',
        'after_directory':'3510:3510:700:directory','after_file':'3510:3510:600:regular file',
        'base_before':'3510:3510:711:directory','base_after':'3510:3510:711:directory',
        'payload_before':run_id,'payload_after':run_id,'fixture_cleaned':'absent'}
    if set(observations)!=set(expected)|{'helper'} or any(
        observations[name].strip()!=value for name,value in expected.items()):
        raise ValueError('real owned fixture data/ownership/modes/cleanup differ')
    actual=helper(observations['helper'])
    if actual['pid']==boot['pid'] or actual['files']<1 or actual['directories']<2:
        raise ValueError('fixture requires a separate real helper and real file migration')
    return {'boot_helper':boot,'normal_service_pids':pids,'fixture_helper':actual,
            'uid':3510,'directory_mode':'700','file_mode':'600',
            'actual_owned_payload_preserved':True,'base_owner_and_mode_preserved':True,
            'owned_fixture_cleaned':True,'legacy_crypto_not_claimed':True}


def verify_evidence(document,root,boot,archive_sha,boot_id):
    from pathlib import Path
    from run_root_probe import digest
    root=Path(root)
    env=boot.get('test_environment',{})
    image=Path(document.get('system_image',''))
    if (document.get('status')!='pass' or document.get('persona')!='huks-compatibility' or
        document.get('scope')!=SCOPE or document.get('archive_sha256')!=archive_sha or
        document.get('boot_id')!=boot_id or document.get('verifier_sha256')!=digest(Path(__file__)) or
        boot.get('status')!='pass' or boot.get('purpose')!='acceptance' or
        boot.get('archive_sha256')!=archive_sha or env.get('boot_id')!=boot_id or
        env.get('external_keepalive') is not False or image.is_symlink() or not image.is_file() or
        image.name!='system.img' or image.parent.name!='images' or
        root.parent/'boot/extract' not in image.parents or
        env.get('freshly_extracted_directory')!=str(image.parent.parent) or
        digest(image)!=document.get('system_image_sha256') or
        digest(image)!=boot.get('initial_package_file_sha256',{}).get('images/system.img')):
        raise ValueError('HUKS proof is not from this unchanged acceptance package and boot')
    run_id=document.get('run_id','')
    if (not isinstance(run_id,str) or re.fullmatch('[0-9a-f]{32}',run_id) is None or
        document.get('owned_fixture')!='/data/data/huks_service/.qemu-compatibility-'+run_id):
        raise ValueError('HUKS proof lacks its exact exclusive fixture nonce/path')

    def captured(row):
        path=Path(row['file'])
        if path.parent!=root or path.is_symlink() or not path.is_file() or digest(path)!=row.get('sha256'):
            raise ValueError('captured HUKS proof escaped, changed or disappeared')
        return path.read_text(errors='replace').replace('\r','')

    records=document.get('image_contract_files',{})
    if set(records)!={BINARY,CFG,'/etc/passwd','/etc/group'}:
        raise ValueError('complete actual HUKS image files required')
    files={name:captured(row) for name,row in records.items()}
    required={'before_directory','before_file','after_directory','after_file','base_before','base_after',
              'payload_before','payload_after','helper','fixture_cleaned'}
    if set(document.get('observation_files',{}))!=required:
        raise ValueError('complete original migration observations required')
    actual={}
    nonces=set()
    for name,row in document['observation_files'].items():
        nonce=row.get('remote_exit_nonce','')
        if not nonce.startswith(run_id+'_') or nonce in nonces:
            raise ValueError('migration observation has stale or repeated guest exit challenge')
        nonces.add(nonce)
        actual[name]=remote_output(captured(row),nonce).strip()
    if actual!=document.get('observations'):
        raise ValueError('reported HUKS migration differs from actual capture')
    serial=root/'serial.log'
    if document.get('serial')!=str(serial):
        raise ValueError('HUKS init proof does not name its own captured trace')
    value=captured({'file':str(serial),'sha256':document.get('serial_sha256')})
    result=verify(files[BINARY],files[CFG],files['/etc/passwd'],files['/etc/group'],value,actual,run_id)
    if result!=document.get('result'):
        raise ValueError('reported HUKS proof differs from actual image/init/fixture inputs')
    return result
