#!/usr/bin/env python3
"""Regression of diagnostic CLI/data/error paths with controlled ALSA; never guest capability evidence."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
STUB=r'''
#include <alloca.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned long snd_pcm_uframes_t;
typedef long snd_pcm_sframes_t;
typedef int snd_pcm_format_t;
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
static int calls;
static const char *mode(void){const char*p=getenv("BATCH_MEDIA_TEST_ALSA_MODE");return p?p:"";}
static int snd_pcm_open(snd_pcm_t **p,const char*d,int stream,int flags){static snd_pcm_t fake;if(strcmp(d,"hw:CARD=QemuCapture,DEV=1,SUBDEV=0")||stream!=SND_PCM_STREAM_PLAYBACK||flags!=SND_PCM_NONBLOCK)abort();if(!strcmp(mode(),"open-error"))return -ENODEV;*p=&fake;return 0;}
static const char*snd_strerror(int n){(void)n;return "controlled regression error";}
static int snd_pcm_set_params(snd_pcm_t*p,int f,int a,unsigned int c,unsigned int r,int soft,unsigned int latency){(void)p;if(f!=SND_PCM_FORMAT_S16_LE||a!=SND_PCM_ACCESS_RW_INTERLEAVED||soft||latency!=100000)abort();actualRate=r;actualChannels=c;return 0;}
static int snd_pcm_hw_params_current(snd_pcm_t*p,snd_pcm_hw_params_t*h){(void)p;(void)h;return 0;}
static int snd_pcm_hw_params_get_rate(snd_pcm_hw_params_t*h,unsigned int*r,int*d){(void)h;*r=actualRate;*d=0;return 0;}
static int snd_pcm_hw_params_get_channels(snd_pcm_hw_params_t*h,unsigned int*c){(void)h;*c=actualChannels;return 0;}
static int snd_pcm_hw_params_get_format(snd_pcm_hw_params_t*h,snd_pcm_format_t*f){(void)h;*f=strcmp(mode(),"wrong-format")?SND_PCM_FORMAT_S16_LE:3;return 0;}
static snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t*p,const void*d,snd_pcm_uframes_t n){(void)p;const uint8_t*b=d;++calls;if(!strcmp(mode(),"write-error"))return -EIO;if(!strcmp(mode(),"overreport"))return (long)n+1;if(!strcmp(mode(),"wait-error"))return -EAGAIN;if(!strcmp(mode(),"short")&&calls%3==1)return -EAGAIN;if(!strcmp(mode(),"short")&&n>2)n=2;for(size_t i=0;i<n*actualChannels*2;++i){uint8_t expected=(uint8_t)((totalFrames*actualChannels*2+i)%256);if(b[i]!=expected)abort();}totalFrames+=n;return (long)n;}
static int snd_pcm_wait(snd_pcm_t*p,int n){(void)p;if(n!=100)abort();return !strcmp(mode(),"wait-error")?-EIO:1;}
static int snd_pcm_drain(snd_pcm_t*p){(void)p;return !strcmp(mode(),"drain-error")?-EIO:0;}
static int snd_pcm_drop(snd_pcm_t*p){(void)p;return 0;}
static int snd_pcm_close(snd_pcm_t*p){(void)p;return !strcmp(mode(),"close-error")?-EIO:0;}
'''
class Inject(unittest.TestCase):
    def test_actual_full_diagnostic_and_error_paths(self):
        with tempfile.TemporaryDirectory(prefix='batch-media-alsa-inject-') as temp:
            root=Path(temp);(root/'alsa').mkdir();(root/'alsa/asoundlib.h').write_text(STUB)
            exe=root/'inject';subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(root),str(ROOT/'ci/capability-audit/batch_media_alsa_inject.c'),'-o',str(exe)],check=True)
            pcm=root/'challenge.pcm';pcm.write_bytes(bytes(range(256))*16)
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1')
            args=[str(exe),'--input',str(pcm),'--repeat','2']
            for mode in ['', 'short']:
                r=subprocess.run(args,env=dict(env,BATCH_MEDIA_TEST_ALSA_MODE=mode),capture_output=True,text=True,timeout=5);self.assertEqual(r.returncode,0,r.stderr);self.assertIn('"frames":2048',r.stdout)
            for mode in ['open-error','wrong-format','write-error','overreport','wait-error','drain-error','close-error']:
                r=subprocess.run(args,env=dict(env,BATCH_MEDIA_TEST_ALSA_MODE=mode),capture_output=True,text=True,timeout=5);self.assertNotEqual(r.returncode,0,mode);self.assertNotIn('"event":"played"',r.stdout)
            for key,value in [('--rate','48000x'),('--rate','-1'),('--rate','1'),('--channels','3'),('--repeat','0'),('--timeout-ms','999999999999999999999')]:
                self.assertEqual(subprocess.run([str(exe),'--input',str(pcm),key,value],env=env,capture_output=True,timeout=5).returncode,2)
            for name,data in [('empty.pcm',b''),('misaligned.pcm',b'123')]:
                bad=root/name;bad.write_bytes(data);self.assertNotEqual(subprocess.run([str(exe),'--input',str(bad)],env=env,capture_output=True,timeout=5).returncode,0)
            link=root/'link.pcm';link.symlink_to(pcm);self.assertNotEqual(subprocess.run([str(exe),'--input',str(link)],env=env,capture_output=True,timeout=5).returncode,0)
            print('actual diagnostic compiled; exact and segmented file writes, negotiation/error propagation, invalid/empty/link inputs checked; controlled ALSA only')

if __name__=='__main__':unittest.main(verbosity=2)
