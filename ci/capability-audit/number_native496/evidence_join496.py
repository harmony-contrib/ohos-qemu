"""Read-only raw replay inside the original admitted Number411 context.

No CLI creates an admitted context or Owner. The parent may call review() after
the original source/build/recheck/ELF admission; summaries cannot replace it.
"""
from pathlib import Path
import hashlib
import builtins
import re
import stat
import struct
import types

try:
    from . import consumer496 as core
except ImportError:
    import consumer496 as core

HERE=Path(__file__).resolve().parent
SUPPORT={
 'napi_protocol411.py':'03ae5a3a5d5cdc4932e6421bc64c39e06880b701326682bb6dfaf0c4d7c5ec49',
 'number_local_collector411.py':'6f9a1fff50af9c3111e70a9646fa8d1aab0836c1b7f9668a8eb8cca31feb84de',
 'guest_ui.py':'8f8fba0256492ff3d9d8bcfa526540954a8cafa42381cc16fd02c7cd48a4147f',
}
TOKEN_QUERY='/data/local/tmp/number-token395'
CAPTURE_SHA='e0cc7372d13c71d3d08269d42ea1c71738d9672761ba4cf17a66d47e8c236bb6'
CPP_SHA='b56d895cddd5dcc375b7b871e871b199540b43c0a495d7ec8b31ff1106a4e5ed'


def checked(row, maximum=16*1024*1024):
    core.need(type(row) is dict and set(row)=={'path','sha256','bytes'} and type(row['path']) is str and
        type(row['bytes']) is int and 0<row['bytes']<=maximum and re.fullmatch('[0-9a-f]{64}',row['sha256'] or ''),
        'exact bounded actual file descriptor required')
    path=Path(row['path'])
    core.need(path.is_absolute() and path.resolve()==path and all(not p.is_symlink() for p in (path,*path.parents)),
        'canonical evidence path/ancestors required')
    info=path.stat()
    core.need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size==row['bytes'],
        'one regular immutable evidence inode/size required')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    core.need(digest.hexdigest()==row['sha256'],'actual evidence bytes changed')
    return path


def original_modules():
    modules={}
    for name,sha in SUPPORT.items():
        path=HERE/'support'/name
        row={'path':str(path),'bytes':path.stat().st_size,'sha256':sha}
        checked(row)
        module_name=name.removesuffix('.py')
        # Fixed private definition loading does not replace modules already used
        # by the live original Owner. Only the one literal unchanged collector
        # import is resolved to this byte-pinned original NAPI dependency.
        module=types.ModuleType('_number496_original_'+module_name);module.__file__=str(path)
        imports=dict(vars(builtins))
        def fixed_import(import_name, globals=None, locals=None, fromlist=(), level=0):
            if import_name=='napi_protocol411' and level==0:
                core.need('napi_protocol411' in modules,'pinned original NAPI dependency must load first')
                return modules['napi_protocol411']
            return builtins.__import__(import_name,globals,locals,fromlist,level)
        imports['__import__']=fixed_import;module.__dict__['__builtins__']=imports
        raw=path.read_bytes();core.need(hashlib.sha256(raw).hexdigest()==sha,'original support changed before definition load')
        exec(compile(raw,str(path),'exec'),module.__dict__)
        modules[module_name]=module
    path=HERE/'candidate/native_observation411.py'
    checked({'path':str(path),'bytes':path.stat().st_size,'sha256':CAPTURE_SHA})
    native=types.ModuleType('_number496_native_capture');native.__file__=str(path)
    raw=path.read_bytes();core.need(hashlib.sha256(raw).hexdigest()==CAPTURE_SHA,'reviewed capture changed before definition load')
    exec(compile(raw,str(path),'exec'),native.__dict__)
    return modules['number_local_collector411'],modules['napi_protocol411'],modules['guest_ui'],native


def ledger(descriptors, hdc, target):
    core.need(type(descriptors) is list and descriptors,'actual original Bridge call ledger required')
    entries={};indices=set()
    for descriptor in descriptors:
        row=core.decode_json(checked(descriptor).read_bytes())
        core.need(type(row) is dict and set(row)=={'argv','exit_code','stdout_hex','stderr_hex','transport_failure','held_index'} and
            row['exit_code']==0 and type(row['exit_code']) is int and row['transport_failure'] is False and
            type(row['held_index']) is int and row['held_index']>=0 and row['held_index'] not in indices and
            type(row['argv']) is list and all(type(v) is str for v in row['argv']) and
            row['argv'][:3]==[hdc,'-t',target],'actual serial original Bridge record/target required')
        indices.add(row['held_index'])
        entries[row['held_index']]=row
    return entries


