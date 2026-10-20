"""Fixed Number provider observations via the already-held root Bridge only.

This captures real identities/maps and image-byte joins when supplied. It does
not promote log substrings or API resolution to creator/OnConnect proof.
"""
from pathlib import PurePosixPath
import re
import secrets
import shlex

BUNDLE = 'com.ohos.numberidentity'
LIB = 'libnumber_identity.z.so'


def need(ok, text):
    if not ok: raise ValueError(text)


def provider_bms(c, raw):
    doc = c.bms_document(raw, BUNDLE); app = doc['applicationInfo']
    need(type(app.get('uid')) is int and app['uid'] > 0 and
         type(app.get('accessTokenId')) is int and app['accessTokenId'] > 0 and
         app.get('isSystemApp') is True, 'actual Number provider BMS UID/token/system identity required')
    modules = doc.get('hapModuleInfos')
    need(type(modules) is list and modules, 'actual Number provider HAP metadata required')
    rows = []
    for row in modules:
        need(type(row) is dict and row.get('bundleName') == BUNDLE, 'foreign/malformed provider HAP module')
        if row.get('moduleName') == 'entry' or row.get('name') == 'entry':
            need(row.get('name') == row.get('moduleName') == 'entry', 'conflicting provider module names')
            rows.append(row)
    need(len(rows) == 1, 'one actual Number entry HAP required')
    path = c.guest_path(rows[0].get('hapPath'))
    need(re.fullmatch('/[A-Za-z0-9_./-]+\\.hap',path), 'actual provider HAP path required')
    return dict(bundle=BUNDLE,uid=app['uid'],token=app['accessTokenId'],hap_path=path,
                actual_entry_metadata=rows[0])


def loaded_maps(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 16*1024*1024, 'bounded actual process maps required')
    found = []
    for line in raw.decode('ascii').splitlines():
        fields = line.split(None,5)
        need(len(fields) in (5,6) and re.fullmatch('[0-9a-f]+-[0-9a-f]+',fields[0]) and
             re.fullmatch('[r-][w-][x-][ps]',fields[1]) and re.fullmatch('[0-9a-f]+',fields[2]) and
             re.fullmatch('[0-9a-f]+:[0-9a-f]+',fields[3]) and fields[4].isdigit(), 'invalid actual maps row')
        if len(fields) != 6 or PurePosixPath(fields[5]).name not in (LIB,'libnumber_identity.so'): continue
        path = fields[5]; p = PurePosixPath(path)
        need(path.startswith('/') and str(p) == path and '..' not in p.parts and
             not any(k.isspace() for k in path) and int(fields[4]) > 0, 'mapped provider deleted/unsafe/nonfile')
        major,minor = [int(v,16) for v in fields[3].split(':')]
        found.append(dict(path=path,inode=int(fields[4]),major=major,minor=minor,permissions=fields[1],raw=line))
    need(found and any('x' in r['permissions'] for r in found) and
         len({(r['path'],r['inode'],r['major'],r['minor']) for r in found}) == 1,
         'one actual mapped Number native DSO identity required')
    return found


def file_observation(c, raw, path):
    lines = raw.decode('ascii').splitlines()
    need(len(lines) == 2 and re.fullmatch('[0-9]+ [0-9]+ [0-7]{3,4} [0-9]+ [0-9]+ [0-9]+ [0-9]+',lines[0]),
         'exact provider stat raw required')
    vals = [int(v,8 if i == 2 else 10) for i,v in enumerate(lines[0].split())]
    m = re.fullmatch('([a-f0-9]{64}) [ *](.+)',lines[1])
    need(0 < vals[3] <= 512*1024*1024 and vals[4] > 0 and vals[5] > 0 and vals[6] == 1 and m and m[2] == path,
         'actual provider file size/inode/nonalias/hash differs')
    dev=vals[4]
    return dict(uid=vals[0],gid=vals[1],mode=vals[2],bytes=vals[3],dev=dev,inode=vals[5],nlink=vals[6],sha256=m[1],
                linux_major=((dev>>8)&0xfff)|((dev>>32)&~0xfff),
                linux_minor=(dev&0xff)|((dev>>12)&~0xff))



