"""Verify only original Fusion account and I18n init/data findings."""
import json
import re

FUSION=(('fusion_ranging',6067,8631),('partner_device_agent',6068,8630))
I18N_DIRECTORIES=('','timezone','libphonenumber','taboo','global','icu')
I18N_CFG='/etc/init/i18n_service.cfg'
FUSION_CFG={'fusion_ranging':'/etc/init/fusion_ranging.cfg',
            'partner_device_agent':'/etc/init/fusion_connectivity.cfg'}

def account_tables(passwd,group):
    users={}
    groups={}
    for text,table,minimum in ((passwd,users,7),(group,groups,4)):
        seen_ids=set()
        for line in text.splitlines():
            if not line or line.startswith('#'):
                continue
            parts=line.split(':')
            if len(parts)!=minimum or parts[0] in table:
                raise ValueError('malformed/duplicate packaged account row')
            if not parts[2].isdigit():
                raise ValueError('non-numeric packaged account id')
            table[parts[0]]=parts
            # Other legacy accounts may share IDs; the two new dedicated IDs
            # must be globally unique in their own account table.
            number=int(parts[2])
            if number in (6067,6068) and number in seen_ids:
                raise ValueError('Fusion identity aliases another packaged account')
            seen_ids.add(number)
    for name,number,_ in FUSION:
        if name not in users or users[name][2:4]!=[str(number)]*2 or name not in groups or groups[name][2]!=str(number):
            raise ValueError('missing/wrong dedicated Fusion account: '+name)
    if users.get('i18n',[])[2:4]!=['3013','3013'] or groups.get('i18n',[])[2:3]!=['3013']:
        raise ValueError('I18n image does not register the service identity')

def service(cfg,name):
    value=json.loads(cfg)
    rows=[entry for entry in value.get('services',[]) if entry.get('name')==name]
    if len(rows)!=1:
        raise ValueError('missing/duplicate packaged init service: '+name)
    return value,rows[0]

def verify(passwd,group,configs,ownership,serial):
    account_tables(passwd,group)
    result={'fusion':{},'i18n':{}}
    for name,number,ability in FUSION:
        cfg,row=service(configs[FUSION_CFG[name]],name)
        if (row.get('uid')!=name or row.get('gid')!=[name,'shell'] or
            row.get('path')!=['/system/bin/sa_main','/system/profile/'+name+'.json'] or
            row.get('ondemand') is not True):
            raise ValueError('Fusion init is not using its real isolated identity')
        path='/data/service/el1/public/'+name
        expected=f'{number}:{number}:711:directory'
        if ownership.get(path)!=expected:
            raise ValueError('Fusion init directory ownership differs: '+name)
        start=re.findall(r'ServiceStart started info '+re.escape(name)+r'\(pid (\d+) uid '+str(number)+r'\)',serial)
        if not start:
            raise ValueError('no real Fusion service started under its packaged account: '+name)
        verified=[]
        for pid in start:
            if (re.search(r'\[pid='+pid+r'\].*ServiceExec '+re.escape(name)+r'\b',serial) and
                re.search(r'SAMGR: Start dynamic proc:'+re.escape(name)+','+str(ability)+r',',serial) and
                re.search(r'SAFWK: Publish SA:'+str(ability)+r' result:0\b',serial)):
                verified.append(int(pid))
        if not verified:
            raise ValueError('Fusion account could not execute/publish its actual service: '+name)
        result['fusion'][name]={'uid':number,'gid':number,'ability':ability,'executed_pids':verified}
    cfg,row=service(configs[I18N_CFG],'i18n_service')
    if row.get('uid')!='i18n' or row.get('gid')!=['i18n','shell']:
        raise ValueError('I18n service uses an unregistered owner')
    cmds=[cmd for job in cfg.get('jobs',[]) if job.get('name')=='boot' for cmd in job.get('cmds',[])]
    for leaf in I18N_DIRECTORIES:
        path='/data/service/el1/public/i18n/'+leaf
        mode='777' if leaf=='global' else '755'
        expected='mkdir '+path+'/' if leaf else 'mkdir '+path
        expected+=' 0'+mode+' i18n i18n'
        if cmds.count(expected)!=1 or ownership.get(path.rstrip('/'))!=f'3013:3013:{mode}:directory':
            raise ValueError('I18n init directory owner/mode differs: '+leaf)
    if ([cmd for cmd in cmds if cmd.startswith('exec ')]!=['exec /system/bin/icu72_dat_mount'] or
        re.search(r'hmos_cust_(timezone|libphonenumber|taboo)_mount',serial)):
        raise ValueError('I18n still invokes unpackaged customization helpers')
    if not re.search(r'ServiceStart started info i18n_service\(pid \d+ uid 3013\)',serial):
        raise ValueError('I18n service has not actually run with the registered identity')
    result['i18n']={'uid':3013,'gid':3013,'directories':len(I18N_DIRECTORIES),
        'customization_strategy':'bundled_timezone_phone_locale_data_no_missing_exec_helpers',
        'ordinary_data_probe_required_separately':True}
    return result