def snapshot(descriptor, entries, hdc, target, modules):
    c,napi,ui,native=modules
    report=core.decode_json(checked(descriptor).read_bytes())
    core.need(type(report) is dict and report.get('native_callback_proven') is False and
        report.get('first_artifact_behavior_gate_passed') is False and type(report.get('actual_calls')) is list,
        'original raw-only capture fields required')
    commands={};indices=[]
    wrapper=re.compile(r'^\( (.+) \); r=\$\?; printf "\\n(__NUMBER_NATIVE_EXIT_[0-9a-f]{32}__=)%s\\n" "\$r"$')
    for row in report['actual_calls']:
        core.need(type(row) is dict and set(row)=={'argv','exit_code','guest_exit_code','stdout_hex','stderr_hex','held_index'},
            'exact original native command raw fields required')
        argv=row['argv']
        core.need(type(argv) is list and len(argv)==5 and argv[:4]==[hdc,'-t',target,'shell'],'fixed captured HDC wrapper required')
        match=wrapper.fullmatch(argv[4]);core.need(match is not None,'fixed original native shell wrapper required')
        index=row['held_index']
        expected={k:v for k,v in row.items() if k not in ('guest_exit_code',)}
        expected['transport_failure']=False
        core.need(type(index) is int and index in entries and entries[index]==expected,
            'native raw is not at its exact original held Bridge authority index')
        indices.append(index)
        raw=bytes.fromhex(row['stdout_hex'])
        body,code=ui.command_exit(raw.decode('utf-8','strict'),match[2])
        core.need(type(row['guest_exit_code']) is int and row['guest_exit_code']==code,
            'raw terminal footer/guest exit differs')
        commands.setdefault(match[1],[]).append((body.encode(),code))
    core.need(indices and all(indices[i]<indices[i+1] for i in range(len(indices)-1)),'native command order is not retained authority order')
    def rows(command):
        core.need(command in commands,'missing actual native raw command: '+command)
        return commands[command]
    def one(command):
        values=rows(command);core.need(len(values)==1 and values[0][1]==0,'one successful actual command required: '+command)
        return values[0][0]
    boot=report.get('boot_id')
    core.need(re.fullmatch(core.BOOT,boot or '') and all(code==0 and raw.decode().strip()==boot for raw,code in
        rows('cat /proc/sys/kernel/random/boot_id')),'native boot changed or raw binding differs')
    core.need(one('hilog -x').hex()==report.get('hilog_raw_hex'),'retained actual Hilog body differs')
    clocks=[]
    for key in ('native_clock_before496','native_clock_after496'):
        row=report.get(key)
        if type(row) is not dict or row.get('value') is None: raise core.Pending('actual native dual-clock/namespace sample missing or failed')
        raw=one(TOKEN_QUERY+' --native-clock '+row['nonce'])
        core.need(raw.hex()==row['raw_hex'] and row.get('guest_exit_code')==0,'actual clock invocation raw/exit differs')
        value=core.clock(raw,row['nonce'],boot)
        core.need(value==row['value'],'derived clock summary differs from real command')
        clocks.append(value)
    core.clock_offset(clocks)
    pid_body,pid_code=rows('pidof '+native.BUNDLE)[0]
    if report.get('process_absent') is True:
        core.need(pid_code==1 and pid_body==b'','only exact pidof guest1/empty is provider absence')
        return dict(report=report,process=None,clocks=clocks,indices=indices,raw=one('hilog -x'),commands=commands)
    core.need(pid_code==0 and re.fullmatch(rb'[1-9][0-9]*\n?',pid_body),'one actual provider PID required')
    pid=pid_body.decode().strip()
    bms_rows=[native.provider_bms(c,raw) for raw,code in rows('bm dump -n '+native.BUNDLE) if code==0]
    core.need(len(bms_rows)>=2 and all(v==bms_rows[0] for v in bms_rows) and bms_rows[0]==report['bms'],
        'actual before/after provider BMS differs')
    statuses=rows('cat /proc/'+pid+'/status');cmdlines=rows('cat /proc/'+pid+'/cmdline');stats=rows('cat /proc/'+pid+'/stat')
    core.need(len(statuses)==len(cmdlines)==len(stats)>=2,'actual stable provider process before/after raw required')
    identities=[]
    for (status,sc),(cmdline,cc),(raw,rc) in zip(statuses,cmdlines,stats):
        core.need(sc==cc==rc==0,'actual process observation failed')
        identities.append(c.process_identity(pid,status,cmdline,raw,native.BUNDLE,bms_rows[0]['uid']))
    core.need(all(v==identities[0] for v in identities) and identities[0]==report['process'],'actual provider PID/birth/UID changed')
    maps=rows('cat /proc/'+pid+'/maps')
    core.need(len(maps)==2 and all(code==0 for _,code in maps) and maps[0][0].hex()==report['maps_raw_hex'] and
        maps[1][0].hex()==report.get('maps_after_raw_hex496'),'actual dual emitter maps before/after required')
    loaded={}
    for soname in core.SONAMES:
        first=native.emitter_maps496(maps[0][0],soname);last=native.emitter_maps496(maps[1][0],soname)
        core.need(first==last,'emitter mapping/device/inode changed')
        path='/proc/'+pid+'/root'+first[0]['path']
        observations=[]
        for raw,code in rows(c.stat_script(path,process_root=True)):
            core.need(code==0,'actual mapped emitter hash failed');observations.append(native.file_observation(c,raw,path))
        core.need(len(observations)>=2 and all(v==observations[0] for v in observations),'mapped file bytes/metadata changed')
        file=observations[0]
        core.need((file['inode'],file['linux_major'],file['linux_minor'])==(first[0]['inode'],first[0]['major'],first[0]['minor']),
            'hashed mapped file differs from executable mapping inode/device')
        loaded[soname]=dict(mappings=first,file=file,path=path)
    core.need(loaded==report.get('loaded_emitters496'),'derived emitter summary differs from actual raw')
    namespaces=rows("stat -Lc '%d %i' /proc/"+pid+'/ns/time')
    namespace_values=[]
    for raw,code in namespaces:
        if code!=0: raise core.Pending('actual provider time namespace read failed')
        core.need(re.fullmatch(rb'[1-9][0-9]* [1-9][0-9]*\n?',raw),'actual provider namespace dev/inode required')
        namespace_values.append(tuple(map(int,raw.split())))
    core.need(len(namespace_values)==2 and namespace_values[0]==namespace_values[1],'provider namespace changed/missing')
    for sample in clocks:
        if namespace_values[0]!=(sample['time_ns_dev'],sample['time_ns_inode']):
            raise core.Pending('provider/helper clocks belong to different actual time namespaces')
    return dict(report=report,process=identities[0],clocks=clocks,indices=indices,raw=one('hilog -x'),
        commands=commands,loaded=loaded,namespace=namespace_values[0])