def emitter_maps496(raw, soname):
    """Exact actual494 Ninja identities; paths/inodes are still guest observations."""
    need(soname in ('libappkit_native.z.so', LIB), 'fixed actual emitter required')
    need(type(raw) is bytes and 0 < len(raw) <= 16*1024*1024, 'bounded actual emitter maps required')
    found=[]
    for line in raw.decode('ascii').splitlines():
        fields=line.split(None,5)
        need(len(fields) in (5,6) and re.fullmatch('[0-9a-f]+-[0-9a-f]+',fields[0]) and
             re.fullmatch('[r-][w-][x-][ps]',fields[1]) and re.fullmatch('[0-9a-f]+',fields[2]) and
             re.fullmatch('[0-9a-f]+:[0-9a-f]+',fields[3]) and fields[4].isdigit(), 'invalid emitter maps row')
        if len(fields) != 6 or PurePosixPath(fields[5]).name != soname: continue
        path=fields[5]; p=PurePosixPath(path)
        need(path.startswith('/') and str(p)==path and '..' not in p.parts and
             not any(k.isspace() for k in path) and int(fields[4])>0, 'deleted/unsafe emitter mapping')
        major,minor=[int(v,16) for v in fields[3].split(':')]
        found.append(dict(path=path,inode=int(fields[4]),major=major,minor=minor,permissions=fields[1],raw=line))
    need(found and any('x' in r['permissions'] for r in found) and
         len({(r['path'],r['inode'],r['major'],r['minor']) for r in found})==1,
         'one actual executable emitter inode required')
    return found


