#!/usr/bin/env python3
"""Regression of diagnostic CLI/data/error paths with controlled ALSA; never guest capability evidence."""
import os
import json
import errno
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
STUB=r'''
#include <alloca.h>
#include <errno.h>
#include <stdint.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef ESTRPIPE
#define ESTRPIPE 86
#endif
typedef unsigned long snd_pcm_uframes_t;
typedef long snd_pcm_sframes_t;
typedef int snd_pcm_format_t;
typedef int snd_pcm_state_t;
typedef struct {int none;} snd_pcm_status_t;
#define SND_PCM_STATE_SETUP 1
#define SND_PCM_STATE_PREPARED 2
#define SND_PCM_STATE_RUNNING 3
#define SND_PCM_STATE_XRUN 4
#define SND_PCM_STATE_DRAINING 5
#define SND_PCM_STATE_SUSPENDED 7
#define SND_PCM_STATE_DISCONNECTED 8
#define snd_pcm_status_alloca(p) do {*(p)=alloca(sizeof(snd_pcm_status_t));}while(0)
typedef struct {int count;} snd_pcm_t;
typedef struct {int none;} snd_pcm_hw_params_t;
#define SND_PCM_FORMAT_UNKNOWN -1
#define SND_PCM_FORMAT_S16_LE 2
#define SND_PCM_ACCESS_RW_INTERLEAVED 0
#define SND_PCM_STREAM_PLAYBACK 0
#define SND_PCM_NONBLOCK 1
#define snd_pcm_hw_params_alloca(p) do {*(p)=alloca(sizeof(snd_pcm_hw_params_t));}while(0)
static unsigned int actualRate,actualChannels;
static uint64_t totalFrames;
static int calls,drainCalls,statusCalls;
static const char *mode(void){const char*p=getenv("BATCH_MEDIA_TEST_ALSA_MODE");return p?p:"";}
static int snd_pcm_open(snd_pcm_t **p,const char*d,int stream,int flags){static snd_pcm_t fake;if(strcmp(d,"hw:CARD=QemuCapture,DEV=1,SUBDEV=0")||stream!=SND_PCM_STREAM_PLAYBACK||flags!=SND_PCM_NONBLOCK)abort();if(!strcmp(mode(),"open-error"))return -ENODEV;*p=&fake;return 0;}
static const char*snd_strerror(int n){(void)n;return "controlled regression error";}
static int snd_pcm_set_params(snd_pcm_t*p,int f,int a,unsigned int c,unsigned int r,int soft,unsigned int latency){(void)p;if(f!=SND_PCM_FORMAT_S16_LE||a!=SND_PCM_ACCESS_RW_INTERLEAVED||soft||latency!=100000)abort();actualRate=r;actualChannels=c;return 0;}
static int snd_pcm_hw_params_current(snd_pcm_t*p,snd_pcm_hw_params_t*h){(void)p;(void)h;return 0;}
static int snd_pcm_hw_params_get_rate(snd_pcm_hw_params_t*h,unsigned int*r,int*d){(void)h;*r=actualRate;*d=0;return 0;}
static int snd_pcm_hw_params_get_channels(snd_pcm_hw_params_t*h,unsigned int*c){(void)h;*c=actualChannels;return 0;}
static int snd_pcm_hw_params_get_format(snd_pcm_hw_params_t*h,snd_pcm_format_t*f){(void)h;*f=strcmp(mode(),"wrong-format")?SND_PCM_FORMAT_S16_LE:3;return 0;}
static snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t*p,const void*d,snd_pcm_uframes_t n){(void)p;const uint8_t*b=d;++calls;if(!strcmp(mode(),"write-error"))return -EIO;if(!strcmp(mode(),"write-xrun"))return -EPIPE;if(!strcmp(mode(),"write-timeout"))return -EAGAIN;if(!strcmp(mode(),"overreport"))return (long)n+1;if(!strcmp(mode(),"wait-error")||!strcmp(mode(),"wait-xrun"))return -EAGAIN;if(!strcmp(mode(),"short")&&calls%3==1)return -EAGAIN;if(!strcmp(mode(),"short")&&n>2)n=2;for(size_t i=0;i<n*actualChannels*2;++i){uint8_t expected=(uint8_t)((totalFrames*actualChannels*2+i)%256);if(b[i]!=expected)abort();}totalFrames+=n;return (long)n;}
static int snd_pcm_wait(snd_pcm_t*p,int n){(void)p;if(n!=100||drainCalls)abort();return !strcmp(mode(),"wait-xrun")?-EPIPE:(!strcmp(mode(),"wait-error")||!strcmp(mode(),"drain-wait-error"))?-EIO:1;}
static int snd_pcm_drain(snd_pcm_t*p){(void)p;if(drainCalls&&!strcmp(mode(),"drain-nonblock-completes"))abort();if(drainCalls&&!strcmp(mode(),"drain-completes")&&statusCalls<5)abort();++drainCalls;return (!strcmp(mode(),"drain-interrupt-setup")||!strcmp(mode(),"drain-eintr-late-setup"))?-EINTR:!strcmp(mode(),"drain-false-success")?0:!strcmp(mode(),"drain-error")?-EIO:(!strncmp(mode(),"drain-",6)&&strcmp(mode(),"drain-completes")&&strcmp(mode(),"drain-interrupt-completes"))?-EAGAIN:(!strcmp(mode(),"drain-completes")&&drainCalls==1)?-EAGAIN:(!strcmp(mode(),"drain-interrupt-completes")&&drainCalls==1)?-EINTR:0;}
static int snd_pcm_status(snd_pcm_t*p,snd_pcm_status_t*s){(void)p;(void)s;++statusCalls;if(!strcmp(mode(),"drain-cancel"))raise(SIGTERM);return !strcmp(mode(),"drain-status-error")?-EIO:0;}
static snd_pcm_sframes_t snd_pcm_status_get_delay(const snd_pcm_status_t*s){(void)s;return !strcmp(mode(),"drain-setup-with-delay")?1:0;}
static snd_pcm_state_t snd_pcm_status_get_state(const snd_pcm_status_t*s){(void)s;if(!strcmp(mode(),"drain-regressed"))return !drainCalls||statusCalls>2?SND_PCM_STATE_RUNNING:SND_PCM_STATE_DRAINING;if(!strcmp(mode(),"drain-not-started"))return SND_PCM_STATE_RUNNING;if(!strcmp(mode(),"drain-eintr-late-setup"))return statusCalls>=3?SND_PCM_STATE_SETUP:SND_PCM_STATE_RUNNING;if(!strcmp(mode(),"drain-nonblock-completes")&&drainCalls&&statusCalls<5)return SND_PCM_STATE_DRAINING;if(!strcmp(mode(),"drain-false-success")&&drainCalls)return SND_PCM_STATE_DRAINING;if(!strcmp(mode(),"drain-initial-draining"))return SND_PCM_STATE_DRAINING;if(!strcmp(mode(),"drain-xrun"))return SND_PCM_STATE_XRUN;if(!strcmp(mode(),"drain-suspended"))return SND_PCM_STATE_SUSPENDED;if(!strcmp(mode(),"drain-disconnected"))return SND_PCM_STATE_DISCONNECTED;if((!strcmp(mode(),"drain-timeout")&&drainCalls)||(!strcmp(mode(),"drain-completes")&&drainCalls==1&&statusCalls<5))return SND_PCM_STATE_DRAINING;if(!strcmp(mode(),"drain-initial-setup"))return SND_PCM_STATE_SETUP;if(!drainCalls||(!strcmp(mode(),"drain-interrupt-completes")&&drainCalls==1))return SND_PCM_STATE_RUNNING;return SND_PCM_STATE_SETUP;}
static int snd_pcm_drop(snd_pcm_t*p){(void)p;return 0;}
static int snd_pcm_close(snd_pcm_t*p){(void)p;return !strcmp(mode(),"close-error")?-EIO:0;}
'''
class Inject(unittest.TestCase):
    def test_actual_full_diagnostic_and_error_paths(self):
        with tempfile.TemporaryDirectory(prefix='batch-media-alsa-inject-') as temp:
            root=Path(temp);(root/'alsa').mkdir();(root/'alsa/asoundlib.h').write_text(STUB)
            exe=root/'inject';subprocess.run([os.environ.get('OHOS_QA_CC','clang'),'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root),str(ROOT/'ci/capability-audit/batch_media_alsa_inject.c'),'-o',str(exe)],check=True)
            pcm=root/'challenge.pcm';pcm.write_bytes(bytes(range(256))*16)
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1')
            args=[str(exe),'--input',str(pcm),'--repeat','2']
            for mode in ['', 'short', 'drain-completes', 'drain-interrupt-completes', 'drain-nonblock-completes', 'drain-kernel-immediate-setup']:
                r=subprocess.run(args,env=dict(env,BATCH_MEDIA_TEST_ALSA_MODE=mode),capture_output=True,text=True,timeout=5);self.assertEqual(r.returncode,0,r.stderr);self.assertIn('"frames":2048',r.stdout)
                drained=[json.loads(line) for line in r.stderr.splitlines() if line.startswith('{') and json.loads(line)['event']=='drained']
                self.assertEqual(len(drained),1,r.stderr)
                self.assertEqual((drained[0]['status_rc'],drained[0]['state'],drained[0]['delay_frames'],drained[0]['written_frames']),(0,1,0,2048))
                self.assertEqual(drained[0]['alsa_rc'],-errno.EAGAIN if mode in ('drain-completes','drain-nonblock-completes','drain-kernel-immediate-setup') else 0)
            for mode in ['open-error','wrong-format','write-error','overreport','wait-error','drain-error','close-error']:
                r=subprocess.run(args,env=dict(env,BATCH_MEDIA_TEST_ALSA_MODE=mode),capture_output=True,text=True,timeout=5);self.assertNotEqual(r.returncode,0,mode);self.assertNotIn('"event":"played"',r.stdout)
            for mode,stage,code in [('write-xrun','write',-32),('wait-xrun','write_wait',-32),
                                    ('drain-status-error','drain_status',-5),('drain-setup-with-delay','drain_terminal_delay',-5),('drain-interrupt-setup','drain_interrupt_before_start',-4),('drain-eintr-late-setup','drain_unstarted_setup',-4),('drain-xrun','drain_state',-32),('drain-suspended','drain_state',-getattr(errno,'ESTRPIPE',86)),('drain-disconnected','drain_state',-19),('drain-regressed','drain_state_transition',-5),('drain-not-started','drain_not_started',-5),('drain-false-success','drain_terminal_state',-5),('drain-initial-draining','drain_initial_state',-5),('drain-initial-setup','drain_state',-5),('drain-cancel','drain_deadline_or_signal',0),('close-error','close',-5),
                                    ('write-timeout','write_deadline_or_signal',0),('drain-timeout','drain_deadline_or_signal',0)]:
                r=subprocess.run(args+['--timeout-ms','100'],env=dict(env,BATCH_MEDIA_TEST_ALSA_MODE=mode),capture_output=True,text=True,timeout=5)
                self.assertNotEqual(r.returncode,0,mode)
                rows=[json.loads(line) for line in r.stderr.splitlines() if line.startswith('{')]
                failures=[row for row in rows if row['event']=='failed']
                self.assertEqual(len(failures),1,r.stderr)
                self.assertEqual((failures[0]['stage'],failures[0]['alsa_rc']),(stage,code),r.stderr)
                self.assertNotIn('"event":"played"',r.stdout)
            for key,value in [('--rate','48000x'),('--rate','-1'),('--rate','1'),('--channels','3'),('--repeat','0'),('--timeout-ms','999999999999999999999')]:
                self.assertEqual(subprocess.run([str(exe),'--input',str(pcm),key,value],env=env,capture_output=True,timeout=5).returncode,2)
            for name,data in [('empty.pcm',b''),('misaligned.pcm',b'123')]:
                bad=root/name;bad.write_bytes(data);self.assertNotEqual(subprocess.run([str(exe),'--input',str(bad)],env=env,capture_output=True,timeout=5).returncode,0)
            link=root/'link.pcm';link.symlink_to(pcm);self.assertNotEqual(subprocess.run([str(exe),'--input',str(link)],env=env,capture_output=True,timeout=5).returncode,0)
            print('actual diagnostic compiled; exact and segmented file writes, negotiation/error propagation, invalid/empty/link inputs checked; controlled ALSA only')

if __name__=='__main__':unittest.main(verbosity=2)
