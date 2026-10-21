"""Actual raw global inventory; never inject namespace fields into CONTROL13."""
from pathlib import Path
import hashlib,json,re,stat,struct,shlex,time
import onset579_global_clock as clock
INVENTORY_KEYS=('holder_pid','holder_ticks','holder_uid','holder_gid','fd','dev','ino','rdev','card','device','subdevice')
def need(ok,message):
    if not ok:raise ValueError(message)
def checked(ref):
    need(type(ref) is dict and set(ref)=={'path','sha256'},'actual raw Ref2 required')
    p=Path(ref['path']);need(p.is_absolute() and p.resolve()==p and not any(n.is_symlink() for n in (p,*p.parents)) and
        p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==ref['sha256'],'actual original raw bytes changed')
    return p
def inventory(raw,*,boot,run,domain):
    from onset579_global_mapping import decode
    need(type(raw) is str and raw.endswith('\n') and 0<len(raw.encode())<=2*1024*1024,'bounded actual complete inventory raw')
    rows=[decode(line) for line in raw.splitlines()]
    need(len(rows)==4 and [r['kind'] for r in rows]==['inventory_begin','inventory_before','inventory_after','inventory_complete'],'complete actual four-row INFO/OFD inventory')
    begin,before,after,end=rows
    need(begin['schema']==end['schema']=='existing-pcm-holder-global-clock579/v1' and begin['run']==end['run']==run and begin['boot']==end['boot']==boot and end['candidates']==1 and end['duplicate_close_rc']==end['pidfd_close_rc']==0 and end['ready'] is True and end['accepted'] is end['onset_proven'] is False,'actual inventory identity/unique candidate/FD closure')
    need(0<begin['before_ns']<=before['before_ns']<=before['after_ns']<=after['before_ns']<=after['after_ns']<=end['after_ns'],'actual inventory monotonic two-cut sequence')
    fields=('pid','ticks','fd','borrowed_fd','uids','gids','descriptor_stat','proc_fd_stat','pcm_info_bytes','pcm_info_hex','boot','fd_link','exe')
    need(all(before[k]==after[k] for k in fields) and before['pid']>1 and before['ticks']>0 and before['borrowed_fd']>=0 and before['fd']>=0 and before['boot']==boot,'stable actual same holder/OFD/info/ns')
    for cut in (before,after):
        need(cut['kcmp_rc']==0 and len(cut['uids'])==len(cut['gids'])==4 and len(set(cut['uids']))==len(set(cut['gids']))==1,'same-OFD kcmp and four credentials')
        stat_row=cut['descriptor_stat'];need(stat_row==cut['proc_fd_stat'] and stat.S_ISCHR(stat_row['mode']),'actual duplicated character-device descriptor stat')
        producer_clock=begin['producer_clock_domain']
        own=clock.observation(producer_clock,domain=domain,run=run,role='inventory_observer',
            expected=(begin['producer_pid'],begin['producer_ticks'],begin['producer_pid'],-1))
        holder=clock.observation(cut['clock_domain'],domain=domain,run=run,role='alsa_holder',
            expected=(cut['pid'],cut['ticks'],begin['producer_pid'],cut['clock_domain']['held_pidfd']))
        clock.pair(own,holder)
        tail=cut['proc_stat_raw'].rsplit(') ',1)[1].split();need(cut['proc_stat_raw'].startswith(str(cut['pid'])+' (') and len(tail)>19 and int(tail[19])==cut['ticks'],'raw current holder birth')
        for name,expected in (('Uid',cut['uids']),('Gid',cut['gids'])):
            match=re.search(r'(?m)^'+name+r':\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$',cut['proc_status_raw']);need(match is not None and list(map(int,match.groups()))==expected,'raw actual four '+name)
        listeners=[]
        for line in cut['proc_net_unix_raw'].splitlines():
            words=line.split()
            if len(words)==8 and words[7]=='@ohos-audio598/'+str(cut['pid'])+'/'+str(cut['ticks']):
                need(int(words[4],16)==5 and int(words[3],16)&0x10000,'actual398 seqpacket listener flags');listeners.append(line)
        need(len(listeners)==1,'one actual original398 listener')
        info=bytes.fromhex(cut['pcm_info_hex']);need(len(info)==cut['pcm_info_bytes'] and 16<=len(info)<=512,'actual bounded target INFO raw bytes')
        device,subdevice,stream,card=struct.unpack_from('<IIIi',info)
        match=re.fullmatch(r'/dev/snd/pcmC([0-9]+)D([0-9]+)p',cut['fd_link']);need(match is not None and card>=0 and stream==0 and (int(match[1]),int(match[2]))==(card,device),'actual INFO playback/card/device agree with observed node')
    s=before['descriptor_stat']
    result=dict(holder_pid=before['pid'],holder_ticks=before['ticks'],holder_uid=before['uids'][0],holder_gid=before['gids'][0],fd=before['fd'],dev=s['dev'],ino=s['ino'],rdev=s['rdev'],card=card,device=device,subdevice=subdevice)
    need(set(result)==set(INVENTORY_KEYS),'exact eleven non-clock inventory facts; typed clock proof separate');return result

