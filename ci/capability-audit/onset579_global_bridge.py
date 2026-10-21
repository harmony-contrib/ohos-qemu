"""Global580 AF window inside the original held three-UID collector.

Fixed Root code supplies its original admitted bindings and clock domain.
No module/global substitution, Owner, Authority, lease or constructor is added.
"""
from pathlib import Path
import hashlib,json,re,shlex,time
import onset579_global_clock as clock
import onset579_global_tools as tools
from onset579_global_mapping import decode,lines,qap_rows,source_identity,need
NAME='audio_global579_af'
AF_DSOS={'libaudio_common.z.so','libaudio_engine_utils.z.so','libaudio_engine_node.z.so','libaudio_process_service.z.so','libaudio_effect.z.so'}
DRIVER_DSOS={'libaudio_render_adapter.z.so','libaudio_primary_impl_vendor.z.so'}
PROVENANCE_DSOS={'libaudio_haptic.z.so','libmedia_engine_histreamer.z.so','libmedia_plugin_AudioServerSink.z.so'}

def ref2(row):return {k:row[k] for k in ('path','sha256')}
def sized(row,*,bindings):
    b=bindings
    path=b.checked(ref2(row));need(type(row.get('bytes')) is int and path.stat().st_size==row['bytes'],'actual full file size differs');return path
def pinned(row,*,bindings):
    b=bindings
    path=b.checked(ref2(row));need(b.verify_sources().get(str(path))==row['sha256'],'producer source absent from explicit private source admission');return path

