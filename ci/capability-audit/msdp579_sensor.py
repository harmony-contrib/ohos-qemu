"""Run at fixed original Capture seam; reuse its one owned QSN1 forward."""
from pathlib import Path
import json,os,secrets,struct,time,threading,sys
from msdp579_contract import need,ref,raw,doc,save
from msdp579_capture_bridge import CaptureBridge
from msdp579_io import Flow
from msdp579_project import ROLES
from msdp579_runtime import permissions

def vector():
 high=struct.unpack('<f',struct.pack('<f',9.3+secrets.randbelow(90)/100))[0]
 low=struct.unpack('<f',struct.pack('<f',secrets.randbelow(50)/100))[0]
 return [dict(at_ms=i*160,x=0.1 if i<10 or i>=20 else 0.01,y=0.1 if i<10 or i>=20 else low+0.2,z=high if i<10 or i>=20 else 0.01) for i in range(30)]

def after_original(capture):
 """Original argv and two generations remain; normal SDK production is automatic."""
 from msdp579_capture_production import prepare_on_capture
 path=prepare_on_capture(capture)
 spec=doc(ref(path));need(set(spec)=={'schema','unsigned','signer_dist'} and spec['schema']=='msdp579-original-Capture-supplement-inputs/v1','finite normal data only')
 io=CaptureBridge(capture,spec['unsigned'],spec['signer_dist']);flow=Flow(io,'sensor');streams=[];source=[];failure=None
 flow.data['normal_supplement']=spec['unsigned']
 try:
  flow.prepare()
  image=doc(spec['unsigned'])['image']
  for role in ROLES:flow.install(role)
  permissions(flow)
  from msdp579_rotation import run as rotation_source
  rotation_source(capture,flow)
  for generation in (1,2):
   for role in ROLES:
    for action in ('algo-on','sensor-on','still-on','relative-on','still-once','relative-once'):flow.call(role,action)
   challenge=vector()
   while source and challenge[0]['z']==source[0]['trace'][0]['z']:challenge=vector()
   capture.generation=100+generation
   stream,nonce,record=capture.connect('sensor','msdp579_generation_'+str(generation));streams.append(stream)
   record['trace_start_monotonic_ns']=time.monotonic_ns();row=dict(generation=generation,trace=challenge,wire=record,role_cuts={})
   source.append(row);base=time.monotonic()
   for seq,sample in enumerate(challenge,1):
    delay=base+sample['at_ms']/1000-time.monotonic()
    if delay>0:time.sleep(delay)
    frame=capture.frame('sensor',nonce,seq,sample);stream.sendall(frame);record['frames'].append(dict(hex=frame.hex(),host_monotonic_ns=time.monotonic_ns()))
   # Keep this SAME original stream active while real IPC/HDC operations run.
   # The fixed sender is bounded, joined, and cannot create a socket/Owner.
   stop=threading.Event();phase_lock=threading.Lock();phase=[dict(challenge[-1])];writer_errors=[];closing=[False]
   def send_held():
    deadline=time.monotonic()+90
    try:
     while not stop.wait(.16):
      need(time.monotonic()<deadline,'bounded source hold expired')
      with phase_lock:sample=dict(phase[0])
      sample['at_ms']=(time.monotonic_ns()-record['trace_start_monotonic_ns'])//1_000_000
      seq=len(record['frames'])+1;frame=capture.frame('sensor',nonce,seq,sample);stream.sendall(frame)
      record['frames'].append(dict(hex=frame.hex(),host_monotonic_ns=time.monotonic_ns()));challenge.append(sample)
    except Exception as error:
     writer_errors.append(dict(error=repr(error),during_last_unsubscribe=closing[0] and isinstance(error,(BrokenPipeError,ConnectionResetError)),error_type=type(error).__name__,monotonic_ns=time.monotonic_ns()))
   worker=threading.Thread(target=send_held,name='msdp579-owned-source',daemon=False);worker.start()
   try:
    for role in ROLES:flow.call(role,'algo-drain');flow.call(role,'algo-off-one',{'type':0})
    # Type0 is stopped; the same real type1/type2 source now changes posture.
    with phase_lock:phase[0]=dict(x=0.01,y=0.5,z=0.01)
    row['partial_unsubscribe_frame']=len(record['frames']);deadline=time.monotonic()+5
    while len(record['frames'])<row['partial_unsubscribe_frame']+10:
     need(not writer_errors and time.monotonic()<deadline,'actual partial-unsubscribe input did not arrive');time.sleep(.05)
    row['role_source_limits']={}
    for role in ROLES:
     flow.call(role,'algo-drain')
     for type_id in (2,1):flow.call(role,'algo-off-one',{'type':type_id})
     flow.call(role,'algo-drain');flow.call(role,'relative-off');flow.call(role,'still-off')
     row['role_source_limits'][role]=len(record['frames'])
     if role==ROLES[-1]:closing[0]=True
     flow.call(role,'sensor-off')
   finally:
    interrupted=sys.exc_info()[1]
    stop.set();worker.join(timeout=3)
    if worker.is_alive():
     from capability578_stage import UnsettledCapability
     flow.data['failures'].append('original source sender failed bounded join; no guest reuse')
     if interrupted is not None and not isinstance(interrupted,Exception):raise interrupted
     raise UnsettledCapability('original source sender failed bounded join; no guest reuse')
   need(not any(not e['during_last_unsubscribe'] for e in writer_errors),'provider disconnected before actual last unsubscribe')
   row['writer_errors']=writer_errors
   record['stop_disconnect']=capture.eof(stream);row['eof_monotonic_ns']=time.monotonic_ns();stream.close()
   need(row['eof_monotonic_ns']-record['frames'][-1]['host_monotonic_ns']<4_000_000_000,'EOF could be unrelated 5s idle timeout')
   for role in ROLES:
    flow.call(role,'quiet');flow.call(role,'algo-drain');rows,refs=flow.rows(role);row['role_cuts'][role]=refs
   from msdp579_image import observe,CLIENT
   row['native_client_images']={role:observe(io,image,name=CLIENT,uid=flow.data['installed'][role]['uid']) for role in ROLES}
   row['maps']=ref(capture.mappings('msdp579_generation_'+str(generation)))
   if generation==1:
    flow.stop('grant');flow.call('grant','context')
   flow.data['source_generations']=source;flow.persist()
 except BaseException as error:failure=error;flow.data['failures'].append(repr(error))
 finally:
  # Originals are still in capture.streams; original finally also closes them.
  for stream in streams:stream.close()
  try:io.close()
  except BaseException as error:
   flow.data['failures'].append('cleanup: '+repr(error))
   if failure is None or isinstance(failure,Exception):failure=error
  flow.data['source_generations']=source;flow.persist()
  capture.report['msdp579']=dict(schema='msdp579-original-Capture-retention/v1',input=ref(path),flow=ref(flow.path/'flow.json'),io=ref(io.output/'io.json'),normal_supplement=spec['unsigned'])
  if failure:raise failure
 return capture.report['msdp579']
