"""Finite actual-guest flows. The replayer independently derives verdicts."""
from pathlib import Path
import json,secrets
from owning_services579_contract import need,save,IDS,KEYS
from owning_services579_project import ROLES


def run(guest,callbacks,parameters):
 need(set(callbacks)==KEYS and parameters['case'] in ('local','dfs'),'fixed seven real callbacks')
 case=parameters['case'];run=parameters['run_id'];boot=guest.report['test_environment']['boot_id']
 report={'schema':'six-owning-services579-actual-business/v1','case':case,'run_id':run,'boot_id':boot,
  'archive_sha256':guest.report['archive_sha256'],'operations':[],'failures':[],
  'runtime_pass':False,'first_artifact_behavior_gate_passed':False}
 serial=0
 def call(name,*args):
  value=callbacks[name](*args);need(value['boot_id']==boot,'actual callback boot changed')
  report['operations'].append({'callback':name,'arguments':args,'result':value});return value
 def action(role,action,payload=None):
  nonlocal serial
  serial+=1;request=dict(run_id=run,request_id='services_'+str(serial),action=action,payload=payload or {})
  call('start',role,action,request);return call('collect',role,request['request_id'])
 def native(role,operation,argument='',account=100):return action(role,'native',dict(operation=operation,argument=argument,account=account))
 def event(result,name):
  rows=[r for r in result['journal'] if r['request_id']==result['request']['request_id'] and r['event']==name]
  need(len(rows)==1,'actual '+name+' missing/duplicate');return rows[0]
 def value(result,name):return json.loads(event(result,name)['value'])
 try:
  call('prepare_callers',case,run,ROLES)
  for role in ROLES:call('install',role);action(role,'identity');action(role,'declarations');call('input','observe-process',{'role':role})
  call('network','observe',{})
  if case=='local':
   for role in ROLES:
    native(role,'dump-invalid');native(role,'dump')
    for op in ('dsl-invalid','dsl-sync','dsl-async','dtm-invalid','dtm-sync','dtm-async'):
     native(role,op,parameters['udid'])
     # DATASL has no join/cancel API. A real process exit separates async
     # registry lifetimes; no destructor races a provider callback stack.
     if op=='dtm-async':call('input','force-stop',{'role':role});action(role,'identity')
    native(role,'gm-denied','{"groupType":256,"groupName":"services579_'+run+'"}')
   cred_params={'method':1,'credType':2,'keyFormat':3,'authorizedScope':3,'algorithmType':3,
    'subject':1,'deviceId':'services579_'+run,'credentialOwner':'services579_'+run,
    'proofType':1,'authorizedAppList':['org.ohos.qemu.services579.local.grant']}
   created=value(native('grant','cred-add',json.dumps(cred_params,separators=(',',':'))),'native-result')
   need(created['rc']==0 and created['data'],'actual credential creation failed')
   credential=created['data']
   native('grant','cred-query',credential);native('grant','cred-export',credential)
   for role in ('normal','denied'):native(role,'cred-query',credential);native(role,'cred-add',json.dumps(cred_params));action(role,'pin-denied')
   native('grant','cred-invalid');call('input','force-stop',{'role':'grant'});action('grant','identity')
   native('grant','cred-query',credential);native('grant','cred-delete',credential);native('grant','cred-query',credential)
   account=value(action('grant','account-create'),'account-created')['localId']
   action('grant','pin-open',{'account':account});action('grant','pin-info');action('grant','pin-enroll');action('grant','pin-info')
   action('grant','pin-wrong');action('grant','pin-auth')
   pending=action('grant','pin-cancel');call('start','grant','pin-cancel-now',dict(run_id=run,request_id='cancel_now',action='pin-cancel-now',payload={}))
   call('collect','grant','cancel_now');call('collect','grant',pending['request']['request_id'])
   action('grant','pin-close');call('input','force-stop',{'role':'grant'});action('grant','identity')
   action('grant','pin-open',{'account':account});action('grant','pin-info');action('grant','pin-auth');action('grant','pin-delete');action('grant','pin-info');action('grant','pin-close');action('grant','account-restore')
  # DFS uses run_paired() below. Local success never implies cross-device data.
 except BaseException as error:report['failures'].append({'type':type(error).__name__,'message':str(error)})
 finally:
  try:report['cleanup']=call('cleanup')
  except BaseException as error:
   report['cleanup_error']=repr(error);report['failures'].append({'cleanup':repr(error)})
 return report


