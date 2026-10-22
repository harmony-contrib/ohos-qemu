"""Fixed business on existing Owner IOs; actual API failures are retained."""
import json,time,secrets
from msdp579_contract import need,ref,raw,save
from msdp579_project import bundle,ROLES
from msdp579_io import Flow

LOCAL_ACTIONS=('capabilities','context','sensor-list','still-on-invalid','relative-on','relative-once','relative-off','device-on','device-off',
 'motion-on','motion-recent','motion-off','holding-on','holding-off','pickup-on','pickup-off','rotate-on','rotate-off','smart-on','smart-off','hover-on','hover-invalid','hover-off',
 'distance-on','distance-off','door-on','door-off','age-on','age-off','user-capabilities','user-configure','user-on','user-off',
 'metadata-encode','screen-content','screen-permission-on','screen-on','screen-trigger','screen-capture',
 'screen-interact','screen-apperceive','screen-control','screen-control-invalid','screen-off','screen-permission-off','drag-summary','cooperate-activate-invalid')

def permissions(flow):
 token=flow.begin('grant','permissions');deadline=time.monotonic()+45
 from guest_ui import select_node,NodeNotReady,LayoutNotReady
 while True:
  rows,_=flow.rows('grant')
  if any(r['request_id']==token[0]['request']['request_id'] and r['event'] in ('done','error') for r in rows):return flow.finish(token)
  try:
   layout,path=flow.io.ui.layout(label='msdp579_permission')
   label='MSDP579 '+flow.case+' grant '+flow.io.run_id[:8]
   if label not in json.dumps(layout,ensure_ascii=False):raise NodeNotReady('owned MSDP permission dialog not yet visible')
   select_node(layout,'com.ohos.permissionmanager',text=flow.io.environment['permission_allow_text'])
   flow.data['inputs'].append(dict(kind='permission',allow_text=flow.io.environment['permission_allow_text'],layout=ref(path),click=flow.io.ui.click('com.ohos.permissionmanager',text=flow.io.environment['permission_allow_text'],label='msdp579_allow')));flow.persist()
  except (NodeNotReady,LayoutNotReady):pass
  need(time.monotonic()<deadline,'actual owned permission interaction timed out');time.sleep(.2)

