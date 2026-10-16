#!/usr/bin/env python3
"""Actual capture selector, JSON parser, read and vendor regressions; no simulated backend acceptance."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
COMP=ROOT/'patches/common/drivers/peripheral/audio/capture_loopback'
FIX=Path(__file__).parent/'fixtures/batch_media/audio'
SHIM=(FIX/'alsa_shim.h').read_text()

def function(source,signature):
    a=source.index(signature);b=source.index('\n}',a)+2;return source[a:b]

class Alsa(unittest.TestCase):
    def compile_run(self,source,extra=None):
        with tempfile.TemporaryDirectory(prefix='batch-media-alsa-') as temp:
            root=Path(temp);c=root/'test.c';c.write_text(SHIM+'\n'+source);cmd=['clang','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-Wno-deprecated-declarations','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root),str(c)]
            if extra:
                fixture=json.loads((FIX/'cjson.json').read_text())
                for name,entry in fixture['files'].items():
                    b=gzip.decompress(base64.b64decode(entry['gzip_base64']));self.assertEqual(hashlib.sha256(b).hexdigest(),entry['sha256']);(root/name).write_bytes(b)
                cmd.extend([str(root/'cJSON.c'),'-lm'])
            cmd.extend(['-o',str(root/'test')]);subprocess.run(cmd,check=True)
            subprocess.run([str(root/'test')],check=True,timeout=15,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1'))

    def test_actual_json_and_directional_selection(self):
        s=(COMP/'files/alsa_soundcard.c').read_text();defs=s[s.index('struct AlsaAdapterCfgInfo {'):s.index('static char *CfgReadAdapterFile')]
        funcs='\n'.join(function(s,x) for x in ['static enum SndCardType CfgGetAdapterCardType','static struct AlsaAdapterCfgInfo *CfgGetAdapterInfo','static int32_t CfgSaveCaptureRoute','static int32_t CfgSaveAdapterStruct','static struct AlsaDevInfo *DevGetInfoByCardId','static int32_t SndMatchSelAdapterUnlocked','int32_t SndMatchSelAdapter(','static int32_t SndMatchExplicitCapture','int32_t SndMatchSelCaptureAdapter('])
        self.compile_run('#include "cJSON.h"\n'+defs+funcs+r'''
int main(void){
 struct AlsaAdapterCfgInfo cfg={0};cJSON *j=cJSON_Parse("{\"name\":\"primary\",\"cardId\":0,\"cardName\":\"AudioPCI\"}");assert(j);
 assert(CfgSaveAdapterStruct(j,&cfg)==0&&!cfg.hasCaptureRoute);cJSON_Delete(j);
 const char* bad[]={"{\"captureCardId\":1}","{\"captureCardName\":\"QemuCapture\"}","{\"captureDevice\":0}","{\"captureCardId\":true,\"captureCardName\":\"QemuCapture\",\"captureDevice\":0}","{\"captureCardId\":1.1,\"captureCardName\":\"QemuCapture\",\"captureDevice\":0}","{\"captureCardId\":-1,\"captureCardName\":\"QemuCapture\",\"captureDevice\":0}","{\"captureCardId\":1,\"captureCardName\":\"\",\"captureDevice\":0}","{\"captureCardId\":1,\"captureCardName\":\"QemuCapture\",\"captureDevice\":-1}","{\"captureCardId\":1,\"captureCardName\":\"QemuCapture\",\"captureDevice\":null}","{\"captureCardId\":1e400,\"captureCardName\":\"QemuCapture\",\"captureDevice\":0}"};
 for(size_t n=0;n<sizeof(bad)/sizeof(bad[0]);++n){j=cJSON_Parse(bad[n]);assert(j);assert(CfgSaveCaptureRoute(j,&cfg)!=0);cJSON_Delete(j);}
 j=cJSON_Parse("{\"captureCardId\":1,\"captureCardName\":\"QemuCapture\",\"captureDevice\":0}");assert(CfgSaveCaptureRoute(j,&cfg)==0&&cfg.hasCaptureRoute);cJSON_Delete(j);strcpy(cfg.adapterName,"primary");cfg.cardId=0;
 g_alsaAdapterList[SND_CARD_PRIMARY].num=1;g_alsaAdapterList[SND_CARD_PRIMARY].list[0]=cfg;
 g_alsaCardsDevList.num=1;g_alsaCardsDevList.alsaDevIns[0].card=0;g_alsaCardsDevList.alsaDevIns[0].device=0;strcpy(g_alsaCardsDevList.alsaDevIns[0].cardId,"AudioPCI");
 struct AlsaSoundCard card={0};assert(SndMatchSelCaptureAdapter(&card,"primary")==0);assert(strcmp(card.devName,"hw:1,0,0")==0&&strcmp(card.alsaCardId,"QemuCapture")==0);assert(ctlCalls==1&&closeCalls==1);
 assert(SndMatchSelAdapter(&card,"primary")==0);assert(strcmp(card.devName,"hw:0,0")==0&&strcmp(card.alsaCardId,"AudioPCI")==0);
 actualCardId="OtherCard";assert(SndMatchSelCaptureAdapter(&card,"primary")!=0);assert(closeCalls==2);actualCardId="QemuCapture";
 pcmInfoResult=-ENODEV;assert(SndMatchSelCaptureAdapter(&card,"primary")!=0);assert(closeCalls==3);pcmInfoResult=0;
 cardInfoResult=-EIO;assert(SndMatchSelCaptureAdapter(&card,"primary")!=0);assert(closeCalls==4);cardInfoResult=0;
 ctlOpenResult=-ENODEV;assert(SndMatchSelCaptureAdapter(&card,"primary")!=0);assert(closeCalls==4);ctlOpenResult=0;
 g_alsaAdapterList[SND_CARD_PRIMARY].list[0].hasCaptureRoute=false;assert(SndMatchSelCaptureAdapter(&card,"primary")==0);assert(strcmp(card.devName,"hw:0,0")==0);assert(ctlCalls==5);
 assert(SndMatchSelCaptureAdapter(NULL,"primary")!=0);puts("actual JSON/directional selection: legacy/render preserved; malformed and nonexistent capture rejected");
}
''',extra=True)

    def test_actual_read_wait_and_no_stale_success(self):
        s=(COMP/'files/alsa_snd_capture.c').read_text();self.compile_run(function(s,'static int32_t CapturePcmReadi(')+r'''
int main(void){snd_pcm_t pcm={SND_PCM_STATE_RUNNING};char data[32];uint64_t frames=99;
 long patterns[][3]={{8,0,0},{-EAGAIN,8,0},{0,8,0},{-EINTR,8,0},{-EPIPE,8,0},{0,0,0},{-EIO,0,0},{-EBADFD,0,0},{9,0,0}};
 for(size_t n=0;n<9;++n){memcpy(readValues,patterns[n],sizeof(patterns[n]));readIndex=0;readCount=3;frames=99;int ret=CapturePcmReadi(&pcm,&frames,data,8);assert((ret==0)==(n<5));assert(frames==(n<5?8:0));}
 assert(CapturePcmReadi(&pcm,&frames,data,0)!=0);waitResult=-EIO;readValues[0]=-EAGAIN;readIndex=0;assert(CapturePcmReadi(&pcm,&frames,data,8)!=0&&frames==0);
 assert(prepareCalls==0);puts("actual nonblocking PCM read: bounded waits, recovery, zero/error/overflow and stopped-state rejection");}
''')

    def test_both_actual_vendor_files(self):
        for name in ['vendor_capture.c','qemu_vendor_capture.c']:
            s=(COMP/'files'/name).read_text();s=re.sub(r'^#include[^\n]*\n','',s,flags=re.M)
            self.compile_run(s+r'''
int main(void){struct AlsaCapture c={0};strcpy(c.soundCard.alsaCardId,"QemuCapture");c.soundCard.cardType=SND_CARD_PRIMARY;assert(CaptureOverrideFunc(&c)==0);assert(c.Init(&c)==0&&c.priData==NULL);assert(mixerCalls==0);
 assert(c.Start(&c,NULL)!=0);snd_pcm_t pcm={SND_PCM_STATE_OPEN};c.soundCard.pcmHandle=&pcm;assert(c.Start(&c,NULL)!=0);pcm.state=SND_PCM_STATE_PREPARED;
 assert(c.Start(&c,NULL)==0&&pcm.state==SND_PCM_STATE_RUNNING&&c.soundCard.mmapFlag&&!c.soundCard.pauseState);int prev=startCalls;assert(c.Start(&c,NULL)==0&&startCalls==prev);
 long a=55,b=66;float x=3,y=4;assert(c.GetVolThreshold(&c,&a,&b)==HDF_ERR_NOT_SUPPORT&&a==55&&b==66);assert(c.GetVolume(&c,&a)==HDF_ERR_NOT_SUPPORT&&a==55);assert(c.SetVolume(&c,5)==HDF_ERR_NOT_SUPPORT);assert(c.SetMute(&c,true)==HDF_ERR_NOT_SUPPORT&&!c.muteState);assert(c.GetGainThreshold(&c,&x,&y)==HDF_ERR_NOT_SUPPORT&&x==3&&y==4);assert(c.GetGain(&c,&x)==HDF_ERR_NOT_SUPPORT&&x==3);assert(c.SetGain(&c,1)==HDF_ERR_NOT_SUPPORT);assert(mixerCalls==0);
 dropResult=-EIO;assert(c.Stop(&c)!=0&&c.soundCard.mmapFlag);dropResult=0;assert(c.Stop(&c)==0&&!c.soundCard.mmapFlag&&c.soundCard.pauseState&&pcm.state==SND_PCM_STATE_SETUP);
 prepareResult=-EIO;assert(c.Start(&c,NULL)!=0&&!c.soundCard.mmapFlag);prepareResult=0;startResult=-EIO;assert(c.Start(&c,NULL)!=0&&!c.soundCard.mmapFlag);startResult=0;assert(c.Start(&c,NULL)==0);assert(c.Stop(&c)==0);assert(c.Init(NULL)!=0);puts("actual vendor capture: PCM start/drop errors propagated; absent mixer capabilities rejected");}
''')

    def test_actual_open_and_no_read_restart_after_stop(self):
        s=(COMP/'files/alsa_snd_capture.c').read_text();self.compile_run(function(s,'static int32_t CaptureOpenImpl(')+'\n'+function(s,'static int32_t CaptureCheckMmapMode(')+r'''
int main(void){struct AlsaCapture c={0};strcpy(c.soundCard.alsaCardId,"QemuCapture");assert(CaptureOpenImpl(&c)==0&&mixerCalls==0);c.soundCard.pcmHandle->state=SND_PCM_STATE_RUNNING;c.soundCard.mmapFlag=true;assert(CaptureCheckMmapMode(&c.soundCard)==0);c.soundCard.mmapFlag=false;c.soundCard.pcmHandle->state=SND_PCM_STATE_SETUP;assert(CaptureCheckMmapMode(&c.soundCard)!=0&&startCalls==0);strcpy(c.soundCard.alsaCardId,"AudioPCI");assert(CaptureOpenImpl(&c)!=0&&mixerCalls==1);puts("actual capture open: PCM-only needs no fictitious mixer; old read cannot restart a dropped PCM");}
''')

    def test_actual_allocated_capture_period_bound(self):
        s=(COMP/'files/alsa_snd_capture.c').read_text();self.compile_run(function(s,'static int32_t CheckCapturePeriodCapacity(')+r'''
int main(void){snd_pcm_t pcm={SND_PCM_STATE_RUNNING};assert(CheckCapturePeriodCapacity(&pcm,6000)==0);assert(CheckCapturePeriodCapacity(&pcm,6001)!=0);assert(CheckCapturePeriodCapacity(&pcm,0)!=0);assert(CheckCapturePeriodCapacity(&pcm,~(snd_pcm_uframes_t)0)!=0);frameBytes=-1;assert(CheckCapturePeriodCapacity(&pcm,1)!=0);frameBytes=0;assert(CheckCapturePeriodCapacity(&pcm,1)!=0);frameBytes=24001;assert(CheckCapturePeriodCapacity(&pcm,1)!=0);puts("actual capture period: physical ALSA frame bytes and allocated tail checked without multiplication overflow");}
''')

    def test_complete_source_install_and_old_patch_coexistence(self):
        spec=importlib.util.spec_from_file_location('capture_loopback',COMP/'apply.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        baseline=json.loads((FIX/'baseline.json').read_text())
        with tempfile.TemporaryDirectory(prefix='batch-media-alsa-source-') as temp:
            root=Path(temp)
            for project,info in baseline['projects'].items():
                if project=='foundation/multimedia/av_codec':continue
                for name,entry in info['files'].items():
                    path=root/project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(gzip.decompress(base64.b64decode(entry['gzip_base64'])))
            mod.run(root);mod.run(root);self.assertTrue(mod.validate(root,True))
            # The unchanged render hunks belong to the original component; prove every prior capture hunk still reverses.
            for patch in sorted(COMP.parent.glob('000[4-7]-*.patch')):
                selected=[]
                for part in re.split(r'(?=^diff --git )',patch.read_text(),flags=re.M):
                    if part.startswith('diff --git ') and '/vendor_capture.c ' in part.splitlines()[0]:selected.append(part)
                f=root/'prior.patch';f.write_text(''.join(selected));subprocess.run(['git','-C',str(root),'apply','--check','--reverse','--ignore-space-change',str(f)],check=True)
            target=root/next(iter(mod.MANIFEST['files']));target.write_bytes(target.read_bytes()+b'unknown\n')
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(ValueError):mod.run(root)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

if __name__=='__main__':unittest.main(verbosity=2)
