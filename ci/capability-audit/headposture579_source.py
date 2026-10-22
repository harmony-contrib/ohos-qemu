"""Fixed HEADPOSTURE input on one ORIGINAL registered IO; no Owner/Guest.

Only source/wire evidence is returned. Actual SensorEvent->HeadTracker->SET_IMU
consumption and PCM behavior must be joined by the owning media raw oracle.
"""
from pathlib import Path
import hashlib,json,math,secrets,socket,struct,threading,time

PATH='/dev/unix/socket/qemu_sensor/headposture'
MAX_FRAMES=8192
INVALID=('wrong_nonce','zero_nonce','zero_sequence','wrong_version','nonfinite','nonunit','zero_order','overflow_order','old_nonce')
def need(value,message):
 if not value:raise ValueError(message)
def ref(path):
 p=Path(path).absolute();need(p.is_file() and not p.is_symlink() and p.resolve()==p,'actual absolute regular raw required')
 return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def checked(value):
 need(type(value)is dict and set(value)=={'path','sha256'} and ref(value['path'])==value,'exact actual Ref2')
 return Path(value['path'])
def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
def quat(value):
 need(type(value)is dict and set(value)=={'w','x','y','z'},'exact independently supplied quaternion')
 values={k:f32(value[k]) for k in ('w','x','y','z')}
 need(all(type(value[k]) in (int,float) and math.isfinite(values[k]) and abs(values[k])<=1 for k in values) and
  abs(sum(v*v for v in values.values())-1)<1e-4,'finite unit quaternion required')
 return values
def exact(stream,length):
 data=b''
 while len(data)<length:
  part=stream.recv(length-len(data))
  if not part:raise EOFError('actual headposture source EOF')
  data+=part
 return data

