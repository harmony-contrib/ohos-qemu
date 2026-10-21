"""Independent explicit NEW398 replay; never normalizes to legacy379.

A globally mixed PCM/OFD observation cannot identify an AudioHaptic stream.
This module therefore proves only the limited raw window, always NOT onset.
"""
import json,re,shlex
from pathlib import Path
import onset579_global_tools as tools
import verify_control_global579 as v
import control_session_global579 as session
from control_global579_bridge import admit_input
from onset579_global_bridge import profile_from_config


def derive398(journal,tap,control,status,*,expected,verifier,domain):
    """Tap-byte -> accepted appl interval, NOT source frame -> presentation.

    Original398 validation supplies continuity, no reset/xrun, bounds and the
    immutable snapshot source. No first nonzero/global PCM sample is an onset.
    """
    local=verifier.memory_journal(journal,tap,control_result=control,expected=expected,domain=domain)
    rows=verifier.raw_lines(journal,6002)
    mapped=[dict(seq=r['seq'],tap_byte_interval=[r['tap_offset'],r['tap_offset']+r['pcm_bytes']],
                 appl_frame_interval=[r['appl_before'],r['appl_after']],
                 write_monotonic_interval=[r['before_ns'],r['returned_ns']],empty_eagain=bool(r['empty_eagain']))
            for r in rows[1:-1]]
    return dict(schema='NEW398-accepted-PCM-intervals/480-v1',snapshot_source=verifier.SOURCE,
      run=expected['run'],boot=expected['boot'],holder_pid=expected['holder_pid'],holder_ticks=expected['holder_ticks'],
      fd=expected['fd'],epoch=control['epoch'],instance=control['instance'],segments=mapped,
      source_frame_zero=None,renderer_stream_session=None,stream_to_mix_frame_mapping=None,
      source_bound_HW_crossing_interval=None,hardware_sample_count=len(status['samples']),
      local_integrity=local,accepted=False,onset_proven=False,presentation_anchor_proven=False,
      ledger_closed=False,first_artifact_behavior_gate_passed=False)


def owner_transport(row,registry,held,*,actor,coordinator_argv,coordinator_entry,bindings):
    b=bindings
    b.need(registry.get('schema_version')==1 and registry.get('scope')=='actual_root_held_registered_constructor_tree_ONLY' and
      registry.get('failures')==[] and re.fullmatch('[a-f0-9]{32}',registry.get('nonce','')) is not None,'actual original root constructor registry required')
    root=registry['actors'][actor]
    entry=Path(coordinator_entry)
    b.need(entry.is_absolute() and str(entry) in b.verify_sources() and b.sha(entry)==b.verify_sources()[str(entry)],
           'fixed Root-supplied source-admitted Coordinator entry, never a JSON-selected script')
    b.need(root['entry']==str(entry) and root['kind']=='python' and root['argv']==coordinator_argv and
      root['parent']=='root-threeuid414' and root['done'] is True,'exact settled root coordinator actor required')
    b.need(held.get('unknown_creation') is False,'unknown root construction forbids window replay')
    bound=row['constructor480'];b.need(bound['actor']==actor and set(bound['handles'])=={'control','status'},'same root coordinator ownership required')
    used=set()
    for name in ('control','status'):
        ref=bound['handles'][name];key=ref['handle'];b.need(key not in used,'distinct actual CONTROL/sampler handles');used.add(key)
        record=registry['handles'][key]
        b.need(type(ref['pid']) is int and ref['pid']>1 and record['pid']==ref['pid'] and record['parent']==actor and
          record['original_argv']==row[name]['argv'] and record['settled'] is True and type(record['returncode']) is int and
          type(row[name]['exit_code']) is int and record['returncode']==row[name]['exit_code']==0,'actual held native transport handle/exit differs')
        native=registry['actors'][record['actor']]
        b.need(native['kind']=='native' and native['parent']==actor and native['argv']==row[name]['argv'] and native['pid']==ref['pid'],
          'original native actor identity differs')
        matches=[r for r in held['children'] if r['pid']==ref['pid']]
        b.need(len(matches)==1 and matches[0]['argv']==row[name]['argv'] and matches[0]['reaped'] is True and
          type(matches[0]['exit_code']) is int and matches[0]['exit_code']==0,'actual root-held native process not closed')
        events=[r for r in held['events'] if r.get('state')=='actual_handle_retained' and r.get('pid')==ref['pid']]
        b.need(len(events)==1 and events[0]['argv']==row[name]['argv'],'actual root native launch record missing')
        spawn=events[0]['spawn_argv']
        b.need(spawn[:5]==[coordinator_argv[0],'-B',str(b.KIT/'spawn_trampoline376.py'),'--restore-mask',spawn[4]] and
          spawn[5:]==['--',*row[name]['argv']],'original fixed root trampoline/argv differs')
        mask=json.loads(spawn[4]);b.need(type(mask) is list and all(type(n) is int and n>0 for n in mask) and
          mask==sorted(set(mask)) and not ({2,15}&set(mask)),'original restored signal mask invalid')
    return dict(scope='two original retained native transport handles only',actor=actor,handles=sorted(used))