def plain_call(descriptor, expected, entries):
    row=core.decode_json(checked(descriptor).read_bytes())
    core.need(row.get('argv')==expected and row.get('exit_code')==0 and row.get('transport_failure') is False,
        'actual fixed original Bridge caller command required')
    core.need(type(row.get('held_index')) is int and entries.get(row['held_index'])==row,
        'caller raw not at exact same held original Bridge authority index')
    return bytes.fromhex(row['stdout_hex'])


def replay_caller(after, role, fields, c, *, allow_absent=False):
    commands=after['commands'];observed=after['report'].get('caller496')
    if allow_absent and type(observed) is dict and observed.get('process_absent') is True:
        core.need(observed=={'role':role,'process_absent':True} and
            commands.get('pidof '+c.ROLES[role][0])==[(b'',1)],
            'before caller absence requires exact original pidof guest1/empty raw')
        return None
    if type(observed) is not dict or observed.get('process_absent') is not False:
        raise core.Pending('actual current caller process/time namespace observation absent')
    core.need(observed.get('role')==role,'caller capture role differs')
    bundle=c.ROLES[role][0]
    pid_rows=commands.get('pidof '+bundle,[])
    core.need(len(pid_rows)==1 and pid_rows[0][1]==0 and re.fullmatch(rb'[1-9][0-9]*\n?',pid_rows[0][0]),
        'actual captured caller pidof required')
    pid=pid_rows[0][0].decode().strip()
    bms_raws=commands.get('bm dump -n '+bundle,[])
    core.need(len(bms_raws)==2 and all(code==0 for _,code in bms_raws),'actual caller BMS before/after raw missing')
    bms=[c.bms_fields(raw,bundle,fields) for raw,code in bms_raws]
    core.need(bms[0]==bms[1]==observed['bms'],'actual caller BMS changed/summary differs')
    leaves=[commands.get('cat /proc/'+pid+'/'+leaf,[]) for leaf in ('status','cmdline','stat')]
    core.need(all(len(rows)==2 and all(code==0 for _,code in rows) for rows in leaves),
        'actual caller PID/birth before/after missing')
    identities=[c.process_identity(pid,leaves[0][i][0],leaves[1][i][0],leaves[2][i][0],bundle,bms[0]['uid']) for i in range(2)]
    core.need(identities[0]==identities[1]==observed['process'],'actual caller PID/birth changed/summary differs')
    namespaces=commands.get("stat -Lc '%d %i' /proc/"+pid+'/ns/time',[])
    if len(namespaces)!=2 or any(code!=0 for _,code in namespaces):
        raise core.Pending('actual caller namespace reads missing/failed')
    parsed=[]
    for (raw,code),key in zip(namespaces,('namespace_before','namespace_after')):
        core.need(re.fullmatch(rb'[1-9][0-9]* [1-9][0-9]*\n?',raw),'actual caller namespace dev/inode required')
        value=dict(zip(('dev','inode'),map(int,raw.split())))
        core.need(observed[key]==dict(path='/proc/'+pid+'/ns/time',raw_hex=raw.hex(),guest_exit_code=code,value=value),
            'caller namespace summary not derived from retained actual command')
        parsed.append((value['dev'],value['inode']))
    namespace=after.get('namespace')
    if namespace is None:
        namespace=(after['clocks'][0]['time_ns_dev'],after['clocks'][0]['time_ns_inode'])
        core.need(all((row['time_ns_dev'],row['time_ns_inode'])==namespace for row in after['clocks']),
            'actual helper namespace differs within provider-absent caller capture')
    if parsed[0]!=parsed[1] or parsed[0]!=namespace:
        raise core.Pending('actual caller/provider/helper time namespaces differ or change')
    return dict(process=identities[0],bms=bms[0],namespace=parsed[0])


