#!/usr/bin/env python3
"""Exact client methods + complete AudioSpeed/Sonic with exact arithmetic prerequisite in explicit host dependencies only."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess
from test_audio_haptic_sync_id_component import git_environment
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
FIX=HERE/'fixtures/audio_haptic_sync_id'
COMP=ROOT/'patches/common/foundation/multimedia/audio_framework/audio_haptic_sync_id'
A=Path('foundation/multimedia/audio_framework')
INFO='#pragma once\n#include <cstdint>\n#include <memory>\n#include <functional>\nnamespace OHOS::AudioStandard { enum {SAMPLE_U8,SAMPLE_S16LE,SAMPLE_S24LE,SAMPLE_S32LE,SAMPLE_F32LE}; struct AudioStreamParams {}; }\n'
UTILS='#pragma once\n#include <string>\n#include <cstring>\n#include <algorithm>\n#include <cstdint>\n#define CHECK_AND_RETURN_RET_LOG(c,r,...) do { if (!(c)) return (r); } while(0)\nnamespace OHOS::AudioStandard {\nstruct Trace {explicit Trace(const std::string&) {} void End() {}};\n// External PCM conversion helpers are bounded format shims; Sonic and AudioSpeed are actual bytes.\ninline void ConvertFrom24BitToFloat(size_t n,uint8_t*p,float*q){for(size_t i=0;i<n;i++){int32_t v=static_cast<int32_t>((uint32_t(p[i*3+2])<<24)|(uint32_t(p[i*3+1])<<16)|(uint32_t(p[i*3])<<8));q[i]=float(v)/2147483648.0f;}}\ninline void ConvertFromFloatTo24Bit(size_t n,float*p,uint8_t*q){for(size_t i=0;i<n;i++){int32_t v=int32_t(std::clamp(p[i],-.99f,.99f)*8388608);q[i*3]=v;q[i*3+1]=v>>8;q[i*3+2]=v>>16;}}\ninline void ConvertFrom32BitToFloat(size_t n,int32_t*p,float*q){for(size_t i=0;i<n;i++)q[i]=float(p[i])/2147483648.0f;}\ninline void ConvertFromFloatTo32Bit(size_t n,float*p,int32_t*q){for(size_t i=0;i<n;i++)q[i]=int32_t(std::clamp(p[i],-.99f,.99f)*2147483648.0f);}\n}\n'

"""Extract function bytes, preserving the whole actual definition incl. comments."""
def extract(path,signature):
 t=path.read_bytes().decode();start=t.index(signature);p=t.index('{',start)
 depth=0;i=p;mode='code'
 while i<len(t):
  c=t[i];n=t[i:i+2]
  if mode=='line':
   if c=='\n':mode='code'
  elif mode=='block':
   if n=='*/':mode='code';i+=1
  elif mode in ('"',"'"):
   if c=='\\':i+=1
   elif c==mode:mode='code'
  elif n=='//':mode='line';i+=1
  elif n=='/*':mode='block';i+=1
  elif c in ('"',"'"):mode=c
  elif c=='{':depth+=1
  elif c=='}':
   depth-=1
   if depth==0:return t[start:i+1]
  i+=1
 raise ValueError(signature)

def prepare(out):
 out.mkdir(parents=True,exist_ok=False)
 tree=out/'source';shutil.copytree(FIX/'before',tree)
 for source in tree.rglob('*'):
  if source.is_file():source.chmod(0o644)
 env=git_environment(out);env['ASAN_OPTIONS']='detect_leaks=0';env['UBSAN_OPTIONS']='halt_on_error=1:print_stacktrace=1'
 cmd=['bash',str(COMP/'apply.sh'),'--source-root',str(tree)]
 p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env)
 (out/'apply.log').write_text(p.stdout)
 if p.returncode:raise RuntimeError('exact generic application failed')
 return tree,env,dict(argv=cmd,exit=p.returncode,log='apply.log')

def dependencies(out,tree):
 for src,dest in [(tree/A/'frameworks/native/audioutils/src/audio_speed.cpp','audio_speed.cpp'),(tree/A/'frameworks/native/audioutils/include/audio_speed.h','audio_speed.h'),(tree/A/'interfaces/inner_api/native/audiocommon/include/ring_buffer_wrapper.h','ring_buffer_wrapper.h'),(tree/'third_party/sonic/sonic.c','sonic.c'),(tree/'third_party/sonic/sonic.h','sonic.h')]:shutil.copyfile(src,out/dest)
 (out/'audio_utils.h').write_text(UTILS);(out/'audio_info.h').write_text(INFO)
 (out/'audio_errors.h').write_text('#pragma once\nconstexpr int SUCCESS=0,ERROR=-1,ERR_MEMORY_ALLOC_FAILED=-2,ERR_INVALID_PARAM=-3,ERR_OPERATION_FAILED=-4,ERR_ILLEGAL_STATE=-5;\n')
 (out/'audio_common_log.h').write_text('#pragma once\n#define AUDIO_INFO_LOG(...) ((void)0)\n#define AUDIO_ERR_LOG(...) ((void)0)\n')
 (out/'audio_log.h').write_text('#pragma once\n')
 (out/'securec.h').write_text('#pragma once\nconstexpr int EOK=0;\nstatic int memcpy_s(void*d,size_t c,const void*s,size_t n){if(!d||!s||n>c)return 22;std::memcpy(d,s,n);return 0;}\nstatic int memset_s(void*d,size_t c,int v,size_t n){if(!d||n>c)return 22;std::memset(d,v,n);return 0;}\n')

def compile_and_run(out,compiler,env):
 flags=['-DSONIC_ENABLE','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined','-fno-omit-frame-pointer','-I'+str(out)]
 cc=compiler.with_name('clang')
 cmds=[[str(cc),*flags,'-c',str(out/'sonic.c'),'-o',str(out/'sonic.o')],[str(compiler),'-std=c++20','-fno-exceptions',*flags,str(out/'audio_speed.cpp'),str(out/'driver.cpp'),str(out/'sonic.o'),'-o',str(out/'driver')],[str(out/'driver')]]
 rows=[]
 for i,cmd in enumerate(cmds):
  p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env);(out/(str(i)+'.log')).write_text(p.stdout);rows.append(dict(argv=cmd,exit=p.returncode,log=str(i)+'.log'))
  if p.returncode:break
 return rows

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
 tree,env,applied=prepare(out);dependencies(out,tree)
 source=tree/A/'services/audio_service/client/src/renderer_in_client.cpp'
 sigs=['int32_t RendererInClientInner::ProcessSpeed(','int32_t RendererInClientInner::ProcessPitch(','RendererInClientInner::WriteProgress RendererInClientInner::WriteCacheData(','void RendererInClientInner::DropOwnedOutput(','int32_t RendererInClientInner::DrainOwnedOutput(','int32_t RendererInClientInner::CacheConvertedOutput(','int32_t RendererInClientInner::DrainPendingOutput(','int32_t RendererInClientInner::ProcessBufferAndWriteCache(','int32_t RendererInClientInner::ProcessWriteInner(','bool RendererInClientInner::WriteCallbackFunc(','bool RendererInClientInner::DrainAudioStreamInner(','void RendererInClientInner::FlushSpeedBuffer(']
 funcs=[extract(source,s)for s in sigs]
 public=tree/A/'services/audio_service/client/src/renderer_in_client_public.cpp'
 public_sigs=['int32_t RendererInClientInner::RebuildWriteTransforms(','int32_t RendererInClientInner::SetPitch(']
 public_funcs=[extract(public,s)for s in public_sigs]
 (out/'driver.cpp').write_text((FIX/'client_harness528.cpp.in').read_text().replace('@FUNCTIONS@','\n\n'.join(funcs+public_funcs)))
 (out/'EXTRACTED.json').write_text(json.dumps([dict(signature=s,sha256=hashlib.sha256(t.encode()).hexdigest(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())for s,t in zip(sigs,funcs)]+[dict(signature=s,sha256=hashlib.sha256(t.encode()).hexdigest(),source_sha256=hashlib.sha256(public.read_bytes()).hexdigest())for s,t in zip(public_sigs,public_funcs)],indent=2)+'\n')
 rows=compile_and_run(out,a.compiler,env)
 value=dict(commands=[applied,*rows],scope='fourteen literal client methods, complete AudioSpeed and the separately certified defined-arithmetic Sonic; shared buffer/IPC/pitch/effect/clock dependencies are explicit models; no full client TU, service scheduling, real pitch library, target ABI or guest audio claim',target_build_passed=False,runtime_passed=False,onset_proven=False,first_artifact_behavior_gate_passed=False)
 (out/'RESULT.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps([r['exit']for r in rows]));assert len(rows)==3 and all(r['exit']==0 for r in rows)
if __name__=='__main__':main()
