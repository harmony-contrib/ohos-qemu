"""Pure physical raw replay. API return/error is never an inference provider."""
from pathlib import Path
import json,re,struct,zipfile
from msdp579_contract import need,ref,raw,doc,save,CAPS,POSITIVE_SCOPES
from msdp579_project import ROLES,bundle,source_files,module_fields,configure_profile
from msdp579_process import replay as replay_process

def norm(r):
 v={k:r[k] for k in ('argv','exit_code','boot_id','timed_out')};v.update(stdout=r['stdout_ref'],stderr=r['stderr_ref'])
 if 'shell_stdout' in r:v.update(shell_stdout=r['shell_stdout_ref'],shell_exit_code=r['shell_exit_code'])
 return v

def body(r):
 need(type(r['exit_code'])is int and r['timed_out'] is False,'actual complete command status')
 out=raw(r['stdout_ref']).decode();err=raw(r['stderr_ref']).decode();need(out==r['stdout'] and err==r['stderr'] and raw(r['log'])==(out+err).encode(),'actual two streams/log changed')
 if len(r['argv'])>=5 and r['argv'][3]=='shell':
  from guest_ui import command_exit
  markers=re.findall(r'__(?:CAP578|LIVE_GUEST|UITEST)_EXIT_[a-f0-9]{32}__=',r['argv'][4]);need(len(markers)==1,'one exact actual transport marker')
  value,code=command_exit(out.replace('\r','') if 'LIVE_GUEST' in markers[0] else out,markers[0])
  if 'shell_stdout' in r:need(value==r['shell_stdout']==raw(r['shell_stdout_ref']).decode() and code==r['shell_exit_code'],'actual shell body/status differs')
  return value,code
 return out,r['exit_code']

