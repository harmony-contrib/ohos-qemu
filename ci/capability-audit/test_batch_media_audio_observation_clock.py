"""Root host counterexamples/native controlled ALSA; never guest/audio evidence."""
import copy
import errno
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

import batch_media_audio_observation_clock as clock
from test_batch_media_alsa_inject import STUB
from batch_media_audio_haptic_project import record

ROOT=Path(__file__).resolve().parents[2]
REMOTE='/data/local/tmp/qemu-mic-'+'a'*32
MARKER='__PCM_CHILD_EXIT_'+'b'*32+'__='
HARDWARE=(' 0 [AudioPCI       ]: ENS1370 - Ensoniq AudioPCI\n'
 '00-01: ES1370/2 : ES1370 DAC1 : playback 1\nstate: RUNNING\nowner_pid   : 123\n'
 'access: RW_INTERLEAVED\nformat: S16_LE\nchannels: 2\nrate: 44100 (44100/1)\n')
READY=dict(event='clock_ready',pid=123,uid=0,device=clock.DEVICE,rate=44100,channels=2)
END=dict(event='clock_end',reason='owned_sigterm',written_frames=16384,drop_rc=0,close_rc=0)


class ClockProtocol(unittest.TestCase):
 def test_failed_guest_cleanup_still_reaps_only_owned_hdc_leader_and_preserves_files(self):
  with tempfile.TemporaryDirectory() as temporary:
   log=Path(temporary)/'native.log';log.write_text('HOST failure fixture')
   events=[]
   class Process:
    count=0
    def wait(self,timeout):
     self.count+=1
     if self.count==1:raise subprocess.TimeoutExpired('owned HDC',timeout)
     return -15
    def terminate(self):events.append('terminate-owned-leader')
   def observe(script,label):
    events.append(label);raise ValueError('guest unavailable')
   owner=clock.ObserverClock.__new__(clock.ObserverClock)
   owner.collector=SimpleNamespace(observe=observe,persist=lambda:None)
   owner.row=dict(remote=REMOTE,log_path=str(log));owner.created=True;owner.process=Process();owner.stream=log.open('ab')
   with self.assertRaisesRegex(ValueError,'guest clock cleanup unproved'):owner.dispose()
   self.assertEqual(['emergency-only-owned-clock','terminate-owned-leader'],events)
   self.assertIsNone(owner.process);self.assertIsNone(owner.stream);self.assertTrue(owner.created)
   self.assertNotIn('emergency_removed',owner.row)

 def test_terminal_record_rejects_timeout_failed_drop_or_close_and_false_status(self):
  body=lambda r,e:json.dumps(r)+'\n'+json.dumps(e)+'\n\n'+MARKER+'0\n'
  self.assertEqual((READY,END),clock.log_rows(body(READY,END),MARKER,0))
  for field,value in [('reason','time_bound'),('drop_rc',-5),('close_rc',-5),('written_frames',8191),('close_rc',False)]:
   with self.subTest(field=field),self.assertRaises(ValueError):clock.log_rows(body(READY,{**END,field:value}),MARKER,0)
  for code in [False,1]:
   with self.subTest(code=code),self.assertRaises(ValueError):clock.log_rows(body(READY,END),MARKER,code)
  for raw in [body(READY,END)+'trailing',body(READY,END).replace('0\n','1\n'),json.dumps(READY)+'\n\n'+MARKER+'0\n']:
   with self.assertRaises(ValueError):clock.log_rows(raw,MARKER,0)

 def test_complete_actual_shaped_proof_must_bracket_original_capture_and_owned_stop(self):
  with tempfile.TemporaryDirectory() as temporary:
   directory=Path(temporary);observations={};indexes={}
   def put(raw,script):
    p=directory/(str(len(observations))+'.raw');p.write_text(raw);r=record(p);observations[p.as_posix()]=(raw,script);indexes[p.as_posix()]=len(indexes);return r
   row=dict(remote=REMOTE,marker=MARKER,identity=dict(pid=123,starttime=456),argv=['hdc','-t','127.0.0.1:7','shell',clock.wrapper(REMOTE,MARKER)],host_exit_code=0,started_ns=1,ready_ns=2,stop_requested_ns=5,finished_ns=6)
   identity='123\n456\n'+REMOTE+'/alsa_inject\n456\n0 0 0 0'
   for suffix in ('before','after'):
    row['identity_'+suffix]=put(identity,clock.identity_script(REMOTE));row['hardware_'+suffix]=put(HARDWARE,clock.HARDWARE)
   for key,script in [('stop',clock.stop_script(REMOTE,123)),('gone',clock.cleanup_producer_shell(REMOTE)),('removed',clock.remove_script(REMOTE))]:row[key]=put('',script)
   row['log']=put(json.dumps(READY)+'\n'+json.dumps(END)+'\n\n'+MARKER+'0\n','native log ONLY')
   def observed(r,script):
    raw,actual=observations[r['path']];self.assertEqual(actual,script);return raw
   args=dict(helper={'binary':{'scope':'HOST fixture ONLY'}},hdc='hdc',target='127.0.0.1:7',observed=observed,command_index=lambda r:indexes[r['path']])
   capture=dict(host_begin_ns=3,host_end_ns=4)
   self.assertEqual(123,clock.verify_clock(row,capture,**args)['pid'])
   for fault in ['early-stop','late-ready','foreign-argv','stale-process','wrong-card-owner','reordered-stop','false-time']:
    with self.subTest(fault=fault):
     changed=copy.deepcopy(row);old_indexes=dict(indexes)
     if fault=='early-stop':changed['stop_requested_ns']=3
     elif fault=='late-ready':changed['ready_ns']=4
     elif fault=='foreign-argv':changed['argv'][2]='127.0.0.1:9'
     elif fault=='stale-process':changed['identity']['starttime']=457
     elif fault=='wrong-card-owner':changed['hardware_after']=put(HARDWARE.replace('owner_pid   : 123','owner_pid   : 124'),clock.HARDWARE)
     elif fault=='reordered-stop':indexes[changed['stop']['path']]=0
     else:changed['ready_ns']=True
     with self.assertRaises((ValueError,AssertionError)):clock.verify_clock(changed,capture,**args)
     indexes.clear();indexes.update(old_indexes)

 def test_native_whole_clock_only_writes_zero_and_retains_actual_failures(self):
  stub=STUB.replace('hw:CARD=QemuCapture,DEV=1,SUBDEV=0',clock.DEVICE)
  stub=stub.replace('*(p)=alloca(sizeof(snd_pcm_hw_params_t))','*(p)=(snd_pcm_hw_params_t*)alloca(sizeof(snd_pcm_hw_params_t))')
  stub=stub.replace('*(p)=alloca(sizeof(snd_pcm_status_t))','*(p)=(snd_pcm_status_t*)alloca(sizeof(snd_pcm_status_t))')
  stub=stub.replace('uint8_t expected=(uint8_t)((totalFrames*actualChannels*2+i)%256);','uint8_t expected=0;')
  stub=stub.replace('++calls;if','++calls;if(!strcmp(mode(),"clock-signal")&&totalFrames>=16384)raise(SIGTERM);if')
  stub=stub.replace('static int snd_pcm_drop(snd_pcm_t*p){(void)p;return 0;}','static int snd_pcm_drop(snd_pcm_t*p){(void)p;return !strcmp(mode(),"drop-error")?-EIO:0;}')
  stub=stub.replace('const uint8_t*b=d;', 'const uint8_t*b=(const uint8_t*)d;')
  stub=stub.replace('static ','[[maybe_unused]] static ')
  with tempfile.TemporaryDirectory(prefix='actual-clock-host-') as temporary:
   root=Path(temporary);(root/'alsa').mkdir();(root/'alsa/asoundlib.h').write_text(stub)
   binary=root/'clock';subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root),str(ROOT/'ci/capability-audit/fixtures/batch_media/audio_observation_clock/clock.cpp'),'-o',str(binary)],check=True,timeout=45)
   env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1' if os.uname().sysname=='Linux' else 'detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
   for mode,reason in [('clock-signal','owned_sigterm'),('','time_bound')]:
    with self.subTest(mode=mode):
     result=subprocess.run([str(binary),'--seconds','1'],capture_output=True,text=True,env=dict(env,BATCH_MEDIA_TEST_ALSA_MODE=mode),timeout=5)
     self.assertEqual(0,result.returncode,result.stderr);rows=[json.loads(s) for s in result.stderr.splitlines()]
     self.assertEqual(os.getuid(),rows[0]['uid']);self.assertEqual(reason,rows[-1]['reason']);self.assertEqual(0,rows[-1]['close_rc'])
   for mode in ['open-error','wrong-format','write-xrun','wait-xrun','write-error','drop-error','close-error']:
    with self.subTest(mode=mode):
     result=subprocess.run([str(binary),'--seconds','1'],capture_output=True,text=True,env=dict(env,BATCH_MEDIA_TEST_ALSA_MODE=mode),timeout=5)
     self.assertNotEqual(0,result.returncode,result.stderr);self.assertIn('"event":"clock_failed"',result.stderr);self.assertNotIn('"event":"clock_end"',result.stderr)

if __name__=='__main__':unittest.main()
