"""Real SDK caller syntax and actual copy code; synthetic oracle fixtures never prove Recorder runtime."""
from array import array
import copy,importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).parent
SDK=Path(os.environ.get('BATCH_MEDIA_PUBLIC_SDK_INCLUDE','/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0/native/sysroot/usr/include'))
spec=importlib.util.spec_from_file_location('recorder_oracle',HERE/'batch_media_recorder_challenge.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
RUN='0123456789abcdef0123456789abcdef'
def function(s,signature):
 a=s.index(signature);return s[a:s.index('\n}',a)+2]
class Recorder(unittest.TestCase):
 def test_full_public_callers_and_actual_surface_private_input_functions(self):
  flags=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-pthread','-idirafter',str(SDK)]
  subprocess.run(flags+['-fsyntax-only',str(HERE/'batch_media_recorder_probe.cpp'),str(HERE/'batch_media_recorder_hap.cpp')],check=True)
  source=(HERE/'batch_media_recorder_probe.cpp').read_text();constants=source[source.index('constexpr int WIDTH'):source.index('int64_t Now()')]
  harness=(HERE/'fixtures/batch_media/recorder/surface_harness.cpp').read_text().replace('// ACTUAL_CONSTANTS',constants).replace('// ACTUAL_FUNCTIONS',function(source,'bool ReadChallenge(')+'\n'+function(source,'bool Surface('))
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);path=root/'surface.cpp';path.write_text(harness);challenge=root/'input';challenge.write_bytes(bytes([48])*7680);challenge.chmod(0o600)
   subprocess.run(flags+['-fsanitize=address,undefined',str(path),'-o',str(root/'test')],check=True)
   subprocess.run([str(root/'test'),str(challenge)],check=True,timeout=10,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1'))
 def test_fresh_external_audio_and_video_hash_contract(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'challenge';first=oracle.generate(root,RUN);manifest,reference,video=oracle.load_reference(root,RUN)
   self.assertEqual(first,manifest);self.assertEqual(len(reference),96000);self.assertEqual(len(video),7680);self.assertEqual(manifest['audio']['chip_frames'],64)
   other=oracle.generate(Path(temp)/'other',RUN);self.assertNotEqual(first['audio']['sha256'],other['audio']['sha256']);self.assertNotEqual(first['video']['sha256'],other['video']['sha256'])
   with self.assertRaises(ValueError):oracle.generate(root,RUN)
   path=root/first['video']['file'];path.write_bytes(video[:-1])
   with self.assertRaises(ValueError):oracle.load_reference(root,RUN)
 def test_independent_rgb_pixels_reject_frame_replay_silence_and_truncation(self):
  video=bytes(48+(frame+tile)%14*12 for frame in range(120) for tile in range(64));data=bytearray()
  for frame in range(60):
   tiles=video[frame*64:(frame+1)*64]
   for y in range(64):
    for x in range(64):data.extend(bytes([tiles[(y//8)*8+x//8]])*3)
  self.assertEqual(oracle.rgb_content(data,video,1)['maximum_error'],0)
  for bad in [bytes(len(data)),data[:-3],data[12288:]+data[:12288],data[:12288]*60]:
   with self.assertRaises(ValueError):oracle.rgb_content(bad,video,1)
 def test_packet_pts_real_input_pause_and_stream_contract(self):
  frames=[{'frame':i,'phase':1 if i<30 else 2,'input_ns':10000000000+i*1000000000//30+(0 if i<30 else 300000000)} for i in range(60)]
  steps=[{'name':'pause','monotonic_ns':11000000000},{'name':'resume','monotonic_ns':11300000000}];pause={'before_ns':11000000000,'after_ns':11300000000}
  probe={'streams':[{'index':0,'codec_type':'video','codec_name':'h264','width':64,'height':64},{'index':1,'codec_type':'audio','codec_name':'aac','sample_rate':'48000','channels':2}],
   'frames':[{'media_type':'video','best_effort_timestamp_time':str(i/30)} for i in range(60)],
   'packets':[{'stream_index':0,'pts_time':str(i/30),'dts_time':str(i/30),'duration_time':str(1/30)} for i in range(60)]+[{'stream_index':1,'pts_time':str(i*1024/48000),'dts_time':str(i*1024/48000),'duration_time':str(1024/48000)} for i in range(94)]}
  self.assertEqual(len(oracle.timeline(probe,frames,steps,pause)['video_pts']),60)
  for variant in range(5):
   bad=copy.deepcopy(probe)
   if variant==0:bad['streams'][1]['channels']=1
   if variant==1:bad['frames'].pop()
   if variant==2:bad['frames'][30]['best_effort_timestamp_time']='1.3'
   if variant==3:bad['packets'][1]['dts_time']='0'
   if variant==4:bad['streams'][0]['codec_name']='hevc'
   with self.assertRaises(ValueError):oracle.timeline(bad,frames,steps,pause)
 def test_lossy_pcm_unit_fixture_still_requires_fresh_stereo_content(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'challenge';oracle.generate(root,RUN);_,reference,_=oracle.load_reference(root,RUN)
   values=array('h',(int(reference[((i+1937)%48000)*2+c]*0.93)+(i%5-2)*30 for i in range(32768) for c in range(2)))
   self.assertEqual(oracle.pcm.phase_content(values.tobytes(),reference)['continuity_error_frames'],0)
   with self.assertRaises(ValueError):oracle.pcm.phase_content(bytes(len(values)*2),reference)
if __name__=='__main__':unittest.main(verbosity=2)
