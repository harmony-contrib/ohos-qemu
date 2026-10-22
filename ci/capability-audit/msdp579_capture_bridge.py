"""Primitive view of ORIGINAL Capture; no Owner/Guest/Runner or transport."""
from pathlib import Path
from types import SimpleNamespace
import json,re,time
from msdp579_contract import need,ref,raw,doc,save
from msdp579_project import ROLES,bundle,configure_profile
class CaptureBridge:
 def __init__(self,capture,unsigned,signer_dist):
  self.capture=capture;self.output=Path(capture.output)/'msdp579-sensor-bridge';self.output.mkdir(exist_ok=False)
  self.boot=doc(ref(capture.a.boot));self.env=self.boot['test_environment'];self.boot_id=self.env['boot_id'];self.udid=self.env['udid'];self.profile=self.env['device_type']
  self.run_id=capture.a.run_id;self.archive_sha256=self.boot['archive_sha256'];self.hdc=capture.a.hdc;self.target=capture.a.target
  self.ui=capture.ui;self.qmp_receipts=[];self.environment={'permission_allow_text':capture.a.permission_allow_text};self._closed=False;self._cleanup=[];self.signer_dist=Path(signer_dist)
  self.supplement=unsigned;self.assert_original()
 def assert_original(self):
  c=self.capture;need(type(c).__name__=='Capture' and self.boot['purpose']=='acceptance' and self.env['external_keepalive'] is False and
   self.archive_sha256==c.report['archive_sha256'] and c.report['boot_id']==self.boot_id and self.env['target']==c.a.target and self.run_id==c.report['run_id'] and
   c.report['runner_sha256']==ref(Path(__file__).with_name('batch_system_run_live_inputs.py'))['sha256'],'exact original live Capture/boot/source')
  need(c.shell('cat /proc/sys/kernel/random/boot_id','msdp579_original_boot')==self.boot_id,'capture guest rebooted')
 @property
 def receipts(self):
  out=[]
  for r in self.capture.report['commands']:
   if 'stdout_record' not in r:continue
   value=dict(argv=r['argv'],exit_code=r['exit_code'],timed_out=r.get('timed_out',False),boot_id=self.boot_id,
    stdout=raw(r['stdout_record']).decode(),stderr=raw(r['stderr_record']).decode(),stdout_ref=r['stdout_record'],stderr_ref=r['stderr_record'],log={'path':r['log'],'sha256':r['sha256']})
   if 'msdp_shell' in r:value.update(r['msdp_shell'])
   out.append(value)
  return out
 @staticmethod
 def ref_receipt(r):
  result={k:r[k] for k in ('argv','exit_code','boot_id','timed_out')};result.update(stdout=r['stdout_ref'],stderr=r['stderr_ref'])
  if 'shell_stdout' in r:result.update(shell_stdout=r['shell_stdout_ref'],shell_exit_code=r['shell_exit_code'])
  if 'transport_exit_code' in r:result.update(exit_code=r['transport_exit_code'],stdout=r['transport_stdout_ref'])
  return result
 def shell(self,script,label,timeout=60,allow_failure=False):
  need(timeout<=60 and re.fullmatch('[A-Za-z0-9_-]+',label),'bounded fixed original shell label')
  body=self.capture.shell(script,label,accepted_failure=allow_failure);r=self.capture.report['commands'][-1]
  match=re.findall(r'__LIVE_GUEST_EXIT_[a-f0-9]{32}__=',r['argv'][4]);need(len(match)==1,'actual original shell marker')
  from guest_ui import command_exit
  actual,code=command_exit(raw(r['stdout_record']).decode().replace('\r',''),match[0]);need(actual.rstrip('\n')==body,'actual Capture body differs')
  p=self.output/('body_'+str(len(self.capture.report['commands']))+'.txt');p.write_text(actual)
  r['msdp_shell']=dict(shell_stdout=actual,shell_stdout_ref=ref(p),shell_exit_code=code)
  value=self.receipts[-1];return dict(value,stdout=actual,stdout_ref=ref(p),exit_code=code,transport_exit_code=value['exit_code'],transport_stdout_ref=value['stdout_ref'])
 def send(self,local,remote,label):self.capture.command([self.hdc,'-t',self.target,'file','send',local,remote],label);return self.receipts[-1]
 def receive(self,remote,local,label):self.capture.command([self.hdc,'-t',self.target,'file','recv',remote,local],label);return self.receipts[-1]
 def register_cleanup(self,f):self._cleanup.append(f)
 def prepare_callers(self,family,case,run,roles,parameters):
  need(family=='msdp579' and case=='sensor' and run==self.run_id and roles==ROLES and parameters=={'profile':self.profile},'fixed actual sensor caller input')
  from msdp579_sdk import verify
  supplement=verify(self.supplement,ref(self.capture.a.archive),run,self.profile)
  from batch_apps_contact_picker_coordinator import signer_inputs
  dist,jar,_=signer_inputs(self.signer_dist,self.capture.a.signer_jar)
  from sign_certificate_probe import sign
  result=dict(case=case,run_id=run,boot_id=self.boot_id,callers={})
  for role,c in supplement['callers'].items():
   signed=self.output/(role+'.hap');commands=[]
   def actual(argv,**options):
    self.capture.command(argv,'msdp579_sign_'+role+'_'+str(len(commands)),timeout=300,accepted_failure=not options.get('check',False));r=self.receipts[-1];commands.append(r)
    return SimpleNamespace(returncode=r['exit_code'],stdout=r['stdout'],stderr=r['stderr'])
   sign(SimpleNamespace(unsigned=Path(c['unsigned']['path']),output=signed,role=role,udid=self.udid,signer_dist=dist,jar=jar),configure=configure_profile('sensor'),command=actual)
   signing=signed.with_suffix('.signing.json');profile=save(self.output/(role+'-profile.json'),doc(ref(signing))['verified_profile'])
   verify_rows=[r for r in commands if 'verify-app' in r['argv'] or 'verify-profile' in r['argv']]
   result['callers'][role]=dict(c,signed=ref(signed),signing=ref(signing),verified_profile=profile,
    sign_commands=[self.ref_receipt(r) for r in commands if r not in verify_rows],verify_commands=[self.ref_receipt(r) for r in verify_rows])
  return result
 def close(self):
  errors=[];interrupt=None
  for f in reversed(self._cleanup):
   try:f()
   except BaseException as error:
    errors.append(repr(error))
    if not isinstance(error,Exception) and interrupt is None:interrupt=error
  self._closed=not errors
  save(self.output/'io.json',dict(scope='actual_original_Capture_view_NOT_new_Owner_IO',boot_id=self.boot_id,archive_sha256=self.archive_sha256,
   commands=self.receipts,qmp=[],closed=self._closed,held_transports={},errors=errors,original_capture=ref(self.capture.output/'capture.json') if (self.capture.output/'capture.json').is_file() else None))
  if interrupt is not None:raise interrupt
  if errors:
   from capability578_stage import UnsettledCapability
   raise UnsettledCapability('original Capture MSDP supplement cleanup uncertain: '+repr(errors))