class HeadPostureSource:
 def __init__(self,io):
  need(not io._closed,'original held IO required');io.owner.held_binding(io.guest)
  self.io=io;self.output=Path(io.output)/'headposture579';self.output.mkdir(exist_ok=False)
  self.lock=threading.RLock();self.halt=threading.Event();self.thread=None;self.stream=None;self.forward=None
  self.file=None;self.counter=0;self.sessions=0;self.connection_attempts=0;self.pose_value=None;self.current_pose=None
  self.order=secrets.randbelow(1048575)+2;self.frames=0;self.baseline_frames=0;self.commands=[];self.errors=[];self.poses=[]
  self.started=False;self.closed=False;self.probed=False;self.disabled_ns=None;self.end=None;self.finished=None
  self.result={'schema':'headposture579-original-IO-input/v1','archive_sha256':io.archive_sha256,
   'boot_id':io.boot_id,'run_id':io.run_id,'target':io.target,'input_path':PATH,'type':268,
   'poses':self.poses,'commands':self.commands,'errors':self.errors,'closed':False,
   'runtime_pass':False,'first_artifact_behavior_gate_passed':False}
  # Register before creating any endpoint/stream/thread.
  io.register_cleanup(self.cleanup)
 def record(self,kind,**fields):
  with self.lock:
   self.counter+=1;value=dict(fields);value.update(kind=kind,event=self.counter);value.setdefault('monotonic_ns',time.monotonic_ns())
   self.file.write((json.dumps(value,allow_nan=False,separators=(',',':'))+'\n').encode())
   return value
 def command(self,argv,label):
  row=self.io.command(argv,'headposture579_'+label,timeout=15)
  self.commands.append(self.io.ref_receipt(row));need(row['exit_code']==0 and not row.get('timed_out',False),'actual owned HDC forward command failed')
  return row
 def start(self):
  need(not self.started and not self.closed,'one fixed source lifecycle');self.started=True
  self.file=(self.output/'wire.jsonl').open('xb',buffering=0)
  with socket.socket() as probe:
   probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
  self.forward=('tcp:'+str(port),'localfilesystem:'+PATH);self.port=port
  self.record('forward_intent',local=self.forward[0],remote=self.forward[1])
  self.command([self.io.hdc,'-t',self.io.target,'fport',*self.forward],'open')
  return self
 def connection(self):
  self.connection_attempts+=1;need(self.connection_attempts<=64,'bounded source connection attempts')
  self.record('connection_intent',attempt=self.connection_attempts)
  stream=socket.socket();stream.settimeout(1)
  with self.lock:self.stream=stream
  try:
   stream.connect(('127.0.0.1',self.port));hello=exact(stream,32)
   magic,version,nonce,sensor,reserved=struct.unpack('<4sI16sII',hello)
   need((magic,version,sensor,reserved)==(b'QHP1',1,268,0) and nonce!=bytes(16),'real HEADPOSTURE handshake required')
   self.sessions+=1;need(self.sessions<=64,'bounded source reconnect count')
   self.record('hello',generation=self.sessions,hex=hello.hex());return stream,nonce,self.sessions
  except BaseException:
   stream.close()
   with self.lock:
    if self.stream is stream:self.stream=None
   raise
 def release(self,stream):
  stream.close()
  with self.lock:
   if self.stream is stream:self.stream=None
 def probe_invalid(self):
  need(self.started and not self.probed and self.thread is None,'one finite boundary batch before positive source')
  previous=None
  for case in INVALID:
   stream,nonce,generation=self.connection()
   try:
    wire=bytearray(struct.pack('<4sI16sQIffff',b'QHF1',1,nonce,1,1,1.,0.,0.,0.))
    if case=='wrong_nonce':wire[8]^=1
    elif case=='zero_nonce':wire[8:24]=bytes(16)
    elif case=='zero_sequence':wire[24:32]=bytes(8)
    elif case=='wrong_version':wire[4:8]=struct.pack('<I',2)
    elif case=='nonfinite':wire[36:40]=struct.pack('<f',float('nan'))
    elif case=='nonunit':wire[36:52]=bytes(16)
    elif case=='zero_order':wire[32:36]=bytes(4)
    elif case=='overflow_order':wire[32:36]=struct.pack('<I',16777216)
    elif case=='old_nonce':wire[8:24]=previous
    start=time.monotonic_ns();stream.sendall(wire);self.record('invalid_frame',generation=generation,case=case,hex=wire.hex(),send_started_ns=start)
    try:
     value=stream.recv(1);need(value==b'','malformed writer received unexpected data');ending='EOF'
    except ConnectionResetError:ending='ECONNRESET'
    self.record('invalid_eof',generation=generation,case=case,result=ending);previous=nonce
   finally:self.release(stream)
  self.probed=True
 def pose(self,*,cycle,index,quaternion):
  need(self.started and self.probed and self.disabled_ns is None and (cycle,index) in ((0,0),(0,1),(1,0),(1,1)),'fixed real media pose window')
  self.io.owner.held_binding(self.io.guest);value=quat(quaternion)
  with self.lock:
   need(not any(p['cycle']==cycle and p['index']==index for p in self.poses) and not self.errors,'duplicate/failed source pose')
   row=dict(cycle=cycle,index=index,quaternion=value,monotonic_ns=time.monotonic_ns(),pose=len(self.poses))
   self.poses.append(row);self.pose_value=value;self.current_pose=row['pose'];self.record('pose',**row)
  if self.thread is None:
   self.thread=threading.Thread(target=self.worker,name='headposture579-original-source',daemon=False);self.thread.start()
  return dict(row)
 def restore(self):
  need(self.thread is not None and self.disabled_ns is None and not self.errors,'active source restoration')
  with self.lock:
   self.pose_value={'w':1.,'x':0.,'y':0.,'z':0.};self.current_pose='baseline';wanted=self.baseline_frames+5;result=self.record('restore')
  deadline=time.monotonic()+1
  while self.baseline_frames<wanted:
   need(not self.errors and time.monotonic()<deadline,'baseline source frames did not actually send');time.sleep(.01)
  return result
 def expect_disabled(self):
  need(self.thread is not None and self.disabled_ns is None,'one public-disable boundary')
  with self.lock:
   need(self.current_pose=='baseline','restore baseline before public disable');self.disabled_ns=time.monotonic_ns();return self.record('expect_disabled')
 def worker(self):
  deadline=time.monotonic()+120;last_send=None
  try:
   while not self.halt.is_set():
    need(time.monotonic()<deadline,'bounded headposture source expired')
    try:stream,nonce,generation=self.connection()
    except (EOFError,ConnectionResetError,BrokenPipeError) as error:
     # A real enable/disable can invalidate a socket during its hello. Retain
     # this, retry finitely, and never classify an incomplete hello as stop proof.
     self.record('connection_invalidated',error=type(error).__name__)
     need(self.disabled_ns is None,'public disable did not close a completed source generation')
     self.halt.wait(.025);continue
    sequence=0
    try:
     while not self.halt.wait(.025):
      need(time.monotonic()<deadline and self.frames<MAX_FRAMES,'bounded source frames/time exceeded')
      with self.lock:
       value=dict(self.pose_value);pose=self.current_pose;self.order+=1;order=self.order
      need(order<=16777215,'exact adapter int24 order exhausted');sequence+=1
      frame=struct.pack('<4sI16sQIffff',b'QHF1',1,nonce,sequence,order,*[value[k] for k in ('w','x','y','z')]);start=time.monotonic_ns()
      try:stream.sendall(frame)
      except OSError as error:
       self.record('send_error',generation=generation,hex=frame.hex(),pose=pose,error=repr(error),send_started_ns=start);raise
      self.frames+=1;last_send=time.monotonic_ns()
      if pose=='baseline':self.baseline_frames+=1
      self.record('frame',generation=generation,hex=frame.hex(),pose=pose,send_started_ns=start)
      # SO_RCVBUF/stream EOF is observed without consuming a fabricated ack.
      import select
      if select.select([stream],[],[],0)[0]:
       ending=stream.recv(1);need(ending==b'','source-only protocol has no returned samples');raise EOFError('actual peer EOF')
    except (EOFError,BrokenPipeError,ConnectionResetError) as error:
     row=self.record('peer_disconnect',generation=generation,error=type(error).__name__,last_send_ns=last_send)
     with self.lock:expected=self.disabled_ns
     if expected is not None:
      need(last_send is not None and expected<=row['monotonic_ns'] and row['monotonic_ns']-last_send<4_000_000_000,'EOF could be unrelated idle expiry')
      self.end=row;return
    finally:self.release(stream)
  except BaseException as error:
   self.errors.append(repr(error));self.record('worker_error',error=repr(error))
   if not isinstance(error,Exception):raise
 def finish(self):
  need(self.disabled_ns is not None,'public disable must be explicitly bracketed')
  failure=None
  try:
   if self.thread is not None:self.thread.join(timeout=4)
   need(self.thread is not None and not self.thread.is_alive() and self.end is not None and not self.errors,'real last-disable EOF/source quiescence absent')
  except BaseException as error:failure=error
  try:result=self.cleanup()
  except BaseException:
   if failure is not None and not isinstance(failure,Exception):raise failure
   raise
  if failure:raise failure
  return result
 def cleanup(self):
  if self.closed:return self.finished
  errors=[];interrupt=None;self.halt.set()
  with self.lock:stream=self.stream
  if stream is not None:
   try:stream.shutdown(socket.SHUT_RDWR)
   except OSError:pass
  try:
   if self.thread is not None:self.thread.join(timeout=3)
  except BaseException as error:
   errors.append(repr(error))
   if not isinstance(error,Exception):interrupt=error
  if self.thread is not None and self.thread.is_alive():errors.append('original source worker not joined; guest cannot be reused')
  if self.forward is not None:
   try:
    self.command([self.io.hdc,'-t',self.io.target,'fport','rm',*self.forward],'remove')
    listing=self.command([self.io.hdc,'-t',self.io.target,'fport','ls'],'absent')
    need(self.forward[0] not in listing['stdout'] and self.forward[1] not in listing['stdout'],'owned forward survived cleanup')
   except BaseException as error:
    errors.append(repr(error))
    if not isinstance(error,Exception):interrupt=error
  self.result.update(closed=not errors,cleanup_errors=errors,last_disable_eof=self.end,disabled_ns=self.disabled_ns)
  if self.file is not None and (self.thread is None or not self.thread.is_alive()):
   self.file.close();self.file=None;self.result['wire']=ref(self.output/'wire.jsonl')
  p=self.output/'source.json'
  # Each cleanup attempt has its own immutable receipt; retries retain failures.
  if p.exists():p=self.output/('source-cleanup-'+str(time.monotonic_ns())+'.json')
  p.write_text(json.dumps(self.result,indent=2,allow_nan=False)+'\n');self.finished=ref(p);self.closed=not errors
  if interrupt is not None:raise interrupt
  if errors:
   from capability578_stage import UnsettledCapability
   raise UnsettledCapability('HEADPOSTURE cleanup uncertain: '+repr(errors))
  return self.finished