def capture(bridge, label):
    """No external argv/code/owner booleans; all calls retain actual Authority handles."""
    c=bridge.c; pending=[]; calls=[]
    def read(script):
        # Dynamic footer is for this fixed shell wrapper only. Parent root's
        #canonical command_exit retains echo text and rejects truncated footer.
        from guest_ui import command_exit
        marker='__NUMBER_NATIVE_EXIT_'+secrets.token_hex(16)+'__='
        wrapped='( '+script+' ); r=$?; printf "\\n'+marker+'%s\\n" "$r"'
        result=bridge.leaf([bridge.owner.hdc,'-t',bridge.guest.target,'shell',wrapped],'number-native411-'+label)
        need(result['exit_code'] == 0 and not bridge.calls[-1]['transport_failure'], 'native observation transport/host failed')
        need(0 < len(result['stdout']) <= 16*1024*1024,'bounded complete native command raw required')
        body, code=command_exit(result['stdout'].decode('utf-8','strict'),marker)
        calls.append(dict(argv=result['argv'],exit_code=result['exit_code'],guest_exit_code=code,
                          stdout_hex=result['stdout'].hex(),stderr_hex=result['stderr'].hex(),
                          held_index=bridge.calls[-1]['held_index']))
        return body.encode(),code
    def required(script):
        body,code=read(script);need(code == 0,'actual native observation command failed: '+script);return body
    def clock496():
        bridge.verify_observer()
        nonce=secrets.token_hex(16)
        try:
            raw,code=read(shlex.quote(c.TOKEN_QUERY)+' --native-clock '+nonce)
        finally:
            bridge.check_observer_file()
        if code!=0:
            pending.append('actual native clock guest exit '+str(code)+'; raw/stderr retained, no clock-domain proof')
            return dict(nonce=nonce,raw_hex=raw.hex(),guest_exit_code=code,value=None)
        row=c.decode(raw)
        fields={'schema','nonce','boot_id','clk_tck','monotonic_before_ns','boottime_ns','monotonic_after_ns','time_ns_dev','time_ns_inode'}
        need(type(row) is dict and set(row)==fields and row['schema']=='number-native-clock496/v1' and
             row['nonce']==nonce and row['boot_id']==boot and all(type(row[k]) is int and row[k]>0 for k in
             ('clk_tck','monotonic_before_ns','boottime_ns','monotonic_after_ns','time_ns_dev','time_ns_inode')) and
             row['monotonic_before_ns']<=row['monotonic_after_ns'], 'exact same-boot real native clock raw required')
        return dict(nonce=nonce,raw_hex=raw.hex(),guest_exit_code=code,value=row)
    def time_namespace496(pid):
        path='/proc/'+pid+'/ns/time'
        raw,code=read("stat -Lc '%d %i' "+path)
        value=None
        if code==0:
            need(re.fullmatch(rb'[1-9][0-9]* [1-9][0-9]*\n?',raw),'actual time namespace dev/inode raw required')
            value=dict(zip(('dev','inode'),map(int,raw.split())))
        else:
            pending.append('actual time namespace read guest exit '+str(code)+'; no clock-domain equivalence')
        return dict(path=path,raw_hex=raw.hex(),guest_exit_code=code,value=value)
    def caller496():
        roles=[role for role in c.ROLES if label in (role+'-before',role+'-after')]
        if not roles: return None
        role=roles[0];bundle=c.ROLES[role][0]
        raw,code=read('pidof '+bundle)
        if code==1 and raw==b'': return dict(role=role,process_absent=True)
        need(code==0 and re.fullmatch(rb'[1-9][0-9]*\n?',raw),'one actual current NAPI caller PID required')
        caller_pid=raw.decode().strip()
        fields=bridge.spec['roles'][role]['bms']['fields']
        first_bms=c.bms_fields(required('bm dump -n '+bundle),bundle,fields)
        def identity():
            return c.process_identity(caller_pid,required('cat /proc/'+caller_pid+'/status'),
                required('cat /proc/'+caller_pid+'/cmdline'),required('cat /proc/'+caller_pid+'/stat'),bundle,first_bms['uid'])
        identity_before=identity();ns_before=time_namespace496(caller_pid)
        ns_after=time_namespace496(caller_pid)
        need(identity()==identity_before and c.bms_fields(required('bm dump -n '+bundle),bundle,fields)==first_bms,
             'actual NAPI caller PID/birth/BMS changed during namespace observation')
        if ns_before['value']!=ns_after['value']:
            pending.append('actual NAPI caller time namespace changed; no clock-domain proof')
        return dict(role=role,process_absent=False,process=identity_before,bms=first_bms,
            namespace_before=ns_before,namespace_after=ns_after)
    boot=required('cat /proc/sys/kernel/random/boot_id').decode().strip()
    need(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot),'actual native boot required')
    uptime=required('cat /proc/uptime').decode().strip()
    need(re.fullmatch('[0-9]+\\.[0-9]+ [0-9]+\\.[0-9]+',uptime),'actual uptime required')
    clock_before=clock496()
    pidraw,code=read('pidof '+BUNDLE)
    base=dict(label=label,boot_id=boot,uptime=uptime,actual_calls=calls,native_clock_before496=clock_before,
              scope='actual same-boot native observation ONLY; callback attribution pending',
              native_callback_proven=False,first_artifact_behavior_gate_passed=False,pending=pending)
    base['caller496']=caller496()
    if code == 1 and pidraw == b'':
        base['hilog_raw_hex']=required('hilog -x').hex()
        need(required('cat /proc/sys/kernel/random/boot_id').decode().strip() == boot,'absence observation crossed boot')
        base['process_absent']=True;pending.append('exact pidof guest1/emptybody; no provider PID at this observation')
        base['native_clock_after496']=clock496()
        return base
    need(code == 0 and re.fullmatch(b'[1-9][0-9]*\\n?',pidraw), 'unique real provider PID required; no arbitrary guest1 allowance')
    pid=pidraw.decode().strip();bmsraw=required('bm dump -n '+BUNDLE);bms=provider_bms(c,bmsraw)
    def process():
        return c.process_identity(pid,required('cat /proc/'+pid+'/status'),
            required('cat /proc/'+pid+'/cmdline'),required('cat /proc/'+pid+'/stat'),BUNDLE,bms['uid'])
    before=process();mapsraw=required('cat /proc/'+pid+'/maps');maps=loaded_maps(mapsraw)
    path='/proc/'+pid+'/root'+maps[0]['path']
    stat=file_observation(c,required(c.stat_script(path,process_root=True)),path)
    need((stat['inode'],stat['linux_major'],stat['linux_minor']) ==
         (maps[0]['inode'],maps[0]['major'],maps[0]['minor']),'actual mapped inode/device differs from hashed file')
    hap=file_observation(c,required(c.stat_script(bms['hap_path'])),bms['hap_path'])
    emitters={}
    provider_namespace_before=time_namespace496(pid)
    for soname in ('libappkit_native.z.so',LIB):
        mapped=emitter_maps496(mapsraw,soname)
        observed_path='/proc/'+pid+'/root'+mapped[0]['path']
        observed=file_observation(c,required(c.stat_script(observed_path,process_root=True)),observed_path)
        need((observed['inode'],observed['linux_major'],observed['linux_minor'])==
             (mapped[0]['inode'],mapped[0]['major'],mapped[0]['minor']), 'emitter mapped inode/device differs from actual file')
        emitters[soname]=dict(mappings=mapped,file=observed,path=observed_path)
    logs=required('hilog -x')
    need(process() == before and provider_bms(c,required('bm dump -n '+BUNDLE)) == bms and
         required('cat /proc/sys/kernel/random/boot_id').decode().strip() == boot,
         'provider PID/birth/BMS or boot changed during native observation')
    maps_after=required('cat /proc/'+pid+'/maps')
    provider_namespace_after=time_namespace496(pid)
    base['provider_namespace496']=dict(before=provider_namespace_before,after=provider_namespace_after)
    if provider_namespace_before['value']!=provider_namespace_after['value']:
        pending.append('actual provider time namespace changed; no clock-domain proof')
    for soname,emitter in emitters.items():
        need(emitter_maps496(maps_after,soname)==emitter['mappings'], 'actual emitter mapping changed during observation')
        need(file_observation(c,required(c.stat_script(emitter['path'],process_root=True)),emitter['path'])==emitter['file'],
             'actual emitter file bytes/inode changed during observation')
    need(process()==before and required('cat /proc/sys/kernel/random/boot_id').decode().strip()==boot,
         'provider generation changed after emitter recheck')
    base['loaded_emitters496']=emitters
    base['maps_after_raw_hex496']=maps_after.hex()
    base['native_clock_after496']=clock496()
    base.update(process_absent=False,hilog_raw_hex=logs.hex(),process=before,bms=bms,bms_raw_hex=bmsraw.hex(),maps_raw_hex=mapsraw.hex(),
                mapped_provider=maps,mapped_file=stat,installed_hap=hap)
    # Byte association never labels a report status or log substring as callback
    #proof. The original fixed image verifier remains independent and required.
    proof=bridge.spec.get('native_image_report')
    if proof is None:
        pending.append('new package canonical Number image report absent; loaded bytes captured, not image-bound')
    else:
        report=c.decode(c.checked(proof).read_bytes())
        import hashlib
        actual_system=bridge.guest.directory/'images/system.img'
        hasher=hashlib.sha256()
        with actual_system.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''): hasher.update(chunk)
        actual_system_sha=hasher.hexdigest()
        need(report.get('status') == 'pass' and report.get('failures') == [] and report.get('source_revision') == '50e1330646432ce166e7981c577f25f46c90e7ac' and
             report.get('system_image_sha256') == actual_system_sha and
             report.get('hap_sha256') == hap['sha256'] and
             report.get('bundled_native_provider',{}).get('sha256') == stat['sha256'] and
             report.get('native_libraries',{}).get(LIB,{}).get('sha256') == stat['sha256'],
             'actual new image/HAP/bundled ELF/system ELF/loaded inode bytes differ')
        base['new_image_byte_join']=dict(image_report=proof,archive_sha256=bridge.owner.config['archive']['sha256'],
            system_image_sha256=report['system_image_sha256'],scope='bytes join ONLY; callback loading remains independent')
    pending.append('Existing source callback logs lack a proved request nonce/PID+birth log parser; raw window retained, no callback claim')
    return base