def pointer(flow,source_id,target_id,*,drag=False):
 """QMP coordinates are derived from actual UITest ROI and real framebuffer."""
 from guest_ui import select_node
 from PIL import Image
 io=flow.io;layout,path=io.ui.layout(bundle=bundle(flow.case,'grant'),label='msdp579_geometry')
 picture=io.ui.screenshot(label='msdp579_geometry_frame')
 with Image.open(picture) as image:width,height=image.size
 a=select_node(layout,bundle(flow.case,'grant'),identifier=source_id)
 b=select_node(layout,bundle(flow.case,'grant'),identifier=target_id)
 def center(n):
  x,y,w,h=n['rect'];need(0<=x<x+w<=width and 0<=y<y+h<=height,'actual ROI outside framebuffer');return x+w//2,y+h//2
 first,last=center(a),center(b);cut=dict(kind='drag' if drag else 'pointer',layout=ref(path),picture=ref(picture),size=[width,height],source=a,target=b,started_ns=time.monotonic_ns(),qmp=[])
 def q(args):cut['qmp'].append(io.qmp('input-send-event',{'events':args}))
 def move(x,y):q([dict(type='abs',data=dict(axis='x',value=x*32767//(width-1))),dict(type='abs',data=dict(axis='y',value=y*32767//(height-1)))])
 try:
  move(*first);q([dict(type='btn',data=dict(button='left',down=True))]);time.sleep(.8 if drag else .1)
  for i in range(1,17):
   move(first[0]+(last[0]-first[0])*i//16,first[1]+(last[1]-first[1])*i//16);time.sleep(.08)
 finally:
  q([dict(type='btn',data=dict(button='left',down=False))]);cut['finished_ns']=time.monotonic_ns();flow.data['inputs'].append(cut);flow.persist()
 return cut

def run_local(io):
 flow=Flow(io,'local');failure=None;cleanup_error=None
 try:
  flow.prepare()
  for role in ROLES:flow.install(role)
  permissions(flow)
  for role in ROLES:
   for action in LOCAL_ACTIONS:
    try:flow.call(role,action,{'peer':'0'*64})
    except Exception as error:
     from capability578_stage import UnsettledCapability
     if isinstance(error,UnsettledCapability):raise
     flow.data['failures'].append(dict(role=role,action=action,error=repr(error)));flow.persist()
  # Service-mediated cross-UID metadata request -> callback -> submit -> reply.
  flow.call('normal','metadata-on')
  flow.call('grant','metadata-notify',{'bundle':bundle('local','normal')})
  flow.call('normal','metadata-off');flow.call('grant','metadata-notify',{'bundle':bundle('local','normal')});flow.call('normal','quiet')
  flow.stop('normal');flow.call('normal','metadata-on');flow.call('grant','metadata-notify',{'bundle':bundle('local','normal')});flow.call('normal','metadata-off');flow.call('normal','quiet')
  for role in ('normal','denied'):flow.call(role,'drag-on')
  for generation in (1,2):
   flow.call('grant','drag-on');pointer(flow,'msdp579-drag-source','msdp579-drag-sink',drag=True)
   flow.call('grant','drag-off');flow.call('grant','quiet')
   if generation==1:
    flow.stop('grant')
    for action in LOCAL_ACTIONS:flow.call('grant',action,{'peer':'0'*64})
  for role in ('normal','denied'):flow.call(role,'drag-off');flow.call(role,'quiet')
 except BaseException as error:
  failure=error;flow.data['failures'].append(repr(error))
 finally:
  try:flow.cleanup()
  except BaseException as error:cleanup_error=error
  flow.persist()
 if failure is not None and not isinstance(failure,Exception):raise failure
 if cleanup_error is not None:raise cleanup_error
 if failure is not None:raise failure
 need(not flow.data['failures'],'MSDP actual transport/collection failure retained')
 return flow

def run_cooperate(source,sink,*,locals,source_trust,sink_trust,trusted_window,image):
 """Only inside original paired trusted seam, before original remote media."""
 need(source.archive_sha256==sink.archive_sha256 and source.boot_id!=sink.boot_id and source.udid!=sink.udid,'two actual independent same-package guests')
 need(set(locals)=={'source','sink'} and locals['source']['networkId']!=locals['sink']['networkId'],'actual paired SoftBus identities')
 flows={'source':Flow(source,'cooperate'),'sink':Flow(sink,'cooperate')};challenge=''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(12))
 failure=None;cleanup_interrupt=None
 common=dict(trusted_window=trusted_window,schema='msdp579-cooperate-business/v1',challenge=challenge,locals=locals,source_trust=source_trust,sink_trust=sink_trust,
  boots={e:f.io.boot_id for e,f in flows.items()},failures=[],runtime_pass=False,first_artifact_behavior_gate_passed=False)
 try:
  for endpoint,f in flows.items():
   f.prepare()
   for role in ROLES:f.install(role)
   permissions(f)
   peer=locals['sink' if endpoint=='source' else 'source']['networkId']
   for role in ('normal','denied'):
    for action in ('cooperate-on','cooperate-prepare','cooperate-activate-invalid','cooperate-deactivate','cooperate-unprepare','cooperate-off'):f.call(role,action,{'peer':peer})
   f.call('grant','cooperate-on');f.call('grant','cooperate-prepare');f.call('grant','cooperate-state',{'peer':peer})
  a,b=flows['source'],flows['sink'];peer=locals['sink']['networkId']
  # Observe the actual QEMU->MMI device ID BEFORE supplying it to public activate.
  pointer(a,'msdp579-nonce','msdp579-remote-input')
  a.call('grant','input-devices');rows,_=a.rows('grant')
  mouse=[json.loads(r['value']) for r in rows if r['event']=='ui-mouse'];devices=[json.loads(r['value']) for r in rows if r['event']=='input-device']
  need(mouse,'no actual QEMU mouse delivered to source caller')
  selected=[d for d in devices if d['id']==mouse[-1]['deviceId'] and 'mouse' in d['sources']];need(len(selected)==1,'observed QEMU input must match real MMI mouse')
  common['input_device']=selected[0];a.call('grant','cooperate-mouse-on',{'peer':peer})
  for generation in (1,2):
   a.call('grant','cooperate-activate',{'peer':peer,'device_id':selected[0]['id']})
   from msdp579_image import observe
   for f in flows.values():f.data.setdefault('cooperate_provider',[]).append(observe(f.io,image));f.persist()
   # Sink focuses its actual consumer; QMP injects ONLY source input afterward.
   b.io.ui.click(bundle('cooperate','grant'),identifier='msdp579-remote-input',label='msdp579_sink_focus')
   injected=[]
   for c in challenge:
    injected.append(source.qmp('send-key',{'keys':[{'type':'qcode','data':c}],'hold-time':60}));time.sleep(.12)
   common.setdefault('generations',[]).append(dict(generation=generation,source_keys=injected))
   a.call('grant','cooperate-deactivate');a.call('grant','quiet');b.call('grant','quiet')
   before,_=b.rows('grant');quiet='z'
   stopped=source.qmp('send-key',{'keys':[{'type':'qcode','data':quiet}],'hold-time':60});b.call('grant','quiet')
   after,_=b.rows('grant');common['generations'][-1].update(quiet_source_key=stopped,sink_before=before,sink_after=after)
   if generation==1:
    a.call('grant','cooperate-mouse-off',{'peer':peer});a.call('grant','cooperate-unprepare');a.call('grant','cooperate-off');a.stop('grant')
    a.call('grant','cooperate-on');a.call('grant','cooperate-prepare');a.call('grant','cooperate-mouse-on',{'peer':peer})
  a.call('grant','cooperate-mouse-off',{'peer':peer})
 except BaseException as error:
  failure=error;common['failures'].append(repr(error))
 finally:
  errors=[]
  for endpoint,f in reversed(list(flows.items())):
   for action in ('cooperate-deactivate','cooperate-unprepare','cooperate-off'):
    try:f.call('grant',action)
    except BaseException as error:
     errors.append(dict(endpoint=endpoint,action=action,error=repr(error)))
     if not isinstance(error,Exception) and cleanup_interrupt is None:cleanup_interrupt=error
   try:f.cleanup()
   except BaseException as error:
    errors.append(dict(endpoint=endpoint,error=repr(error)))
    if not isinstance(error,Exception) and cleanup_interrupt is None:cleanup_interrupt=error
   f.data['paired_business']=common;f.persist()
  common['cleanup_errors']=errors
  for f in flows.values():f.data['paired_business']=common;f.persist()
 if failure is not None and not isinstance(failure,Exception):raise failure
 if cleanup_interrupt is not None:raise cleanup_interrupt
 if errors:
  from capability578_stage import UnsettledCapability
  raise UnsettledCapability('actual cooperation cleanup uncertain: '+repr(errors))
 if failure is not None:raise failure
 return flows