def replay_caller_generation(before, after, role, fields, c):
    observed=replay_caller(after,role,fields,c)
    earlier=replay_caller(before,role,fields,c,allow_absent=True)
    if earlier is not None:
        core.need(earlier==observed,'caller PID/birth/BMS/namespace changed across the public request window')
    return observed


def helper_identity(entries, hdc, target, c, native, admitted):
    expected=[hdc,'-t',target,'shell',c.stat_script(TOKEN_QUERY)]
    rows=[]
    for row in entries.values():
        if row['argv']!=expected:continue
        core.need(row['exit_code']==0 and row['stderr_hex']=='','actual observer stat failed')
        value=native.file_observation(c,bytes.fromhex(row['stdout_hex']),TOKEN_QUERY)
        core.need(value['uid']==0 and value['mode']==0o500 and value['sha256']==admitted.binary_record['sha256'] and
            value['bytes']==admitted.binary_record['bytes'],'actual staged observer bytes/root mode differ from original admission')
        rows.append(value)
    core.need(len(rows)>=4 and all(row==rows[0] for row in rows),'actual original observer inode/hash before/after samples missing/changed')
    return rows[0]


def image_bytes(bindings, after):
    loader=bindings.get('loader_image_report')
    if loader is None: raise core.Pending('independent same-new-image MainThread loader ELF proof missing')
    number=core.decode_json(checked(bindings['number_image_report']).read_bytes())
    loader_report=core.decode_json(checked(loader).read_bytes())
    loader=loader_report.get('loader_library')
    image=bindings['system_image'];checked(image,maximum=16*1024**3)
    core.need(number.get('status')=='pass' and number.get('failures')==[] and
        number.get('system_image_sha256')==image['sha256'],'actual Number image/hash proof required')
    # The parent owns the finite offline loader export. This independent nullable
    # interface does not guess a hash from historical bytes or generated Ninja.
    core.need(loader_report.get('status')=='pass' and loader_report.get('failures')==[] and
        type(loader) is dict and loader.get('scope')=='on-disk loader ELF only; loaded process and callback remain unverified' and
        loader.get('system_image_sha256')==loader_report.get('system_image_sha256')==image['sha256'] and
        loader.get('basename')==core.SONAMES[0] and loader.get('loaded_process_verified') is False and
        loader.get('native_callback_proven') is False and
        (loader.get('elf_class'),loader.get('elf_machine'),loader.get('elf_type'))==(2,183,3) and
        type(loader.get('image_inode')) is int and loader['image_inode']>0 and
        type(loader.get('image_path')) is str,
        'actual independent loader extraction/image binding required')
    aliases=loader.get('image_path_aliases')
    candidates=['/lib64/'+core.SONAMES[0],'/system/lib64/'+core.SONAMES[0],
        '/lib64/platformsdk/'+core.SONAMES[0],'/system/lib64/platformsdk/'+core.SONAMES[0]]
    core.need(type(aliases) is list and aliases and
        aliases == [path for path in candidates if path in aliases] and
        loader['image_path']==aliases[0],
        'actual loader aliases must retain the finite same-inode extraction order')
    actual={}
    core.need(type(bindings['emitter_elfs']) is dict and set(bindings['emitter_elfs'])==set(core.SONAMES),
        'exact two real emitter ELF descriptors required')
    for soname,descriptor in bindings['emitter_elfs'].items():
        path=checked(descriptor,maximum=256*1024*1024);raw=path.read_bytes()
        core.need(len(raw)>=64 and raw[:7]==b'\x7fELF\x02\x01\x01' and struct.unpack_from('<HH',raw,16)==(3,183),
            'actual AArch64 dynamic ELF required')
        prefix=b'NUMBER_NATIVE495_LOAD v=1' if soname==core.SONAMES[0] else b'NUMBER_NATIVE495 v=1'
        core.need(prefix in raw,'new diagnostic producer missing from actual image ELF')
        image_sha=loader.get('sha256') if soname==core.SONAMES[0] else number.get('native_libraries',{}).get(soname,{}).get('sha256')
        if soname==core.SONAMES[0]:
            core.need(loader.get('file')==str(path) and loader.get('bytes')==descriptor['bytes'],
                'actual loader export file path/size differs from independent image proof')
        core.need(descriptor['sha256']==image_sha==after['loaded'][soname]['file']['sha256'],
            'new image/dumped ELF/actual mapped file full-byte join differs')
        actual[soname]=descriptor
    core.need(number.get('bundled_native_provider',{}).get('sha256')==actual[core.SONAMES[1]]['sha256'],
        'Number installed system and HAP native implementation differ')
    return actual


