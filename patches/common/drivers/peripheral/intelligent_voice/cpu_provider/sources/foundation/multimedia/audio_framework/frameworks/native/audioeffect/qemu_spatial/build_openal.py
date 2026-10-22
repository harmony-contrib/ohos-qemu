"""Normal GN action: fixed OpenAL 1.24.3 CPU HRTF archive, no test execution.

Invoked only by the existing product Ninja/Owner. Actual toolchain and complete
commands/deps/objects are retained; this action never creates a container/lease.
"""
from pathlib import Path
import argparse,hashlib,json,os,shlex,shutil,subprocess

def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--clang',type=Path,required=True);p.add_argument('--sysroot',type=Path,required=True);p.add_argument('--cpu',choices=['arm','arm64','x86_64','x64'],required=True);p.add_argument('--cmake',type=Path,required=True);p.add_argument('--ninja',type=Path,required=True);a=p.parse_args()
 src=a.source.resolve();out=a.build.resolve();cc=a.clang.resolve();out.mkdir(parents=True,exist_ok=True)
 tools=out/'actual-tools';tools.mkdir(exist_ok=True);tool_refs={}
 for name,path in [('cmake',a.cmake),('ninja',a.ninja)]:
  before=ref(path);dst=tools/name;shutil.copyfile(path.resolve(),dst)
  if ref(dst)['sha256']!=before['sha256'] or ref(path)!=before:raise ValueError('actual normal build tool changed')
  tool_refs[name]=dict(invoked_path=str(path),sha256=before['sha256'],bytes=before['bytes'],retained_copy=ref(dst))
 target={'arm':'arm-linux-ohos','arm64':'aarch64-linux-ohos','x64':'x86_64-linux-ohos','x86_64':'x86_64-linux-ohos'}[a.cpu]
 flags='-fPIC -O2 -flto=thin -fsanitize=cfi -fsanitize-cfi-cross-dso -fvisibility=hidden -fno-sanitize-trap=cfi'
 if a.cpu=='arm':flags+=' -march=armv7-a -mfloat-abi=softfp -mfpu=neon'
 tc=out/'product-toolchain.cmake'
 def q(x):return '"'+str(x).replace('\\','/').replace('"','\\"')+'"'
 tc.write_text('\n'.join(['set(CMAKE_SYSTEM_NAME Linux)','set(CMAKE_SYSTEM_PROCESSOR '+q(a.cpu)+')','set(CMAKE_C_COMPILER '+q(cc)+')','set(CMAKE_CXX_COMPILER '+q(cc.with_name('clang++'))+')','set(CMAKE_AR '+q(cc.with_name('llvm-ar'))+')','set(CMAKE_RANLIB '+q(cc.with_name('llvm-ranlib'))+')','set(CMAKE_C_COMPILER_TARGET '+q(target)+')','set(CMAKE_CXX_COMPILER_TARGET '+q(target)+')','set(CMAKE_SYSROOT '+q(a.sysroot.resolve())+')','set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)','set(CMAKE_FIND_ROOT_PATH '+q(a.sysroot.resolve())+')','set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)','set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)','set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)','set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)','set(CMAKE_C_FLAGS_INIT '+q(flags)+')','set(CMAKE_CXX_FLAGS_INIT '+q(flags)+')','set(CMAKE_EXE_LINKER_FLAGS_INIT "-fuse-ld=lld -flto=thin -fsanitize=cfi -fsanitize-cfi-cross-dso")'])+'\n')
 commands=[]
 def run(words,label,query=False):
  stdout=out/(label+'.stdout');stderr=out/(label+'.stderr')
  with stdout.open('wb') as o,stderr.open('wb') as e:r=subprocess.run([str(w) for w in words],stdout=o,stderr=e,env={**os.environ,'LC_ALL':'C'},timeout=1800,cwd=out)
  commands.append(dict(argv=[str(w) for w in words],exit_code=r.returncode,stdout=ref(stdout),stderr=ref(stderr),normal_product_build=True,read_only_query=query))
  (out/'BUILD.json').write_text(json.dumps(dict(schema='normal-openal-hrtf-build/v1',status='building',commands=commands,runtime_pass=False),indent=2)+'\n')
  if r.returncode:raise RuntimeError('normal product OpenAL '+label+' failed; original stdio retained')
 opts=['-DLIBTYPE=STATIC','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_POSITION_INDEPENDENT_CODE=ON','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DALSOFT_EMBED_HRTF_DATA=ON','-DALSOFT_UPDATE_BUILD_VERSION=OFF','-DALSOFT_UTILS=OFF','-DALSOFT_EXAMPLES=OFF','-DALSOFT_TESTS=OFF','-DALSOFT_INSTALL=OFF','-DALSOFT_DLOPEN=OFF','-DALSOFT_RTKIT=OFF']
 for backend in ['PIPEWIRE','PULSEAUDIO','ALSA','OSS','SOLARIS','SNDIO','JACK','COREAUDIO','OBOE','OPENSL','PORTAUDIO','SDL2','SDL3','WAVE']:opts.append('-DALSOFT_BACKEND_'+backend+'=OFF')
 run([a.cmake,'-S',src,'-B',out,'-G','Ninja','-DCMAKE_MAKE_PROGRAM='+str(a.ninja.resolve()),'-DCMAKE_TOOLCHAIN_FILE='+str(tc),*opts],'configure')
 run([a.cmake,'--build',out,'--target','OpenAL','--parallel','2','--verbose'],'compile-and-archive')
 run([a.ninja,'-C',out,'-t','commands','OpenAL'],'full-commands',True);run([a.ninja,'-C',out,'-t','deps'],'full-deps',True)
 db=json.loads((out/'compile_commands.json').read_bytes());units=[]
 for e in db:
  words=e.get('arguments') or shlex.split(e['command']);obj=words[words.index('-o')+1];object_path=Path(e['directory'])/obj
  units.append(dict(source=ref(Path(e['directory'])/e['file']),object=ref(object_path),command=words,effective_CFI=('-fsanitize=cfi' in words and '-fsanitize-cfi-cross-dso' in words)))
 if not units or not all(u['effective_CFI'] for u in units):raise ValueError('all real OpenAL TUs must retain product CFI and thin LTO')
 value=dict(schema='normal-openal-hrtf-build/v1',status='complete',normal_product_build=True,target=target,tools=tool_refs,compiler=ref(cc),sysroot=str(a.sysroot.resolve()),toolchain=ref(tc),source_manifest=ref(src.parent/'OPENAL-INPUTS.json'),archive=ref(out/'libopenal.a'),archive_logical=str(out/'libopenal.a'),translation_units=units,commands=commands,compilation_database=ref(out/'compile_commands.json'),ninja=ref(out/'build.ninja'),ninja_log=ref(out/'.ninja_log'),runtime_pass=False)
 (out/'BUILD.json').write_text(json.dumps(value,indent=2)+'\n')
 return 0
if __name__=='__main__':raise SystemExit(main())
