"""Real original Ads business body plus raw cuts, and pure boundary replay.

The two canonical copies are byte-identical @677 source predecessors under NEW
module names. No module cache/filename is forged and no generic hook is bypassed
by rebinding a cached canonical name. Only their fixed 'ads' path is called.
"""
from pathlib import Path
import copy,json,time
from owning_services579_contract import need,ref,raw,doc,loads,save,KEYS,check_ref
from owning_services579_records import normalized,body


def run_ads(io):
 import ads579_canonical_runtime as runtime
 import ads579_canonical_bindings as binding
 from system_services578_project import ROLES
 need(io.owner.vm is io.guest and not io._closed and ROLES['ads']==('normal',),'actual original held Ads IO')
 io.owner.held_binding(io.guest);callbacks=binding.bind(io);cuts=[];identity={}
 root=Path(io.output)/'ads579-boundary';root.mkdir(exist_ok=False)
 def state(label):
  return {'config':io.ref_receipt(io.shell('cat /system/etc/advertising/ads_framework/ad_service_config.json','ads579_'+label+'_config')),
   'bms':io.ref_receipt(io.shell('bm dump -a','ads579_'+label+'_bms'))}
 before=state('before')
 def processes(label):
  need(identity,'actual installed UID required')
  from owning_services579_process import observe
  return observe(io,identity['uid'],identity['bundle'],'ads579_'+label,maps=True)
 def empty(observation):
  from owning_services579_process import replay
  def command(row):
   matches=[r for r in io.receipts if io.ref_receipt(r)==row];need(len(matches)==1,'actual scan receipt')
   return matches[0].get('shell_stdout',matches[0]['stdout'])
  return not replay(observation,command)['processes']
 def wrap(name):
  def actual(*args):
   begin=(len(io.receipts),len(io.qmp_receipts));value=None;error=None;extra={};exit_error=None;start=time.monotonic_ns()
   try:
    if name=='input' and args[0]=='force-stop':extra['process_before']=processes('before_stop')
    if name=='cleanup' and identity:
     try:
      request={'run_id':io.run_id,'request_id':'ads_exit579','action':'exit'}
      launched=callbacks['start']('normal','exit',request);deadline=time.monotonic()+20
      while True:
       observed=callbacks['collect']('normal','ads_exit579')
       events=[loads(line) for line in raw(observed['journal']).splitlines()]
       if any(r['request_id']=='ads_exit579' and r['event']=='ability-destroy' for r in events):break
       need(time.monotonic()<deadline,'actual public Ads caller terminateSelf did not destroy ability');time.sleep(.2)
      extra['public_exit']=dict(request=request,start=launched,collect=observed,
       ams_after=io.ref_receipt(io.shell('aa dump -a -u 100','ads579_public_exit_ams')))
     except BaseException as failure:
      exit_error=failure;extra['public_exit_error']={'type':type(failure).__name__,'message':str(failure)}
    value=callbacks[name](*args)
    if name=='prepare_callers':
     value=dict(value,commands=[io.ref_receipt(r) for r in io.receipts[begin[0]:]],qmp_records=io.qmp_receipts[begin[1]:])
    if name=='install':identity.update(doc(value['identity']))
    if name=='input' and args[0]=='force-stop':
     extra['process_after']=processes('after_stop')
     need(empty(extra['process_after']),'Ads process survived actual force-stop')
    if name=='cleanup':
     extra['uid_after']=processes('cleanup_uid');extra['ams_after']=io.ref_receipt(io.shell('aa dump -a -u 100','ads579_cleanup_ams'));extra['bms_after']=io.ref_receipt(io.shell('bm dump -a','ads579_cleanup_bms'))
     need(empty(extra['uid_after']),'Ads UID cleanup unsettled')
     if exit_error is not None:raise exit_error
    return value
   except BaseException as exc:error=dict(type=type(exc).__name__,message=str(exc));raise
   finally:
    cuts.append(save(root/('cut_'+str(len(cuts))+'.json'),dict(callback=name,arguments=args,result=value,error=error,extra=extra,
     started_ns=start,finished_ns=time.monotonic_ns(),boot_id=io.boot_id,
     commands=[io.ref_receipt(r) for r in io.receipts[begin[0]:]],qmp_records=io.qmp_receipts[begin[1]:])))
  return actual
 seven={k:wrap(k) for k in KEYS}
 result=runtime.run(io.guest,seven,dict(case='ads',run_id=io.run_id,udid=io.udid,primary_user=100))
 after=state('after');result_ref=save(root/'producer.json',result)
 capture=save(root/'capture.json',dict(schema='ads579-original-actual-cuts/v1',run_id=io.run_id,boot_id=io.boot_id,
  archive_sha256=io.archive_sha256,udid=io.udid,before=before,after=after,cuts=cuts,result=result_ref))
 attempt=dict(result=result_ref,capture=capture);io.ads579_boundary_attempt=attempt
 if result['failures']:raise RuntimeError('actual Ads framework failed; raw retained at '+str(result_ref['path']))
 return attempt


