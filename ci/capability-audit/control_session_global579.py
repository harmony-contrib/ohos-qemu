"""Fixed398 native CONTROL + separate original377 native status window.

Called only inside the original already-owned397 collector. All Popen handles
are intercepted by its existing frozen377 constructor broker. No owner, lease,
VM, helper compiler, PCM path open or new public operation is created here.
A completed local window still never admits onset or the legacy379 schema.
"""
from __future__ import annotations
import json,os,re,secrets,shlex,subprocess,time
from pathlib import Path
import onset579_global_tools as tools
import verify_control_global579 as verify

INVENTORY=('holder_pid','holder_ticks','holder_uid','holder_gid','fd','dev','ino','rdev','card','device','subdevice')
SAMPLES=7500  # original377 bounded finite CLI, ~60s; never a public lifecycle latency proof

def need(ok,message):
    if not ok:raise ValueError(message)

def configuration(path,*,archive_sha256,profile_descriptor,domain,inventory_io_ref):
    value=tools.decode(path)
    need(type(value) is dict and set(value)=={'schema','tools','profile','inventory','inventory_proof','kernel_admission'} and value['schema']=='actual-arm32-global-CONTROL579/v1' and value['profile']==profile_descriptor,
         'fixed404 actual tools/profile/inventory input only')
    admitted=tools.admit(value['tools'],profile_descriptor=value['profile'],archive_sha256=archive_sha256,domain=domain)
    inventory=value['inventory']
    need(type(inventory) is dict and set(inventory)==set(INVENTORY),'explicit actual holder/OFD inventory required')
    for k in INVENTORY:verify.integer(inventory,k,1 if k in ('holder_pid','holder_ticks') else 0)
    need(inventory['holder_pid']>1 and inventory['fd']<2**31 and inventory['holder_uid']<2**32 and
      inventory['holder_gid']<2**32,'actual native PID/credential/FD ranges')
    from onset579_global_inventory import replay_inventory_proof
    need(value['kernel_admission']==dict(path=domain.kernel.original_kernel_admission_ref[0],sha256=domain.kernel.original_kernel_admission_ref[1]),'same original actual kernel admission')
    replayed=replay_inventory_proof(value['inventory_proof'],domain=domain,original_io_ref=inventory_io_ref)
    need(replayed==inventory,'actual global inventory raw differs')
    return admitted,dict(inventory)

def stat_ticks(raw):
    # Linux /proc comm can contain spaces and parentheses; field22 follows last ).
    tail=raw[raw.rfind(')')+2:].split()
    need(len(tail)>19 and tail[19].isdigit() and int(tail[19])>0,'actual proc start_ticks required')
    return int(tail[19])

def native_output(raw,marker):
    text=raw.replace('\r\n','\n')
    sentinel='\n'+marker
    need(text.count(marker)==1 and sentinel in text,'actual guest exit footer required')
    body,code=text.rsplit(sentinel,1)
    need(re.fullmatch('[0-9]+\n?',code) is not None and int(code)==0,'actual native guest exit0 required')
    return body+('' if body.endswith('\n') else '\n')