def installed_supplement(spec,*,archive,original_ref,original,product,bindings):
    b=bindings
    import tarfile
    supp_path=b.checked(spec);supp=b.load(supp_path)
    need(set(supp)=={'schema','source_commit','archive','package_receipt','build_inputs','export_receipt','source_export','profile_producer_source','original_profile','images','profile','proofs','provenance_dsos','libasound','runtime_pass','first_artifact_behavior_gate_passed'} and supp['schema']=='actual-package-audio-onset579-installed-dsos/v1','finite independent installed-DSO supplement')
    need(supp['runtime_pass'] is False and supp['first_artifact_behavior_gate_passed'] is False and ref2(supp['archive'])==archive and ref2(supp['original_profile'])==ref2(original_ref),'supplement same archive/original15 and nonruntime scope')
    original_path=b.checked(ref2(original_ref));need(b.load(original_path)==original and len(original['dsos'])==15,'unaltered actual original15 profile')
    pinned(supp['profile_producer_source'],bindings=b)
    receipt=b.load(original_path.parent/'receipt.json')
    need(receipt['exit_code']==0 and receipt['status']=='pass_actual_NEW_archive_image_staged_bytes_ONLY' and receipt['profile']==supp['original_profile'] and receipt['source_commit']==supp['source_commit'] and receipt['package']==supp['archive'] and receipt['images']==supp['images'] and receipt['source_export']==supp['source_export'] and receipt['export_receipt']==supp['export_receipt'] and receipt['profile_producer_source']==supp['profile_producer_source'],'actual original extraction receipt linkage')
    package=b.load(b.checked(ref2(supp['package_receipt'])));export=b.load(b.checked(ref2(supp['export_receipt'])));staged_file=b.checked(ref2(supp['source_export']));staged=b.load(staged_file);build_inputs=b.load(b.checked(ref2(supp['build_inputs'])))
    need(package['exit_code']==export['exit_code']==0 and package['source_commit']==export['source_commit']==supp['source_commit']==build_inputs['source_git_revision'] and ref2(package['package'])==archive and export['source_export']==supp['source_export'] and ref2(export['package'])==archive and export['cleanup_verified'] is True and staged['source_ro'] is True and staged['out_ro'] is True,'actual successful readonly source/new archive receipts')
    profile=supp['profile'];need(profile.get('kind')=='installed_audio_onset_dsos' and set(profile['dsos'])==AF_DSOS|DRIVER_DSOS and set(supp['proofs'])==AF_DSOS|DRIVER_DSOS,'independent exact seven-DSO sidecar')
    for key in ('archive','system_image','vendor_image','source_root','product','arch','device'):
        need(profile[key]==original[key],'supplement belongs to another original profile: '+key)
    provenance=supp['provenance_dsos'];need(type(provenance) is dict and set(provenance)==PROVENANCE_DSOS and all(set(item)=={'entry','proof'} for item in provenance.values()),'independent exact three provenance DSO witnesses')
    view=dict(original,dsos=dict(original['dsos'],**profile['dsos'],**{name:item['entry'] for name,item in provenance.items()}));product.validate_installed_profile(view,archive_sha256=archive['sha256'])
    images={name:sized(row,bindings=b) for name,row in supp['images'].items()}
    need(set(images)=={'system','vendor','chip_prod'},'actual three independently extracted images')
    for name in ('system','vendor'):
        row=profile[name+'_image'];need(row['sha256']==supp['images'][name]['sha256'] and row['bytes']==images[name].stat().st_size,'profile/image full bytes differ')
    # Pure archive replay: no external debugfs or tool invocation here. Parent's
    # actual stat/dump commands and image-member inodes are re-read below.
    seen=set()
    with tarfile.open(b.checked(archive),'r:gz') as stream:
        wanted={profile[n+'_image']['archive_member']:n for n in ('system','vendor')}
        for member in stream:
            if member.name not in wanted:continue
            need(member.isfile() and member.name not in seen,'one actual regular image archive member');seen.add(member.name);name=wanted[member.name]
            f=stream.extractfile(member);need(f is not None,'actual image member unavailable');h=hashlib.sha256();length=0
            with f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk);length+=len(chunk)
            need(h.hexdigest()==supp['images'][name]['sha256'] and length==supp['images'][name]['bytes'],'actual archive/image rehash differs')
        need(seen==set(wanted),'same new archive is missing installed images')
    for name,proof in dict(supp['proofs'],**{n:item['proof'] for n,item in provenance.items()},**{'libasound.so':supp['libasound']}).items():
        need(set(proof)=={'staged','actual_image','image_inode','partition'} and proof['partition'] in ('system','vendor') and type(proof['image_inode']) is int and proof['image_inode']>0,'actual installed inode/partition proof')
        entry=view['dsos'][name];row=proof['staged'];actual=sized(proof['actual_image'],bindings=b);exported=sized(dict(path=str(staged_file.parent/row['export_relative']),sha256=row['sha256'],bytes=row['bytes']),bindings=b)
        need(row in staged['files'] and not row['symlink'] and row['partition']==proof['partition'] and row['image_member']==entry['image_member'] and row['path']==entry['staged']['path'] and row['sha256']==entry['staged']['sha256']==entry['image_file']['sha256']==b.sha(actual)==b.sha(exported) and row['bytes']==entry['staged']['bytes']==entry['image_file']['bytes']==actual.stat().st_size,'staged/full extracted DSO bytes differ')
        need(original_path.parent/Path(entry['image_file']['path']).relative_to('/runtime-profile')==actual,'fixed image-dump path binding')
        need(re.findall(r'\(SONAME\)\s+Library soname: \[([^\]]+)\]',row['elf'])==[name],'actual source-export ELF SONAME differs')
        for action in ('stat','dump'):
            text=action+' '+entry['image_member']+(' '+str(actual) if action=='dump' else '')
            expected=[receipt['debugfs']['path'],'-R',text,str(images[proof['partition']])]
            commands=[c for c in receipt['commands'] if c['argv']==expected]
            need(len(commands)==1 and commands[0]['exit_code']==0 and commands[0]['timed_out'] is False,'actual image debugfs command/exit missing')
            command=commands[0];out=sized(command['stdout'],bindings=b).read_text();sized(command['stderr'],bindings=b)
            if action=='stat':need(re.search(r'(?m)^Inode:\s+'+str(proof['image_inode'])+r'\s+Type:\s+regular\s',out) is not None,'actual image inode differs')
    return profile,view,supp

