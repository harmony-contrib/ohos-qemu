#!/usr/bin/env python3
"""Host tests of the actual public capture caller and independent oracle, never runtime acceptance."""
from array import array
import base64
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('batch_capture_oracle',HERE/'batch_media_audio_capture_challenge.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
RUN='0123456789abcdef0123456789abcdef'

def function(source,signature):
    start=source.index(signature);end=source.index('\n}',start)+2;return source[start:end]

class Capture(unittest.TestCase):
    def headers(self,root):
        sdk=json.loads((HERE/'fixtures/batch_media/audio_capture/public_sdk.json').read_text())
        (root/'ohaudio').mkdir();(root/'multimedia').mkdir()
        for path,entry in sdk['files'].items():
            data=gzip.decompress(base64.b64decode(entry['gzip_base64']));self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'])
            (root/Path(path).name).write_bytes(data)
            (root/'ohaudio'/Path(path).name).write_bytes(data)
            if Path(path).name=='native_audio_channel_layout.h':(root/'multimedia/native_audio_channel_layout.h').write_bytes(data)

    def test_actual_public_sdk_caller_compiles_and_callback_copies(self):
        source=(HERE/'batch_media_audio_capture_probe.cpp').read_text()
        with tempfile.TemporaryDirectory(prefix='batch-media-capture-sdk-') as temp:
            root=Path(temp);self.headers(root)
            flags=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-pthread','-I',str(root)]
            subprocess.run(flags+['-fsyntax-only',str(HERE/'batch_media_audio_capture_probe.cpp')],check=True)
            prefix=source[:source.index('namespace {')]
            declarations=source[source.index('constexpr int32_t RATE'):source.index('int64_t Now()')]
            test=prefix+'\n'+declarations+function(source,'int64_t Now()')+'\n'+function(source,'void Read(')+r'''
#include <cassert>
#include <iostream>
int main(){assert(CHANNELS==2);Capture state;state.phase=1;uint8_t original[17];for(int i=0;i<17;++i)original[i]=static_cast<uint8_t>(i);
Read(nullptr,&state,original+1,16);assert(state.size==16&&state.chunks.size()==1&&state.chunks[0].phase==1);for(size_t i=0;i<16;++i)assert(state.bytes[i]==i+1);
Read(nullptr,&state,nullptr,16);Read(nullptr,&state,original,0);Read(nullptr,&state,original,-4);Read(nullptr,&state,original,15);assert(state.invalid==4&&state.size==16);
state.phase=0;Read(nullptr,&state,original,4);assert(state.unexpected==1&&state.size==20&&state.chunks[1].phase==0);
state.phase=2;state.size=state.bytes.size()-4;Read(nullptr,&state,original,4);assert(state.size==state.bytes.size());Read(nullptr,&state,original,4);assert(state.invalid==5);
state.size=0;state.chunks.resize(MAX_CHUNKS);Read(nullptr,&state,original,4);assert(state.invalid==6&&state.size==0);
std::cout<<"actual public-header capture caller syntax and actual buffer callback boundaries passed\n";}
'''
            cpp=root/'callback.cpp';cpp.write_text(test);subprocess.run(flags+['-fsanitize=address,undefined',str(cpp),'-o',str(root/'callback')],check=True)
            subprocess.run([str(root/'callback')],check=True,timeout=10,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1'))

    def prepare(self,root):
        challenge=root/'challenge';manifest=oracle.generate(challenge,RUN);reference=(challenge/'challenge.pcm').read_bytes();values=oracle.pcm_values(reference)
        rows=[{'type':'identity','run_id':RUN,'uid':20010011,'euid':20010011,'mode':'granted'}]
        for cycle in [1,2]:
            def add(kind,**entries):rows.append(dict(type=kind,run_id=RUN,cycle=cycle,**entries))
            clock=10000000000+cycle*10000000000
            for index,(name,expected) in enumerate(oracle.CONFIG_STEPS):add('step',name=name,actual=expected,expected=expected,monotonic_ns=clock+index*1000000)
            add('format',rate=48000,channels=2,sample_format=1,frame_bytes=4)
            count=48000;phase_data=[]
            for phase,source_offset in [(1,cycle*279),(2,cycle*347+7000)]:
                # Controlled fixture verifies the independent diagnostic; it is not a backend result.
                data=array('h',(values[((source_offset+i)%48000)*2+c] for i in range(count) for c in [0,1])).tobytes()
                phase_data.append(data)
                for point in range(3):
                    position=19200*(point+1)+(phase-1)*57600
                    t=clock+position*1000000000//48000
                    add('snapshot',phase=phase,timestamp_result=0,frames_result=0,position=position,timestamp_ns=t,
                        frames_read=position,copied_bytes=min((phase-1)*count*4+(point+1)*16000*4,phase*count*4),before_ns=t+1000000,after_ns=t+2000000)
            for name in ['paused','stopped','released']:add('quiet',name=name,before_bytes=count*8,after_bytes=count*8,unexpected=0)
            data=b''.join(phase_data);offset=0
            for phase in [1,2]:
                for index in range(100):
                    add('chunk',offset=offset,bytes=1920,phase=phase,monotonic_ns=clock+offset//4*1000000000//48000);offset+=1920
            basename=f'audio-capture-{RUN}-cycle{cycle}.pcm';(root/basename).write_bytes(data)
            add('pcm_file',basename=basename,bytes=len(data),written_bytes=len(data),invalid_buffers=0,unexpected_buffers=0,callback_error=0,persisted=True)
        rows.append({'type':'summary','run_id':RUN,'cycles':2,'candidate_ok':True,'independent_pcm_verification_required':True})
        results=root/'results.log';results.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        identity=root/'identity.json';identity.write_text(json.dumps({'applicationInfo':{'uid':20010011,'isSystemApp':False,'appPrivilegeLevel':'normal'}}))
        return rows,results,challenge,identity

    def check(self,root,results,challenge,identity):
        return oracle.verify(results,root,challenge/'challenge.json',challenge/'challenge.pcm',RUN,identity)

    def test_fresh_stereo_challenge_and_windows(self):
        with tempfile.TemporaryDirectory(prefix='batch-media-challenge-') as temp:
            root=Path(temp);rows,results,challenge,identity=self.prepare(root)
            self.assertEqual(self.check(root,results,challenge,identity)['status'],'candidate_pcm_diagnostic_pass')
            other=root/'other';m=oracle.generate(other,RUN);self.assertNotEqual(m['sha256'],json.loads((challenge/'challenge.json').read_text())['sha256'])
            with self.assertRaises(ValueError):oracle.generate(other,RUN)
            with self.assertRaises(ValueError):self.check(root,results,other,identity)

    def test_content_rejects_silence_mono_swapped_truncated_and_replay(self):
        with tempfile.TemporaryDirectory(prefix='batch-media-challenge-') as temp:
            root=Path(temp);rows,results,challenge,identity=self.prepare(root);path=root/f'audio-capture-{RUN}-cycle1.pcm';original=path.read_bytes();samples=oracle.pcm_values(original)
            variants=[bytes(len(original)),array('h',(samples[(i//2)*2] for i in range(len(samples)))).tobytes(),
                array('h',(samples[i^1] for i in range(len(samples)))).tobytes(),original[:-4],original[:4096]*(len(original)//4096)]
            # Last-window content may be valid but must reject incorrect sequence advancement.
            corrupted=bytearray(original);corrupted[80000:192000]=original[0:112000];variants.append(bytes(corrupted))
            for data in variants:
                path.write_bytes(data)
                with self.assertRaises(ValueError):self.check(root,results,challenge,identity)
            path.write_bytes(original)

    def test_record_errors_timestamps_roles_and_lifecycle_cannot_self_certify(self):
        with tempfile.TemporaryDirectory(prefix='batch-media-challenge-') as temp:
            root=Path(temp);rows,results,challenge,identity=self.prepare(root)
            mutations=[]
            for kind,key,value in [('step','actual',3),('format','channels',1),('quiet','after_bytes',4),('pcm_file','invalid_buffers',1),('chunk','offset',4),('snapshot','timestamp_result',3),('snapshot','timestamp_ns',1),('snapshot','frames_read',0)]:
                copy_rows=copy.deepcopy(rows);row=next(r for r in copy_rows if r['type']==kind);row[key]=value;mutations.append(copy_rows)
            stale=copy.deepcopy(rows);stale[0]['run_id']='f'*32;mutations.append(stale)
            absent=copy.deepcopy(rows);absent=[r for r in absent if not (r['type']=='step' and r['name']=='resume')];mutations.append(absent)
            for bad in mutations:
                results.write_text(''.join(json.dumps(r)+'\n' for r in bad))
                with self.assertRaises(ValueError):self.check(root,results,challenge,identity)
            results.write_text(''.join(json.dumps(r)+'\n' for r in rows));identity.write_text(json.dumps({'applicationInfo':{'uid':20010011,'isSystemApp':True,'appPrivilegeLevel':'system_basic'}}))
            with self.assertRaises(ValueError):self.check(root,results,challenge,identity)

if __name__=='__main__':unittest.main(verbosity=2)
