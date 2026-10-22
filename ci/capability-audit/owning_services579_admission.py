"""Pure actual normal-product addon admission, shared by producer and raw replay.

Only the selected diagnostic C++ NAPI row is admitted. Nothing here executes a
compiler, ELF utility or guest command, and input DATA cannot select Python code.
"""
from pathlib import Path
import posixpath,re
from owning_services579_contract import need,raw,doc,ref
from owning_services579_native import helper_recipes,ANCHORS

HELPER='owning_services579_napi'


def admit(native,*,archive_sha256,arch):
 need(type(native) is dict and set(native)=={'binary','build','abi'},'exact three-key actual addon DATA')
 need(native['abi']=={'arm64':'arm64-v8a','armv7a':'armeabi-v7a','x86_64':'x86_64'}[arch],'actual addon ABI')
 for key in ('binary','build'):
  need(set(native[key])=={'path','sha256'},'addon inputs are actual Ref2');raw(native[key])
 build=doc(native['build']);need(build['status']=='pass_compile_link_ONLY' and set(build['helpers'])=={HELPER},'separate selected original Builder batch')
 row=build['helpers'][HELPER];spec=helper_recipes()[HELPER]
 recipe=build['owning_services_native_recipe'];need(recipe['sha256']==ref(Path(__file__).with_name('owning_services579_native.py'))['sha256'] and
  build['inputs'][recipe['path']]==recipe,'actual fixed normal recipe source')
 def artifact(record):
  from native579_artifact_context import checked
  path=Path(record['path'])
  if str(path).startswith('/build/helpers/'):
   local=Path(native['build']['path']).parent/str(path).removeprefix('/build/helpers/')
   need(local.resolve()==local and ref(local)['sha256']==record['sha256'] and local.stat().st_size==record['bytes'],'retained original helper artifact')
   return local
  return checked(record)
 from native579_artifact_context import binding_context
 context=binding_context(build,row,Path(native['binary']['path']),artifact)
 need(context['arch']==arch and context['normal'] is not None and row['status']=='pass_compile_link_ONLY' and
  row['installed_runtime_profile']['profile']['archive']['sha256']==archive_sha256 and row['elf_kind']=='shared_napi' and
  row['language']=='c++' and row['CFI_preserved'] is True and row['binary_sha256']==native['binary']['sha256'],'actual package/target/native row')
 source=Path(__file__).with_name('owning_services579')/'native/ServicesNative.cpp';source_sha=ref(source)['sha256']
 need(row['source']['sha256']==source_sha==row['private_source_sha256'],'actual compiled fixed caller source')
 def command(label,argv=None):
  found=[v for v in build['commands'] if v['label']==label]
  need(len(found)==1 and found[0]['exit_code']==0 and not found[0].get('timed_out'),'actual successful normal production '+label)
  v=found[0]
  if argv is not None:need(v['argv']==argv,'actual compiler/linker argv differs '+label)
  need(v['log'].startswith('/build/helpers/'),'normal build command log leaves fixed production output')
  local=Path(native['build']['path']).parent/str(v['log']).removeprefix('/build/helpers/')
  path=artifact(dict(path=v['log'],sha256=v['sha256'],bytes=local.stat().st_size))
  return path.read_text()
 import batch_system_build_runtime_helpers as product
 compile_argv=row['compile_command'];link_argv=row['link_command']
 command(HELPER+'-compile',compile_argv);trace=command(HELPER+'-link',link_argv)
 need(compile_argv[-4]=='-c' and compile_argv[-2]=='-o' and compile_argv.count('-fPIC')>=1 and
  link_argv.count('-shared')==1 and '-Wl,-soname=libowning_services579.so' in link_argv and '-nostdlib' in link_argv and
  '-Wl,--threads=2' in link_argv and '-Wl,-t' in link_argv,'original actual shared-NAPI compile/link layout')
 compiled=artifact(dict(path=compile_argv[-3],sha256=source_sha,bytes=source.stat().st_size));need(compiled.read_bytes()==source.read_bytes(),'retained compiler source is not fixed source')
 guards=[compile_argv[i+1] for i,v in enumerate(compile_argv[:-1]) if v=='-include' and compile_argv[i+1].endswith('/actual_system_abi.h')]
 need(len(guards)==1,'one original product __h ABI guard')
 guard_path=guards[0]
 guard=artifact(dict(path=guard_path,sha256=row['abi_guard_sha256'],bytes=len(product.ABI_GUARD.encode())))
 need(guard.read_text()==product.ABI_GUARD,'actual normal system __h ABI compile guard')
 need(len(row['anchors'])==len(ANCHORS),'exact actual graph anchors')
 for index,(anchor,wanted) in enumerate(zip(row['anchors'],ANCHORS)):
  need(anchor['graph']['path']==build['build_directory']+'/'+wanted['graph'] and anchor['object_target']==wanted['object'] and
   build['inputs'][anchor['graph']['path']]==anchor['graph'],'actual selected existing GN graph/object')
  text=command(HELPER+'-'+str(index)+'-actual-GN-command')
  matches=[line for line in text.splitlines() if ('clang ' if wanted['source'].endswith('.c') else 'clang++ ') in line and ' -c ' in line]
  need(matches==[anchor['actual_command']],'actual complete Ninja anchor compiler row')
  driver=build['normal_link_tools']['c_compiler' if wanted['source'].endswith('.c') else 'compiler']['literal']
  need(product.compile_flags(matches[0],Path(driver),Path(build['source_root'])/wanted['source'],Path(build['build_directory']))==anchor['flags'],
   'retained GN anchor flags differ from actual command')
 info=command(HELPER+'-actual-ELF-ABI')
 need(product.defined_symbol(info,'__cfi_check') and 'std::__h::' in info and 'std::__n1::' not in info and
  product.dynamic_needed(info)==set(row['DT_NEEDED']) and {Path(n).name for n in spec['libraries']}<=set(row['DT_NEEDED']),
  'actual product C++ CFI/DT_NEEDED/full readelf output')
 need(product.elf_soname(native['binary']['path'],product=context['product'])=='libowning_services579.so','actual binary SONAME')
 need(set(product.elf_needed(native['binary']['path'],product=context['product']))==set(row['DT_NEEDED']),'actual ELF DT_NEEDED differs')
 for soname in row['DT_NEEDED']:product.runtime_link_records(row,soname)
 # Preserve the actual '-t' path tokens without consulting vanished CID
 # paths on the host. Original Builder performed regular-file/realpath checks.
 # This replay joins the literal trace to its retained canonical input rows.
 opened=set()
 for line in re.sub(r'\x1b\[[0-9;]*m','',trace).splitlines():
  token=line.strip().split('(',1)[0]
  if token and not any(ch.isspace() for ch in token):
   opened.add(posixpath.normpath(token if token.startswith('/') else build['build_directory']+'/'+token))
 need(all(v['path'] in opened and v in row['actual_link_inputs'] for v in row['linked_libraries']),
  'actual linker trace omitted selected direct DSO')
 need(all(v['path'] in build['inputs'] and build['inputs'][v['path']]==v for v in row['actual_compiler_dependencies'] if v['path'].startswith(build['source_root']+'/')),
  'actual compiler dependencies absent from source/out input manifest')
 return context
