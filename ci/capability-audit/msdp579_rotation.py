"""Independent unit-quaternion source through original Capture resources only."""
import math,secrets,struct,time,json
from msdp579_contract import need,ref,raw
from msdp579_project import ROLES

def quaternion(axis):
 angle=(350+secrets.randbelow(500))/1000
 values=[0.0,0.0,0.0,math.cos(angle/2)];values[axis]=math.sin(angle/2)
 return {k:struct.unpack('<f',struct.pack('<f',v))[0] for k,v in zip(('x','y','z','w'),values)}

def run(capture,flow):
 capture.own_forward('rotation','/dev/unix/socket/qemu_sensor/rotation')
 result=dict(schema='msdp579-independent-rotation-input/v1',generations=[],invalid=[],runtime_pass=False)
 previous=None;used=set()
 def fresh(axis):
  q=quaternion(axis);key=lambda q:tuple(q[k] for k in ('x','y','z','w'))
  while key(q) in used:q=quaternion(axis)
  used.add(key(q));return q
 for generation in (1,2):
  capture.generation=200+generation
  for role in ROLES:flow.call(role,'rotation-writer-denial');flow.call(role,'rotation-sensor-on')
  # Every malformed record traverses the original root-authorized HDC forward.
  names=('wrong_nonce','zero_nonce','zero_sequence','wrong_version','nonfinite','nonunit')+ (('old_generation_nonce',) if previous is not None else ())
  for name in names:
   stream,nonce,wire=capture.connect('rotation','invalid_'+str(generation)+'_'+name)
   q=fresh(0);frame=bytearray(capture.frame('rotation',nonce,1,q))
   if name=='wrong_nonce':frame[8]^=1
   elif name=='zero_nonce':frame[8:24]=bytes(16)
   elif name=='zero_sequence':frame[24:32]=bytes(8)
   elif name=='wrong_version':frame[4:8]=struct.pack('<I',2)
   elif name=='nonfinite':frame[32:36]=struct.pack('<f',float('nan'))
   elif name=='nonunit':frame[32:48]=bytes(16)
   elif name=='old_generation_nonce':frame[8:24]=previous
   stream.sendall(frame);wire['frames'].append(dict(hex=frame.hex(),host_monotonic_ns=time.monotonic_ns()))
   wire['disconnect']=capture.eof(stream);stream.close();result['invalid'].append(dict(generation=generation,case=name,wire=wire))
  stream,nonce,wire=capture.connect('rotation','valid_generation_'+str(generation));previous=nonce;sequence=0
  g=dict(generation=generation,wire=wire,queries=[]);result['generations'].append(g)
  try:
   for axis in range(3):
    q=fresh(axis)
    for role in ROLES:
     token=flow.begin(role,'rotation');before=len(wire['frames'])
     # Native public request runs asynchronously. Repeated independent samples
     # cover its <=1s wait; every frame and raw callback remains retained.
     for unused in range(8):
      sequence+=1;data=capture.frame('rotation',nonce,sequence,q);stream.sendall(data)
      wire['frames'].append(dict(hex=data.hex(),host_monotonic_ns=time.monotonic_ns()));time.sleep(.08)
     flow.finish(token);g['queries'].append(dict(role=role,request_id=token[0]['request']['request_id'],quaternion=q,frames=[before,len(wire['frames'])]))
   for role in ROLES:
    sequence+=1;data=capture.frame('rotation',nonce,sequence,q);stream.sendall(data)
    wire['frames'].append(dict(hex=data.hex(),host_monotonic_ns=time.monotonic_ns()))
    flow.call(role,'rotation-sensor-off')
   wire['stop_disconnect']=capture.eof(stream);g['eof_monotonic_ns']=time.monotonic_ns()
   need(g['eof_monotonic_ns']-wire['frames'][-1]['host_monotonic_ns']<4_000_000_000,'rotation EOF could be unrelated idle timeout')
  finally:stream.close()
  g['maps']=ref(capture.mappings('msdp579_rotation_'+str(generation)))
  for role in ROLES:flow.call(role,'quiet')
  # Fresh one-shot without ANY source input must fail; stale cache is forbidden.
  for role in ('grant','denied'):flow.call(role,'rotation')
  if generation==1:
   flow.stop('grant');flow.call('grant','context')
  flow.data['rotation_source']=result;flow.persist()
 return result

def expected(q):
 # Same axis and radians convention as PUBLIC x=roll,y=pitch,z=yaw. This is
 # calculated from independent source values, never from callback/getter data.
 x,y,z,w=(q[k] for k in ('x','y','z','w'))
 m20=2*(x*z-w*y);m22=1-2*(x*x+y*y);m21=2*(y*z+w*x)
 m01=2*(x*y-w*z);m11=1-2*(x*x+z*z)
 positive=lambda a:a+2*math.pi if a<0 else a
 pitch=positive(math.atan2(-m20,m22));yaw=positive(math.atan2(-m01,m11))
 roll=positive(math.atan2(m21,m22/math.cos(pitch) if math.cos(pitch)>=1e-6 else -m20/math.sin(pitch)))
 return dict(x=roll,y=pitch,z=yaw)