def verify_evidence(document,root,boot,archive_sha,boot_id):
    """Re-read captured image/stat/init records; never trust a pass flag alone."""
    from pathlib import Path
    from run_root_probe import digest
    root=Path(root)
    env=boot.get('test_environment',{})
    image=Path(document.get('system_image',''))
    if (document.get('status')!='pass' or document.get('persona')!='service-init-contracts' or
        document.get('scope')!='Fusion_init_accounts_and_I18n_init_paths_only' or
        document.get('archive_sha256')!=archive_sha or document.get('boot_id')!=boot_id or
        document.get('verifier_sha256')!=digest(Path(__file__)) or
        boot.get('status')!='pass' or boot.get('purpose')!='acceptance' or
        boot.get('archive_sha256')!=archive_sha or env.get('boot_id')!=boot_id or
        env.get('external_keepalive') is not False or
        not image.is_file() or image.is_symlink() or image.name!='system.img' or
        image.parent.name!='images' or root.parent/'boot/extract' not in image.parents or
        env.get('freshly_extracted_directory')!=str(image.parent.parent) or
        digest(image)!=document.get('system_image_sha256') or
        digest(image)!=boot.get('initial_package_file_sha256',{}).get('images/system.img')):
        raise ValueError('init evidence is not bound to the unchanged accepted package image/boot')
    def captured(record):
        path=Path(record['file'])
        if (path.parent!=root or path.is_symlink() or not path.is_file() or
            digest(path)!=record.get('sha256')):
            raise ValueError('init evidence file escaped, changed or disappeared')
        return path.read_text(errors='replace')
    records=document.get('image_contract_files',{})
    required={'/etc/passwd','/etc/group',I18N_CFG,*FUSION_CFG.values()}
    if set(records)!=required:
        raise ValueError('complete packaged accounts and init configs required')
    files={name:captured(record) for name,record in records.items()}
    expected_paths={'/data/service/el1/public/'+name for name,_,_ in FUSION}|{
        ('/data/service/el1/public/i18n/'+leaf).rstrip('/') for leaf in I18N_DIRECTORIES}
    if set(document.get('ownership_files',{}))!=expected_paths:
        raise ValueError('complete real init data ownership observations required')
    ownership={name:captured(record).replace('\r','').strip()
               for name,record in document['ownership_files'].items()}
    if ownership!=document.get('ownership'):
        raise ValueError('reported init ownership differs from captured stat output')
    serial_path=root/'serial.log'
    if document.get('serial')!=str(serial_path):
        raise ValueError('init serial file is not the owned captured trace')
    serial=captured({'file':str(serial_path),'sha256':document.get('serial_sha256')})
    actual=verify(files['/etc/passwd'],files['/etc/group'],
                  {name:files[name] for name in required-{'/etc/passwd','/etc/group'}},ownership,serial)
    if actual!=document.get('result'):
        raise ValueError('reported init result differs from actual captured inputs')
    return actual