def record(path):
    p=Path(path);return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def write(path,value):
    p=Path(path);need(not p.exists() and not p.is_symlink(),'fresh actual global inventory artifact')
    with p.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')

def observe_inventory(io,tools_proof,*,profile_ref,domain):
    """Original already-registered OwnedIO only; no new resources are created."""
    import onset579_global_tools as tools
    admitted=tools.admit(tools_proof,profile_descriptor=profile_ref,
        archive_sha256=io.archive_sha256,domain=domain)
    need(io.boot_id==domain.kernel.boot_id and not io._closed,'same held original IO/clock boot')
    remote='/data/local/tmp/au579-inventory-'+io.run_id;receipts=[]
    def command(script,label,allow=False):
        actual=io.shell(script,label,timeout=30,allow_failure=allow)
        receipts.append(dict(script=script,receipt=io.ref_receipt(actual),body=actual['stdout_ref']))
        return actual
    def cleanup():command('rm -- '+shlex.quote(remote)+' && test ! -e '+shlex.quote(remote),'au579_inventory_remove')
    io.register_cleanup(cleanup)
    io.send(admitted.status,remote,'au579_inventory_send')
    staged=command('chmod 0700 '+shlex.quote(remote)+' && test "$(stat -c "%u %a" '+shlex.quote(remote)+')" = "0 700" && sha256sum '+shlex.quote(remote),'au579_inventory_hash')
    need(staged['stdout'].split()==[tools.digest(admitted.status),remote],'actual deployed root0700 inventory bytes')
    product=tools.product_module();helper=admitted.tools['audio_status377']['helper']
    for soname in admitted.tools['audio_status377']['needed']:
        raw=command(product.runtime_guest_script(helper,soname),'au579_inventory_dso_'+soname.replace('.','_'))
        product.verify_guest_runtime_raw(helper,soname,raw['stdout'],archive_sha256=io.archive_sha256)
    result=None;probe=None
    for attempt in range(4):
        actual=command(shlex.join([remote,'--inventory',io.boot_id,io.run_id]),'au579_inventory_actual_'+str(attempt),True)
        if actual['exit_code']==0:
            result=inventory(actual['stdout'],boot=io.boot_id,run=io.run_id,domain=domain);probe=len(receipts)-1;break
        if attempt<3:time.sleep(.25)
    need(result is not None,'actual existing global PCM/OFD not ready; no priming or PCM-open fallback')
    path=io.output/'actual-control-global-inventory579.json'
    write(path,dict(schema='AU-global579-actual-control-inventory/v1',archive_sha256=io.archive_sha256,
        boot=io.boot_id,run=io.run_id,tools=tools_proof,profile=profile_ref,commands=receipts,
        probe_command=probe,inventory=result,runtime_pass=False,first_artifact_behavior_gate_passed=False))
    return result,record(path)

def receipt(row):
    actual={k:row[k] for k in ('argv','exit_code','boot_id','timed_out')}
    actual.update(stdout=row['stdout_ref'],stderr=row['stderr_ref'])
    if 'shell_exit_code' in row:actual.update(shell_exit_code=row['shell_exit_code'],shell_stdout=row['shell_stdout_ref'])
    return actual