def seal_ads(io,attempt):
 need(io._closed and doc(ref(Path(io.output)/'io.json'))['closed'] is True,'actual original Ads IO closed')
 return save(Path(io.output)/'ads579-retained.json',dict(schema='ads579-closed-original-IO/v1',attempt=attempt,
  io=ref(Path(io.output)/'io.json'),boot=save(Path(io.output)/'ads579-caseboot.json',copy.deepcopy(io.guest.report)),
  build_inputs=ref(io.guest.directory/'build-inputs.json'),package_manifest=ref(io.guest.directory/'manifest.json')))


def replay_ads(retained,archive):
 from system_services578_project import bundle
 from ads579_canonical_runtime import prepared
 r=doc(retained);need(r['schema']=='ads579-closed-original-IO/v1','fixed Ads retained source')
 boot=doc(r['boot']);env=boot['test_environment'];io=doc(r['io']);capture=doc(r['attempt']['capture']);producer=doc(r['attempt']['result'])
 need(boot['archive_sha256']==io['archive_sha256']==capture['archive_sha256']==archive['sha256'] and
  env['boot_id']==io['boot_id']==capture['boot_id']==producer['boot_id'] and env['device_type']=='phone' and
  boot['purpose']=='acceptance' and env['external_keepalive'] is False and io['closed'] is True and not producer['failures'],'actual Ads attempt/closed IO/boot/producer')
 need(boot['initial_package_file_sha256']['build-inputs.json']==r['build_inputs']['sha256'] and boot['initial_package_file_sha256']['manifest.json']==r['package_manifest']['sha256'],'actual initial package metadata')
 check_ref(archive);doc(r['build_inputs']);doc(r['package_manifest'])
 rows=io['commands'];commands=[normalized(x) for x in rows];texts=[body(x) for x in rows]
 def command(record):
  need(record in commands,'Ads receipt not in closed actual IO');text,code=texts[commands.index(record)];need(code==0,'actual Ads command failed');return text
 cuts=[doc(x) for x in capture['cuts']]
 need(all(c['error'] is None and c['boot_id']==env['boot_id'] and c['started_ns']<=c['finished_ns'] for c in cuts),'Ads callback failure')
 for cut in cuts:
  for c in cut['commands']:command(c)
  for q in cut['qmp_records']:
   need(q in io['qmp'],'unbound original QMP')
   from apps_ui578_contract import qmp_wire
   qmp_wire(q)
 original=[x for x in producer['records'] if x['callback']=='prepare_callers'];need(len(original)==1,'one actual Ads prepared caller')
 spec=original[0]['result'];callers=prepared(spec,'ads',capture['run_id'],None,env['boot_id'],capture['udid'])
 for role,caller in callers.items():
  for key in ('build_commands','sign_commands','verify_commands'):
   for c in caller[key]:command(c)
 installed=[c for c in cuts if c['callback']=='install'];need(len(installed)==1,'one original Ads installed caller')
 identity=doc(installed[0]['result']['identity']);need(identity['bundle']==bundle('ads','normal') and identity['fingerprint']==callers['normal']['identity']['fingerprint'],'actual Ads app/signer/UID')
 events={};requests=[]
 public_exit=[c['extra']['public_exit'] for c in cuts if c['callback']=='cleanup' and 'public_exit' in c['extra']]
 need(len(public_exit)==1,'actual ordinary public terminateSelf boundary required')
 exit_record=public_exit[0]
 need(exit_record['request']=={'run_id':capture['run_id'],'request_id':'ads_exit579','action':'exit'},'actual fixed public exit request')
 need(identity['bundle'] not in command(exit_record['ams_after']),'public Ads caller ability survived terminateSelf')
 for cut in cuts:
  if cut['callback']=='start':requests.append(cut['arguments'][2])
  journals=[cut['result']['journal']] if cut['callback']=='collect' else ([cut['extra']['public_exit']['collect']['journal']] if cut['callback']=='cleanup' else [])
  for journal in journals:
   for line in raw(journal).splitlines():
    e=loads(line);need(e['run_id']==capture['run_id'] and e['kind']=='ads' and e['role']=='normal' and e['bundle']==identity['bundle'] and e['uid']==identity['uid'],'actual Ads journal identity')
    key=(e['pid'],e['seq']);need(key not in events or events[key]==e,'Ads append-only journal changed');events[key]=e
 def one(action,event,code,index=0):
  selected=[q for q in requests if q['action']==action];need(len(selected)>index,'actual Ads action '+action)
  q=selected[index];values=[e for e in events.values() if e['request_id']==q['request_id']]
  need(any(e['event']=='request' and e['action']==action for e in values),'actual Ads typed request')
  hits=[e for e in values if e['event']==event and e['code']==code];need(len(hits)==1,'Ads raw semantic '+action+'/'+event)
  need(not any(e['event']=='ad-success' for e in values),'unexpected complete provider: reopen positive behavior')
  return hits[0]
 for pid in {k[0] for k in events}:
  actual=sorted((r for k,r in events.items() if k[0]==pid),key=lambda r:r['seq'])
  need([r['seq'] for r in actual]==list(range(len(actual))),'actual Ads lifecycle journal truncated')
  need(any(r['event']=='foreground' for r in actual),'actual Ads caller foreground callback absent')
 need(not any(r['event']=='ad-success' for r in events.values()),'unclaimed real provider success must reopen Ads positive scope')
 exited=[r for r in events.values() if r['request_id']=='ads_exit579']
 actual_requests=[loads(r['value']) for r in exited if r['event']=='request']
 need(len(actual_requests)==1 and all(actual_requests[0][k]==v for k,v in exit_record['request'].items()),'actual public exit Want request differs')
 need(sum(r['event']=='exit-request' and r['code']==0 for r in exited)==1 and
  sum(r['event']=='ability-destroy' for r in exited)==1,'actual public Ads exit/destroy raw callback')
 probe=one('probe','syscap',0);need(loads(probe['value']) is True,'actual advertised Ads framework syscap')
 for action in ('invalid','invalid-display'):one(action,'error',401)
 loaded=one('load','ad-failure',12);one('multi','ad-failure',12);restart=one('load','ad-failure',12,1)
 need(loaded['pid']!=restart['pid'],'actual Ads caller restart not observed')
 stops=[c for c in cuts if c['callback']=='input' and c['arguments'][0]=='force-stop']
 from owning_services579_process import replay
 need(len(stops)==1 and not replay(stops[0]['extra']['process_after'],command)['processes'],'actual Ads UID death')
 for state in (capture['before'],capture['after']):
  config=loads(command(state['config']));bms=command(state['bms'])
  need(config.get('providerBundleName')==['com.samples.AdsServiceDemo'] and not config.get('providerApiAbilityName') and 'com.samples.AdsServiceDemo' not in bms,'actual product has a different/full provider: unsupported claim invalid')
 need(command(capture['before']['config'])==command(capture['after']['config']),'actual configuration changed')
 clean=[c for c in cuts if c['callback']=='cleanup'];need(len(clean)==1 and not clean[0]['result'].get('failures'),'original Ads cleanup')
 need(not replay(clean[0]['extra']['uid_after'],command)['processes'] and identity['bundle'] not in command(clean[0]['extra']['ams_after']) and identity['bundle'] not in command(clean[0]['extra']['bms_after']),'actual Ads UID/AMS/BMS cleanup')
 need(all(x['reaped'] is True and type(x['exit_code']) is int for x in io['held_transports'].values()),'actual Ads transports not reaped')
 return dict(supported_framework_complete=True,positive_load_render_interaction_supported=False,
  status='raw_framework_boundary_complete_positive_provider_not_claimed',boot_id=env['boot_id'],run_id=capture['run_id'],
  raw_provider_config=capture['after']['config'],raw_bms=capture['after']['bms'],runtime_pass=False,
  first_artifact_behavior_gate_passed=False)