def action_binding(value,row,control,*,bindings):
    b=bindings
    bind=row['binding480'];b.need(bind.get('schema')=='threeuid-CONTROL-global579/v1' and
      bind['coordinator_run']==value['run_id'] and bind['boot']==value['boot_id'],'actual same threeUID run/boot required')
    cuts=[bind[k] for k in ('guest_begin','guest_armed','guest_finish_begin','guest_finish_end')]
    b.need(all(type(n) is int for n in cuts) and 0<=cuts[0]<cuts[1]<=cuts[2]<cuts[3]<=len(value['enclosing_guest_commands']),
      'actual native ARM/finish guest command cuts required')
    lo,hi=bind['action_begin'],bind['action_end']
    b.need(type(lo) is int and type(hi) is int and 0<=lo<hi<=len(value['actions']),'actual bounded business action range')
    actions=value['actions'][lo:hi];first=actions[0]
    b.need(first['role']=='owner' and first['action']=='start' and bind['owner_start']=={
      k:first[k] for k in ('operation','request','control_interval_ns')},'real public owner Start differs')
    b.need(len([a for a in actions if a['role']=='contender' and a['action']=='start'])==1 and
      any(a['role']=='owner' and a['action']=='background-start' for a in actions),'original focus/background actions missing from window')
    arm=control['rows'][6]['monotonic_ns'];sealed=control['rows'][10]['monotonic_ns']
    for item in actions:
        before,after=item['control_interval_ns']
        b.need(type(before) is int and type(after) is int and arm<=before<=after<=sealed,'business action outside actual CONTROL lifetime')
        b.checked(item['request'])
    b.need(all(a['action'] not in ('background-stop','release','control-close') for a in actions) and
      all(a['action'] in ('background-stop','release','control-close') for a in value['actions'][hi:]),'public cleanup must follow native DISARM')
    return dict(owner_operation=first['operation'],covered_action_count=len(actions),native_arm_ns=arm,native_sealed_ns=sealed,
      source_first_frame_still_missing=True)


