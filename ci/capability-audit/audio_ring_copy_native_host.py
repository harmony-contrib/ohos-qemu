#!/usr/bin/env python3
import argparse,pathlib,hashlib,json,subprocess,shutil,os
from audio_write_queue_native_host import prepare,extract,FIX
p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--compiler',type=pathlib.Path,required=True);args=p.parse_args()
OUT=args.output.resolve();SOURCE,ENV,APPLIED=prepare(OUT)
A=pathlib.Path('foundation/multimedia/audio_framework');O=FIX
NODE=SOURCE/A/'services/audio_engine/node/src/hpae_sink_input_node.cpp'
CPP=A/'services/audio_service/server/src/renderer_in_server.cpp';HPAE=A/'services/audio_service/server/src/hpae_renderer_stream_impl.cpp'
WRAP=A/'interfaces/inner_api/native/audiocommon/include/ring_buffer_wrapper.h'
def run(argv,name):
 p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=ENV);(OUT/(name+'.log')).write_text(p.stdout);return dict(argv=argv,exit=p.returncode,log=name+'.log')
results={"generic_apply":APPLIED};manifest=[]
for phase in ('after',):
 d=OUT/phase;d.mkdir();functions=[]
 signatures=['@COPY@','int32_t RendererInServer::WriteData(int8_t *inputData','BufferDesc RendererInServer::PrepareOutputBuffer(','int32_t RendererInServer::WriteData()','int32_t RendererInServer::SelectModeAndWriteData(','int32_t RendererInServer::OnWriteDataInternal(','int32_t RendererInServer::OnWriteData(int8_t','int32_t RendererInServer::OnWriteDataNoWake(']
 signatures[0]=('void' if phase=='before' else 'int32_t')+' RendererInServer::CopyDataToInputBuffer('
 for path,sigs in ((SOURCE/CPP,signatures),(SOURCE/HPAE,['int32_t HpaeRendererStreamImpl::OnStreamData(']),(NODE,['bool HpaeSinkInputNode::ReadToAudioBuffer(','void HpaeSinkInputNode::DoProcess('])):
  for sig in sigs:
   body=extract(path,sig);functions.append(body);manifest.append(dict(phase=phase,source=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),signature=sig,extracted_sha256=hashlib.sha256(body.encode()).hexdigest()))
   (d/(str(len(functions))+'.inc')).write_text(body)
 shutil.copyfile(SOURCE/WRAP,d/'ring_buffer_wrapper.h')
 (d/'audio_errors.h').write_text('// driver constants\n');(d/'audio_log.h').write_text('// driver no-op logs\n')
 (d/'securec.h').write_text('''#pragma once
constexpr int EOK=0;
static int memcpy_s(void*d,size_t c,const void*s,size_t n){copyCalls++;if(copyCalls==failCopy)return 22;if(!d||!s||n>c)return 22;std::memcpy(d,s,n);return 0;}
static int memset_s(void*d,size_t c,int v,size_t n){if(!d||n>c)return 22;std::memset(d,v,n);return 0;}
''')
 t=(O/'server_harness528.cpp.in').read_text().replace('@COPY_DECL@',('void' if phase=='before' else 'int32_t')+' CopyDataToInputBuffer(int8_t*,size_t,const RingBufferWrapper&);').replace('@FUNCTIONS@','\n\n'.join(functions)).replace('@PATCHED@','true' if phase=='after' else 'false');(d/'driver.cpp').write_text(t)
 cmd=[str(args.compiler),'-std=c++20','-fno-exceptions','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined','-fno-omit-frame-pointer','-I'+str(d),str(d/'driver.cpp'),'-o',str(d/'driver')]
 rs=[run(cmd,phase+'-compile')]
 if rs[0]['exit']==0:rs += [run([str(d/'driver')],phase+'-matrix')]
 results[phase]=rs
(OUT/'EXTRACTED.json').write_text(json.dumps(manifest,indent=2)+'\n');(OUT/'RESULT.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps([v['exit']for v in results['after']]))
assert all(r['exit']==0 for r in results['after'])