class Evidence:
 def __init__(self,*,flow,io,boot,archive):
  self.flow=doc(flow);self.io=doc(io);self.boot=doc(boot);self.archive=archive;raw(archive)
  self.env=self.boot['test_environment'];self.case=self.flow['case'];self.run=self.flow['run_id']
  need(self.boot['purpose']=='acceptance' and self.env['external_keepalive'] is False and self.env['device_type'] in ('phone','2in1') and
   self.boot['archive_sha256']==self.flow['archive_sha256']==self.io['archive_sha256']==archive['sha256'] and self.env['boot_id']==self.flow['boot_id']==self.io['boot_id'] and
   self.io['closed'] is True and not self.flow['failures'] and self.flow['cleanup'] is not None and not self.flow['cleanup']['errors'] and not any(a['errors'] for a in self.flow['cleanup_attempts']),'actual new-image flow/closed transport/cleanup failed')
  self.commands=self.io['commands'];self.norm=[norm(r) for r in self.commands];self.parts=[body(r) for r in self.commands]
  need(all(r['boot_id']==self.env['boot_id'] for r in self.commands),'foreign command boot')
  self.events={};self.prepared=self.flow['prepared'];self.identities={}
  need(self.prepared['boot_id']==self.env['boot_id'] and self.prepared['run_id']==self.run and set(self.prepared['callers'])==set(ROLES),'three actual signed callers')
  self.prepare()
  for cut in self.flow['actions']:
   need(cut['error'] is None and 0<cut['started_ns']<=cut['finished_ns'],'actual source operation missing/failed')
   for r in cut['commands']:self.command(r)
   for q in cut['qmp']:self.qmp(q)
   role=cut['role'];q=cut['request'];rows=[]
   for f in cut['raw']:rows.extend(json.loads(line) for line in raw(f).splitlines())
   for r in rows:
    need(r['run_id']==self.run and r['kind']==self.case and r['role']==role and r['bundle']==bundle(self.case,role) and r['uid']==self.identities[role]['uid'] and type(r['pid'])is int and r['pid']>0 and int(r['boot_ns'])>0,'actual journal nonce/UID/process/clock')
    key=(role,r['pid'],r['seq']);need(key not in self.events or self.events[key]==r,'raw append-only history replaced');self.events[key]=r
   requests=[r for r in rows if r['request_id']==q['request_id'] and r['event']=='request'];need(len(requests)==1,'actual Want absent/duplicated')
   actual=json.loads(requests[0]['value']);need(all(actual[k]==q[k] for k in ('run_id','request_id','action')) and json.loads(actual['payload'])==q['payload'],'actual Want did not carry source-selected input')
   terminal=[r for r in rows if r['request_id']==q['request_id'] and r['event'] in ('done','error','request-error','page-error')];need(len(terminal)==1,'exact API terminal absent/duplicate')
  for role in ROLES:
   for pid in {k[1] for k in self.events if k[0]==role}:
    rows=sorted((r for k,r in self.events.items() if k[:2]==(role,pid)),key=lambda r:r['seq']);need([r['seq'] for r in rows]==list(range(len(rows))),'truncated process journal')
    need(all(int(a['boot_ns'])<=int(b['boot_ns']) for a,b in zip(rows,rows[1:])),'actual public BOOTTIME reversed')
   identities=[json.loads(r['value']) for k,r in self.events.items() if k[0]==role and r['event']=='self-identity'];need(identities and all(v['bundle']==bundle(self.case,role) and v['fingerprint'].replace(':','').upper()==self.identities[role]['fingerprint'] for v in identities),'public self identity differs from actual certificate')
  permissions=self.values('grant','permission-result')
  need(len(permissions)==1,'actual user permission request result missing')
  value=json.loads(permissions[0]['value'])
  need(value['permissions']==['ohos.permission.ACTIVITY_MOTION','ohos.permission.DISTRIBUTED_DATASYNC'] and value['authResults']==[0,0],'actual declared grant role lacks authorization')
  from guest_ui import select_node
  for item in self.flow['inputs']:
   if item['kind']!='permission':continue
   layout=doc(item['layout']);need('MSDP579 '+self.case+' grant '+self.run[:8] in json.dumps(layout,ensure_ascii=False),'permission UI lost original caller identity')
   click=item['click'];actual=doc(ref(click['layout']))
   need(select_node(actual,'com.ohos.permissionmanager',text=item['allow_text'],clickable=True)==click['selected_node'],'actual allow node differs from raw layout')
   x,y,w,h=click['selected_node']['rect'];needle='uitest uiInput click '+str(x+w//2)+' '+str(y+h//2)
   need(any(r['argv'][3]=='shell' and needle in r['argv'][4] and self.parts[i][1]==0 for i,r in enumerate(self.commands) if len(r['argv'])==5),'actual UITest click/transport absent')
  for p in self.flow['processes']:
   actual=replay_process(p['after'],self.command);need(not actual['processes'],'caller UID survived force-stop')
  for r in self.flow['cleanup']['commands']:self.command(r)
  for role in ROLES:
   absent=[r for r in self.flow['cleanup']['commands'] if r['argv'][3]=='shell' and 'bm dump -a' in r['argv'][4]]
   need(any(bundle(self.case,role) not in self.command(r) and 'com.ohos.' in self.command(r) for r in absent),'actual post-uninstall BMS absence missing')
 def command(self,r):
  need(r in self.norm,'raw command not from this original closed producer IO');value,code=self.parts[self.norm.index(r)]
  need(code==0 and r['exit_code']==0,'actual shell/transport failed');return value
 def qmp(self,r):
  from apps_ui578_contract import qmp_wire
  need(r in self.io['qmp'],'foreign QMP');return qmp_wire(r)
 def prepare(self):
  from capability578_callers import compiled_fields_match
  for role,c in self.prepared['callers'].items():
   p=Path(c['project']);index=doc(ref(p/'capability578-source-inputs.json'))
   for name,text in source_files(self.case,self.run,role,{'profile':self.env['device_type']}).items():need(raw(index[name])==text.encode(),'SDK compiled different source '+name)
   for f in index.values():raw(f)
   for k in ('sign_commands','verify_commands'):
    need(c[k],'real signer command missing')
    for r in c[k]:self.command(r)
   if self.case=='sensor':
    from msdp579_sdk import verify
    verify(self.flow['normal_supplement'],self.archive,self.run,self.env['device_type'])
   else:
    for r in c['build_commands']:self.command(r)
    need('BUILD SUCCESSFUL' in ''.join(raw(r['stdout']).decode()+raw(r['stderr']).decode() for r in c['build_commands']),'actual SDK success absent')
   from msdp579_admission import admit
   native=self.flow['native'];admit(native,archive_sha256=self.archive['sha256'],arch=self.env['guest_arch'])
   with zipfile.ZipFile(c['signed']['path']) as signed,zipfile.ZipFile(c['unsigned']['path']) as unsigned:
    raw(c['signed']);raw(c['unsigned']);need(signed.read('ets/modules.abc') and len(signed.namelist())==len(set(signed.namelist())),'actual HAP ABC')
    need(all(signed.read(n)==unsigned.read(n) for n in unsigned.namelist()),'signer changed compiled payload')
    need(signed.read('libs/'+native['abi']+'/libmsdp579.so')==raw(native['binary']),'actual compiled platform addon bytes changed')
    compiled=json.loads(signed.read('module.json'));need(compiled['app']['bundleName']==bundle(self.case,role) and compiled_fields_match(compiled['module'],module_fields(self.case,role)),'actual role permissions/skills')
   profile=doc(c['verified_profile']);need(configure_profile(self.case)(json.loads(json.dumps(profile)),role,self.env['udid'],compiled)==profile and doc(c['signing'])['verified_profile']==profile,'actual signed role/UDID')
   verify=[r for r in c['verify_commands'] if 'verify-app' in r['argv']];need(len(verify)==1,'real signature verifier transcript')
   text=raw(verify[0]['stdout']).decode()+raw(verify[0]['stderr']).decode();leaf=re.split(r'certificate #1\b',re.split(r'certificate #0\b',text,maxsplit=1)[1],maxsplit=1)[0]
   matches=re.findall(r'SHA256:\s*([0-9A-Fa-f:]+)',leaf);need(len(matches)==1,'real application certificate leaf')
   bms=self.flow['installed'][role]
   from apps_providers579_bindings import bms_json
   need(bms_json(self.command(bms['bms']))['applicationInfo']['uid']==bms['uid'] and self.command(bms['hap']).split()[0]==c['signed']['sha256'],'actual BMS/installed HAP bytes differ')
   self.identities[role]=dict(uid=bms['uid'],fingerprint=matches[0].replace(':','').upper())
 def values(self,role,event):return sorted((r for k,r in self.events.items() if k[0]==role and r['event']==event),key=lambda r:(int(r['boot_ns']),r['pid'],r['seq']))
 def actions(self,role,action):
  out=[]
  for cut in self.flow['actions']:
   if cut['role']==role and cut['request']['action']==action:
    out.append([r for k,r in self.events.items() if k[0]==role and r['request_id']==cut['request']['request_id']])
  return out
 def require_done(self,role,action):
  rows=self.actions(role,action);need(rows and all(len([r for r in rs if r['event']=='done'])==1 and not any(r['event']=='error' for r in rs) for rs in rows),'actual public action failed '+role+'/'+action);return rows
 def quiet(self,role):
  for rs in self.actions(role,'quiet'):
   a=[r for r in rs if r['event']=='request'][0];b=[r for r in rs if r['event']=='quiet-end'][0]
   need(b['pid']==a['pid'] and int(b['boot_ns'])-int(a['boot_ns'])>=4_000_000_000,'real quiet duration absent')
   need(not any(r['pid']==a['pid'] and int(a['boot_ns'])<int(r['boot_ns'])<int(b['boot_ns']) and r['event'].endswith('-callback') for k,r in self.events.items() if k[0]==role),'callback survived actual off/stop')

def local(e):
 from msdp579_runtime import LOCAL_ACTIONS
 result={};failures=[]
 for role in ROLES:
  for action in LOCAL_ACTIONS:need(e.actions(role,action),'missing actual '+role+'/'+action)
  caps=e.values(role,'capabilities');need(caps and all(json.loads(r['value'])==[True]*len(CAPS) for r in caps),'actual nine declared capabilities differ')
  e.quiet(role)
 # Existing service metadata handshake is supported separately from watermark.
 notified=e.values('grant','metadata-notified');positive=[r for r in notified if json.loads(r['value'])=='msdp579://'+bundle('local','normal')+'/'+e.run]
 need(len(positive)==2 and positive[0]['pid']==positive[1]['pid'],'cross-UID metadata replies absent')
 submit=e.values('normal','metadata-submitted');need(len(submit)==2 and submit[0]['pid']!=submit[1]['pid'],'metadata listener death/reopen was not exercised')
 need(any(r['event']=='error' for rs in e.actions('grant','metadata-notify') for r in rs),'off listener did not reject fresh service request')
 result['metadata-event-roundtrip']=dict(complete=True,requests=positive,subscriber_restart=submit)
 starts=e.values('grant','ui-drag-start');drops=e.values('grant','ui-drop-data');states=[json.loads(r['value']) for r in e.values('grant','drag-callback')]
 need(len(starts)==len(drops)==2 and starts[0]['pid']!=starts[1]['pid'] and all(json.loads(r['value'])==['msdp579_'+e.run] for r in drops) and states==[1,2,1,2],'actual drag state/UDMF nonce/drop/restart')
 for inp in e.flow['inputs']:
  if inp['kind'] not in ('drag','pointer'):continue
  from PIL import Image
  from guest_ui import select_node
  layout=doc(inp['layout'])
  with Image.open(Path(inp['picture']['path'])) as image:need(list(image.size)==inp['size'],'raw screenshot dimensions')
  raw(inp['picture']);need(select_node(layout,bundle(e.case,'grant'),identifier='msdp579-drag-source')==inp['source'] and select_node(layout,bundle(e.case,'grant'),identifier='msdp579-drag-sink')==inp['target'],'real drag selector/ROI differs')
  need(inp['started_ns']<=inp['finished_ns'] and inp['qmp'],'actual drag interval missing')
  for q in inp['qmp']:e.qmp(q)
 result['drag-udmf-roundtrip']=dict(complete=True,states=states,drops=drops)
 # No generic error classifies a missing provider. These EXACT source-backed
 # boundaries are required if Root later explicitly adopts the narrow policy.
 expected={'device-on':801,'motion-on':801,'holding-on':801,'pickup-on':801,'rotate-on':801,
  'smart-on':801,'hover-on':801,'distance-on':801,'door-on':801,'age-on':801,'user-on':801,'screen-content':801}
 boundary={}
 for action,code in expected.items():
  rows=e.actions('grant',action);need(len(rows)==2,'framework restart boundary missing '+action)
  for rs in rows:need(len([r for r in rs if r['event']=='error' and r['code']==code])==1,'unexpected service/parameter failure cannot prove unavailable provider '+action)
  boundary[action]=rows
 for role in ('normal','denied'):
  for action in ('screen-content',):
   rows=e.actions(role,action);need(rows and all(any(r['event']=='error' and r['code'] in (201,202) for r in rs) for rs in rows),'actual available permission/system role rejection missing')
  need(all(any(r['event']=='error' and r['code']==202 for r in rs) for rs in e.actions(role,'metadata-encode') if role=='normal'),'ordinary metadata system API boundary')
 for role in ROLES:
  need(all(any(r['event']=='error' and r['code']==401 for r in rs) for rs in e.actions(role,'still-on-invalid')),'real stationary argument rejection')
 need(not e.values('normal','drag-callback') and [json.loads(r['value']) for r in e.values('denied','drag-callback')]==[1,2,1,2],'Drag is system-identity protected; denied ACL role still has system identity')
 for rs in e.actions('grant','metadata-encode'):
  decoded=[json.loads(r['value']) for r in rs if r['event']=='decoded-metadata']
  need(not decoded or decoded!=['msdp579_'+e.run],'a working public watermark provider contradicts unavailable-provider scope; re-evaluate actual product')
 result['framework-boundaries']=dict(complete=True,observations=boundary,not_positive_inference=True)
 return result

def sensor(e,capture):
 from batch_system_live_inputs import f32
 from batch_system_verify_live_inputs import mapped_processes
 need(capture['msdp579']['normal_supplement']==e.flow['normal_supplement'] and capture['boot_id']==e.env['boot_id'] and capture['archive_sha256']==e.archive['sha256'],'same original Capture actual input and boot')
 source=e.flow['source_generations'];need(len(source)==2 and source[0]['trace']!=source[1]['trace'],'fresh independent generations')
 proofs=[]
 for g in source:
  wire=g['wire'];need(wire in capture['sessions'],'wire not part of original Capture');hello=bytes.fromhex(wire['hello_hex']);magic,version,nonce,sid,reserved=struct.unpack('<4sI16sII',hello)
  need((magic,version,sid,reserved)==(b'QSN1',1,1,0) and wire['stop_disconnect'] in ('EOF','ECONNRESET'),'real input challenge/last-stop EOF')
  need(len(wire['frames'])==len(g['trace']) and 40<=len(g['trace'])<=1000,'input loss')
  for index,(sample,frame) in enumerate(zip(g['trace'],wire['frames']),1):
   actual=struct.unpack('<4sI16sQfff',bytes.fromhex(frame['hex']));need(actual==(b'QSF1',1,nonce,index,*[f32(sample[k]) for k in ('x','y','z')]),'raw independently sent frame differs')
  maps=mapped_processes(raw(g['maps']).decode());need(any(uid<10000 and 'libdevicestatus_algo.z.so' in paths and 'libdevicestatus_service.z.so' in paths for uid,paths in maps) and not any('libdevicestatus_mock.z.so' in paths for _,paths in maps),'real source algorithm/service mapped; mock prohibited')
  roles={}
  for role in ROLES:
   # Bind callbacks to actual source by exact float32 values and sensor's real
   # guest timestamps; never estimate guest onset from host send time.
   rows=e.values(role,'sensor-callback');matched=[r for r in rows if json.loads(r['value'])['z'] in {s['z'] for s in g['trace']}]
   # low values may coincide across generations, so use the unique high phase
   # to locate this generation, then preserve the entire chronological block.
   high=g['trace'][0]['z'];first=[i for i,r in enumerate(rows) if json.loads(r['value'])['z']==high];need(first,'actual source acceleration did not reach public API')
   count=g['role_source_limits'][role];block=rows[first[0]:first[0]+count];need(len(block)==count,'all input frames must publicly arrive')
   for r,s in zip(block,g['trace'][:count]):
    v=json.loads(r['value']);need([f32(v[k]) for k in ('x','y','z')]==[f32(s[k]) for k in ('x','y','z')] and 0<v['timestamp']<=int(r['boot_ns']),'public sensor values/clock differ from wire')
   callbacks=[r for r in e.values(role,'still-callback') if json.loads(block[0]['value'])['timestamp']<=int(r['boot_ns'])<=int(block[-1]['boot_ns'])+2_000_000_000]
   need([json.loads(r['value'])['state'] for r in callbacks]==[1,2,1,2],'actual public still transitions differ')
   for r,lo,hi in zip(callbacks,(4,10,24,g['partial_unsubscribe_frame']),(9,19,29,g['partial_unsubscribe_frame']+9)):
    need(json.loads(block[lo]['value'])['timestamp']<=int(r['boot_ns'])<=int(block[hi]['boot_ns'])+2_000_000_000,'public state arrived before native input threshold')
   need(not e.values(role,'relative-callback') and not e.values(role,'relative-once-callback'),'relativeStill lacks a real provider; synthetic success must fail')
   e.quiet(role);roles[role]=dict(sensor=block,still=callbacks)
  from msdp579_image import replay as replay_image
  need(set(g['native_client_images'])==set(ROLES),'all real HAP UIDs loaded actual client')
  for role,observation in g['native_client_images'].items():
   need(observation['uid']==e.identities[role]['uid'],'loaded client UID differs');replay_image(observation,e)
  algorithms=algorithm_replay(e,g,roles)
  proofs.append(dict(generation=g['generation'],roles=roles,wire=wire,algorithms=algorithms))
 need(e.values('grant','sensor-callback')[0]['pid']!=e.values('grant','sensor-callback')[-1]['pid'],'actual shared subscriber death/reopen missing')
 return {'stationary-still-input':dict(complete=True,proof=proofs,real_three_algorithms=[g['algorithms'] for g in proofs],physical_immobility_accuracy_claimed=False),
  'stationary-relative-framework':dict(complete=True,positive_provider_supported=False)}

def cooperate(source,sink,paired):
 a=source.flow['paired_business'];b=sink.flow['paired_business'];need(a==b and not a['failures'] and not a['cleanup_errors'],'actual full paired cooperation flow failed')
 need(source.env['boot_id']!=sink.env['boot_id'] and source.archive==sink.archive and source.env['udid']!=sink.env['udid'],'independent same-archive pair')
 need(paired['semantic_replay_complete'] is True and not paired['replay_errors'] and not paired['retained_failures'],'original full PIN/trusted/media/unbind raw failed')
 from owning_services579_replay import dfs_peer_identity
 trust=doc(a['trusted_window']);need(trust=={k:a[k] for k in ('locals','source_trust','sink_trust')},'trusted-window raw replaced')
 dfs_peer_identity(a['trusted_window'],source.archive['sha256'],source.env['boot_id'],sink.env['boot_id'])
 need(set(paired['checks']['original_resources']['distinct_boots'])==set(a['boots'].values()),'paired original resources differ')
 values=[json.loads(r['value']) for r in source.values('grant','cooperate-callback')];peer=a['locals']['sink']['networkId']
 need(sum(v['networkId']==peer and v['state']==3 for v in values)==2 and sum(v['networkId']==peer and v['state']==5 for v in values)==2,'real activate/deactivate callbacks absent')
 sink_text=[json.loads(r['value']) for r in sink.values('grant','ui-text-changed')];need(sink_text and sink_text[-1]==a['challenge']*2,'fresh independent remote keyboard nonce consumption absent')
 for g in a['generations']:
  need([q['arguments']['keys'][0]['data'] for q in g['source_keys']]==list(a['challenge']),'actual source QMP keys differ')
  for q in g['source_keys']:source.qmp(q)
  source.qmp(g['quiet_source_key'])
  before=[r for r in g['sink_before'] if r['event']=='ui-text-changed'];after=[r for r in g['sink_after'] if r['event']=='ui-text-changed'];need(before==after,'input continued remotely after deactivate')
 for e in (source,sink):
  for role in ('normal','denied'):
   for action in ('cooperate-prepare',):
    need(all(any(r['event']=='error' and r['code'] in (201,202) for r in rs) for rs in e.actions(role,action)),'actual role/argument denial absent')
 return {'cooperate-remote-input':dict(complete=True,challenge=a['challenge'],source_input=a['input_device'],actual_boots=a['boots'])}


def algorithm_replay(e,g,roles):
 result={}
 for role in ROLES:
  values=[(r,json.loads(r['value'])) for r in e.values(role,'algo-native-raw')]
  unique={}
  for journal,value in values:
   need(value['pid']==journal['pid'] and value['uid']==journal['uid'] and value['overflow'] is False,'real native callback producer identity/bound exceeded')
   for row in value['rows']:
    key=(value['pid'],row['seq']);need(key not in unique or unique[key]==row,'native append-only queue replaced');unique[key]=row
  block=roles[role]['sensor'];lo=json.loads(block[0]['value'])['timestamp'];hi=json.loads(block[-1]['value'])['timestamp']
  callbacks=[r for r in unique.values() if r['kind']=='callback' and lo<=int(r['mono_ns'])<=hi+2_000_000_000]
  expected={0:[1,2,1],1:[1,2,1,2],2:[1,2,1]}
  for kind,wanted in expected.items():
   actual=sorted((r for r in callbacks if r['type']==kind),key=lambda r:int(r['mono_ns']))
   need([r['value'] for r in actual]==wanted,'actual real3 algorithm input/partial-unsubscribe callbacks differ '+str(kind))
   need(all(r['result']==0 and int(r['boot_ns'])>0 and not r['after_off'] for r in actual),'callback after native unsubscribe or invalid clock')
  for rs in e.actions(role,'algo-on'):
   if not (lo-10_000_000_000<=int(rs[0]['boot_ns'])<=hi):continue
   need([json.loads(r['value']) for r in rs if r['event']=='algo-on-return']==[{'type':i,'result':0} for i in (0,1,2)],'three real inner subscriptions must all succeed')
  for rs in e.actions(role,'algo-off-one'):
   need(all(json.loads(r['value'])['result']==0 for r in rs if r['event']=='algo-off-return'),'actual inner unsubscribe failed')
  for quiet in e.actions(role,'quiet'):
   a=next(r for r in quiet if r['event']=='request');b=next(r for r in quiet if r['event']=='quiet-end')
   need(not any(int(a['boot_ns'])<int(r['boot_ns'])<int(b['boot_ns']) for r in unique.values() if r['kind']=='callback'),'native callback continued after off within actual quiet window')
  result[role]=dict(callbacks=callbacks,expected=expected)
 return result
