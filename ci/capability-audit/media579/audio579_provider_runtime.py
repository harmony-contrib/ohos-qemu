"""Actual frame-driven CPU IV/HRTF cases on the original Audio10 IO only.

The model recordings/nonce are private to the independent stimulus, never given
back by the HAP. No additional Owner, transport, SDK, QEMU or constructor site.
"""
from pathlib import Path
from array import array
import json,math,re,secrets,shlex,sys,time,wave
from audio579_common import need,checked,doc,ref,dependency

VOICE='/data/service/el0/intelligent_voice/wakeup/cpu'
SPATIAL='/data/data/hvs/qemu_spatial'
PHRASES=(('文森特卡索','3.wav','4.wav'),('蒋友伯','4.wav','3.wav'))

def challenge(positive,negative,nonce,*,negative_window=True):
    """Pure licensed source DATA transform; no host recognition or validation."""
    def clip(reference,seconds):
        with wave.open(str(checked(reference)),'rb') as source:
            need(source.getsampwidth()==2 and source.getnchannels()==1 and source.getframerate()==16000,'actual fixed original mono16k source')
            samples=array('h');samples.frombytes(source.readframes(int(seconds*16000)))
            if sys.byteorder!='little':samples.byteswap()
            need(len(samples)==int(seconds*16000),'complete fixed source clip')
            return list(samples)
    speech=clip(positive,3.0);wrong=clip(negative,2.4)
    base=([0]*8000+wrong+[0]*19200+speech+[0]*16000) if negative_window else ([0]*8000+speech+[0]*8000)
    positive_start=(8000+len(wrong)+19200) if negative_window else 8000
    gain=.76+int(nonce[:4],16)/65535*.18;state=int(nonce[4:20],16);out=array('h')
    for sample in base:
        for unused in range(3):
            state=(state*6364136223846793005+1442695040888963407)&((1<<64)-1)
            value=max(-32768,min(32767,int(round(sample*gain))+int((state>>56)&7)-3))
            out.extend((value,value))
    if sys.byteorder!='little':out.byteswap()
    return out.tobytes(),dict(rate=48000,channels=2,sample_format='S16LE',source_rate=16000,nonce=nonce,
        positive_source=positive,negative_source=negative,positive_start_frame=positive_start*3,
        frames=len(base)*3,negative_window=negative_window,gain=gain)

