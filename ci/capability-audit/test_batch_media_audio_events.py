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
   subprocess.run([str(root/'test'),str(root)],check=True,timeout=10,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
 def test_actual_fresh_request_PCM_reply_and_live_callback_under_sanitizers(self):
  source=(HERE/'batch_media_audio_event_probe.cpp').read_text();prefix=source[:source.index('namespace {')]
  decl=source[source.index('constexpr size_t CAPACITY'):source.index('int64_t Now()')].replace('constexpr const char *PRIVATE="/data/storage/el2/base/files/";','const char *PRIVATE=nullptr;')
  keys=['int64_t Now()', 'void Read(', 'void Interrupt(', 'void Error(', 'bool Snapshot(', 'bool WritePrivate(', 'bool Nonce(', 'bool Ack(', 'bool SnapshotRequest(', 'bool WriteSnapshotPrivate(', 'bool ReadFreshQueries(', 'int FreshError(', 'int FreshQueryError(', 'int FreshSnapshotReply(', 'bool Handshake(', 'bool Persist(']
  actual='\n'.join(function(source,key) for key in keys)
  fake=r'''
#include <cassert>
#include <fstream>
#include <iterator>
#include <thread>
static std::atomic<int> fakeState{AUDIOSTREAM_STATE_RUNNING},fakeSource{AUDIOSTREAM_SOURCE_TYPE_MIC},fakeRate{48000},fakeChannels{2},fakeFormat{AUDIOSTREAM_SAMPLE_S16LE},failGetter{0},getterCalls{0};
static std::atomic<int64_t> fakeFrames{100000},fakePosition{100000};
static std::atomic<bool> wrongOwner{false};
static uid_t ProbeUid(){return wrongOwner.load()?::getuid()+1: ::getuid();}
OH_AudioStream_Result OH_AudioCapturer_GetCurrentState(OH_AudioCapturer*,OH_AudioStream_State *out){++getterCalls;if(failGetter==1)return AUDIOSTREAM_ERROR_ILLEGAL_STATE;*out=static_cast<OH_AudioStream_State>(fakeState.load());return AUDIOSTREAM_SUCCESS;}
OH_AudioStream_Result OH_AudioCapturer_GetFramesRead(OH_AudioCapturer*,int64_t *out){++getterCalls;if(failGetter==2)return AUDIOSTREAM_ERROR_ILLEGAL_STATE;*out=fakeFrames;return AUDIOSTREAM_SUCCESS;}
OH_AudioStream_Result OH_AudioCapturer_GetTimestamp(OH_AudioCapturer*,clockid_t,int64_t *position,int64_t *stamp){++getterCalls;if(failGetter==3)return AUDIOSTREAM_ERROR_ILLEGAL_STATE;*position=fakePosition;timespec time{};assert(clock_gettime(CLOCK_MONOTONIC,&time)==0);*stamp=static_cast<int64_t>(time.tv_sec)*1000000000+time.tv_nsec;return AUDIOSTREAM_SUCCESS;}
OH_AudioStream_Result OH_AudioCapturer_GetCapturerInfo(OH_AudioCapturer*,OH_AudioStream_SourceType *out){++getterCalls;if(failGetter==4)return AUDIOSTREAM_ERROR_ILLEGAL_STATE;*out=static_cast<OH_AudioStream_SourceType>(fakeSource.load());return AUDIOSTREAM_SUCCESS;}
OH_AudioStream_Result OH_AudioCapturer_GetSamplingRate(OH_AudioCapturer*,int32_t *out){++getterCalls;if(failGetter==5)return AUDIOSTREAM_ERROR_ILLEGAL_STATE;*out=fakeRate;return AUDIOSTREAM_SUCCESS;}
OH_AudioStream_Result OH_AudioCapturer_GetChannelCount(OH_AudioCapturer*,int32_t *out){++getterCalls;if(failGetter==6)return AUDIOSTREAM_ERROR_ILLEGAL_STATE;*out=fakeChannels;return AUDIOSTREAM_SUCCESS;}
OH_AudioStream_Result OH_AudioCapturer_GetSampleFormat(OH_AudioCapturer*,OH_AudioStream_SampleFormat *out){++getterCalls;if(failGetter==7)return AUDIOSTREAM_ERROR_ILLEGAL_STATE;*out=static_cast<OH_AudioStream_SampleFormat>(fakeFormat.load());return AUDIOSTREAM_SUCCESS;}
#define getuid ProbeUid
'''
  harness=prefix+decl+fake+actual+r'''
#undef getuid
static std::string ReadFile(const std::string &name){std::ifstream in(name,std::ios::binary);return {std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>()};}
static bool Exists(const std::string &name){struct stat info{};return lstat(name.c_str(),&info)==0;}
static std::string Run(unsigned index){char text[33]{};assert(snprintf(text,sizeof(text),"%032x",index)==32);return text;}
static void Reset(Context &c,int phase){c.size=0;c.phase=phase;c.invalid=0;c.chunks.clear();c.events.clear();cancelled=false;fakeState=AUDIOSTREAM_STATE_RUNNING;fakeSource=AUDIOSTREAM_SOURCE_TYPE_MIC;fakeRate=48000;fakeChannels=2;fakeFormat=AUDIOSTREAM_SAMPLE_S16LE;fakeFrames=100000;fakePosition=100000;failGetter=0;wrongOwner=false;}
static void Audio(Context &c,size_t size,uint8_t seed){std::vector<uint8_t> bytes(size);for(size_t i=0;i<size;++i)bytes[i]=static_cast<uint8_t>(seed+i%173);fakeFrames+=size/4;fakePosition+=size/4;Read(nullptr,&c,bytes.data(),static_cast<int>(bytes.size()));}
static bool WaitFor(const std::string &path,const std::string &needle){for(int i=0;i<100;++i){if(ReadFile(path).find(needle)!=std::string::npos)return true;usleep(10000);}return false;}
int main(int argc,char **argv){assert(argc==2);const std::string directory=std::string(argv[1])+"/";PRIVATE=directory.c_str();
 const std::string nonce="0123456789abcdef0123456789abcdef",input=nonce+"\n";bool pending=false;
 const std::string request=directory+"request";assert(!SnapshotRequest(request,nonce,pending)&&pending);
 assert(WritePrivate(request,input.data(),input.size()));assert(SnapshotRequest(request,nonce,pending)&&!pending);
 assert(!SnapshotRequest(request,std::string(32,'f'),pending)&&!pending);wrongOwner=true;assert(!SnapshotRequest(request,nonce,pending));wrongOwner=false;
 assert(chmod(request.c_str(),0400)==0);assert(!SnapshotRequest(request,nonce,pending));assert(chmod(request.c_str(),0644)==0);assert(!SnapshotRequest(request,nonce,pending));assert(chmod(request.c_str(),0600)==0);
 assert(symlink(request.c_str(),(request+"-link").c_str())==0);assert(!SnapshotRequest(request+"-link",nonce,pending));
 assert(mkfifo((request+"-fifo").c_str(),0600)==0);assert(!SnapshotRequest(request+"-fifo",nonce,pending));
 assert(WritePrivate(request+"-short",input.data(),32));assert(!SnapshotRequest(request+"-short",nonce,pending));
 assert(WritePrivate(request+"-long",(input+"x").data(),34));assert(!SnapshotRequest(request+"-long",nonce,pending));
 Context c;OH_AudioCapturer *capturer=reinterpret_cast<OH_AudioCapturer*>(1);FILE *out=tmpfile();assert(out);
 for(int phase:{1,0}){Reset(c,phase);Audio(c,192000,11);const std::string run=Run(10+phase),action=phase?"focus_begin":"contender_start",base=directory+"audio-event-"+run+"-"+action;
  FreshSnapshot fresh;const auto created=Now();assert(FreshSnapshotReply(out,run.c_str(),action.c_str(),base,nonce,created,capturer,c,fresh)==0&&!fresh.requested);
  assert(WritePrivate(base+"-snapshot-request",input.data(),input.size()));assert(FreshSnapshotReply(out,run.c_str(),action.c_str(),base,nonce,created,capturer,c,fresh)==0&&fresh.requested);assert(fresh.offset==192000);
  usleep(3000);assert(FreshSnapshotReply(out,run.c_str(),action.c_str(),base,nonce,created,capturer,c,fresh)==0); // a timer cannot republish old PCM
  Audio(c,48000,91);assert(FreshSnapshotReply(out,run.c_str(),action.c_str(),base,nonce,created,capturer,c,fresh)==0);
  Audio(c,48000,127);assert(FreshSnapshotReply(out,run.c_str(),action.c_str(),base,nonce,created,capturer,c,fresh)==1&&fresh.replied);
  const std::string pcm=directory+"audio-event-"+run+"-"+action+"-snapshot-"+nonce+".pcm",reply=base+"-snapshot-reply.json";
  assert(ReadFile(pcm)==std::string(reinterpret_cast<const char*>(c.bytes.data()+192000),96000));const std::string saved=ReadFile(reply);const int calls=getterCalls;
  Audio(c,96000,77);assert(FreshSnapshotReply(out,run.c_str(),action.c_str(),base,nonce,created,capturer,c,fresh)==1);assert(ReadFile(reply)==saved&&getterCalls==calls); // one request/reply only
 }
 // All failure cases execute the actual handler. Getter values are controlled dependencies, never real audio backend proof.
 for(int fault=0;fault<20;++fault){Reset(c,1);Audio(c,192000,11);const std::string run=Run(100+fault),action="focus_begin",base=directory+"audio-event-"+run+"-"+action;
  FreshSnapshot fresh;const auto created=Now();assert(WritePrivate(base+"-snapshot-request",input.data(),input.size()));assert(FreshSnapshotReply(out,run.c_str(),action.c_str(),base,nonce,created,capturer,c,fresh)==0);
  Audio(c,96000,91);
  if(fault==0)c.invalid=1;else if(fault==1)c.phase=2;else if(fault==2)c.chunks.back().time=fresh.seen;
  else if(fault==3)c.chunks.back().offset=c.size+1;else if(fault==4)c.chunks.back().length=-1;
  else if(fault==5){fakeFrames=fresh.base.frames;fakePosition=fresh.base.position;}
  else if(fault==6)fakeState=AUDIOSTREAM_STATE_STOPPED;else if(fault==7)fakeSource=AUDIOSTREAM_SOURCE_TYPE_VOICE_COMMUNICATION;
  else if(fault==8)fakeRate=44100;else if(fault==9)fakeChannels=1;else if(fault==10)fakeFormat=AUDIOSTREAM_SAMPLE_F32LE;
  else if(fault==11)cancelled=true;else if(fault==12)c.chunks.resize(fresh.chunks);
  else if(fault==13)c.chunks.back().time=Now()+1000000000LL;
  else if(fault==14){const std::string pcm=directory+"audio-event-"+run+"-"+action+"-snapshot-"+nonce+".pcm";assert(WritePrivate(pcm,"old",3));}
  else if(fault==15)assert(WritePrivate(base+"-snapshot-reply.json","old",3));
  else if(fault==16)c.size=c.bytes.size()+1;else if(fault==17)c.chunks.back().phase=0;else if(fault==19){++c.size;++c.chunks.back().offset;}
  const int64_t start=fault==18?Now()-15000000000LL:created;
  assert(FreshSnapshotReply(out,run.c_str(),action.c_str(),base,nonce,start,capturer,c,fresh)==-1&&!fresh.replied);
  if(fault==14)assert(ReadFile(directory+"audio-event-"+run+"-"+action+"-snapshot-"+nonce+".pcm")=="old");
  if(fault==15)assert(ReadFile(base+"-snapshot-reply.json")=="old");
 }
 for(int getter=1;getter<=7;++getter){Reset(c,1);Audio(c,192000,11);const std::string run=Run(200+getter),base=directory+"audio-event-"+run+"-focus_begin";FreshSnapshot fresh;
  assert(WritePrivate(base+"-snapshot-request",input.data(),input.size()));failGetter=getter;
  assert(FreshSnapshotReply(out,run.c_str(),"focus_begin",base,nonce,Now(),capturer,c,fresh)==-1&&!fresh.replied);
 }
 assert(fclose(out)==0);
 // Actual Snapshot last_callback is null before events and exactly matches final Persist's real callback details afterwards.
 Reset(c,1);Audio(c,192000,7);const std::string callbackLog=directory+"callback.log";out=fopen(callbackLog.c_str(),"wx");assert(out);
 assert(Snapshot(out,Run(300).c_str(),capturer,c,"await_action"));Interrupt(nullptr,&c,AUDIOSTREAM_INTERRUPT_FORCE,AUDIOSTREAM_INTERRUPT_HINT_STOP);
 assert(Snapshot(out,Run(300).c_str(),capturer,c,"await_action"));assert(Persist(out,Run(300).c_str(),1,c));assert(fclose(out)==0);
 // Actual Handshake integration: legacy/other-action behavior, premature ACK rejection, cancellation, and fresh reply before ACK.
 for(int scenario=0;scenario<5;++scenario){Reset(c,1);Audio(c,192000,23);const std::string run=Run(400+scenario),action=scenario==1?"revoke":"focus_begin",base=directory+"audio-event-"+run+"-"+action,log=directory+"handshake-"+std::to_string(scenario)+".log";
  out=fopen(log.c_str(),"wx");assert(out);std::atomic<bool> done{false};bool accepted=false;
  std::thread worker([&]{accepted=Handshake(out,run.c_str(),action.c_str(),capturer,c);done=true;});
  assert(WaitFor(base+"-ready.json","\"nonce\":\""));const std::string ready=ReadFile(base+"-ready.json");const size_t where=ready.find("\"nonce\":\"")+9;const std::string key=ready.substr(where,32),ack=key+"\n";assert(key.size()==32);
  if(scenario==0)assert(WritePrivate(base+"-ack",ack.data(),ack.size()));
  else if(scenario==1){assert(WritePrivate(base+"-snapshot-request","bad",3));assert(WritePrivate(base+"-ack",ack.data(),ack.size()));}
  else if(scenario==2){assert(WritePrivate(base+"-snapshot-request",ack.data(),ack.size()));assert(WritePrivate(base+"-ack",ack.data(),ack.size()));}
  else if(scenario==3){assert(WritePrivate(base+"-snapshot-request",ack.data(),ack.size()));assert(WaitFor(log,"event_fresh_request"));cancelled=true;}
  else {assert(WritePrivate(base+"-snapshot-request",ack.data(),ack.size()));assert(WaitFor(log,"event_fresh_request"));Audio(c,96000,131);
   assert(WaitFor(log,"event_fresh_reply"));assert(!done);assert(WritePrivate(base+"-ack",ack.data(),ack.size()));}
  worker.join();assert(fclose(out)==0);assert(accepted==(scenario==0||scenario==1||scenario==4));
  if(scenario==0||scenario==1)assert(!Exists(base+"-snapshot-reply.json"));
 }
 printf("actual fresh request/PCM/reply and Snapshot callbacks passed: strict nonce/owner/mode/size/NOFOLLOW/FIFO; new-callback half-second;20 refusal/collision/deadline cases;7 getter failures; one reply; legacy/early ACK/cancel/positive handshake. Controlled getters are not runtime proof.\n");
}
'''
  with tempfile.TemporaryDirectory(prefix='batch-media-fresh-snapshot-') as temp:
   root=Path(temp);path=root/'fresh.cpp';path.write_text(harness)
   flags=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-pthread','-idirafter',str(SDK),'-fsanitize=address,undefined']
   subprocess.run(flags+[str(path),'-o',str(root/'test')],check=True)
   subprocess.run([str(root/'test'),str(root)],check=True,timeout=12,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
   for phase in [0,1]:
    action='focus_begin' if phase else 'contender_start';run=f'{10+phase:032x}';reply=json.loads((root/f'audio-event-{run}-{action}-snapshot-reply.json').read_text())
    self.assertEqual(reply['request_nonce'],reply['ready_nonce']);self.assertEqual(reply['phase'],phase);self.assertEqual(reply['bytes'],96000)
    self.assertEqual(reply['offset'],reply['requested_offset']);self.assertEqual(reply['end_offset']-reply['offset'],96000)
    self.assertGreater(reply['first_callback_ns'],reply['request_seen_ns']);self.assertGreaterEqual(reply['last_callback_ns'],reply['first_callback_ns'])
    self.assertGreaterEqual(reply['copy_before_ns'],reply['last_callback_ns']);self.assertGreaterEqual(reply['query_before_ns'],reply['copy_after_ns']);self.assertGreater(reply['frames'],reply['request_frames'])
    self.assertEqual((root/reply['pcm_basename']).stat().st_mode&0o7777,0o600)
   rows=[json.loads(line) for line in (root/'callback.log').read_text().splitlines()];snapshots=[r for r in rows if r['type']=='event_snapshot'];persisted=next(r for r in rows if r['type']=='event_callback')
   self.assertIsNone(snapshots[0]['last_callback']);self.assertEqual(snapshots[1]['last_callback'],{key:persisted[key] for key in ['kind','code','hint','monotonic_ns']})
   self.assertEqual((persisted['kind'],persisted['code'],persisted['hint']),(1,0,3))

 def test_existing_oracle_accepts_extra_fresh_reply_observations_without_closure(self):
  for mode in [1,2]:
   with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);rows,results,identity,challenge=self.prepare(root,mode)
    rows.insert(-1,{'type':'event_fresh_reply','run_id':RUN,'action':'focus_begin' if mode==1 else 'contender_start','phase':1 if mode==1 else 0,'request_nonce':'a'*32,'persisted':True})
    results.write_text(''.join(json.dumps(r)+'\n' for r in rows));report=self.verify(root,results,identity,challenge,mode)
    self.assertEqual(report['closed_requirements'],0);self.assertTrue(report['external_token_or_second_app_policy_evidence_required'])

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
