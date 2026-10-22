"""Whole original A26 reconstruction from SDK/HAP/IPC/data callbacks.

A nonzero result or absent callback remains a failure/unresolved scope. Neither
six legacy false declarations nor another family status is a closure oracle.
"""
from owning_services579_contract import need,raw,doc,loads,NAMES
from owning_services579_records import Evidence


def dfs_peer_identity(payload,archive_sha,source_boot,sink_boot):
 value=doc(payload);need(set(value)=={'locals','source_trust','sink_trust'},'fixed original trusted-window input')
 local=value['locals'];need(set(local)=={'source','sink'} and local['source']['networkId']!=local['sink']['networkId'],'two actual public local device IDs')
 actual={}
 for endpoint,other,boot in (('source','sink',source_boot),('sink','source',sink_boot)):
  record=value[endpoint+'_trust'];need(record['archive_sha256']==archive_sha and record['endpoints'][endpoint]['boot_id']==boot,'actual original paired callback boot')
  rows=[loads(line) for line in raw(record['journal']).splitlines()];values=[loads(r['value']) for r in rows if r['event']=='actual-trusted-list']
  need(values,'actual trusted-device journal callback missing')
  wanted=local[other]['networkId'];matched=[d for d in values[-1] if d['networkId']==wanted]
  need(len(matched)==1,'independent peer not actually trusted before DFS')
  actual[endpoint]=wanted
 return actual