def admit(spec,*,archive,profile_ref,domain,bindings):
    b=bindings
    need(type(spec) is dict and set(spec)=={'schema','tools','installed_dsos'} and
         spec['schema']=='audio-onset-global579-input/v1','explicit global sixth AU descriptor')
    native=tools.admit(spec['tools'],profile_descriptor=profile_ref,archive_sha256=archive['sha256'],domain=domain)
    product=tools.product_module();row=native.af_tool['helper'];binary=native.af
    helper=dict(binary=tools.record(binary),build=spec['tools']['build'],production=spec['tools']['production'],
                source=tools.record(binary.parent/'audio_onset_global579.c'))
    profile_path=b.checked(ref2(profile_ref));original=b.load(profile_path)
    profile,view,supplement=installed_supplement(spec['installed_dsos'],archive=archive,
        original_ref=profile_ref,original=original,product=product,bindings=b)
    need(supplement['source_commit']==b.load(b.checked(spec['tools']['production']))['source_commit'],
         'global native source and installed AF/driver source revision differ')
    return dict(helper=helper,binary=binary,row=row,needed=native.af_tool['needed'],product=product,
        profile=profile,profile_view=view,supplement=supplement,supplement_ref=spec['installed_dsos'],native=native)

def profile_from_config(config):
    env=config['environment'];row=dict(path=env['OHOS_QA_RUNTIME_PROFILE'],sha256=env['OHOS_QA_RUNTIME_PROFILE_SHA256'])
    return dict(row,bytes=tools.checked(row).stat().st_size)

