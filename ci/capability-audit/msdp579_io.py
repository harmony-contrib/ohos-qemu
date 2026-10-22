"""Actual HAP operations on ONE original registered IO. No resource owner."""
from pathlib import Path
import json,re,secrets,shlex,time
from msdp579_contract import need,ref,raw,doc,save,request
from msdp579_project import ROLES,bundle
from msdp579_process import observe,replay
from apps_providers579_bindings import bms_json,objects
class Flow:
 def __init__(self,io,case):
  need(not io._closed and case in ('local','sensor','cooperate'),'original held IO and fixed case')
  (io.assert_original() if hasattr(io,'capture') else io.owner.held_binding(io.guest));self.io=io;self.case=case;self.path=Path(io.output)/'msdp579';self.path.mkdir(exist_ok=False)
  self.data=dict(schema='msdp579-actual-flow/v1',case=case,run_id=io.run_id,boot_id=io.boot_id,udid=io.udid,archive_sha256=io.archive_sha256,
   prepared=None,installed={},cleanup_attempts=[],actions=[],processes=[],inputs=[],cleanup=None,failures=[],runtime_pass=False,first_artifact_behavior_gate_passed=False)
  self.prefix={};self.serial=0;self.installed=[];self.cleaned=False
  io.register_cleanup(self.cleanup)
 def persist(self):
  # Mutable producer index; every raw cut has a fresh immutable filename.
  (self.path/'flow.json').write_text(json.dumps(self.data,indent=2,allow_nan=False)+'\n')
 def shell(self,s,label,allow=False):return self.io.shell(s,'msdp579_'+label,allow_failure=allow)
 def prepare(self):
  if hasattr(self.io,'capture'):
   self.data['native']=doc(self.io.supplement)['native']
  else:self.data['native']=self.io.package_inputs['native_addons']['msdp579']
  self.data['prepared']=self.io.prepare_callers('msdp579',self.case,self.io.run_id,ROLES,{'profile':(self.io.profile if hasattr(self.io,'capture') else self.io.guest.report['test_environment']['device_type'])});self.persist()
 def install(self,role):
  need(role in ROLES and role not in self.installed,'fixed uninstalled role')
  caller=self.data['prepared']['callers'][role];b=bundle(self.case,role)
  before=self.shell('bm dump -a','absent_'+role);need(b not in before['stdout'],'fixture not fresh')
  remote='/data/local/tmp/msdp579_'+self.io.run_id+'_'+role+'.hap'
  self.io.send(caller['signed']['path'],remote,'msdp579_hap_'+role)
  # Register intent before install can partially succeed.
  self.installed.append(role)
  install=self.shell(shlex.join(['bm','install','-p',remote,'-u','100']),'install_'+role)
  need('success' in install['stdout'].lower(),'actual BMS install failed')
  bms=self.shell('bm dump -n '+b+' -u 100','bms_'+role);v=bms_json(bms['stdout']);app=v['applicationInfo']
  need(app['isSystemApp']==(role!='normal') and app['appPrivilegeLevel']==('normal' if role=='normal' else 'system_core'),'actual role/APL differs')
  paths=sorted({x['hapPath'] for x in objects(v) if x.get('hapPath')});need(len(paths)==1 and re.fullmatch('/data/app/[^\\s;]+\\.hap',paths[0]),'actual installed HAP path')
  h=self.shell('sha256sum '+shlex.quote(paths[0]),'hap_hash_'+role);need(h['stdout'].split()[0]==caller['signed']['sha256'],'installed bytes differ')
  self.data['installed'][role]=dict(uid=app['uid'],bms=self.io.ref_receipt(bms),hap=self.io.ref_receipt(h),install=self.io.ref_receipt(install),remote=remote)
  self.persist()
 def rows(self,role):
  pattern='/data/app/el2/100/base/'+bundle(self.case,role)+'/files/msdp579-'+self.io.run_id+'-*.jsonl'
  listing=self.shell('for p in '+pattern+'; do test ! -f "$p" || printf "%s\\n" "$p"; done','journals_'+role,True)
  refs=[];rows=[]
  for remote in listing['stdout'].splitlines():
   need(re.fullmatch(re.escape(pattern).replace(r'\*','[0-9]+'),remote),'fixed caller journal path')
   self.serial+=1;p=self.path/('raw_'+str(self.serial)+'.jsonl');self.io.receive(remote,p,'msdp579_raw_'+role)
   data=p.read_bytes();key=(role,remote);need(data.startswith(self.prefix.get(key,b'')),'append-only journal replaced');self.prefix[key]=data;refs.append(ref(p))
   rows.extend(json.loads(line) for line in data.splitlines())
  for r in rows:need(r['run_id']==self.io.run_id and r['kind']==self.case and r['role']==role and r['bundle']==bundle(self.case,role) and r['uid']==self.data['installed'][role]['uid'],'actual caller role/nonce/UID')
  return rows,refs
 def begin(self,role,action,payload=None):
  need(role in self.data['installed'],'actual installed role')
  self.serial+=1;q=request(self.io.run_id,self.serial,action,payload);start=(len(self.io.receipts),len(self.io.qmp_receipts));stamp=time.monotonic_ns()
  argv=['aa','start','-b',bundle(self.case,role),'-a','EntryAbility','-m','entry','-u','100']
  for key in ('run_id','request_id','action'):argv+=['--ps',key,q[key]]
  argv+=['--ps','payload',json.dumps(q['payload'],separators=(',',':'))]
  r=self.shell(shlex.join(argv),'launch_'+str(self.serial));need('start ability successfully' in r['stdout'].lower(),'actual AMS launch')
  cut=dict(role=role,request=q,started_ns=stamp,finished_ns=None,commands=[],qmp=[],raw=[],error=None)
  self.data['actions'].append(cut);self.persist();return cut,start
 def finish(self,token,timeout=45):
  cut,start=token;deadline=time.monotonic()+timeout
  try:
   while True:
    rows,refs=self.rows(cut['role']);cut['raw']=refs
    selected=[r for r in rows if r['request_id']==cut['request']['request_id']]
    if any(r['event'] in ('done','error','request-error','page-error') for r in selected):break
    need(time.monotonic()<deadline,'actual API terminal missing '+cut['request']['action']);time.sleep(.25)
   return selected
  except BaseException as error:cut['error']=repr(error);raise
  finally:
   cut['commands']=[self.io.ref_receipt(r) for r in self.io.receipts[start[0]:]];cut['qmp']=self.io.qmp_receipts[start[1]:];cut['finished_ns']=time.monotonic_ns();self.persist()
 def call(self,role,action,payload=None):return self.finish(self.begin(role,action,payload))
 def stop(self,role):
  uid=self.data['installed'][role]['uid'];before=observe(self.io,uid,bundle(self.case,role),'msdp579_pre_stop',maps=True)
  stopped=self.shell('aa force-stop '+bundle(self.case,role),'stop_'+role);deadline=time.monotonic()+20
  while True:
   after=observe(self.io,uid,bundle(self.case,role),'msdp579_post_stop')
   def body(r):
    matches=[x for x in self.io.receipts if self.io.ref_receipt(x)==r];need(len(matches)==1,'actual process cut');return matches[0].get('shell_stdout',matches[0]['stdout'])
   if not replay(after,body)['processes']:break
   need(time.monotonic()<deadline,'UID processes survived stop');time.sleep(.2)
  value=dict(role=role,before=before,stop=self.io.ref_receipt(stopped),after=after);self.data['processes'].append(value);self.persist();return value
 def cleanup(self):
  if self.cleaned:return self.data['cleanup']
  errors=[];commands=[];interrupt=None
  for role in reversed(self.installed):
   operations=[]
   if role in self.data['installed']:operations.append(('stop',lambda role=role:self.stop(role)))
   def uninstall(role=role):
    r=self.shell('bm uninstall -n '+bundle(self.case,role)+' -u 100','uninstall_'+role);commands.append(self.io.ref_receipt(r));need('success' in r['stdout'].lower(),'uninstall failed')
   def absent(role=role):
    r=self.shell('bm dump -a','final_absent_'+role);commands.append(self.io.ref_receipt(r));need(bundle(self.case,role) not in r['stdout'],'fixture remains')
   def temporary(role=role):
    remote=self.data['installed'].get(role,{}).get('remote','/data/local/tmp/msdp579_'+self.io.run_id+'_'+role+'.hap')
    commands.append(self.io.ref_receipt(self.shell('rm -f '+shlex.quote(remote)+' && test ! -e '+shlex.quote(remote),'remote_absent_'+role)))
   operations.extend((('uninstall',uninstall),('absence',absent),('temporary',temporary)))
   for step,operation in operations:
    try:operation()
    except BaseException as error:
     errors.append(dict(role=role,step=step,error=repr(error)))
     if not isinstance(error,Exception) and interrupt is None:interrupt=error
  self.data['cleanup']=dict(commands=commands,errors=errors);self.data['cleanup_attempts'].append(self.data['cleanup']);self.cleaned=not errors;self.persist()
  if interrupt is not None:raise interrupt
  if errors:
   from capability578_stage import UnsettledCapability
   raise UnsettledCapability('MSDP cleanup uncertain; prohibit guest reuse: '+repr(errors))
  return self.data['cleanup']

def seal_closed(io,flow,boot):
 need(io._closed and flow.cleaned,'all original IO transports and business cleanup must finish')
 return save(Path(io.output)/'msdp579-retained.json',dict(schema='msdp579-closed-IO/v1',archive_sha256=io.archive_sha256,boot_id=io.boot_id,
  boot=boot,io=ref(Path(io.output)/'io.json'),flow=ref(flow.path/'flow.json')))