def local_replay(e):
 result={};failures=[]
 def check(service,body):
  try:result[service]=dict(complete=True,raw=body())
  except (ValueError,KeyError,IndexError,TypeError) as error:
   result[service]=dict(complete=False,error=type(error).__name__+': '+str(error));failures.append(dict(service=service,error=str(error)))
 def dump():
  for role in ('normal','grant','denied'):
   for op in ('dump','dump-invalid'):
    v=e.native(role,op)[0];need(v['output_eof'] is True and v['output_errno']==0,'actual synchronous dump full FD read')
  positive=e.native('grant','dump');need(len(positive)==1 and positive[0]['rc']==0 and positive[0]['data'].strip(),'actual permitted dump output')
  for role in ('normal','denied'):
   v=e.native(role,'dump');need(len(v)==1 and v[0]['rc']!=0 and 'no dump permission' in v[0]['data'],'real DUMP permission denial')
  for role in ('normal','grant','denied'):need(e.native(role,'dump-invalid')[0]['rc']!=0,'actual empty-argument rejection')
  return positive
 def dsl():
  values={}
  for role in ('normal','grant','denied'):
   need(e.native(role,'dsl-invalid')[0]['rc']==1,'DSL null-parameter error from public SDK')
   sync=e.native(role,'dsl-sync')[0];asyn=e.native(role,'dsl-async')[0]
   need(sync['rc']==0 and sync['data']=='0' and 0<=sync['value']<=5,'actual self DSL sync classification')
   need(asyn['rc']==0 and len(asyn['callbacks'])==1 and asyn['callbacks'][0]['rc']==0 and asyn['callbacks'][0]['kind']=='dsl' and asyn['callbacks'][0]['level']==sync['value'] and
    asyn['callbacks'][0]['identity_hex']==sync['argument'].encode().hex(),'actual DSL asynchronous classification/identity')
   values[role]=dict(sync=sync,async_result=asyn)
  return values
 def dtm():
  values={}
  for role in ('normal','grant','denied'):
   need(e.native(role,'dtm-invalid')[0]['rc']==105,'DTM null-parameter error')
   sync=e.native(role,'dtm-sync')[0];asyn=e.native(role,'dtm-async')[0]
   dsl_value=e.native(role,'dsl-sync')[0]['value'];expected={1:1,2:2,3:3,4:4,5:4}.get(dsl_value,0)
   need(sync['rc']==0 and sync['data']=='0' and sync['value']==expected,'actual DTM/DSL classification mapping')
   need(asyn['rc']==0 and len(asyn['callbacks'])==1 and asyn['callbacks'][0]['rc']==0 and asyn['callbacks'][0]['kind']=='dtm' and asyn['callbacks'][0]['level']==expected and
    asyn['callbacks'][0]['identity_hex']==sync['argument'].encode().hex(),'actual asynchronous DTM callback')
   values[role]=dict(sync=sync,async_result=asyn)
  return values
 def auth():
  for role in ('normal','grant','denied'):need(e.native(role,'gm-denied')[0]['rc']==12307,'GM is native-token restricted, not an ordinary HAP permission')
  created=e.native('grant','cred-add');need(len(created)==1 and created[0]['rc']==0 and created[0]['data'],'real HUKS-backed credential creation')
  credential=created[0]['data'];queries=e.native('grant','cred-query')
  need(len(queries)==3 and all(v['argument']==credential for v in queries) and queries[0]['rc']==queries[1]['rc']==0 and
   queries[0]['data']==queries[1]['data'] and queries[2]['rc']!=0,'actual credential persisted across real caller death and removed')
  need(e.native('grant','cred-export')[0]['rc']==0 and e.native('grant','cred-export')[0]['data'],'actual public credential material export')
  deleted=e.native('grant','cred-delete');need(len(deleted)==1 and deleted[0]['rc']==0 and deleted[0]['argument']==credential,'owned credential deletion')
  need(e.native('grant','cred-invalid')[0]['rc']!=0,'public invalid credential parameter')
  for role in ('normal','denied'):
   for operation in ('cred-add','cred-query'):need(e.native(role,operation)[0]['rc']==12307,'actual credential manager permission boundary')
  need(queries[1]['pid']!=queries[0]['pid'],'credential reopen was not an actual new process')
  return dict(created=created[0],queries=queries,deleted=deleted[0])
 def pin():
  before=loads(e.one('grant','account-create','accounts-before')['value']);created=loads(e.one('grant','account-create','account-created')['value']);account=created['localId']
  need(created['localName']=='services579_'+e.run and account not in [x['localId'] for x in before] and account!=100,'new disposable actual account')
  for role in ('normal','denied'):
   denied=e.one(role,'pin-denied','error');need(denied['code']==(202 if role=='normal' else 201),'documented PIN constructor/ACL denial')
  info=e.actions('grant','pin-info');need(len(info)==4,'exact PIN before/enrolled/restart/deleted observations')
  states=[loads(e.one('grant','pin-info','pin-info',i)['value']) for i in range(4)]
  need(states[0]==[] and len(states[1])==len(states[2])==1 and states[3]==[],'real credential lifecycle')
  need(e.one('grant','pin-enroll','pin-enrolled')['code']==0,'actual selected PIN driver enrollment failed')
  wrong=e.one('grant','pin-wrong','pin-auth-result');need(wrong['code']==1 and not loads(wrong['value'])['token'],'actual wrong PIN must fail without token')
  authenticated=[e.one('grant','pin-auth','pin-auth-result',i) for i in range(2)]
  for value in authenticated:need(value['code']==0 and loads(value['value'])['token'],'real successful PIN token callback')
  need(authenticated[0]['pid']!=authenticated[1]['pid'] and loads(authenticated[0]['value'])['challenge']!=loads(authenticated[1]['value'])['challenge'],'PIN persistence/new process/fresh auth challenge')
  cancelled=e.one('grant','pin-cancel','pin-auth-result');need(cancelled['code']==3 and not loads(cancelled['value'])['token'],'actual cancellation result')
  need(e.one('grant','pin-delete','pin-deleted')['code']==0,'actual authenticated credential removal')
  after=loads(e.one('grant','account-restore','accounts-after')['value']);need(sorted(x['localId'] for x in after)==sorted(x['localId'] for x in before),'actual OS account restoration')
  return dict(account=account,states=states,wrong=wrong,auth=authenticated,cancel=cancelled,after=after)
 for name,body in (('HiDumper',dump),('DeviceSecurityLevel',dsl),('DataTransitManager',dtm),('DeviceAuth',auth),('PinAuth',pin)):check(name,body)
 declarations={}
 for role in ('normal','grant','denied'):
  row=loads(e.one(role,'declarations','declarations')['value']);need(set(row)==set(NAMES) and all(type(x) is bool for x in row.values()),'actual exact six declaration observations')
  declarations[role]=row
 # Reconcile the actual package's guarded source-derived device contract;
 # this label check never replaces any of the five service SDK raw or DFS.
 policy=e.device_profile['qemu_adaptations'];retired=policy['retired_documented_syscap_names']
 owners={'SystemCapability.FileManagement.File.DistributedFile':'filemanagement:dfs_service',
  'SystemCapability.HiviewDFX.HiDumper':'hiviewdfx:hidumper',
  'SystemCapability.Security.DataTransitManager':'security:dataclassification',
  'SystemCapability.Security.DeviceAuth':'security:device_auth',
  'SystemCapability.Security.DeviceSecurityLevel':'security:device_security_level',
  'SystemCapability.UserIAM.UserAuth.PinAuth':'useriam:pin_auth'}
 need(set(retired)==set(owners) and all(not x for role in declarations.values() for x in role.values()),
  'actual package retirement and three actual declared label views disagree')
 for cap,owner in owners.items():
  item=retired[cap];need(item['owning_part']==owner and item['registry_status']=='abandoned' and
   item['sdk_device_requirement'] is False and item['arkts_api_reference_count']==0 and
   item['behavior_validated'] is False and item['registry']=='developtools/syscap_codec/include/codec_config/syscap_define.h' and
   len(item['registry_sha256'])==64, 'actual source-derived narrow retirement contract differs')
 return {'services':result,'failures':failures,'legacy_declarations':declarations,
  'actual_package_device_contract':e.retained['device_profile'],'retired_labels_are_not_service_behavior':True}