def replay_closed_inventory(prelude_ref,*,original_io_ref,domain):
    from guest_ui import command_exit
    value=json.loads(checked(prelude_ref).read_text());io=json.loads(checked(original_io_ref).read_text())
    need(value['schema']=='AU-global579-actual-control-inventory/v1' and value['boot']==domain.kernel.boot_id and
         value['archive_sha256']==domain.kernel.archive_sha256 and value['runtime_pass'] is False and
         value['first_artifact_behavior_gate_passed'] is False,'same actual nonacceptance inventory prelude')
    need(io['scope']=='actual_original_Owner_IO_only_NOT_acceptance' and io['closed'] is True and
         io['boot_id']==value['boot'] and io['archive_sha256']==value['archive_sha256'] and
         all(r['reaped'] is True and type(r['exit_code']) is int for r in io['held_transports'].values()),
         'actual original closed IO journal; Root separately binds it to retained resources')
    originals=[receipt(row) for row in io['commands']]
    for item in value['commands']:
        actual=item['receipt'];need(actual in originals and actual['exit_code']==0 and actual['timed_out'] is False and
            actual['boot_id']==value['boot'],'original held operation raw is absent')
        prefix=shlex.join(['sh','-c',item['script']]);argv=actual['argv']
        need(len(argv)==5 and argv[1]=='-t' and argv[3]=='shell' and argv[4].startswith(prefix),
             'fixed actual HDC shell program')
        tail=argv[4][len(prefix):]
        match=re.fullmatch(r'; cap578_rc=\$\?; printf "\\n(__CAP578_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"',tail)
        need(match is not None,'actual original shell footer')
        body,code=command_exit(checked(actual['stdout']).read_text(),match[1])
        need(code==actual['shell_exit_code'] and checked(item['body']).read_text()==body and
             actual['shell_stdout']==item['body'],'actual program body/status differs')
        checked(actual['stderr'])
    index=value['probe_command'];need(type(index) is int and 0<=index<len(value['commands']),'actual bounded probe index')
    selected=value['commands'][index]
    need(selected['script']==shlex.join(['/data/local/tmp/au579-inventory-'+value['run'],'--inventory',value['boot'],value['run']]) and
         selected['receipt']['shell_exit_code']==0,'one fixed actual inventory invocation')
    remote='/data/local/tmp/au579-inventory-'+value['run']
    cleanup='rm -- '+shlex.quote(remote)+' && test ! -e '+shlex.quote(remote)
    prefix=shlex.join(['sh','-c',cleanup])
    matches=[(index,receipt(row)) for index,row in enumerate(io['commands']) if len(row['argv'])==5 and
             row['argv'][:4]==selected['receipt']['argv'][:4] and row['argv'][4].startswith(prefix)]
    need(len(matches)==1 and matches[0][0]>max(originals.index(item['receipt']) for item in value['commands']),
         'actual unique inventory cleanup after every retained observation')
    _,closed=matches[0];tail=closed['argv'][4][len(prefix):]
    marker=re.fullmatch(r'; cap578_rc=\$\?; printf "\\n(__CAP578_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"',tail)
    need(marker is not None and closed['exit_code']==0 and closed['shell_exit_code']==0 and
         closed['timed_out'] is False and closed['boot_id']==value['boot'],'actual cleanup command/footer exit')
    body,code=command_exit(checked(closed['stdout']).read_text(),marker[1])
    need(code==0 and body==checked(closed['shell_stdout']).read_text(),'actual root inventory removal/absence raw')
    checked(closed['stderr'])
    result=inventory(checked(selected['body']).read_text(),boot=value['boot'],run=value['run'],domain=domain)
    need(result==value['inventory'],'copied inventory differs from full raw replay')
    return result

def seal_inventory(io,prelude_ref,*,domain):
    """Call only AFTER original io.close(), no root finish or resource replacement."""
    need(io._closed and io.boot_id==domain.kernel.boot_id and io.archive_sha256==domain.kernel.archive_sha256,
         'actual original IO settled before sealing inventory')
    journal=record(io.output/'io.json');result=replay_closed_inventory(prelude_ref,original_io_ref=journal,domain=domain)
    path=io.output/'sealed-control-global-inventory579.json'
    write(path,dict(schema='actual-arm32-global-inventory579/v1',prelude=prelude_ref,original_io=journal,
        kernel_admission=dict(path=domain.kernel.original_kernel_admission_ref[0],sha256=domain.kernel.original_kernel_admission_ref[1])))
    return result,record(path),journal

def replay_inventory_proof(ref,*,domain,original_io_ref):
    value=json.loads(checked(ref).read_text())
    need(set(value)=={'schema','prelude','original_io','kernel_admission'} and
         value['schema']=='actual-arm32-global-inventory579/v1' and value['original_io']==original_io_ref and
         value['kernel_admission']==dict(path=domain.kernel.original_kernel_admission_ref[0],sha256=domain.kernel.original_kernel_admission_ref[1]),
         'inventory must bind original Root-retained closed IO and same actual kernel admission')
    return replay_closed_inventory(value['prelude'],original_io_ref=original_io_ref,domain=domain)