def replay(e,capture):
 from batch_system_verify_live_inputs import mapped_processes
 v=e.flow['rotation_source'];need(v['schema']=='msdp579-independent-rotation-input/v1' and len(v['generations'])==2,'two real rotation source generations')
 nonces=[];queries=[]
 for g in v['generations']:
  wire=g['wire'];need(wire in capture['sessions'] and wire['generation']==200+g['generation'] and wire['stop_disconnect'] in ('EOF','ECONNRESET'),'original source/last-subscriber EOF')
  magic,version,nonce,sid,reserved=struct.unpack('<4sI16sII',bytes.fromhex(wire['hello_hex']));need((magic,version,sid,reserved)==(b'QRS1',1,259,0) and nonce!=bytes(16) and nonce not in nonces,'fresh type-specific source challenge');nonces.append(nonce)
  frames=[]
  for seq,row in enumerate(wire['frames'],1):
   f=struct.unpack('<4sI16sQffff',bytes.fromhex(row['hex']));need(f[:4]==(b'QRF1',1,nonce,seq) and all(math.isfinite(x) for x in f[4:]) and abs(sum(x*x for x in f[4:])-1)<1e-4,'actual unit-quaternion frame grammar');frames.append(f)
  need(len(g['queries'])==9,'three real orientations and roles')
  for q in g['queries']:
   lo,hi=q['frames'];need(hi-lo==8 and all(tuple(f[4:])==tuple(q['quaternion'][k] for k in ('x','y','z','w')) for f in frames[lo:hi]),'wire differs from independent input')
   rs=[r for k,r in e.events.items() if k[0]==q['role'] and r['request_id']==q['request_id']]
   if q['role']=='normal':need(any(r['event']=='error' and r['code']==202 for r in rs),'normal actual system identity denial')
   else:
    values=[json.loads(r['value']) for r in rs if r['event']=='rotation'];need(len(values)==1,'actual public rotation result absent')
    want=expected(q['quaternion']);need(all(min(abs(values[0][k]-want[k]),abs(values[0][k]-want[k]+2*math.pi),abs(values[0][k]-want[k]-2*math.pi))<1e-4 for k in want),'public quaternion->ZXY radians/axis result differs')
   queries.append(q)
   callbacks=[json.loads(r['value']) for r in e.values(q['role'],'rotation-sensor-callback')]
   need(any(all(abs(r[k]-q['quaternion'][k])<1e-6 for k in ('x','y','z','w')) for r in callbacks),'independent source did not reach actual public sensor callback')
  # Real provider/service identity shares the original full framed mapping cuts.
  maps=mapped_processes(raw(g['maps']).decode())
  need(any(uid<10000 and 'libdevicestatus_service.z.so' in paths for uid,paths in maps),'native public conversion service mapping missing')
 for role in ('grant','denied'):
  queried={q['request_id'] for q in queries if q['role']==role}
  nofeed=[rs for rs in e.actions(role,'rotation') if rs[0]['request_id'] not in queried]
  need(len(nofeed)==2 and all(any(r['event']=='error' for r in rs) and not any(r['event']=='rotation' for r in rs) for rs in nofeed),'no-input request falsely reused prior quaternion')
 need(len(v['invalid'])==13,'all finite malformed/old generation cases')
 for row in v['invalid']:
  wire=row['wire'];need(wire in capture['sessions'] and wire['disconnect'] in ('EOF','ECONNRESET') and len(wire['frames'])==1,'actual malformed source EOF absent')
  f=bytes.fromhex(wire['frames'][0]['hex']);hello=bytes.fromhex(wire['hello_hex']);case=row['case']
  need(len(f)==48 and ((case=='wrong_nonce' and f[8:24]!=hello[8:24]) or (case=='zero_nonce' and f[8:24]==bytes(16)) or
   (case=='zero_sequence' and f[24:32]==bytes(8)) or (case=='wrong_version' and f[4:8]==struct.pack('<I',2)) or
   (case=='nonfinite' and not math.isfinite(struct.unpack('<f',f[32:36])[0])) or (case=='nonunit' and f[32:48]==bytes(16)) or
   (case=='old_generation_nonce' and f[8:24]==nonces[0] and f[8:24]!=hello[8:24])),'invalid wire case not reconstructed')
 valid={tuple(q['quaternion'][k] for k in ('x','y','z','w')) for q in queries}
 for role in ROLES:
  for row in e.values(role,'rotation-sensor-callback'):
   value=json.loads(row['value']);need(tuple(value[k] for k in ('x','y','z','w')) in valid,'malformed/nonce/stale source escaped into public callbacks')
 for role in ROLES:
  denied=e.values(role,'rotation-writer-denial');need(len(denied)==2,'all actual source-writer UID boundary generations')
  for r in denied:
   denial=json.loads(r['value']);need(denial['uid']==e.identities[role]['uid'] and denial['result']==-1 and denial['errno'] in (1,13),'ordinary or system HAP could write the root-only input channel')
 grant=[r for rs in e.actions('grant','rotation') for r in rs if r['event']=='rotation']
 need(grant and grant[0]['pid']!=grant[-1]['pid'],'actual rotation caller death/reopen missing')
 return {'device-rotation':dict(complete=True,queries=queries,source_nonces=[n.hex() for n in nonces],invalid=v['invalid'],physical_orientation_accuracy_claimed=False)}