def review(bindings, *, admitted=None):
    """Consume actual raw within original admission; return a narrow chain fact.

    No Boolean or JSON status can create `admitted`: parent must replay original
    observer_admission396.admit with the actual build/recheck/profile/ELF inputs.
    This function is not an Owner or an aggregate/full-suite acceptance entry.
    """
    required={'schema','hdc','target','source_commit','archive_sha256','before','after','generation_captures','bridge_calls','caller',
        'number_image_report','loader_image_report','system_image','emitter_elfs','build_inputs','producer_sources'}
    core.need(type(bindings) is dict and set(bindings)==required and bindings['schema']=='number-native-consumer496/v1',
        'fixed source-only consumer bindings schema required')
    missing=[k for k in required-{'schema'} if bindings[k] is None]
    if missing: raise core.Pending('actual inputs pending: '+','.join(sorted(missing)))
    if admitted is None: raise core.Pending('original actual compile/recheck/ELF/profile admission must be replayed, not summarized')
    core.need(re.fullmatch('[0-9a-f]{40}',bindings['source_commit'] or '') and
        re.fullmatch('[0-9a-f]{64}',bindings['archive_sha256'] or ''),'actual new source/archive identity required')
    evidence=admitted.evidence
    core.need(evidence['actual_source']['sha256']==CPP_SHA and checked(evidence['actual_source']).read_bytes()==
        (HERE/'candidate/number_token_query395.cpp').read_bytes(),'actual admitted clock/Token observer source differs')
    checked(evidence['actual_ELF'],maximum=128*1024*1024)
    core.need(admitted.profile['archive']['sha256']==bindings['archive_sha256'] and
        admitted.profile['system_image']['sha256']==bindings['system_image']['sha256'],'original admission belongs to another image')
    sources=bindings['producer_sources']
    core.need(type(sources) is dict and set(sources)=={'capture','observer'} and
        sources['capture']['sha256']==CAPTURE_SHA and sources['observer']['sha256']==CPP_SHA,'fixed reviewed producer source required')
    for row in sources.values():checked(row)
    inputs=core.decode_json(checked(bindings['build_inputs'],maximum=4*1024*1024).read_bytes())
    core.need(inputs.get('source_git_revision')==bindings['source_commit'],'actual new package source commit differs')
    modules=original_modules();c,napi,ui,native=modules
    core.need(type(bindings['generation_captures']) is list and len(bindings['generation_captures'])==2,
        'exact original DataShare-cycle generation before/after descriptors required')
    entries=ledger(bindings['bridge_calls'],bindings['hdc'],bindings['target'])
    helper_identity(entries,bindings['hdc'],bindings['target'],c,native,admitted)
    before=snapshot(bindings['before'],entries,bindings['hdc'],bindings['target'],modules)
    after=snapshot(bindings['after'],entries,bindings['hdc'],bindings['target'],modules)
    generation=[snapshot(row,entries,bindings['hdc'],bindings['target'],modules) for row in bindings['generation_captures']]
    core.need([row['report']['label'] for row in generation]==['datashare-cycle-before','datashare-cycle-after'],
        'fixed original initial generation capture labels required')
    frames=generation+[before,after]
    core.need(all(row['report']['boot_id']==after['report']['boot_id'] for row in frames) and
        all(max(frames[i]['indices'])<min(frames[i+1]['indices']) for i in range(len(frames)-1)),
        'generation/public snapshots must retain same-boot actual Authority order')
    for frame in frames:
        if frame['process'] is not None:
            core.need(frame['process']==after['process'] and frame['loaded']==after['loaded'] and frame['namespace']==after['namespace'],
                'actual provider generation/emitter bytes/namespace changed across generation/public observations')
    core.need(after['process'] is not None and before['report']['boot_id']==after['report']['boot_id'],
        'provider absence/cross-boot is not native callback proof')
    core.need(max(before['indices'])<min(after['indices']),'actual before/after capture authority order differs')
    if before['process'] is not None:
        core.need(before['process']==after['process'] and before['loaded']==after['loaded'] and before['namespace']==after['namespace'],
            'provider generation/emitter bytes/namespace changed across public request')
    caller=bindings['caller']
    caller_keys={'role','run','owner_run','number','actual_context','journal','token_before','token_after','bms_fields','bms_call','query_call'}
    core.need(type(caller) is dict and set(caller)==caller_keys and caller['role'] in ('system-granted','system-readonly'),
        'one real system role public NAPI phase required; ordinary denial remains separate')
    role=caller['role'];run=caller['run'];bundle=c.ROLES[role][0];boot=after['report']['boot_id']
    core.need(before['report']['label']==role+'-before' and after['report']['label']==role+'-after','actual same role public window labels required')
    start_argv=[bindings['hdc'],'-t',bindings['target'],'shell','aa','start','-b',bundle,'-a','EntryAbility',
        '--ps','run',run,'--ps','phase','napi-read','--ps','number',caller['number'],'--ps','ownerRun',caller['owner_run']]
    starts=[index for index,row in entries.items() if row['argv']==start_argv and row['exit_code']==0]
    core.need(len(starts)==1 and max(before['indices'])<starts[0]<min(after['indices']),
        'one actual nonce-bound original public caller start must lie between retained capture commands')
    journal=checked(caller['journal'],maximum=1024*1024).read_bytes()
    public=napi.review(journal,role=role,run=run,owner=caller['owner_run'],number=caller['number'],actual_context=caller['actual_context'])
    journal_rows=napi.rows(journal,run,caller['owner_run'],caller['number'])
    caller_pid=core.caller_pid(after['raw'],journal_rows)
    bms_raw=plain_call(caller['bms_call'],[bindings['hdc'],'-t',bindings['target'],'shell','bm','dump','-n',bundle],entries)
    bms=c.bms_fields(bms_raw,bundle,caller['bms_fields'])
    access_raw=plain_call(caller['query_call'],[bindings['hdc'],'-t',bindings['target'],'shell',TOKEN_QUERY,run,'identity',bundle,str(bms['token'])],entries)
    access=c.query_access(access_raw,role,run,'identity',boot,bms)
    first=c.token_join(checked(caller['token_before'],maximum=1024*1024).read_bytes(),role,run,'napi-before',bms,access)
    last=c.token_join(checked(caller['token_after'],maximum=1024*1024).read_bytes(),role,run,'napi-after',bms,access)
    core.need(first==last,'actual caller Token before/after differs')
    observed=replay_caller_generation(before,after,role,caller['bms_fields'],c)
    core.need(observed['process']['pid']==caller_pid and observed['process']['uid']==first['uid'] and observed['bms']==bms,
        'caller raw header PID/independent Token/BMS/process identity differs')
    images=image_bytes(bindings,after)
    start=before['clocks'][-1]['monotonic_after_ns'];end=after['clocks'][0]['monotonic_before_ns']
    decoded=[core.structured_events(frame['raw']) if frame['process'] is not None and b'NUMBER_NATIVE495' in frame['raw'] else [] for frame in frames]
    events=core.merge_snapshots496(decoded,after['process']['pid'])
    samples=[sample for frame in frames for sample in frame['clocks']]
    proof=core.chain(events,process=after['process'],samples=samples,window=(start,end),
        caller={'pid':caller_pid,'uid':first['uid'],'token':first['token'],
            'start_ticks':observed['process']['start_ticks']})
    proof.update(scope='actual raw native-chain replay within original Number admitted context ONLY',
        image_emitters=images,public_api_review=public,native_callback_chain_checked=True,
        original411_verdict_changed=False,first_artifact_behavior_gate_passed=False,aggregate_provider_passed=False)
    return proof