class ControlWindowGlobal579:
    """One explicit window. Unclosed or failed control quarantines public mutation."""
    def __init__(self,collector,admitted,inventory,phase,*,domain):
        need(type(admitted) is tools.AdmittedGlobalTools579,'actual fixed two-C admission object required')
        need(re.fullmatch('[A-Za-z0-9_.-]+',phase) is not None,'fixed capture phase name')
        self.c=collector;self.admitted=admitted;self.inventory=dict(inventory);self.phase=phase;self.domain=domain
        self.control=self.status=None;self.control_stream=self.status_stream=None;self.closed=False
        self.row=dict(scope='398 control + independent377 kernel stream ONLY_NOT_legacy379_or_onset',phase=phase,
          accepted=False,onset_proven=False,ledger_closed=False,first_artifact_behavior_gate_passed=False,
          normal397_timing_equivalence_claimed=False,failures=[])
        collector.value.setdefault('control_windows404',[]).append(self.row)
        self.run=secrets.token_hex(16);self.remote=collector.remote+'/control404-'+self.run
        self.expected=dict(inventory,run=self.run,boot=collector.env['boot_id'])
        need(domain.kernel.archive_sha256==collector.value['archive_sha256'] and domain.kernel.boot_id==self.expected['boot'],'original admitted package/boot clock domain')
    def observation(self,script,label):
        d=self.c.observe(script,self.phase+'-404-'+label)
        self.row.setdefault('observations',[]).append(d)
        need(type(d) is dict and set(d)=={'path','sha256'} and tools.digest(d['path'])==d['sha256'],'actual collector observation descriptor changed')
        return Path(d['path']).read_text()
    def process_identity(self,pid,ticks,executable,uid):
        raw=self.observation('cat /proc/'+str(pid)+'/stat','stat-'+str(pid))
        need(raw.split(' ',1)[0]==str(pid) and stat_ticks(raw)==ticks,'actual guest incarnation differs')
        status=self.observation('cat /proc/'+str(pid)+'/status','status-'+str(pid))
        match=re.search(r'(?m)^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$',status)
        need(match is not None and all(int(x)==uid for x in match.groups()),'actual four guest UIDs differ')
        self.observation('test "$(readlink /proc/'+str(pid)+'/exe)" = '+shlex.quote(executable)+' && cat /proc/'+str(pid)+'/maps','exe-maps-'+str(pid))
    def spawn(self,executable,args,kind):
        marker='__AUDIO404_'+secrets.token_hex(16)+'__='
        script='unset LD_LIBRARY_PATH LD_PRELOAD; '+shlex.join([executable,*map(str,args)])+'; audio404_rc=$?; printf "\n'+marker+'%s\n" "$audio404_rc"'
        argv=[self.c.args.hdc,'-t',self.c.guest.target,'shell',script]
        path=self.c.args.output/(self.phase+'-404-'+kind+'.log');stream=path.open('xb')
        try:child=subprocess.Popen(argv,stdin=subprocess.PIPE if kind in ('control','onset579') else subprocess.DEVNULL,
          stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        except BaseException:stream.close();raise
        self.row[kind]=dict(argv=argv,path=str(path),marker=marker,exit_code=None)
        self.c.persist();return child,stream
    def prefix(self,kind,count,timeout=15):
        child=self.control if kind=='control' else self.status;path=Path(self.row[kind]['path'])
        deadline=time.monotonic()+timeout
        while True:
            raw=path.read_bytes();need(len(raw)<16*1024*1024,'bounded actual native stream')
            # splitlines() would treat an uncommitted tail as a complete row.
            # A trailing CR is likewise pending until its LF actually arrives.
            lines=raw.replace(b'\r\n',b'\n').split(b'\n')[:-1]
            if len(lines)>=count:
                # Decode complete LF rows only; transport echoes and diagnostics reject.
                prefix=b'\n'.join(lines[:count])+b'\n'
                return verify.raw_lines(prefix.decode('utf-8'),count)
            need(child.poll() is None and time.monotonic()<deadline,'actual native child did not publish required prefix')
            time.sleep(.025)
    def begin(self):
        c=self.c;inv=self.inventory
        need(c.env['boot_id']==self.expected['boot'],'same already-held guest boot')
        # Native398 rechecks holder four UID/GID, birth, actual namespace and OFD.
        holder=self.observation('cat /proc/'+str(inv['holder_pid'])+'/stat','holder-stat-before')
        need(stat_ticks(holder)==inv['holder_ticks'],'actual selected holder generation changed')
        self.observation('cat /proc/'+str(inv['holder_pid'])+'/status && cat /proc/'+str(inv['holder_pid'])+'/maps && cat /proc/'+str(inv['holder_pid'])+'/attr/current','holder-status-maps-domain')
        for name,row in self.admitted.tools.items():
            for soname in row['needed']:
                product=tools.product_module()
                script=product.runtime_guest_script(row['helper'],soname)
                raw=self.observation(script,name+'-DSO-'+soname)
                product.verify_guest_runtime_raw(row['helper'],soname,raw,archive_sha256=c.value['archive_sha256'])
        need(not hasattr(c,'_control404_staged'),'one fixed404 window per collector; no stale holder/epoch reuse')
        for binary,name in ((self.admitted.control,'control404'),(self.admitted.status,'status377')):
            c.stage(dict(path=str(binary),sha256=tools.digest(binary)),c.remote+'/'+name,0,executable=True)
        c._control404_staged=True
        c.shell('test ! -e '+self.remote+' && test ! -L '+self.remote+' && mkdir -m 700 '+self.remote,'new-404-private-window')
        args=[inv[k] for k in ('holder_pid','holder_ticks','holder_uid','holder_gid','fd','dev','ino','rdev')]
        args += [self.expected['boot'],self.run,'--directory',self.remote]
        self.control,self.control_stream=self.spawn(c.remote+'/control404',args,'control')
        ctl=self.prefix('control',7);need(tuple(r.get('kind') for r in ctl)==verify.SEQUENCE[:7],'actual HELLO/ARM native prefix')
        ident=ctl[0]
        for k in ('client_pid','client_ticks','self_gid'):self.expected[k]=verify.integer(ident,k,1 if k in ('client_pid','client_ticks') else 0)
        self.process_identity(self.expected['client_pid'],self.expected['client_ticks'],c.remote+'/control404',0)
        args=[inv[k] for k in ('holder_pid','holder_ticks','fd','dev','ino','rdev','card','device','subdevice')]+[self.run,SAMPLES]
        self.status,self.status_stream=self.spawn(c.remote+'/status377',args,'status')
        header,=self.prefix('status',1);need(header.get('kind')=='header' and header.get('schema')=='media375-hw-sync-global-clock579/v1','original independent sampler header')
        pid,ticks,fd=(verify.integer(header,k,1 if k!='borrowed_fd' else 0) for k in ('sampler_pid','sampler_ticks','borrowed_fd'))
        self.process_identity(pid,ticks,c.remote+'/status377',0)
        self.control.stdin.write(('SAMPLER '+str(pid)+' '+str(ticks)+' '+str(fd)+'\n').encode());self.control.stdin.flush()
        self.prefix('control',8);self.row['native_armed_and_sampler_registered']=True;self.c.persist()
        return self
    def receive_tap(self):
        # Canonical generic receive requires >0 bytes. A real no-progress EAGAIN
        # window legitimately has an empty tap and must remain non-onset, not a
        # permanent-invalid transport. Restrict the zero exception to THIS tap.
        remote=self.remote+'/tap.pcm';path=self.c.args.output/(self.phase+'-404-tap-'+self.run+'.pcm')
        guard=self.observation('test -f '+remote+' && test ! -L '+remote+' && sha256sum '+remote,'tap-guest-hash')
        self.c.command([self.c.args.hdc,'-t',self.c.guest.target,'file','recv',remote,path],self.phase+'-404-receive-tap')
        need(path.is_file() and not path.is_symlink() and 0<=path.stat().st_size<=verify.MAX_BYTES and
          guard.split()==[tools.digest(path),remote],'actual zero-or-bounded complete tap bytes/hash')
        result=dict(path=str(path),sha256=tools.digest(path))
        self.c.value['received'].append(dict(remote=remote,raw=result,guest_hash=guard,command=len(self.c.value['commands'])-1))
        self.c.persist();return result
    def finish(self):
        need(self.control is not None and self.status is not None and not self.closed,'actual started unclosed404 window')
        status_code=self.status.wait(timeout=65);self.status_stream.close();self.status_stream=None
        self.row['status']['exit_code']=status_code
        status_raw=Path(self.row['status']['path']).read_text();status_native=native_output(status_raw,self.row['status']['marker'])
        need(type(status_code) is int and status_code==0,'actual root-held HDC status process exit0')
        # Native CONTROL independently demands real pidfd death AND proc absence
        # before DISARM. Never replace these with a host process boolean.
        self.control.stdin.write(b'DISARM\n');self.control.stdin.flush();self.control.stdin.close()
        code=self.control.wait(timeout=15);self.control_stream.close();self.control_stream=None;self.row['control']['exit_code']=code
        control_raw=Path(self.row['control']['path']).read_text();control_native=native_output(control_raw,self.row['control']['marker'])
        need(type(code) is int and code==0,'actual root-held HDC CONTROL process exit0')
        self.observation('test ! -e /proc/'+str(self.expected['client_pid'])+'/stat','control-native-process-absent')
        pulled={name:self.c.receive(self.remote+'/'+name,self.phase+'-404-'+name.replace('.','-')) for name in ('control.jsonl','journal.jsonl')}
        pulled['tap.pcm']=self.receive_tap()
        self.row['received']=pulled
        control_bytes=Path(pulled['control.jsonl']['path']).read_bytes()
        need(control_bytes==control_native.encode(),'actual target ledger differs from CONTROL transport')
        result=verify.verify_window(control_native,Path(pulled['journal.jsonl']['path']).read_text(),Path(pulled['tap.pcm']['path']).read_bytes(),status_native,
          expected=self.expected,control_exit_code=code,sampler_exit_code=status_code,domain=self.domain)
        self.row['independent_new398_result']=result;self.row['expected_actual_inventory']=self.expected
        # Mark only real protocol/duplicate closure, never legacy/onset success.
        self.closed=True;self.row['control_and_sampler_closed']=True;self.c.persist();return self.row
    def dispose_files(self):
        need(self.closed,'preserve unresolved native witnesses; root must quarantine guest')
        names=[self.remote+'/'+n for n in ('control.jsonl','journal.jsonl','tap.pcm')]
        self.c.shell('rm -- '+shlex.join(names)+' && rmdir '+self.remote+' && rm -- '+self.c.remote+'/control404 '+self.c.remote+'/status377','only-404-owned-files-remove')