def verify(value,*,observed,registry_path,held_path,domain,bindings,inventory_io_ref,coordinator_entry):
    b=bindings
    b.need(value['coordinator']==b.record(coordinator_entry),'actual collector must be the fixed new source entry')
    b.need(value['root_admission'].get('branch')=='owner403/414','480 is an explicit current403 branch only')
    config=b.load(b.checked(value['root_admission']['config']));spec=b.load(b.checked(value['inputs']))
    profile=profile_from_config(config);admitted,inventory=admit_input(spec,archive_sha256=value['archive']['sha256'],profile=profile,domain=domain,bindings=bindings,inventory_io_ref=inventory_io_ref)
    windows=value.get('control_windows404');b.need(type(windows) is list and len(windows)==1,'one actual new398 control window required')
    row=windows[0];bind=row['binding480']
    b.need(row['phase']=='owner-start-480' and bind['config']==spec['control404'] and bind['profile']==profile and
      row.get('control_and_sampler_closed') is True and row.get('files_disposed480') is True,'actual finite native window closure required')
    for gate in ('accepted','onset_proven','ledger_closed','first_artifact_behavior_gate_passed'):
        b.need(row.get(gate) is False,'local window may not claim onset/aggregate acceptance')
    refs=row['observations'];b.need(len(refs)==len({tuple(sorted(r.items())) for r in refs}),'distinct original native observation cuts')
    positions=[]
    for ref in refs:
        matches=[r for r in value['observations'] if r['raw']==ref];b.need(len(matches)==1,'one actual raw native cut')
        positions.append(matches[0]['command'])
    b.need(all(type(n) is int for n in positions) and all(a<z for a,z in zip(positions,positions[1:])) and
      bind['guest_begin']<=positions[0]<positions[-1]<bind['guest_finish_end'],'strict original native observation order and window bounds')
    def read_script(script,*,unique=True):
        candidates=[(ref,r) for ref in refs for r in value['observations'] if r['raw']==ref and r['script']==script]
        b.need(len(candidates)==1 if unique else len(candidates)>0,'exact original native observation command required: '+script)
        bodies=[observed(ref,script) for ref,_ in candidates]
        b.need(all(text==bodies[0] for text in bodies),'native observations disagree')
        return bodies[0]
    # Independently rebind all copied native observations to original guest logs.
    for ref in refs:
        matches=[r for r in value['observations'] if r['raw']==ref];b.need(len(matches)==1,'original native observation absent')
        observed(ref,matches[0]['script'])
    run=row['expected_actual_inventory']['run'];b.need(re.fullmatch('[a-f0-9]{32}',run) is not None,'native run nonce required')
    remote='/data/local/tmp/audio-haptic-'+value['run_id'];directory=remote+'/control404-'+run
    natives={}
    for name in ('control','status'):
        item=row[name];marker=item['marker'];b.need(re.fullmatch('__AUDIO404_[a-f0-9]{32}__=',marker) is not None,'actual native exit nonce')
        args=[inventory[k] for k in (('holder_pid','holder_ticks','holder_uid','holder_gid','fd','dev','ino','rdev') if name=='control' else
          ('holder_pid','holder_ticks','fd','dev','ino','rdev','card','device','subdevice'))]
        args+= [value['boot_id'],run,'--directory',directory] if name=='control' else [run,session.SAMPLES]
        executable=remote+('/control404' if name=='control' else '/status377')
        script='unset LD_LIBRARY_PATH LD_PRELOAD; '+shlex.join([executable,*map(str,args)])+'; audio404_rc=$?; printf "\n'+marker+'%s\n" "$audio404_rc"'
        b.need(item['argv']==[config['hdc']['path'],'-t',value['enclosing_guest_commands'][0]['argv'][2],'shell',script] and
          type(item['exit_code']) is int and item['exit_code']==0,'exact native HDC argv/exit required')
        natives[name]=session.native_output(Path(item['path']).read_text(),marker)
    identity=v.raw_lines(natives['control'],13)[0]
    expected=dict(inventory,run=run,boot=value['boot_id'],**{k:v.integer(identity,k,1 if k in ('client_pid','client_ticks') else 0)
      for k in ('client_pid','client_ticks','self_gid')})
    b.need(row['expected_actual_inventory']==expected,'native identity inventory differs')
    def process(pid,ticks,executable,uid):
        stat=read_script('cat /proc/'+str(pid)+'/stat');b.need(stat.split(' ',1)[0]==str(pid) and session.stat_ticks(stat)==ticks,'raw native proc birth differs')
        raw=read_script('cat /proc/'+str(pid)+'/status');match=re.search(r'(?m)^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$',raw)
        b.need(match is not None and all(int(n)==uid for n in match.groups()),'raw four native UIDs differ')
        read_script('test "$(readlink /proc/'+str(pid)+'/exe)" = '+shlex.quote(executable)+' && cat /proc/'+str(pid)+'/maps')
    holder=read_script('cat /proc/'+str(inventory['holder_pid'])+'/stat')
    b.need(holder.split(' ',1)[0]==str(inventory['holder_pid']) and session.stat_ticks(holder)==inventory['holder_ticks'],'raw holder birth differs')
    read_script('cat /proc/'+str(inventory['holder_pid'])+'/status && cat /proc/'+str(inventory['holder_pid'])+'/maps && cat /proc/'+str(inventory['holder_pid'])+'/attr/current')
    process(expected['client_pid'],expected['client_ticks'],remote+'/control404',0)
    ctl=v.control(natives['control'],expected=expected,exit_code=row['control']['exit_code'],domain=domain)
    sampler=ctl['sampler'];process(sampler['sampler_pid'],sampler['sampler_ticks'],remote+'/status377',0)
    read_script('test ! -e /proc/'+str(expected['client_pid'])+'/stat')
    product=tools.product_module()
    for name,record in admitted.tools.items():
        for soname in record['needed']:
            script=product.runtime_guest_script(record['helper'],soname)
            product.verify_guest_runtime_raw(record['helper'],soname,read_script(script,unique=False),archive_sha256=value['archive']['sha256'])
        binary=admitted.control if name=='audio_control404' else admitted.status
        target=remote+('/control404' if name=='audio_control404' else '/status377')
        script='chmod 0700 '+target+' && test "$(stat -c "%u %a" '+target+')" = "0 700" && sha256sum '+target
        # Stage observations belong to Coordinator, not the original window list.
        matches=[r for r in value['observations'] if r['script']==script];b.need(len(matches)==1,'actual fixed native stage check absent')
        b.need(observed(matches[0]['raw'],script).split()==[b.sha(binary),target],'actual staged native bytes differ')
    pulled=row['received'];b.need(set(pulled)=={'control.jsonl','journal.jsonl','tap.pcm'},'actual three raw downloads required')
    for name in ('control.jsonl','journal.jsonl'):
        matches=[d for d in value['control480_downloads'] if d['file']==pulled[name] and d['remote']==directory+'/'+name]
        b.need(len(matches)==1 and matches[0]['uid']==0 and matches[0]['mode']==600,'actual root private native ledger download required')
        meta=Path(b.checked(matches[0]['stat'])).read_text().splitlines();tokens=meta[0].split()
        b.need(len(meta)==2 and len(tokens)==4 and [int(tokens[0]),int(tokens[1])]==[0,600] and int(tokens[2])==b.checked(pulled[name]).stat().st_size and
          meta[1].split()==[pulled[name]['sha256'],directory+'/'+name],'actual ledger transfer stat/hash differs')
        # Match both real before/after root shell stat/hash logs, not copied metadata.
        script='test -f '+directory+'/'+name+' && test ! -L '+directory+'/'+name+" && stat -c '%u %a %s %i' "+directory+'/'+name+' && sha256sum '+directory+'/'+name
        matches2=[r for r in value['enclosing_guest_commands'] if r['argv'][-1].startswith('('+script+'); task_child_rc=$?; ')]
        b.need(len(matches2)==2,'actual before/after root ledger transfer checks required')
        for r in matches2:
            from guest_ui import command_exit
            marker=re.search(r'__QEMU_CHILD_EXIT_[a-f0-9]{32}__=',r['argv'][-1]).group()
            body,code=command_exit(Path(r['log']).read_text().replace('\r',''),marker)
            b.need(code==0 and body==Path(b.checked(matches[0]['stat'])).read_text(),'actual before/after transfer bytes changed')
    tap=b.checked(pulled['tap.pcm']).read_bytes()
    b.need(read_script('test -f '+directory+'/tap.pcm && test ! -L '+directory+'/tap.pcm && sha256sum '+directory+'/tap.pcm').split()==[pulled['tap.pcm']['sha256'],directory+'/tap.pcm'],'actual tap guest bytes differ')
    control_bytes=b.checked(pulled['control.jsonl']).read_bytes();b.need(control_bytes==natives['control'].encode(),'actual CONTROL download differs from transport')
    journal=b.checked(pulled['journal.jsonl']).read_text();result=v.verify_window(natives['control'],journal,tap,natives['status'],expected=expected,
      control_exit_code=row['control']['exit_code'],sampler_exit_code=row['status']['exit_code'],domain=domain)
    b.need(result==row['independent_new398_result'],'copied new398 result differs from actual raw replay')
    status=v.independent_sampler(natives['status'],control_result=ctl,expected=expected,exit_code=row['status']['exit_code'],domain=domain)
    context=b.load(b.checked(value['root_admission']['proof']['constructor_context']))
    closure=owner_transport(row,b.load(registry_path),b.load(held_path),actor=context['actor'],coordinator_argv=b.load(b.checked(value['root_admission']['lease']))['argv'],coordinator_entry=coordinator_entry,bindings=b)
    actions=action_binding(value,row,ctl,bindings=b)
    return dict(scope='threeUID same-boot CONTROL/raw integrity ONLY_NOT_stream-bound_onset_or_full_finding',
      schema='threeuid-global579-independent/v1',derive398=derive398(journal,tap,ctl,status,expected=expected,verifier=v,domain=domain),
      native_transport=closure,actions=actions,realtime_minus_monotonic_ns=status['clock_offset_ns'],
      actual_PCM_diagnostic_source_image_verified=False,source_first_frame_to_renderer_to_mixed_PCM_mapping=None,TIME_VDI_renderer_QMP_frame_join=None,
      accepted=False,onset_proven=False,presentation_anchor_proven=False,ledger_closed=False,first_artifact_behavior_gate_passed=False)