def dfs_replay(source,sink,paired_proof):
 need(source.run==sink.run and source.env['boot_id']!=sink.env['boot_id'] and source.capture['udid'].lower()!=sink.capture['udid'].lower(),'independent actual DFS endpoints')
 source_identity=[loads(r['value']) for r in source.events.values() if r['event']=='self-identity' and r['role']=='grant'][0]
 sink_identity=[loads(r['value']) for r in sink.events.values() if r['event']=='self-identity' and r['role']=='grant'][0]
 need(source_identity==sink_identity,'actual same-app DFS BMS/signer namespace across per-UDID signing')
 report=source.result;need(report==sink.result and report['boots']=={'source':source.env['boot_id'],'sink':sink.env['boot_id']},'shared actual paired flow')
 peer=dfs_peer_identity(source.retained['attempt']['paired_business'],source.archive['sha256'],source.env['boot_id'],sink.env['boot_id'])
 # The original full paired semantic action must also pass against THESE two
 # owning boots and original PIN/UI/raw captures. No paired status shortcut.
 need(paired_proof['semantic_replay_complete'] is True and not paired_proof['replay_errors'] and not paired_proof['retained_failures'] and
  set(paired_proof['checks']['original_resources']['distinct_boots'])=={source.env['boot_id'],sink.env['boot_id']},'complete original paired raw replay')
 for endpoint,e in (('source',source),('sink',sink)):
  for role in ('normal','denied'):need(e.one(role,'dfs-connect','error')['code']==201,'actual DFS permission denial')
  permission=loads(e.one('grant','permissions','permission-result')['value']);need(permission['permissions']==['ohos.permission.DISTRIBUTED_DATASYNC'] and permission['authResults']==[0],'actual user permission grant')
  connects=e.actions('grant','dfs-connect');disconnects=e.actions('grant','dfs-disconnect')
  need(len(connects)==len(disconnects)==2 and all(req['payload']=={'network_id':peer[endpoint]} for req,_ in connects+disconnects),'actual public remote connect/reconnect/disconnect')
  for i in range(2):need(e.one('grant','dfs-connect','dfs-connected',i)['code']==0 and e.one('grant','dfs-disconnect','dfs-disconnected',i)['code']==0,'actual DFS lifecycle success')
 a=report['challenge']['source'];b=report['challenge']['sink'];need(a.startswith('source_') and b.startswith('sink_') and a!=b,'two fresh nonces')
 written_a=loads(source.one('grant','dfs-write','dfs-written')['value']);written_b=loads(sink.one('grant','dfs-write','dfs-written')['value'])
 need(written_a['data']==a and written_b['data']==b,'actual caller writes')
 sink_read=loads(sink.one('grant','dfs-read','dfs-read',0)['value']);source_read=loads(source.one('grant','dfs-read','dfs-read',0)['value']);restart=loads(source.one('grant','dfs-read','dfs-read',1)['value'])
 need(sink_read['hex']==a.encode().hex() and source_read['hex']==restart['hex']==b.encode().hex(),'actual independent remote data roundtrip and persistence')
 for e in (source,sink):
  failed=[rows for _,rows in e.actions('grant','dfs-read') if any(r['event']=='error' for r in rows)]
  need(len(failed)==1 and len([r for r in failed[0] if r['event']=='error' and r['code']==13900002])==1,'owned delete propagated with exact ENOENT')
 return dict(complete=True,source_nonce=a,sink_nonce=b,network_ids=peer,scope='public connect/file IO/permission/disconnect/caller restart/owned delete on independent original endpoints')
