"""Normal GN action: fixed OpenAL 1.24.3 CPU HRTF archive, no test execution.

Invoked only by the existing product Ninja/Owner. Actual toolchain and complete
commands/deps/objects are retained; this action never creates a container/lease.
"""
from pathlib import Path
import argparse,hashlib,json,os,shlex,shutil,subprocess

def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def compilation_key(words, out):
 # CMake's exported database may omit Ninja's depfile-only switches. Strip
 # only the fixed -MD/-MT/-MF triplet after binding it to the same object;
 # every semantic compiler argument remains part of the exact match.
 if words.count('-o')!=1 or words.index('-o')+1>=len(words):raise ValueError('one complete normal compiler output required')
 obj=(out/words[words.index('-o')+1]).resolve();remove=set();modes=[i for i,w in enumerate(words) if w in ('-MD','-MMD')]
 pairs={flag:[i for i,w in enumerate(words) if w==flag] for flag in ('-MT','-MF')}
 if modes or pairs['-MT'] or pairs['-MF']:
  if len(modes)!=1 or len(pairs['-MT'])!=1 or len(pairs['-MF'])!=1:raise ValueError('one complete normal Ninja dependency switch triplet required')
  remove.add(modes[0])
  for flag,indices in pairs.items():
   at=indices[0]
   if at+1>=len(words):raise ValueError('incomplete Ninja dependency switch')
   expected=obj if flag=='-MT' else Path(str(obj)+'.d')
   if (out/words[at+1]).resolve()!=expected:raise ValueError('dependency switch belongs to a different object')
   remove.update((at,at+1))
 if any(w.startswith('@') for w in words):raise ValueError('unretained compiler response file is outside fixed expanded target grammar')
 return tuple(w for i,w in enumerate(words) if i not in remove)