def run_paired(source,sink,left,right,network_ids):
 """Actual endpoint file exchange; same guest loopback cannot satisfy it."""
 need(source is not sink and source.boot_id!=sink.boot_id and source.udid!=sink.udid and
  source.archive_sha256==sink.archive_sha256 and source.run_id==sink.run_id,'two original independent same-package held IOs')
 need(set(network_ids)=={'source','sink'} and all(isinstance(x,str) and x for x in network_ids.values()),'actual public DM remote network IDs')
 report={'schema':'six-owning-services579-actual-dfs-pair/v1','run_id':source.run_id,
  'archive_sha256':source.archive_sha256,'boots':{'source':source.boot_id,'sink':sink.boot_id},'operations':[],
  'failures':[],'runtime_pass':False,'first_artifact_behavior_gate_passed':False}
 serial=0
 def cb(endpoint,name,*args):
  value={'source':left,'sink':right}[endpoint][name](*args);report['operations'].append(dict(endpoint=endpoint,callback=name,arguments=args,result=value));return value
 def action(endpoint,role,action,payload=None):
  nonlocal serial
  serial+=1;request=dict(run_id=source.run_id,request_id='dfs_'+str(serial),action=action,payload=payload or {})
  cb(endpoint,'start',role,action,request);return cb(endpoint,'collect',role,request['request_id'])
 try:
  for e in ('source','sink'):
   cb(e,'prepare_callers','dfs',source.run_id,ROLES)
   for role in ROLES:cb(e,'install',role);action(e,role,'identity')
   serial+=1;permission_request=dict(run_id=source.run_id,request_id='dfs_'+str(serial),action='permissions',payload={})
   cb(e,'start','grant','permissions',permission_request);cb(e,'input','allow-permission',{'role':'grant'});cb(e,'collect','grant',permission_request['request_id'])
   for role in ('normal','denied'):action(e,role,'dfs-connect',{'network_id':network_ids[e]})
   action(e,'grant','dfs-connect',{'network_id':network_ids[e]})
  a='source_'+secrets.token_hex(32);b='sink_'+secrets.token_hex(32)
  action('source','grant','dfs-write',{'data':a});action('sink','grant','dfs-read')
  action('sink','grant','dfs-write',{'data':b});action('source','grant','dfs-read')
  for e in ('source','sink'):action(e,'grant','dfs-disconnect',{'network_id':network_ids[e]})
  for e in ('source','sink'):cb(e,'input','force-stop',{'role':'grant'});action(e,'grant','identity');action(e,'grant','dfs-connect',{'network_id':network_ids[e]})
  action('source','grant','dfs-read');action('source','grant','dfs-delete')
  for e in ('source','sink'):action(e,'grant','dfs-read');action(e,'grant','dfs-disconnect',{'network_id':network_ids[e]})
  # Mutation, cross-endpoint response and owned delete must be replayed from
  # the separate journals; these values are challenges, never response proofs.
  report['challenge']={'source':a,'sink':b}
 except BaseException as error:report['failures'].append({'type':type(error).__name__,'message':str(error)})
 finally:
  errors=[]
  for e in ('sink','source'):
   try:cb(e,'cleanup')
   except BaseException as error:errors.append(repr(error))
  report['cleanup_failures']=errors
  report['failures'] += [{'cleanup':error} for error in errors]
 return report