def replay(binding,reference,wires):
 """Pure actual source replay; never returns consumed orders or an audio pass."""
 value=json.loads(checked(reference).read_text());io=json.loads(checked(wires).read_text())
 need(set(binding)=={'archive_sha256','boot_id','run_id','target'} and all(value[k]==binding[k] for k in binding) and
  io['closed'] is True and io['boot_id']==binding['boot_id'] and io['archive_sha256']==binding['archive_sha256'] and
  value['closed'] is True and not value['cleanup_errors'] and not value['errors'],'actual original IO/source cleanup/identity failed')
 normalized=[dict(argv=r['argv'],exit_code=r['exit_code'],boot_id=r['boot_id'],timed_out=r['timed_out'],stdout=r['stdout_ref'],stderr=r['stderr_ref']) for r in io['commands']]
 commands=value['commands'];need(len(commands)==3 and all(c in normalized and c['exit_code']==0 and not c['timed_out'] for c in commands),'actual original forward command receipts absent')
 port=commands[0]['argv'][-2];remote='localfilesystem:'+PATH
 need(commands[0]['argv'][-3:]==['fport',port,remote] and commands[1]['argv']==commands[0]['argv'][:-3]+['fport','rm',port,remote] and
  commands[2]['argv']==commands[0]['argv'][:-3]+['fport','ls'],'fixed original fport creation/removal/query differs')
 for c in commands:
  for k in ('stdout','stderr'):checked(c[k])
 need(port not in checked(commands[2]['stdout']).read_text() and remote not in checked(commands[2]['stdout']).read_text(),'actual forward absence differs')
 wire_path=checked(value['wire']);need(wire_path.stat().st_size<=8*1024*1024,'fixed source raw bound exceeded')
 records=[json.loads(line) for line in wire_path.read_bytes().splitlines()]
 need(len(records)<=9000 and [r['event'] for r in records]==list(range(1,len(records)+1)) and all(a['monotonic_ns']<=b['monotonic_ns'] for a,b in zip(records,records[1:])),'raw source history truncated/reordered')
 nonces={};frames={};orders=set();pose_rows=[]
 for r in records:
  if r['kind']=='hello':
   magic,version,nonce,sid,reserved=struct.unpack('<4sI16sII',bytes.fromhex(r['hex']));need((magic,version,sid,reserved)==(b'QHP1',1,268,0) and nonce!=bytes(16) and nonce not in nonces.values(),'fresh native input generation/nonce required');nonces[r['generation']]=nonce
  if r['kind']=='frame':
   data=struct.unpack('<4sI16sQIffff',bytes.fromhex(r['hex']));g=r['generation'];sequence=frames.setdefault(g,[])
   need(data[:4]==(b'QHF1',1,nonces[g],len(sequence)+1) and 0<data[4]<=16777215 and data[4] not in orders and
    all(math.isfinite(x) and abs(x)<=1 for x in data[5:]) and abs(sum(x*x for x in data[5:])-1)<1e-4,'actual wire/header/order/unit pose differs')
   need(r['send_started_ns']<=r['monotonic_ns'],'actual send clock bracket');orders.add(data[4]);sequence.append((r,data))
 for pose in value['poses']:
  found=[(r,f) for rows in frames.values() for r,f in rows if r['pose']==pose['pose']]
  q=quat(pose['quaternion']);need(len(found)>=20 and all(tuple(f[5:])==tuple(q[k] for k in ('w','x','y','z')) for r,f in found),'independent pose did not produce bounded real source frames')
  span=(found[-1][0]['monotonic_ns']-found[0][0]['monotonic_ns'])/1e9
  need(span>=.5 and 35<=(len(found)-1)/span<=50,'actual source must maintain its fixed40Hz pose window')
  pose_rows.append(dict(pose,source_orders=[f[4] for r,f in found],send_monotonic_ns=[r['monotonic_ns'] for r,f in found]))
 need(sum(len(rows) for rows in frames.values())<=MAX_FRAMES,'fixed source frame bound exceeded')
 need([(p['cycle'],p['index']) for p in pose_rows]==[(0,0),(0,1),(1,0),(1,1)] and len({tuple(p['quaternion'][k] for k in ('w','x','y','z')) for p in pose_rows})>=2,'two real cycles/two different source poses required')
 invalid=[r for r in records if r['kind']=='invalid_frame'];need([r['case'] for r in invalid]==list(INVALID),'finite input boundary batch absent')
 for r in invalid:
  need(any(e['kind']=='invalid_eof' and e['generation']==r['generation'] and e['case']==r['case'] and e['result'] in ('EOF','ECONNRESET') for e in records),'actual malformed source EOF absent')
  data=bytes.fromhex(r['hex']);n=nonces[r['generation']];case=r['case'];f=struct.unpack('<4sI16sQIffff',data)
  need((case=='wrong_nonce' and f[2]!=n) or (case=='zero_nonce' and f[2]==bytes(16)) or (case=='zero_sequence' and f[3]==0) or
   (case=='wrong_version' and f[1]==2) or (case=='nonfinite' and not math.isfinite(f[5])) or (case=='nonunit' and f[5:]==(0.,0.,0.,0.)) or
   (case=='zero_order' and f[4]==0) or (case=='overflow_order' and f[4]==16777216) or
   (case=='old_nonce' and f[2] in list(nonces.values())[:-1] and f[2]!=n),'invalid wire case differs')
 end=value['last_disable_eof'];need(end in records and end['kind']=='peer_disconnect' and value['disabled_ns']<=end['monotonic_ns'] and
  0<=end['monotonic_ns']-end['last_send_ns']<4_000_000_000 and any(r['kind']=='restore' and r['monotonic_ns']<=value['disabled_ns'] for r in records),'true last-disable EOF/baseline restoration absent')
 baseline=[f[4] for rows in frames.values() for r,f in rows if r['pose']=='baseline' and f[5:]==(1.,0.,0.,0.)]
 need(len(baseline)>=5,'actual unity baseline source frames absent')
 return {'schema':'headposture579-pure-source-replay/v1','source':reference,'original_io':wires,'binding':binding,'poses':pose_rows,'baseline_source_orders':baseline,
  'generations':{str(k):v.hex() for k,v in nonces.items()},'invalid':invalid,'last_disable_eof':end,'transport_complete':True,
  'consumption_or_audio_behavior_claimed':False,'runtime_pass':False,'first_artifact_behavior_gate_passed':False}
