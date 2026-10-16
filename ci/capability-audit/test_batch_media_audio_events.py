"""Actual public SDK/body tests and explicit synthetic event oracle fixtures; never backend proof."""
from array import array
import copy,importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).parent
SDK=Path(os.environ.get('BATCH_MEDIA_PUBLIC_SDK_INCLUDE','/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0/native/sysroot/usr/include'))
spec=importlib.util.spec_from_file_location('audio_events_diagnostic',HERE/'batch_media_audio_event_challenge.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
RUN='0123456789abcdef0123456789abcdef'
def function(s,key):
 a=s.index(key);return s[a:s.index('\n}',a)+2]
class Events(unittest.TestCase):
 def test_actual_public_sdk_callers_nonce_ack_and_pcm_callback_boundaries(self):
  flags=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-pthread','-idirafter',str(SDK)]
  subprocess.run(flags+['-fsyntax-only',str(HERE/'batch_media_audio_event_probe.cpp'),str(HERE/'batch_media_audio_event_hap.cpp')],check=True)
  source=(HERE/'batch_media_audio_event_probe.cpp').read_text();prefix=source[:source.index('namespace {')];decl=source[source.index('constexpr size_t CAPACITY'):source.index('int64_t Now()')]
  functions='\n'.join(function(source,key) for key in ['int64_t Now()', 'void Read(', 'void Interrupt(', 'void Error(', 'bool WritePrivate(', 'bool Nonce(', 'bool Ack('])
  functions+='\n'+'\n'.join(line for line in source.splitlines() if line.startswith('extern "C" void ') and 'BatchMediaAudioEventProbe()' in line)
  harness=prefix+decl+functions+r'''
#include <cassert>
int main(int argc,char **argv){assert(argc==2);assert(std::string(PRIVATE)=="/data/storage/el2/base/files/");CancelBatchMediaAudioEventProbe();assert(cancelled.load());PrepareBatchMediaAudioEventProbe();assert(!cancelled.load());Context context;uint8_t data[9]={1,2,3,4,5,6,7,8,9};
Read(nullptr,&context,data+1,8);assert(context.size==8&&context.chunks.size()==1&&context.chunks[0].phase==1);for(int i=0;i<8;++i)assert(context.bytes[i]==i+2);
Read(nullptr,&context,nullptr,8);Read(nullptr,&context,data,0);Read(nullptr,&context,data,-1);Read(nullptr,&context,data,7);assert(context.invalid==4&&context.size==8);
context.size=CAPACITY-4;Read(nullptr,&context,data,4);assert(context.size==CAPACITY);Read(nullptr,&context,data,4);assert(context.invalid==5);
Interrupt(nullptr,&context,AUDIOSTREAM_INTERRUPT_FORCE,AUDIOSTREAM_INTERRUPT_HINT_STOP);Error(nullptr,&context,AUDIOSTREAM_ERROR_ILLEGAL_STATE);assert(context.events.size()==2&&context.events[0].kind==1&&context.events[0].code==0&&context.events[0].hint==3&&context.events[1].kind==2);
context.events.resize(MAX_EVENTS);Error(nullptr,&context,AUDIOSTREAM_ERROR_ILLEGAL_STATE);assert(context.invalid==6);
std::string nonce,other;assert(Nonce(nonce)&&Nonce(other)&&nonce.size()==32&&other.size()==32&&nonce!=other);bool pending=false;const std::string path=std::string(argv[1])+"/fresh-ack";
assert(!Ack(path,nonce,pending)&&pending);std::string content=nonce+"\n";assert(WritePrivate(path,content.data(),content.size()));assert(Ack(path,nonce,pending)&&!pending);assert(!Ack(path,other,pending)&&!pending);assert(!WritePrivate(path,content.data(),content.size()));
assert(chmod(path.c_str(),0644)==0);assert(!Ack(path,nonce,pending));assert(chmod(path.c_str(),0600)==0);
const std::string linked=path+"-linked";assert(symlink(path.c_str(),linked.c_str())==0);assert(!Ack(linked,nonce,pending));
printf("actual PCM/interrupt/error functions and genuine entropy/fresh nonce/ack/mode/no-overwrite/NOFOLLOW passed\n");}
'''
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);path=root/'events.cpp';path.write_text(harness)
   subprocess.run(flags+['-fsanitize=address,undefined',str(path),'-o',str(root/'test')],check=True)
   subprocess.run([str(root/'test'),str(root)],check=True,timeout=10,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1'))
 def prepare(self,root,mode):
  challenge=root/'challenge';oracle.pcm.generate(challenge,RUN);_,reference=oracle.pcm.load_reference(challenge/'challenge.json',challenge/'challenge.pcm',RUN)
  start=10000000000;ready_time=start+1300000000;ack_time=ready_time+200000000
  rows=[{'type':'event_identity','run_id':RUN,'mode':mode,'uid':20010011,'euid':20010011}]
  def add(event_type,**values):rows.append(dict(type=event_type,run_id=RUN,**values))
  steps=['create','rate','channels','format','encoding','source','read_callback','interrupt_callback','error_callback','generate','start']
  for index,name in enumerate(steps):add('event_step',name=name,actual=0,monotonic_ns=start+index*1000)
  add('event_start_interval',actual=0,before_ns=start,after_ns=start+1000)
  signals=['revoke'] if mode==0 else ['focus_begin','focus_end'] if mode==1 else ['contender_start','contender_stop']
  for index,action in enumerate(signals):
   nonce=('a' if index==0 else 'b')*32;add('event_ready',action=action,nonce=nonce,monotonic_ns=ready_time+(index-(1 if mode==2 else 0))*(2000000000 if mode==2 else 1200000000));add('event_ack',action=action,nonce=nonce,monotonic_ns=ack_time+(index-(1 if mode==2 else 0))*(2000000000 if mode==2 else 1200000000))
  for i in range(50):
   t=start+(220+i*20)*1000000;add('event_snapshot',point='baseline',phase=1,state_result=0,state=2,frames_result=0,timestamp_result=0,position=(220+i*20)*48,timestamp_ns=t,invalid=0,before_ns=t,after_ns=t+1000)
  data=bytearray();chunks=[]
  def audio(phase,count,clock,source):
   values=array('h',(reference[((i+source)%48000)*2+c] for i in range(count) for c in range(2)));part=values.tobytes()
   for byte in range(0,len(part),1920):chunks.append({'type':'event_chunk','run_id':RUN,'offset':len(data)+byte,'bytes':min(1920,len(part)-byte),'phase':phase,'monotonic_ns':clock+(byte//4+480)*1000000000//48000})
   data.extend(part)
  audio(1,57600,start,777)
  if mode in [0,1]:
   for i in range(75 if mode==0 else 25):add('event_snapshot',point='after_revoke' if mode==0 else 'interrupted',phase=2,state_result=0,state=3,frames_result=0,frames=57600,before_ns=ack_time+(i+1)*20000000,after_ns=ack_time+(i+1)*20000000+1000)
  if mode==0:add('event_restart_after_revoke',actual=2,monotonic_ns=ack_time+1600000000)
  if mode==1:
   add('event_callback',kind=1,code=0,hint=3,monotonic_ns=ready_time+100000000);add('event_step',name='restart_after_focus',actual=0,monotonic_ns=ack_time+1200000000);audio(3,48000,ack_time+1200000000,12345)
  if mode==2:
   primer_start=start-2000000000
   for index,name in enumerate(steps):add('event_primer_step',name=name,actual=0,monotonic_ns=primer_start+index*1000)
   for index,name in enumerate(['stop','release','destroy']):add('event_primer_step',name=name,actual=0,monotonic_ns=start-400000000+index*1000)
   for i in range(50):
    t=primer_start+(220+i*20)*1000000;add('event_snapshot',point='primer_baseline',phase=0,state_result=0,state=2,frames_result=0,timestamp_result=0,position=(220+i*20)*48,timestamp_ns=t,invalid=0,before_ns=t,after_ns=t+1000)
   primer=array('h',(reference[((i+17159)%48000)*2+c] for i in range(76800) for c in range(2))).tobytes()
   for byte in range(0,len(primer),1920):add('event_primer_chunk',offset=byte,bytes=min(1920,len(primer)-byte),phase=0,monotonic_ns=primer_start+(byte//4+480)*1000000000//48000)
   name=f'audio-event-{RUN}-mode2-primer-full.pcm';(root/name).write_bytes(primer);add('event_primer_pcm',basename=name,bytes=len(primer),persisted=True,invalid=0)
   name=f'audio-event-{RUN}-mode2-primer.pcm';(root/name).write_bytes(primer[:57600*4]);add('event_primer_checkpoint',basename=name,bytes=57600*4,persisted=True,monotonic_ns=start-700000000)
  add('event_step',name='release',actual=0,monotonic_ns=start+7000000000);add('event_step',name='destroy',actual=0,monotonic_ns=start+7100000000)
  checkpoint_name=f'audio-event-{RUN}-mode{mode}-baseline.pcm';checkpoint=bytes(data[:57600*4]);(root/checkpoint_name).write_bytes(checkpoint);add('event_checkpoint',basename=checkpoint_name,bytes=len(checkpoint),persisted=True,monotonic_ns=ready_time)
  rows.extend(chunks);name=f'audio-event-{RUN}-mode{mode}.pcm';(root/name).write_bytes(data);add('event_pcm',basename=name,bytes=len(data),persisted=True,invalid=0)
  add('event_summary',mode=mode,candidate_complete=True,token_PCM_and_focus_verification_required=True)
  results=root/'results.log';results.write_text(''.join(json.dumps(r)+'\n' for r in rows));identity=root/'identity.json';identity.write_text(json.dumps({'applicationInfo':{'uid':20010011,'isSystemApp':False,'appPrivilegeLevel':'normal'}}))
  return rows,results,identity,challenge
 def verify(self,root,results,identity,challenge,mode):return oracle.verify(results,root,challenge/'challenge.json',challenge/'challenge.pcm',identity,RUN,mode)
 def test_revoke_and_real_focus_protocol_diagnostic_fixtures(self):
  for mode in [0,1,2]:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
    root=Path(temp);_,results,identity,challenge=self.prepare(root,mode);report=self.verify(root,results,identity,challenge,mode)
    self.assertEqual(report['closed_requirements'],0);self.assertTrue(report['external_token_or_second_app_policy_evidence_required'])
 def test_primer_missing_silence_counter_only_and_stopped_are_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);rows,results,identity,challenge=self.prepare(root,2)
   for event,key,value in [('event_primer_step','actual',2),('event_snapshot','state',3),('event_primer_checkpoint','persisted',False),('event_primer_chunk','bytes',0)]:
    bad=copy.deepcopy(rows);next(r for r in bad if r['type']==event and (event!='event_snapshot' or r.get('point')=='primer_baseline'))[key]=value;results.write_text(''.join(json.dumps(r)+'\n' for r in bad))
    with self.assertRaises(ValueError):self.verify(root,results,identity,challenge,2)
   results.write_text(''.join(json.dumps(r)+'\n' for r in rows));path=root/f'audio-event-{RUN}-mode2-primer.pcm';path.write_bytes(bytes(path.stat().st_size))
   with self.assertRaises(ValueError):self.verify(root,results,identity,challenge,2)
 def test_counter_silence_bad_nonce_missing_focus_and_denied_restart_rejected(self):
  for mode in [0,1]:
   with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);rows,results,identity,challenge=self.prepare(root,mode);path=root/f'audio-event-{RUN}-mode{mode}.pcm';data=path.read_bytes()
    path.write_bytes(bytes(len(data)))
    with self.assertRaises(ValueError):self.verify(root,results,identity,challenge,mode)
    path.write_bytes(data)
    for event,key,value in [('event_ack','nonce','f'*32),('event_summary','candidate_complete',False),('event_snapshot','state',3)]+([('event_restart_after_revoke','actual',0)] if mode==0 else [('event_callback','hint',0)]):
     bad=copy.deepcopy(rows);next(r for r in bad if r['type']==event)[key]=value;results.write_text(''.join(json.dumps(r)+'\n' for r in bad))
     with self.assertRaises(ValueError):self.verify(root,results,identity,challenge,mode)
if __name__=='__main__':unittest.main(verbosity=2)
