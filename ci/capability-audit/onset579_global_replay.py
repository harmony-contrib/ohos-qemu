"""Complete source/frame0/OFD/HW/owner/transfer replay for explicit global580.

The original ordinary public/permission/VDI/QMP verifier remains mandatory.
All full raw checks are retained; only typed clock/protocol input is different.
"""
from pathlib import Path
import re
from onset579_global_mapping import need,lines,integer,decode,af_journal,verify_mapping

def replay_window(value,*,control480,observed,original_command,registry_path,held_path,haptic_episode,domain,bindings):
    """Replay this third transport under the original settled actor/lease tree.

    The old two-native-handle verifier is a mandatory predecessor; all ordinary
    UID, public API, permission, VDI, independent PCM and teardown checks remain
    in coordinator414 and verify_control416_480, without normalization.
    """
    import shlex,struct
    b=bindings
    import onset579_global_clock as clock
    import onset579_global_tools as tools
    import verify_control_global579 as v
    import control_session_global579 as session
    from onset579_global_bridge import admit,AF_DSOS,DRIVER_DSOS,PROVENANCE_DSOS,NAME,profile_from_config
    need(control480 is not None and control480['schema']=='threeuid-global579-independent/v1','original480 complete raw replay is mandatory')
    config=b.load(b.checked(value['root_admission']['config']));spec=b.load(b.checked(value['inputs']))
    admitted=admit(spec['onset579'],archive=value['archive'],profile_ref=profile_from_config(config),domain=domain,bindings=bindings)
    row=value.get('onset579_window');old=value['control_windows404'][0]
    need(type(row) is dict and row.get('schema')=='actual-original480-onset-global579-window/v1' and row['run']==old['expected_actual_inventory']['run'] and row['boot']==value['boot_id'] and row['helper']==admitted['helper'] and row['installed_dsos']==spec['onset579']['installed_dsos'],'actual same-run third native window')
    need(row['native_closed'] is True and row['files_removed'] is True and old['control_and_sampler_closed'] is True and old['files_disposed480'] is True,'all native processes and journals must close before public mutation')
    for key in ('accepted','onset_proven','first_artifact_behavior_gate_passed'):need(row[key] is False,'collector raw cannot assert onset')
    observations=row['observations'];need(type(observations) is list and 10<=len(observations)<=32,'actual new raw observation cuts')
    positions=[];scripts={}
    for item in observations:
        text=observed(item['raw'],item['script']);scripts.setdefault(item['script'],[]).append(text)
        selected=[v for v in value['observations'] if v['raw']==item['raw']];need(len(selected)==1,'one actual enclosing observation');positions.append(selected[0]['command'])
    need(all(a<z for a,z in zip(positions,positions[1:])) and old['binding480']['guest_begin']<=positions[0]<positions[-1]<old['binding480']['guest_finish_end'],'third native observations outside actual original window')
    def read(script):need(script in scripts and len(scripts[script])==1,'missing or ambiguous actual finite579 command: '+script);return scripts[script][0]
    inventory=lines(read(shlex.join(['/data/local/tmp/audio-haptic-'+value['run_id']+'/onset579','--inventory',value['boot_id'],row['run']])),10)
    need(len(inventory)==3 and inventory[0]['kind']=='inventory_begin580' and inventory[0]['boot']==value['boot_id'] and inventory[0]['observer_pid']>1 and inventory[0]['observer_birth']>0 and inventory[2]==dict(kind='inventory_end580',count=1,error=0) and inventory[1]==row['inventory'],'actual unique producer inventory differs')
    inv=row['inventory'];need(inv['kind']=='producer580','actual AF producer row')
    producer_raw=read('cat /proc/'+str(inv['pid'])+'/stat && cat /proc/'+str(inv['pid'])+'/status')
    need(producer_raw.splitlines()[0].split(' ',1)[0]==str(inv['pid']) and session.stat_ticks(producer_raw.splitlines()[0])==inv['birth'],'actual AF producer PID birth')
    for key,expected in (('Uid',inv['uid']),('Gid',inv['gid'])):
        match=re.search(r'(?m)^'+key+r':\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$',producer_raw);need(match is not None and all(int(n)==expected for n in match.groups()),'actual AF producer four '+key)
    need(inv['pidfd_close_rc']==0,'actual inventory pidfd close')
    clock.observation(inv['clock_domain'],domain=domain,run=row['run'],role='af_producer',
        expected=(inv['pid'],inv['birth'],inventory[0]['observer_pid'],inv['clock_domain']['held_pidfd']))
    transport=row['transport'];native_raw=session.native_output(b.checked(transport['raw']).read_text(),transport['marker']);native=lines(native_raw,20)
    need(transport['exit_code']==0 and len(native)==11 and [r['kind'] for r in native]==['hello580','request580','ack580','receiver_clock580','request580','ack580','sealed_file580','close_fd580','close_fd580','close_fd580','end_control580'],'complete actual native579 lifecycle')
    hello,request,arm,receiver_clock,disreq,disarm,sealed,*tail=native
    need(hello==row['hello'] and arm==row['arm'] and hello['boot']==value['boot_id'] and hello['run']==row['run'] and hello['client_uid']==hello['client_gid']==0,'native579 root/client run/boot')
    for src,dst in (('pid','producer_pid'),('birth','producer_birth'),('uid','producer_uid'),('gid','producer_gid')):need(inv[src]==hello[dst],'actual peer producer identity: '+src)
    need(hello['journal_fd']>=0 and hello['pidfd']>=0,'actual held producer pidfd/journal')
    a=clock.observation(hello['client_clock'],domain=domain,run=row['run'],role='af_client',
        expected=(hello['client_pid'],hello['client_birth'],hello['client_pid'],-1))
    z=clock.observation(hello['producer_clock'],domain=domain,run=row['run'],role='af_producer',
        expected=(inv['pid'],inv['birth'],hello['client_pid'],hello['pidfd']))
    clock.pair(a,z)
    client=hello['client_pid'];client_raw=read('cat /proc/'+str(client)+'/stat && cat /proc/'+str(client)+'/status')
    need(client_raw.splitlines()[0].split(' ',1)[0]==str(client) and session.stat_ticks(client_raw.splitlines()[0])==hello['client_birth'],'actual native client incarnation/time namespace')
    for key in ('Uid','Gid'):need(re.search(r'(?m)^'+key+r':\s+0\s+0\s+0\s+0\s*$',client_raw) is not None,'actual four client root identities')
    remote='/data/local/tmp/audio-haptic-'+value['run_id'];directory=remote+'/control404-'+row['run'];journal_remote=directory+'/onset579.jsonl'
    for req,op,fd in ((request,1,hello['journal_fd']),(disreq,2,-1)):
        need({k:req[k] for k in ('kind','op','bytes','errno','passed_fd','clock_error')}==dict(kind='request580',op=op,bytes=56,errno=0,passed_fd=fd,clock_error=0) and 0<integer(req,'before_ns')<=integer(req,'after_ns'),'actual timed SCM_RIGHTS/56-byte request')
    for ack,state,phase in ((arm,1,'arm'),(disarm,0,'disarm')):
        need(ack['errno']==ack['clock_error']==0 and 0<integer(ack,'before_ns')<=integer(ack,'after_ns'),'actual recvmsg timestamp/errno bracket')
        wire=ack['wire_hex'];need(type(wire) is str and re.fullmatch('[a-f0-9]{112}',wire) is not None,'actual fixed native ACK wire bytes')
        parsed=struct.unpack('<6I4Q',bytes.fromhex(wire));keys=('magic','version','error','state','pid','reserved','birth','produced','drained','lost')
        need(dict(zip(keys,parsed))=={k:ack[k] for k in keys} and parsed[:6]==(0x4f353830,1,0,state,inv['pid'],0) and ack['birth']==inv['birth'] and ack['lost']==0 and ack['phase']==phase,'actual AF ACK fields/bytes differ')
    need(request['after_ns']<=arm['before_ns']<=arm['after_ns']<=disreq['before_ns']<=disreq['after_ns']<=disarm['before_ns']<=disarm['after_ns'] and arm['produced']<=disarm['produced']==disarm['drained'],'actual AF ACK/SCM_RIGHTS monotonic lifecycle/count')
    need(sealed['dev']==hello['journal_dev'] and sealed['ino']==hello['journal_ino'] and sealed['mode']==384 and sealed['uid']==0 and sealed['nlink']==1 and sealed['bytes']>0,'actual native sealed root0600 journal inode')
    need([r['role'] for r in tail[:-1]]==['journal','socket','pidfd'] and all(r['rc']==r['errno']==0 for r in tail[:-1]) and tail[0]['fd']==hello['journal_fd'] and tail[2]['fd']==hello['pidfd'] and len({r['fd'] for r in tail[:-1]})==3 and tail[-1]==dict(kind='end_control580',error=0,close_errno=0),'actual native FD closure')
    read('test ! -e /proc/'+str(client)+'/stat')
    stage='chmod 0700 '+shlex.quote(remote+'/onset579')+' && test "$(stat -c "%u %a" '+shlex.quote(remote+'/onset579')+')" = "0 700" && sha256sum '+shlex.quote(remote+'/onset579')
    need(read(stage).split()==[b.sha(admitted['binary']),remote+'/onset579'],'actual staged helper full bytes/root0700')
    for soname in admitted['needed']:
        script=admitted['product'].runtime_guest_script(admitted['row'],soname);admitted['product'].verify_guest_runtime_raw(admitted['row'],soname,read(script),archive_sha256=value['archive']['sha256'])
    # Bind the third held handle to the exact same original constructor tree.
    registry=b.load(registry_path);held=b.load(held_path);context=b.load(b.checked(value['root_admission']['proof']['constructor_context']));actor=context['actor'];constructor=row['constructor'];need(constructor['actor']==actor,'same original coordinator actor')
    root_argv=b.load(b.checked(value['root_admission']['lease']))['argv'];record=registry['handles'][constructor['handle']]
    marker=transport['marker'];need(re.fullmatch('__AUDIO404_[a-f0-9]{32}__=',marker) is not None,'actual transport exit nonce')
    args=[remote+'/onset579',str(inv['pid']),str(inv['birth']),str(inv['uid']),value['boot_id'],row['run'],journal_remote]
    script='unset LD_LIBRARY_PATH LD_PRELOAD; '+shlex.join(args)+'; audio404_rc=$?; printf "\n'+marker+'%s\n" "$audio404_rc"'
    expected=[config['hdc']['path'],'-t',value['enclosing_guest_commands'][0]['argv'][2],'shell',script]
    need(transport['argv']==expected and record['original_argv']==expected and record['pid']==constructor['pid'] and record['parent']==actor and record['settled'] is True and record['returncode']==0 and constructor['handle'] not in {r['handle'] for r in old['constructor480']['handles'].values()},'exact third original retained native transport')
    native_actor=registry['actors'][record['actor']];need(native_actor['kind']=='native' and native_actor['parent']==actor and native_actor['argv']==expected and native_actor['pid']==constructor['pid'],'same original native actor identity')
    matches=[r for r in held['children'] if r['pid']==constructor['pid']];events=[r for r in held['events'] if r.get('state')=='actual_handle_retained' and r.get('pid')==constructor['pid']]
    need(len(matches)==len(events)==1 and matches[0]['argv']==events[0]['argv']==expected and matches[0]['reaped'] is True and matches[0]['exit_code']==0,'actual retained process reaped')
    spawn=events[0]['spawn_argv'];need(spawn[:4]==[root_argv[0],'-B',str(b.KIT/'spawn_trampoline376.py'),'--restore-mask'] and spawn[5:]==['--',*expected],'original fixed trampoline source/argv')
    mask=decode(spawn[4]);need(type(mask) is list and all(type(n) is int and n>0 for n in mask) and mask==sorted(set(mask)) and not ({2,15}&set(mask)),'original restored mask')
    def transfer(remote_path,record):
        entries=[d for d in row['downloads'] if d['remote']==remote_path and d['value']==record];need(len(entries)==1,'one actual download/cut')
        entry=entries[0];quote=shlex.quote(remote_path);script='test -f '+quote+' && test ! -L '+quote+" && stat -c '%u %a %s %i' "+quote+' && sha256sum '+quote
        need(entry['guest_end']==entry['guest_begin']+2,'actual before/after transfer cuts')
        first=original_command(entry['guest_begin'],script);last=original_command(entry['guest_end']-1,script)
        need(first==last==b.checked(record['stat']).read_text(),'actual transfer stat/hash changed')
        rows=first.splitlines();need(len(rows)==2 and len(rows[0].split())==4,'actual transfer metadata shape');uid,mode,size,inode=map(int,rows[0].split());path=b.checked(record['file'])
        need((uid,mode,inode)==(record['uid'],record['mode'],record['inode']) and size==path.stat().st_size and rows[1].split()==[record['file']['sha256'],remote_path] and record['remote']==remote_path,'actual transfer full bytes/inode')
        commands=[r for r in value['commands'] if r['argv']==[config['hdc']['path'],'-t',value['enclosing_guest_commands'][0]['argv'][2],'file','recv',remote_path,str(path)]]
        need(len(commands)==1 and commands[0]['exit_code']==0 and b.checked(commands[0]['log']).is_file(),'actual root HDC transfer argv/exit/raw')
        return path
    source_remote=value['actors']['owner']['files']+value['run_id']+'-stop.wav';need(row['source_remote']==source_remote,'actual public owner filesDir source')
    source_stat=observed(row['source_stat'],'stat -Lc "%d %i %u %s" '+shlex.quote(source_remote));source_file=transfer(source_remote,row['source_file']);prep=b.load(b.checked(value['preparation']))
    need(b.sha(source_file)==prep['roles']['owner']['audio']['sha256'] and row['source_file']['uid']==value['actors']['owner']['uid'] and row['source_file']['mode']==600 and int(source_stat.split()[1])==row['source_file']['inode'],'actual fresh source/UID/inode binding')
    source_raw=source_file.read_bytes();af_file=transfer(journal_remote,row['journal']);need(row['journal']['uid']==0 and row['journal']['mode']==600 and row['journal']['inode']==sealed['ino'] and af_file.stat().st_size==sealed['bytes'],'actual sealed journal transfer inode')
    af_raw=af_file.read_text();begin,end,_,_,_=af_journal(af_raw,run=row['run'],boot=value['boot_id'],domain=domain)
    for key,expected in (('pid',inv['pid']),('birth',inv['birth']),('uid',inv['uid']),('peer_pid',client),('peer_birth',hello['client_birth']),('peer_uid',0),('journal_dev',hello['journal_dev']),('journal_ino',hello['journal_ino'])):need(begin[key]==expected,'actual AF/client native FD identity: '+key)
    need(end['produced']==disarm['produced'] and end['drained']==disarm['drained'],'actual AF/footer ACK drain count')
    owner=value['actors']['owner'];receiver=row['receiver_identity'];pid=receiver['pid']
    receiver_script='cat /proc/'+str(pid)+'/stat && printf \"\\nONSET579_STATUS\\n\" && cat /proc/'+str(pid)+'/status && printf \"\\nONSET579_MAPS\\n\" && cat /proc/'+str(pid)+'/maps'
    need(receiver['script']==receiver_script,'actual fixed source receiver observation command')
    receiver_raw=observed(receiver['raw'],receiver_script)
    proc,status_and_maps=receiver_raw.split('\nONSET579_STATUS\n');status_raw,receiver_maps=status_and_maps.split('\nONSET579_MAPS\n')
    need(proc.split(' ',1)[0]==str(pid) and session.stat_ticks(proc)==receiver['birth'],'actual QAP receiver process incarnation/time namespace')
    need(receiver_clock==row['receiver_clock'] and receiver_clock['pidfd_close_rc']==0 and
         row['receiver_clock_command']=='CLOCK '+str(pid)+' '+str(receiver['birth'])+'\n',
         'actual fixed receiver command/native pidfd closure')
    receiver_domain=clock.observation(receiver_clock['clock_domain'],domain=domain,run=row['run'],role='renderer_receiver',
        expected=(pid,receiver['birth'],hello['client_pid'],receiver_clock['clock_domain']['held_pidfd']))
    need(arm['after_ns']<=receiver_domain['cuts'][0]<=receiver_domain['cuts'][-1]<=disreq['before_ns'],
         'actual receiver read-only observation must be inside the AF armed window')
    uid_match=re.search(r'(?m)^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$',status_raw);need(uid_match is not None and len(set(uid_match.groups()))==1,'actual receiver four UIDs')
    source_maps=observed(row['source_maps'],'cat /proc/'+str(owner['pid'])+'/maps')
    producer_maps=observed(row['producer_maps'],'cat /proc/'+str(inv['pid'])+'/maps');holder_maps=observed(row['holder_maps'],'cat /proc/'+str(old['expected_actual_inventory']['holder_pid'])+'/maps')
    need(len(row['libraries'])==7 and {r['soname'] for r in row['libraries']}==AF_DSOS|DRIVER_DSOS,'all seven actual loaded product DSOs')
    need(len(row['provenance_libraries'])==3 and {r['soname'] for r in row['provenance_libraries']}==PROVENANCE_DSOS,'all three actual source/provenance product DSOs')
    library_proofs={}
    for library in row['libraries']+row['provenance_libraries']:
        name=library['soname']
        if name in PROVENANCE_DSOS:entry=admitted['supplement']['provenance_dsos'][name]['entry'];proof=admitted['supplement']['provenance_dsos'][name]['proof']
        else:entry=admitted['profile']['dsos'][name];proof=admitted['supplement']['proofs'][name]
        path=transfer(library['guest_path'],library['received'])
        prefix=admitted['product'].installed_prefix(admitted['profile'])+'/'
        partition=entry['staged']['path'].removeprefix(prefix).split('/',1)[0];guest='/'+partition+entry['image_member']
        need(library['guest_path']==guest and b.sha(path)==entry['staged']['sha256'] and path.stat().st_size==entry['staged']['bytes'] and library['received']['inode']==proof['image_inode'],'actual guest/image DSO full bytes/inode')
        maps=(source_maps if name=='libaudio_haptic.z.so' else receiver_maps) if name in PROVENANCE_DSOS else (producer_maps if name in AF_DSOS else holder_maps);found=[]
        for line in maps.splitlines():
            fields=line.split(None,5)
            if len(fields)==6 and fields[5]==guest:
                need(fields[4].isdecimal() and int(fields[4])==library['received']['inode'],'actual loaded DSO map inode differs');found.append(fields[1])
        need(found and any('x' in mode for mode in found),'actual producer/holder executable DSO map missing: '+name)
        library_proofs[name]=dict(file=library['received']['file'],guest_path=guest,inode=proof['image_inode'])
    libasound=admitted['supplement']['libasound'];need(any(len(f)==6 and f[5].endswith('/libasound.so') and f[4].isdecimal() and int(f[4])==libasound['image_inode'] and 'x' in f[1] for f in (line.split(None,5) for line in holder_maps.splitlines())),'actual same-OFD holder libasound executable mapping/inode')
    qaps=[]
    need(3<=len(row['qap'])<=8,'before/afterStart/beforeDISARM actual qap observations')
    for ref in row['qap']:qaps.append(observed(ref,'hilog -x'))
    read('rm -- '+shlex.quote(journal_remote)+' '+shlex.quote(remote+'/onset579')+' && test ! -e '+shlex.quote(journal_remote)+' && test ! -e '+shlex.quote(remote+'/onset579'))
    ctl_raw=session.native_output(Path(old['control']['path']).read_text(),old['control']['marker']);status_raw=session.native_output(Path(old['status']['path']).read_text(),old['status']['marker']);expected=old['expected_actual_inventory']
    ctl=v.control(ctl_raw,expected=expected,exit_code=old['control']['exit_code'],domain=domain);status=v.independent_sampler(status_raw,control_result=ctl,expected=expected,exit_code=old['status']['exit_code'],domain=domain)
    need(ctl['rows'][6]['monotonic_ns']<=request['before_ns'] and disarm['after_ns']<=ctl['rows'][8]['monotonic_ns'] and status['samples'][0]['before_ns']<=request['before_ns'] and disarm['after_ns']<=status['samples'][-1]['after_ns'],'actual original independent CONTROL/tap/status window must enclose AF full window')
    for action in value['actions'][old['binding480']['action_begin']:old['binding480']['action_end']]:
        lo,hi=action['control_interval_ns'];need(arm['after_ns']<=lo<=hi<=disreq['before_ns'],'actual public action outside root-ACK AF armed interval')
    af_rows=lines(af_raw,12002)
    for event in af_rows[1:-1]:need(request['before_ns']<=event['before_ns']<=event['after_ns']<=disarm['after_ns'],'AF RT event outside actual native request/ACK brackets')
    journal_rows=v.raw_lines(b.checked(old['received']['journal.jsonl']).read_text(),6002);tap=b.checked(old['received']['tap.pcm']).read_bytes()
    anchor=verify_mapping(af_raw=af_raw,run=row['run'],boot=value['boot_id'],qap_raws=qaps,source_stat_raw=source_stat,source_wav_raw=source_raw,tap=tap,journal_rows=journal_rows,segments=control480['derive398']['segments'],status_samples=status['samples'],haptic_episode=haptic_episode,domain=domain)
    need(anchor['source']==row['source_identity'] and anchor['source']['source_pid']==owner['pid'] and anchor['source']['source_birth']==owner['process_start']['start_ticks'] and anchor['source']['receiver_pid']==receiver['pid'] and anchor['source']['receiver_birth']==receiver['birth'],'actual ordinary owner source/receiver native process incarnations')
    memory_begin=journal_rows[0];status_header=v.raw_lines(status_raw,7502)[0]
    roles=dict(af_producer=begin['producer_clock'],alsa_holder=memory_begin['holder_clock'],
        af_client=hello['client_clock'],status_sampler=status_header['sampler_clock'],
        control_client=ctl['rows'][0]['client_clock'],renderer_receiver=receiver_clock['clock_domain'])
    expected_roles=dict(af_producer=(inv['pid'],inv['birth'],inv['pid'],-1),
        alsa_holder=(expected['holder_pid'],expected['holder_ticks'],expected['holder_pid'],-1),
        af_client=(client,hello['client_birth'],client,-1),
        status_sampler=(ctl['sampler']['sampler_pid'],ctl['sampler']['sampler_ticks'],ctl['sampler']['sampler_pid'],-1),
        control_client=(expected['client_pid'],expected['client_ticks'],expected['client_pid'],-1),
        renderer_receiver=(pid,receiver['birth'],client,receiver_clock['clock_domain']['held_pidfd']))
    clocks=clock.participants(roles,domain=domain,run=row['run'],expected=expected_roles)
    return dict(schema='original480-independent-onset-global579/v1',anchor=anchor,clock_domain=clocks,native_pipeline_source_image_witness_verified=True,
        loaded_dsos=library_proofs,installed_dsos=spec['onset579']['installed_dsos'],af_window_monotonic_ns=[arm['after_ns'],disreq['before_ns']],original_window_encloses_AF=True,native_transport=dict(actor=actor,handle=constructor['handle'],pid=constructor['pid'],closed=True),
        runtime_scope='M02 source-frame0 onset addition; original public three-UID focus/permissions/VDI/PCM/cleanup still independently verified',
        accepted=False,full82=False,first_artifact_behavior_gate_passed=False)
