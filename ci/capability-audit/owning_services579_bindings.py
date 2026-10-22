"""Seven actual callbacks on an already registered original OwnedIO."""
from pathlib import Path
import json,re,shlex,time
from owning_services579_contract import need,ref,raw,doc,save,ACTIONS,KEYS
from owning_services579_project import ROLES,bundle
from apps_providers579_bindings import bms_json,objects


def bind(io):
 need(io.owner.vm is io.guest and not io._closed,'same original held guest IO')
 io.owner.held_binding(io.guest)
 root=Path(io.output)/'owning-services579';root.mkdir(exist_ok=False)
 state={'case':None,'roles':{},'installed':[],'prefix':{},'requests':{},'cuts':[], 'serial':0,'owned_account':None,'cleaned':False,'cleanup':None}
 def shell(script,label,allow=False,timeout=60):
  row=io.shell(script,'services579_'+label,allow_failure=True,timeout=timeout)
  need(allow or row['exit_code']==0,'guest operation failed '+label);return row
 def process(role,label):
  from owning_services579_process import observe
  return observe(io,state['roles'][role]['uid'],bundle(state['case'],role),'services579_'+label,maps=True)
 def empty(observation):
  from owning_services579_process import replay
  def command(row):
   match=[r for r in io.receipts if io.ref_receipt(r)==row];need(len(match)==1,'actual scan receipt')
   return match[0].get('shell_stdout',match[0]['stdout'])
  return not replay(observation,command)['processes']
 def result(begin,**data):
  need(data.get('boot_id',io.boot_id)==io.boot_id,'callback returned another boot')
  value=dict(data);value.update(boot_id=io.boot_id,commands=[io.ref_receipt(r) for r in io.receipts[begin[0]:]],qmp_records=io.qmp_receipts[begin[1]:]);return value
 def pull(role):
  pat='/data/app/el2/100/base/'+bundle(state['case'],role)+'/files/services579-'+io.run_id+'-*.jsonl'
  listing=shell('for p in '+pat+'; do test -f "$p" && printf "%s\\n" "$p"; done','journal_list_'+role,True)
  files=[];rows=[]
  for remote in listing['stdout'].splitlines():
   need(re.fullmatch(pat.replace('*','[0-9]+').replace('.jsonl',r'\.jsonl'),remote),'actual fixed caller journal path')
   state['serial']+=1;local=root/('journal_'+role+'_'+str(state['serial'])+'.jsonl')
   io.receive(remote,local,'services579_journal_'+role);body=local.read_bytes();key=(role,remote)
   need(body.startswith(state['prefix'].get(key,b'')),'journal append-only prefix changed');state['prefix'][key]=body
   files.append(ref(local))
   for line in body.splitlines():
    row=json.loads(line);need(row['run_id']==io.run_id and row['role']==role and row['kind']==state['case'] and row['bundle']==bundle(state['case'],role),'foreign journal identity')
    rows.append(row)
    if row['event']=='accounts-after':state['owned_account']=None
    if row['event']=='account-created':
     account=json.loads(row['value']);need(account['localName']=='services579_'+io.run_id and account['localId']!=100,'only new run-owned secondary account')
     state['owned_account']=account['localId']
  restored=[r for r in rows if r['event']=='accounts-after']
  if restored:state['owned_account']=None
  return rows,files
 def start(role,action,request):
  need(role in state['installed'] and action in ACTIONS and set(request)=={'run_id','request_id','action','payload'} and request['run_id']==io.run_id and request['action']==action and re.fullmatch('[a-z0-9_-]{1,64}',request['request_id']),'fixed actual request')
  argv=['aa','start','-b',bundle(state['case'],role),'-a','EntryAbility','-m','entry','-u','100']
  for k in ('run_id','request_id','action'):argv+=['--ps',k,request[k]]
  argv+=['--ps','payload',json.dumps(request['payload'],separators=(',',':'))]
  row=shell(shlex.join(argv),'start_'+role+'_'+request['request_id']);need('start ability successfully' in row['stdout'].lower(),'AMS actual launch failed')
  state['requests'][(role,request['request_id'])]=request
  return {'started':io.ref_receipt(row)}
 def collect(role,request_id):
  request=state['requests'][(role,request_id)];deadline=time.monotonic()+75
  terminal={'pin-enroll':'pin-enrolled','pin-auth':'pin-auth-result','pin-wrong':'pin-auth-result','pin-delete':'pin-deleted'}.get(request['action'],'done')
  if request['action']=='pin-cancel':terminal='pin-auth-result' if (role,'cancel_now') in state['requests'] else 'pin-input-request'
  while True:
   rows,files=pull(role);selected=[r for r in rows if r['request_id']==request_id]
   if any(r['event'] in (terminal,'error','request-error','page-error') for r in selected):break
   need(time.monotonic()<deadline,'actual public API callback missing '+request['action']);time.sleep(.25)
  value={'journal_files':files,'journal':rows,'request':request}
  if request['action']=='native':value['process_after']=process(role,'native_maps_'+role)
  return value
 def prepare(case,run,roles):
  need(state['case'] is None and case in ('local','dfs') and roles==ROLES and run==io.run_id,'fixed source-bound preparation once')
  state['case']=case
  built=io.prepare_callers('owning_services579',case,run,roles,{'profile':'phone'})
  state['prepared']=built
  return dict(built,native_addon=io.owning_services579_native)
 def install(role):
  need(role in ROLES and role not in state['installed'],'finite once install')
  prepared=state['prepared']['callers'][role];remote='/data/local/tmp/services579_'+io.run_id+'_'+role+'.hap'
  before=shell('bm dump -a','before_install_'+role);need(bundle(state['case'],role) not in before['stdout'],'fixture already installed')
  io.send(prepared['signed']['path'],remote,'services579_send_'+role)
  row=shell(shlex.join(['bm','install','-r','-p',remote,'-u','100']),'install_'+role,timeout=600)
  need('success' in row['stdout'].lower(),'actual BMS install failed');state['installed'].append(role)
  dump=shell('bm dump -n '+bundle(state['case'],role)+' -u 100','bms_'+role);value=bms_json(dump['stdout']);app=value['applicationInfo'];uid=app['uid']
  need(type(uid) is int and uid>10000,'actual BMS application UID')
  paths=sorted({x['hapPath'] for x in objects(value) if x.get('hapPath')})
  need(len(paths)==1 and re.fullmatch(r'/data/app/[^\s;]+\.hap',paths[0]),'exact installed caller HAP')
  installed_hash=shell('sha256sum '+shlex.quote(paths[0]),'installed_hap_'+role)
  need(installed_hash['stdout'].split()[0]==prepared['signed']['sha256'],'actual installed HAP differs from signed fixture')
  state['roles'][role]={'uid':uid,'bms':io.ref_receipt(dump),'hap':io.ref_receipt(installed_hash),'remote':remote}
  return dict(state['roles'][role])
 def input(action,payload):
  role=payload.get('role','grant')
  if action=='force-stop':
   before=process(role,'prestop_'+role);row=shell('aa force-stop '+bundle(state['case'],role),'stop_'+role)
   deadline=time.monotonic()+15
   while True:
    after=process(role,'poststop_'+role)
    if empty(after):break
    need(time.monotonic()<deadline,'caller UID processes survived force stop');time.sleep(.2)
   return dict(before=before,stop=io.ref_receipt(row),after=after)
  if action=='observe-process':return {'process':process(role,'live_'+role)}
  if action=='allow-permission':
   from guest_ui import select_node,NodeNotReady,LayoutNotReady
   deadline=time.monotonic()+30
   while True:
    rows,files=pull(role)
    if any(r['event']=='permission-result' for r in rows):return dict(journal_files=files)
    try:
     layout,path=io.ui.layout(label='services579_permission');select_node(layout,'com.ohos.permissionmanager',text=io.environment['permission_allow_text'])
     label='Services579 '+state['case']+' '+role+' '+io.run_id[:8]
     need(label in json.dumps(layout,ensure_ascii=False),'not this actual caller named permission request')
     clicked=io.ui.click('com.ohos.permissionmanager',text=io.environment['permission_allow_text'],label='services579_allow')
     return dict(layout=ref(Path(path)),selected=clicked)
    except (NodeNotReady,LayoutNotReady):
     need(time.monotonic()<deadline,'owned actual permission UI missing');time.sleep(.25)
  raise ValueError('unlisted source input action')
 def network(action,parameters):
  need(action=='observe' and parameters=={},'no synthetic network/provider fixture')
  profile=doc(io.owning_services579_native['build'])['installed_runtime_profile']['profile']
  dsos={}
  for name in ('libdata_transit_mgr.z.so','libdslm_sdk.z.so','libhidumper_client.z.so','libdeviceauth_sdk.z.so'):
   entry=profile['dsos'][name];remote='/system'+entry['image_member']
   need(entry['image_member'].startswith('/lib') and remote.endswith('/'+name),'fixed actual SDK DSO member')
   dsos[name]=io.ref_receipt(shell('sha256sum '+shlex.quote(remote),'dso_'+str(len(dsos))))
  return {'dsos':dsos,'boot':io.ref_receipt(shell('cat /proc/sys/kernel/random/boot_id','boot')),
   'services':io.ref_receipt(shell('hidumper -ls','service_list')),
   'config':io.ref_receipt(shell('cat /system/etc/advertising/ads_framework/ad_service_config.json','ads_config'))}
 def cleanup():
  if state['cleaned']:return state['cleanup']
  errors=[];recovery=None;dfs_cleanup=None
  if state['case']=='local' and 'grant' in state['installed']:
   try:
    request=dict(run_id=io.run_id,request_id='cleanup_account',action='account-recover',payload={})
    start('grant','account-recover',request);recovery=collect('grant','cleanup_account')
    need(any(r['event']=='accounts-recovered' and r['request_id']=='cleanup_account' for r in recovery['journal']),'actual owned account recovery failed')
   except BaseException as error:errors.append(repr(error))
  if state['case']=='dfs' and 'grant' in state['installed']:
   try:
    rows,_=pull('grant');connected=[json.loads(r['value'])['network_id'] for r in rows if r['event']=='dfs-connected']
    request=dict(run_id=io.run_id,request_id='cleanup_dfs',action='dfs-cleanup',payload={'network_id':connected[-1]} if connected else {})
    start('grant','dfs-cleanup',request);dfs_cleanup=collect('grant','cleanup_dfs')
    need(any(r['event']=='dfs-cleanup-owned' and r['request_id']=='cleanup_dfs' for r in dfs_cleanup['journal']),'actual owned DFS cleanup failed')
   except BaseException as error:errors.append(repr(error))
  for role in reversed(state['installed']):
   try:
    shell('aa force-stop '+bundle(state['case'],role),'cleanup_stop_'+role,True)
    state['serial']+=1
    # Pull before uninstall. Surviving callbacks are evidence, never dropped.
    pull(role)
    gone=process(role,'cleanup_uid_'+role)
    need(empty(gone),'remaining caller UID process')
    row=shell('bm uninstall -n '+bundle(state['case'],role)+' -u 100','cleanup_uninstall_'+role)
    need('success' in row['stdout'].lower(),'actual uninstall failed')
    shell('rm -f '+shlex.quote(state['roles'][role]['remote']),'cleanup_remote_'+role)
   except BaseException as error:errors.append(repr(error))
  after=shell('bm dump -a','cleanup_bms');need(all(bundle(state['case'],r) not in after['stdout'] for r in state['installed']),'fixture BMS survived cleanup')
  final_uids={role:process(role,'final_uid_'+role) for role in state['installed']}
  need(all(empty(value) for value in final_uids.values()),'caller UID survived uninstall')
  ams=shell('aa dump -a -u 100','cleanup_ams');need(all(bundle(state['case'],r) not in ams['stdout'] for r in state['installed']),'caller AMS record survived')
  state['cleanup']={'failures':errors,'bms_after':io.ref_receipt(after),'ams_after':io.ref_receipt(ams),'uids_after':final_uids,'account_recovery':recovery,'dfs_cleanup':dfs_cleanup};state['cleaned']=not errors
  need(not errors,'unsettled actual service cleanup '+repr(errors));return state['cleanup']
 base={'prepare_callers':prepare,'install':install,'start':start,'input':input,'collect':collect,'network':network,'cleanup':cleanup}
 def wrap(name):
  def call(*args):
   before=(len(io.receipts),len(io.qmp_receipts));started=time.monotonic_ns();error=None;value=None
   try:value=base[name](*args);return result(before,**value)
   except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)};raise
   finally:
    cut=save(root/('cut_'+str(len(state['cuts']))+'.json'),dict(schema='owning-services579-actual-callback/v1',callback=name,arguments=args,
     started_ns=started,finished_ns=time.monotonic_ns(),boot_id=io.boot_id,archive_sha256=io.archive_sha256,
     run_id=io.run_id,result=value,error=error,commands=[io.ref_receipt(r) for r in io.receipts[before[0]:]],qmp_records=io.qmp_receipts[before[1]:]))
    state['cuts'].append(cut)
  return call
 callbacks={k:wrap(k) for k in KEYS}
 io.register_cleanup(callbacks['cleanup'])
 callbacks['start'].owning_services579_state=state
 return callbacks