class Session:
    def __init__(self,io,report,shell,process,stimulus_roots):
        self.io=io;self.report=report;self.shell=shell;self.process=process;self.roots=stimulus_roots;self.feeds=[];self.native_used=set();self.seen=set();self.backups=[];self.started=False;self.pose_source=None;self.pose_seen=set()
        inputs=io.package_inputs['media579_audio'];self.facts_ref=inputs['provider_facts'];self.facts=doc(self.facts_ref)
        need(self.facts['source_commit']==report['source_commit'] and self.facts['archive']['sha256']==io.archive_sha256,'same actual new image CPU provider facts')
        self.data=dict(schema='audio579-frame-provider-runtime/v1',provider_facts=self.facts_ref,stimuli=self.feeds,
            operations=[],native_files=[],native_processes=[],backup=self.backups,cleanup=None,runtime_pass=False)
        report['cpu_provider']=self.data
    def start(self):
        need(not self.started,'one frame-provider session on original IO');self.started=True
        # Only these normal product private diagnostics/state. Preserve original
        # enrollment bytes before testing; never replace model/config/input data.
        for directory in (VOICE,SPATIAL):
            script='test -d '+shlex.quote(directory)+' && test ! -L '+shlex.quote(directory)+' && find '+shlex.quote(directory)+' -maxdepth 1 -type f -print'
            names=self.shell(script,'provider_baseline_files').splitlines()
            self.data.setdefault('baseline',{})[directory]=names
            need(all(n.startswith(directory+'/') and re.fullmatch(r'[A-Za-z0-9_./+\-]+',n) for n in names),'exact private ordinary files')
            for number,name in enumerate(names):
                local=self.io.output/('provider-baseline-'+str(len(self.backups))+'.bin');self.io.receive(name,local,'audio579_provider_baseline')
                stat=self.shell('test ! -L '+name+' && stat -c "%u %g %a %s %i" '+name,'provider_baseline_stat')
                self.backups.append(dict(remote=name,file=ref(local),metadata=stat))
        self.shell('if test -f '+VOICE+'/cpu-journal.jsonl; then rm '+VOICE+'/cpu-journal.jsonl; fi','provider_new_journal')
        self.shell('printf \'%s\\n\' '+shlex.quote(self.io.run_id)+' > '+SPATIAL+'/control && chown 0:0 '+SPATIAL+'/control && chmod 0444 '+SPATIAL+'/control','provider_native_trace_control')
    def native_rows(self):
        text=self.shell('if test -f '+VOICE+'/cpu-journal.jsonl; then cat '+VOICE+'/cpu-journal.jsonl; fi','provider_native_journal')
        return [json.loads(line) for line in text.splitlines()]
    def feed(self,operation,phase,positive,negative,trace=None,negative_window=True):
        source=self.facts['cpu_provider']['source_audio'];nonce=secrets.token_hex(16)
        pcm,metadata=challenge(source[positive],source[negative],nonce,negative_window=negative_window)
        path=self.io.output/('voice-source-'+nonce+'.pcm');path.write_bytes(pcm)
        metadata.update(phase=phase,operation=operation,actual_native_trace=trace,PCM=ref(path));helper=self.io.package_inputs['media579_audio']['alsa_inject']
        build=doc(helper['build']);need(build['status']=='pass_compile_link_ONLY' and build['installed_runtime_profile']['profile']['archive']['sha256']==self.io.archive_sha256,'same normal compiled ALSA stimulus')
        remote='/data/local/tmp/qemu-mic-'+nonce;self.roots.append(remote)
        self.shell('test ! -e '+remote+' && mkdir -m 0700 '+remote,'provider_source_private')
        for local,name,mode in ((checked(helper['binary']),'alsa_inject','0700'),(path,'challenge.pcm','0600')):
            self.io.send(local,remote+'/'+name,'audio579_provider_independent_'+name.replace('.','_'))
            need(self.shell('chmod '+mode+' '+remote+'/'+name+' && sha256sum '+remote+'/'+name,'provider_source_identity').split()==[ref(local)['sha256'],remote+'/'+name],'independent root-only actual source full bytes')
        marker='__PCM_CHILD_EXIT_'+secrets.token_hex(16)+'__='
        script=dependency('guest_process_identity').producer_shell(remote,marker,repeat=1,timeout_ms=30000)
        key=self.io.spawn_guest(script,'audio579_independent_real_voice_'+phase)
        row=dict(**metadata,helper=helper,remote=remote,command=script,transport_key=key,completion=None)
        self.feeds.append(row)
        deadline=time.monotonic()+10
        while '"event":"feeding"' not in self.io._long[key]['err'].read_text():
            need(time.monotonic()<deadline,'actual ALSA native feeding edge required');time.sleep(.05)
        return row
    def spatial_poll(self,request,rows):
        own=[r for r in rows if r['operation']==request['operation']]
        for row in own:
            key=(request['operation'],row['seq'])
            if key in self.pose_seen:continue
            event=row['event']
            if event=='spatial-pose-window':
                if self.pose_source is None:
                    self.pose_source=dependency('headposture579_source').HeadPostureSource(self.io)
                    self.pose_source.start();self.pose_source.probe_invalid()
                value=json.loads(row['value']);nonce=secrets.token_hex(16)
                angle=(.35+int(nonce[:4],16)/65535*.45)*(1 if value['index'] else -1)
                quaternion=dict(w=math.cos(angle/2),x=0.0,y=math.sin(angle/2),z=0.0)
                self.pose_source.pose(cycle=value['cycle'],index=value['index'],quaternion=quaternion)
                self.data.setdefault('pose_requests',[]).append(dict(cycle=value['cycle'],index=value['index'],nonce=nonce,quaternion=quaternion))
            elif event=='spatial-restore-pose-window':
                need(self.pose_source is not None,'actual pose source must have run');self.pose_source.restore()
            elif event=='spatial-before-head-disable':
                self.pose_source.expect_disabled()
            elif event=='spatial-head-disabled':
                self.data['headposture']=self.pose_source.finish()
            else:continue
            self.pose_seen.add(key)
    def poll(self,request,rows):
        if request['action']=='spatial':return self.spatial_poll(request,rows)
        if request['action']!='voice' or 'phrase' not in request:return
        op=request['operation'];own=[r for r in rows if r['operation']==op];events={r['event'] for r in own}
        phrase,positive,negative=next(v for v in PHRASES if v[0]==request['phrase'])
        for event,phase,enroll in [('voice-listening','enroll',True),('voice-await-actual-wakeup','wakeup',False)]:
            key=(op,phase)
            if event not in events or key in self.seen:continue
            native=self.native_rows();candidates=[r for r in native if r['event']=='actual-pcm-listening' and r['enroll'] is enroll and r['detail'] not in self.native_used]
            if not candidates:continue
            actual=candidates[-1];self.native_used.add(actual['detail']);self.seen.add(key)
            self.feed(op,phase,positive,negative,actual)
        if 'voice-before-revoke' in events and (op,'revoke') not in self.seen:
            self.seen.add((op,'revoke'));identity=self.process('system','voice_revoke_native_identity')
            command='atm perm -c -i '+str(identity['token_id'])+' -p ohos.permission.MICROPHONE'
            raw=self.shell(command,'provider_actual_MIC_revoke')
            self.data.setdefault('revocations',[]).append(dict(operation=op,identity=identity,command=command,stdout=raw))
            self.feed(op,'revoked-positive',positive,negative,negative_window=False)
    def complete_operation(self,row):
        self.data['operations'].append(row['request']['operation'])
        for feed in self.feeds:
            if feed['operation']!=row['request']['operation'] or feed['completion'] is not None:continue
            done=self.io.wait(feed['transport_key'],timeout=40)
            feed['completion']=dict(self.io.ref_receipt(done),exit_code=done['exit_code'])
            need(done['exit_code']==0 and done['transport_exit_code']==0,'actual complete independent PCM producer')
    def collect(self):
        # Every source file still comes from the guest transport, with actual
        # uid/inode/bytes and native /proc generation, SELinux domain and maps.
        pids=set()
        sensor_inventory=self.io.guest.directory/'runtime-assets-source/inventory.json'
        self.data['sensor_inventory']=ref(sensor_inventory)
        mapping=dependency('batch_system_live_mappings');nonce=secrets.token_hex(16)
        script=mapping.snapshot_script(nonce,self.io.boot_id)
        body=self.shell(script,'provider_actual_sensor_mapping_snapshot')
        path=self.io.output/'provider-sensor-maps.raw.txt';path.write_text(body+'\n')
        actual=mapping.parse_snapshot(path.read_text(),nonce,self.io.boot_id)
        sensors=[p for p in actual['processes'].values() if p['complete'] and p['uids']==[3033]*4 and
                 'sensor_host' in str(p['argv']) and any(Path(r['path']).name=='libhdi_sensor_impl.z.so' for r in p['maps'])]
        need(len(sensors)==1,'one actual fully observed sensor_host3033 with real normal VDI')
        self.data['sensor_mapping']=dict(nonce=nonce,script=script,raw=ref(path),pid=sensors[0]['pid'])
        pids.add(sensors[0]['pid'])
        for directory in (VOICE,SPATIAL):
            names=self.shell('find '+directory+' -maxdepth 1 -type f -print','provider_actual_files').splitlines()
            baseline=set(self.data['baseline'][directory])
            for number,name in enumerate(names):
                if name in baseline and not name.endswith(('cpu-journal.jsonl','cpu-enrollment.bin')):continue
                need(re.fullmatch(re.escape(directory)+r'/[A-Za-z0-9_.+\-]+',name),'fixed actual native private basename')
                stat=self.shell('test ! -L '+name+' && stat -c "%u %g %a %s %i" '+name,'provider_actual_file_stat')
                local=self.io.output/('provider-native-'+str(len(self.data['native_files']))+'-'+Path(name).name)
                before=self.shell('sha256sum '+shlex.quote(name),'provider_native_sha_before')
                self.io.receive(name,local,'audio579_provider_native_file')
                after=self.shell('sha256sum '+shlex.quote(name),'provider_native_sha_after')
                need(before==after and before.split()==[ref(local)['sha256'],name],'actual complete stable native raw transfer')
                self.data['native_files'].append(dict(remote=name,file=ref(local),metadata=stat))
                if name.endswith('jsonl'):
                    for line in local.read_text().splitlines():pids.add(int(json.loads(line)['pid']))
        for pid in sorted(pids):
            birth_script=dependency('guest_process_identity').starttime_shell(str(pid));birth=self.shell(birth_script,'provider_native_birth')
            status=self.shell('cat /proc/'+str(pid)+'/status','provider_native_status');domain=self.shell('cat /proc/'+str(pid)+'/attr/current','provider_native_domain')
            maps=self.shell('cat /proc/'+str(pid)+'/maps','provider_native_maps')
            fds=self.shell('ls -l /proc/'+str(pid)+'/fd','provider_native_open_files')
            loaded=[];profile=doc(self.io.package_inputs['media579_audio']['installed_runtime_profile'])
            for line in maps.splitlines():
                parts=line.split(None,5)
                if len(parts)!=6 or not parts[5].startswith('/') or Path(parts[5]).name not in profile['dsos']:continue
                name=Path(parts[5]).name;path=parts[5]
                if any(r['path']==path for r in loaded):continue
                command='sha256sum /proc/'+str(pid)+'/root'+path
                value=self.shell(command,'provider_actual_mapped_DSO_bytes')
                need(value.split()==[profile['dsos'][name]['image_file']['sha256'],'/proc/'+str(pid)+'/root'+path],'actual mapped DSO file equals independent same-new-image bytes')
                loaded.append(dict(soname=name,path=path,map_inode=int(parts[4]),command=command,stdout=value,image_file=profile['dsos'][name]['image_file']))
            need(self.shell(birth_script,'provider_native_birth_after')==birth,'same native writer process generation after maps')
            self.data['native_processes'].append(dict(pid=pid,birth_ticks=int(birth.strip()),status=status,domain=domain,maps=maps,fds=fds,loaded=loaded))
        self.data['collect_completed']=True
    def restore(self):
        errors=[]
        if not self.started:return
        for directory in (VOICE,SPATIAL):
            try:
                baseline=set(self.data['baseline'][directory]);names=self.shell('find '+directory+' -maxdepth 1 -type f -print','provider_cleanup_list').splitlines()
                for name in names:
                    need(re.fullmatch(re.escape(directory)+r'/[A-Za-z0-9_.+\-]+',name),'private cleanup fixed basename')
                    if name not in baseline:self.shell('rm '+name,'provider_remove_actual_new_file')
                for backup in self.backups:
                    if str(Path(backup['remote']).parent)!=directory:continue
                    uid,gid,mode,size,inode=backup['metadata'].split();self.io.send(checked(backup['file']),backup['remote'],'audio579_provider_restore_original')
                    result=self.shell('chown '+uid+':'+gid+' '+backup['remote']+' && chmod '+mode+' '+backup['remote']+' && sha256sum '+backup['remote'],'provider_original_restored')
                    need(result.split()==[backup['file']['sha256'],backup['remote']],'original product enrollment/diagnostic bytes restored')
                after=self.shell('find '+directory+' -maxdepth 1 -type f -print','provider_cleanup_final_list').splitlines();need(set(after)==baseline,'normal CPU provider private directory baseline restored')
            except Exception as error:errors.append(type(error).__name__+': '+str(error))
        self.data['cleanup']=dict(errors=errors,original_Owner_final_finish_required=True)
        need(not errors,'actual provider cleanup errors retained')