class WindowGlobalAF579:
    def __init__(self,collector,original,*,domain,bindings):
        self.b=bindings;self.domain=domain
        self.c=collector;self.original=original;self.run=original.run
        profile_ref=profile_from_config(self.b.load(collector.args.root_config))
        if 'OHOS_QA_RUNTIME_PROFILE' in collector.guest.env:
            need(ref2(profile_ref)==dict(path=collector.guest.env['OHOS_QA_RUNTIME_PROFILE'],
                sha256=collector.guest.env['OHOS_QA_RUNTIME_PROFILE_SHA256']),'same original actual guest profile binding')
        self.admitted=admit(collector.inputs['onset579'],archive=collector.value['archive'],profile_ref=profile_ref,domain=domain,bindings=bindings)
        self.child=self.stream=None;self.closed=False
        self.row=dict(schema='actual-original480-onset-global579-window/v1',run=self.run,boot=collector.boot,helper=self.admitted['helper'],
            installed_dsos=self.admitted['supplement_ref'],observations=[],libraries=[],provenance_libraries=[],qap=[],downloads=[],native_closed=False,files_removed=False,
            accepted=False,onset_proven=False,first_artifact_behavior_gate_passed=False)
        collector.value['onset579_window']=self.row;collector.save()
    def observe(self,script,label):
        ref=self.c.observe(script,'onset579_'+label);self.row['observations'].append(dict(script=script,raw=ref));self.c.save();return self.b.checked(ref).read_text()
    def capture(self,remote,label,uid=None):
        before=len(self.c.guest.report['commands']);value=self.c.receive(remote,'onset579_'+label,uid)
        entry=dict(remote=remote,value=value,guest_begin=before,guest_end=len(self.c.guest.report['commands']))
        self.row['downloads'].append(entry);self.c.save();return value
    def prefix(self,count):
        deadline=time.monotonic()+20;path=Path(self.row['transport']['path'])
        while True:
            raw=path.read_bytes();need(len(raw)<1024*1024,'bounded native579 transport')
            complete=raw.replace(b'\r\n',b'\n').split(b'\n')[:-1]
            if len(complete)>=count:return [decode(line) for line in complete[:count]]
            need(self.child.poll() is None and time.monotonic()<deadline,'actual native579 prefix unavailable');time.sleep(.025)
    def qap(self,label):
        raw=self.observe('hilog -x','qap_'+label);self.row['qap'].append(self.row['observations'][-1]['raw']);self.c.save();return raw
    def prepare(self):
        c=self.c;tool=self.admitted['binary'];remote=c.remote+'/onset579';self.journal=self.original.remote+'/onset579.jsonl'
        for soname in self.admitted['needed']:
            script=self.admitted['product'].runtime_guest_script(self.admitted['row'],soname)
            raw=self.observe(script,'tool_dso_'+soname.replace('.','_'))
            self.admitted['product'].verify_guest_runtime_raw(self.admitted['row'],soname,raw,archive_sha256=c.value['archive']['sha256'])
        c.publish(tool,remote,0)
        self.observe('chmod 0700 '+shlex.quote(remote)+' && test "$(stat -c "%u %a" '+shlex.quote(remote)+')" = "0 700" && sha256sum '+shlex.quote(remote),'tool_deployed')
        raw=self.observe(shlex.join([remote,'--inventory',c.boot,self.run]),'inventory')
        rows=lines(raw,10);need(len(rows)==3 and rows[0].get('kind')=='inventory_begin580' and rows[0].get('boot')==c.boot and rows[-1]==dict(kind='inventory_end580',count=1,error=0),'actual unique AF producer inventory')
        inv=rows[1];need(inv.get('kind')=='producer580' and all(type(inv.get(k)) is int and inv[k]>=0 for k in ('pid','birth','uid','gid')) and inv['pid']>1 and inv['birth']>0 and inv['pidfd_close_rc']==0,'actual producer fields and inventory pidfd closed')
        clock.observation(inv['clock_domain'],domain=self.domain,run=self.run,role='af_producer',
            expected=(inv['pid'],inv['birth'],rows[0]['observer_pid'],inv['clock_domain']['held_pidfd']))
        need(rows[0]['observer_pid']>1 and rows[0]['observer_birth']>0,'actual inventory observer incarnation')
        self.row['inventory']=inv
        self.observe('cat /proc/'+str(inv['pid'])+'/stat && cat /proc/'+str(inv['pid'])+'/status','producer_identity')
        entries=dict(self.admitted['profile']['dsos'],**{name:item['entry'] for name,item in self.admitted['supplement']['provenance_dsos'].items()})
        for name,entry in entries.items():
            staged=entry['staged']['path'];prefix=self.admitted['product'].installed_prefix(self.admitted['profile'])+'/'
            suffix=staged.removeprefix(prefix);partition,_,_=suffix.partition('/');guest='/'+partition+entry['image_member']
            need(guest.startswith(('/system/','/vendor/')) and '..' not in Path(guest).parts,'fixed installed image member')
            got=self.capture(guest,'loaded_'+name.replace('.','_'))
            need(got['file']['sha256']==entry['staged']['sha256'],'actual loaded product DSO full bytes differ')
            self.row['libraries' if name not in PROVENANCE_DSOS else 'provenance_libraries'].append(dict(soname=name,guest_path=guest,received=got));self.c.save()
        source=c.actor('owner')['files']+c.run+'-stop.wav'
        self.row['source_remote']=source;self.row['source_stat']=self.c.observe('stat -Lc "%d %i %u %s" '+shlex.quote(source),'onset579_source_stat')
        self.row['source_file']=self.capture(source,'fresh_owner_source',c.actor('owner')['uid'])
        need(self.row['source_file']['file']['sha256']==c.preparation['roles']['owner']['audio']['sha256'],'actual fresh nonce source file changed')
        self.qap('before_start')
        self.row['prepared']=True;c.save()
    def begin(self):
        c=self.c;inv=self.row['inventory'];remote=c.remote+'/onset579'
        need(self.row.get('prepared') is True and self.child is None,'finite prepared producer/tool/DSO/source before ARM')
        args=[inv['pid'],inv['birth'],inv['uid'],c.boot,self.run,self.journal]
        self.child,self.stream=self.original.spawn(remote,args,'onset579')
        self.row['transport']=self.original.row['onset579']
        import actor377
        self.row['constructor']=dict(actor=actor377.STATE['actor'],handle=getattr(self.child,'_handle'),pid=self.child.pid)
        c.save();prefix=self.prefix(3)
        need([r.get('kind') for r in prefix]==['hello580','request580','ack580'] and prefix[2].get('phase')=='arm' and prefix[2].get('error')==0 and prefix[2].get('state')==1,'actual root AF ARM/ACK absent')
        self.row['hello']=prefix[0];self.row['arm']=prefix[2]
        client=prefix[0]['client_pid']
        self.observe('cat /proc/'+str(client)+'/stat && cat /proc/'+str(client)+'/status','client_identity')
        c.save();return self
    def owner_start(self):
        identity=None;last_error=None
        # Actual snapshots only. The bounded wait is collection liveness, never
        # a presentation clock or substitute for frame0/HW evidence.
        for attempt in range(6):
            self.qap('after_owner_start_'+str(attempt))
            try:
                raws=[self.b.checked(ref).read_text() for ref in self.row['qap']]
                identity=source_identity(qap_rows(raws),self.b.checked(self.row['source_stat']).read_text(),self.b.checked(self.row['source_file']['file']).read_bytes())
                break
            except ValueError as error:last_error=error
            if attempt<5:time.sleep(.05)
        need(identity is not None,'actual native decoded source/accepted session unavailable: '+str(last_error))
        owner=self.c.actor('owner');need(identity['source_pid']==owner['pid'] and identity['source_birth']==owner['process_start']['start_ticks'],'actual ordinary owner native source incarnation')
        pid=identity['receiver_pid'];need(type(pid) is int and pid>1,'actual QAP receiver process')
        script='cat /proc/'+str(pid)+'/stat && printf "\\nONSET579_STATUS\\n" && cat /proc/'+str(pid)+'/status && printf "\\nONSET579_MAPS\\n" && cat /proc/'+str(pid)+'/maps'
        self.row['receiver_identity']=dict(pid=pid,birth=identity['receiver_birth'],script=script,raw=self.c.observe(script,'onset579_receiver_identity'))
        command='CLOCK '+str(pid)+' '+str(identity['receiver_birth'])+'\n'
        self.child.stdin.write(command.encode());self.child.stdin.flush()
        receiver=self.prefix(4)[3]
        need(receiver.get('kind')=='receiver_clock580' and receiver['pidfd_close_rc']==0,'actual receiver clock pidfd closed')
        clock.observation(receiver['clock_domain'],domain=self.domain,run=self.run,role='renderer_receiver',
            expected=(pid,identity['receiver_birth'],self.row['hello']['client_pid'],receiver['clock_domain']['held_pidfd']))
        self.row['receiver_clock_command']=command;self.row['receiver_clock']=receiver
        self.row['source_identity']={k:v for k,v in identity.items() if k!='prefix'}
        self.row['source_maps']=self.c.observe('cat /proc/'+str(owner['pid'])+'/maps','onset579_source_maps')
        self.row['producer_maps']=self.c.observe('cat /proc/'+str(self.row['inventory']['pid'])+'/maps','onset579_producer_maps')
        self.row['holder_maps']=self.c.observe('cat /proc/'+str(self.original.inventory['holder_pid'])+'/maps','onset579_holder_maps')
        self.c.save()
    def finish(self):
        need(self.child is not None and not self.closed,'actual native579 started once')
        self.qap('finish_before_disarm')
        self.child.stdin.write(b'DISARM\n');self.child.stdin.flush();self.child.stdin.close()
        code=self.child.wait(timeout=20);self.stream.close();self.stream=None
        self.row['transport']['exit_code']=code;self.row['transport']['raw']=self.b.record(self.row['transport']['path']);self.c.save()
        from control_session_global579 import native_output
        raw=native_output(Path(self.row['transport']['path']).read_text(),self.row['transport']['marker'])
        native=lines(raw,20);need(code==0 and native[-1].get('kind')=='end_control580' and native[-1].get('error')==0,'actual native579 process failed')
        hello=native[0];self.observe('test ! -e /proc/'+str(hello['client_pid'])+'/stat','client_absent')
        self.row['journal']=self.capture(self.journal,'af_journal',0)
        self.row['native_closed']=True;self.closed=True;self.c.save()
    def dispose_files(self):
        need(self.closed and self.row['native_closed'],'quiescence before removal')
        self.observe('rm -- '+shlex.quote(self.journal)+' '+shlex.quote(self.c.remote+'/onset579')+' && test ! -e '+shlex.quote(self.journal)+' && test ! -e '+shlex.quote(self.c.remote+'/onset579'),'remove_owned_files')
        self.row['files_removed']=True;self.c.save()