def fixed_target_units(src, out, cc, db):
 # CMake's database describes every configured target, including the unused
 # EXCLUDE_FROM_ALL alsoft.common. Only Ninja's fixed OpenAL command closure
 # selects TUs. A missing selected object is always an error, never a filter.
 commands_path=out/'full-commands.stdout';deps_path=out/'full-deps.stdout'
 lines=commands_path.read_text().splitlines();compiler_paths={cc.resolve(),cc.with_name('clang++').resolve()}
 database={}
 for index,e in enumerate(db):
  words=e.get('arguments') or shlex.split(e['command'])
  if not words or any(type(w) is not str for w in words):raise ValueError('complete actual CMake command argv required')
  database.setdefault(compilation_key(words,out),[]).append((index,e,words))
 selected=[];seen_commands=set();archive_inputs=None;archive_command=None
 for line_number,line in enumerate(lines,1):
  words=shlex.split(line)
  if not words:raise ValueError('empty command in fixed OpenAL closure')
  if Path(words[0]).resolve() in compiler_paths:
   key=compilation_key(words,out);matches=database.get(key,[])
   if len(matches)!=1 or key in seen_commands:raise ValueError('each fixed OpenAL compiler command needs one complete database row')
   seen_commands.add(key);index,e,database_words=matches[0]
   directory=Path(e['directory']).resolve()
   if directory!=out or words.count('-o')!=1:raise ValueError('fixed normal Ninja build directory and one object output required')
   slot=words.index('-o')
   if slot+1>=len(words):raise ValueError('missing actual compiler output')
   obj=(directory/words[slot+1]).resolve();source=(directory/e['file']).resolve()
   if not obj.is_relative_to(out) or not source.is_relative_to(src):raise ValueError('fixed OpenAL source and build object paths required')
   selected.append((index,source,obj,words,line_number,database_words))
  # The exact normal CMake static-library command may be surrounded by its
  # no-op/ranlib shell segments. Admit one llvm-ar segment for libopenal.a.
  for position,word in enumerate(words):
   if word in ('&&','||',';',':') or word.startswith('-'):continue
   if Path(word).resolve()!=cc.with_name('llvm-ar').resolve():continue
   if archive_inputs is not None or (position and words[position-1]!='&&'):raise ValueError('one fixed normal archive command required')
   end=next((i for i in range(position+1,len(words)) if words[i] in ('&&','||',';')),len(words))
   segment=words[position:end]
   if len(segment)<4 or segment[1]!='qc' or (out/segment[2]).resolve()!=out/'libopenal.a':raise ValueError('fixed CMake llvm-ar qc libopenal.a grammar required')
   archive_inputs=[(out/name).resolve() for name in segment[3:]];archive_command=dict(line=line_number,argv=segment,raw=line)
   if any(not p.is_relative_to(out) or p.suffix!='.o' for p in archive_inputs):raise ValueError('complete normal archive object inputs required')
 objects=[row[2] for row in selected]
 if not selected or archive_inputs is None or len(set(objects))!=len(objects) or len(set(archive_inputs))!=len(archive_inputs) or set(objects)!=set(archive_inputs):raise ValueError('all and only fixed target compiler outputs must enter the actual archive')
 # fmt is an OBJECT library and is part of this STATIC OpenAL target. The
 # unrelated alsoft.common target must neither disappear by missing-file
 # filtering nor be confused with the common sources compiled into OpenAL.
 fmt={src/'fmt-11.1.1/src/format.cc',src/'fmt-11.1.1/src/os.cc'}
 if not fmt<={row[1] for row in selected}:raise ValueError('both real bundled fmt OBJECT translation units required')
 dependencies=deps_path.read_text().splitlines();units=[]
 for index,source,obj,words,line_number,database_words in selected:
  name=str(obj.relative_to(out));headers=[i for i,line in enumerate(dependencies) if line.startswith(name+': #deps ')]
  if len(headers)!=1:raise ValueError('one actual Ninja dependency record per selected object required')
  start=headers[0];stop=start+1
  while stop<len(dependencies) and dependencies[stop].startswith('    '):stop+=1
  header=dependencies[start];paths=[line[4:] for line in dependencies[start+1:stop]]
  count=header.split(': #deps ',1)[1].split(',',1)[0]
  if not count.isdecimal() or int(count)!=len(paths) or not header.endswith('(VALID)') or not paths or source not in {(out/p).resolve() for p in paths}:raise ValueError('valid complete actual target dependency record and primary source required')
  effective=all(flag in words for flag in ('-fsanitize=cfi','-fsanitize-cfi-cross-dso','-flto=thin'))
  if not effective:raise ValueError('all selected real OpenAL and fmt TUs require CFI and thin LTO')
  units.append(dict(source=ref(source),object=ref(obj),command=words,effective_CFI=effective,
   compilation_database_index=index,compilation_database_command=database_words,target_command_line=line_number,ninja_dependency_header=header,ninja_dependency_paths=paths))
 indices={row[0] for row in selected}
 closure=dict(schema='normal-fixed-OpenAL-command-dependency-closure/v1',fixed_target='OpenAL',fixed_archive='libopenal.a',
  full_commands=ref(commands_path),full_dependencies=ref(deps_path),target_query=ref(out/'target-query.stdout'),archive_query=ref(out/'archive-query.stdout'),
  configured_compilation_entries=len(db),selected_compilation_database_indices=sorted(indices),outside_target_compilation_database_indices=[i for i in range(len(db)) if i not in indices],
  archive_command=archive_command,archive_object_inputs=[str(p.relative_to(out)) for p in archive_inputs],required_fmt_sources=[str(p.relative_to(src)) for p in sorted(fmt)])
 return units,closure
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
 run([a.ninja,'-C',out,'-t','query','OpenAL'],'target-query',True)
 run([a.ninja,'-C',out,'-t','query','libopenal.a'],'archive-query',True)
 db=json.loads((out/'compile_commands.json').read_bytes());units,closure=fixed_target_units(src,out,cc,db)
 value=dict(schema='normal-openal-hrtf-build/v1',status='complete',normal_product_build=True,target=target,tools=tool_refs,compiler=ref(cc),sysroot=str(a.sysroot.resolve()),toolchain=ref(tc),source_manifest=ref(src.parent/'OPENAL-INPUTS.json'),archive=ref(out/'libopenal.a'),archive_logical=str(out/'libopenal.a'),translation_units=units,target_closure=closure,commands=commands,compilation_database=ref(out/'compile_commands.json'),ninja=ref(out/'build.ninja'),ninja_log=ref(out/'.ninja_log'),runtime_pass=False)
 (out/'BUILD.json').write_text(json.dumps(value,indent=2)+'\n')
 return 0
if __name__=='__main__':raise SystemExit(main())