PACKAGE_KEYS496={'number_image_report','loader_image_report','system_image','emitter_elfs','build_inputs','producer_sources'}


def descriptor496(path):
    path=Path(path)
    core.need(path.is_absolute() and path.resolve()==path and not path.is_symlink(),
        'canonical local original evidence path required')
    raw=path.read_bytes()
    row=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    checked(row,maximum=16*1024**3)
    return row


def write496(path,value):
    # Independent local evidence only; never rewrites original reports/ledgers.
    raw=(__import__('json').dumps(value,indent=2,allow_nan=False)+'\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(raw);stream.flush();__import__('os').fsync(stream.fileno())
    return descriptor496(path)


def collect_bridge496(*,bridge,probe,admitted,package_inputs,output):
    """One local-only hook after original probe.collect(), before Owner cleanup.

    The caller is the unchanged original live Owner holding its Bridge, Collector
    and original AdmittedObserver. No command/callback/Owner is created here.
    Incomplete/old-image inputs yield three independent pending receipts. The
    original Collector status/pending/native_callback_proven/47 are untouched.
    """
    root=Path(output)
    core.need(root.is_absolute() and root.parent.resolve()==root.parent and not root.exists() and
        not root.is_symlink(),'one fresh canonical local native-review output required')
    root.mkdir(mode=0o700)
    if package_inputs is None:package_inputs={key:None for key in PACKAGE_KEYS496}
    core.need(type(package_inputs) is dict and set(package_inputs)==PACKAGE_KEYS496,
        'fixed DATA descriptors only; no package claim/callback is execution authority')
    results={}
    for role in ('system-granted','system-readonly','ordinary'):
        item=dict(role=role,status='pending_actual_native_inputs_ONLY',pending=[],
            native_callback_chain_checked=False,original411_verdict_changed=False,
            first_artifact_behavior_gate_passed=False,aggregate_provider_passed=False)
        try:
            if admitted is None:raise core.Pending('original admitted observer missing; no JSON admission fallback')
            missing=sorted(key for key,value in package_inputs.items() if value is None)
            if missing:raise core.Pending('actual package/producer descriptors pending: '+','.join(missing))
            c,napi,ui,native=original_modules()
            spec=bridge.spec;hdc=bridge.owner.hdc;target=bridge.guest.target
            core.need(bridge.observer is admitted and probe.spec is spec,
                'original Bridge/Collector must share the actual original admitted object/spec')
            actual_calls=[];call_rows=[]
            for index,retained in enumerate(bridge.calls):
                path=bridge.out/('call-%04d.json'%index)
                descriptor=descriptor496(path);row=core.decode_json(checked(descriptor).read_bytes())
                core.need(row==retained,'registered original Bridge row differs from retained raw file')
                # Controlled reboot QMP/host commands are retained by the Owner;
                # they are not falsely relabeled as target HDC observations.
                if row.get('argv',[])[:3]==[hdc,'-t',target]:
                    actual_calls.append(descriptor);call_rows.append((row,descriptor))
            core.need(actual_calls,'actual original held HDC ledger absent')
            phases=[value for value in probe.napi_phases if value.get('role')==role and value.get('phase')=='napi-read']
            if len(phases)!=1:raise core.Pending('one actual completed original public NAPI phase missing/ambiguous')
            phase=phases[0]
            core.need(len(phase['files'])==3 and phase['run']==spec['runs'][role] and
                phase['owner_run']==spec['runs']['system-granted'],'registered original NAPI file/run triple differs')
            phase_path=probe.output/(role+'-napi-read.json')
            phase_descriptor=descriptor496(phase_path)
            core.need(core.decode_json(checked(phase_descriptor).read_bytes())==phase,
                'registered original completed phase differs from independently retained phase file')
            observations=[]
            for suffix in ('before','after'):
                matches=[value for value in bridge.native_observations if value.get('label')==role+'-'+suffix]
                if len(matches)!=1:raise core.Pending('actual native '+role+'-'+suffix+' capture missing/ambiguous')
                value=core.decode_json(checked(matches[0]['evidence']).read_bytes())
                if any(type(value.get(key)) is not dict or value[key].get('value') is None for key in
                    ('native_clock_before496','native_clock_after496')):
                    raise core.Pending('original/failed clock capture is not a new dual-clock raw observation')
                if any('held_index' not in row for row in value.get('actual_calls',[])):
                    raise core.Pending('old native capture lacks exact original Authority indices')
                observations.append(matches[0]['evidence'])
            generation=[]
            for label in ('datashare-cycle-before','datashare-cycle-after'):
                matches=[value for value in bridge.native_observations if value.get('label')==label]
                if len(matches)!=1:raise core.Pending('actual initial '+label+' generation capture missing/ambiguous')
                generation.append(matches[0]['evidence'])
            bundle=c.ROLES[role][0];fields=spec['roles'][role]['bms']['fields']
            def unique_raw_call(argv,boot=None):
                candidates=[]
                for row,descriptor in call_rows:
                    if row.get('argv')!=argv or row.get('exit_code')!=0 or row.get('transport_failure') is not False:continue
                    if boot is not None:
                        parsed=core.decode_json(bytes.fromhex(row['stdout_hex']))
                        if parsed.get('boot_id')!=boot:continue
                    candidates.append((row,descriptor))
                if not candidates:raise core.Pending('actual registered independent identity command absent')
                # Repeated equal identity snapshots are legal. Divergent raw
                # identity is refused, never chosen by nearest timestamp.
                signatures={(row['stdout_hex'],row['stderr_hex']) for row,_ in candidates}
                if len(signatures)!=1:raise core.Pending('independent identity raw has multiple distinct candidates')
                return min(candidates,key=lambda pair:pair[0]['held_index'])
            bms_row,bms_descriptor=unique_raw_call([hdc,'-t',target,'shell','bm','dump','-n',bundle])
            bms=c.bms_fields(bytes.fromhex(bms_row['stdout_hex']),bundle,fields)
            query_row,query_descriptor=unique_raw_call([hdc,'-t',target,'shell',TOKEN_QUERY,
                phase['run'],'identity',bundle,str(bms['token'])],boot=phase['boot_id'])
            caller=dict(role=role,run=phase['run'],owner_run=phase['owner_run'],number=spec['number'],
                actual_context=phase['actual_file_binding']['actual_context'],journal=phase['files'][0],
                token_before=phase['files'][1],token_after=phase['files'][2],bms_fields=fields,
                bms_call=bms_descriptor,query_call=query_descriptor)
            bindings=dict(schema='number-native-consumer496/v1',hdc=hdc,target=target,
                source_commit=spec['source_commit'],archive_sha256=spec['archive_sha256'],
                before=observations[0],after=observations[1],generation_captures=generation,bridge_calls=actual_calls,caller=caller,**package_inputs)
            item['original_phase']=phase_descriptor
            item['bindings']=write496(root/(role+'-bindings.json'),bindings)
            if role=='ordinary':
                # The original ordinary public-denial oracle and pending error
                # domain remain the authority. It has no permitted Query chain.
                raise core.Pending('ordinary role original denial review retained separately; no permission-granted native Query chain claimed')
            proof=review(bindings,admitted=admitted)
            item['proof']=write496(root/(role+'-proof.json'),proof)
            item['native_callback_chain_checked']=proof['native_callback_chain_checked']
            item['status']='checked_native_chain_ONLY'
        except core.Pending as error:item['pending'].append(str(error))
        except (FileNotFoundError,PermissionError) as error:
            item['pending'].append('actual registered local evidence unavailable: '+type(error).__name__+': '+str(error))
        except Exception as error:
            item['status']='rejected_native_evidence_ONLY'
            item['failures']=[type(error).__name__+': '+str(error)]
        results[role]=write496(root/(role+'-review.json'),item)
    return dict(schema='number-native496-independent-index/v1',roles=results,
        scope='local replay of original registered raw only; original Owner verdict and 47 unchanged',
        original411_verdict_changed=False,first_artifact_behavior_gate_passed=False,aggregate_provider_passed=False)
