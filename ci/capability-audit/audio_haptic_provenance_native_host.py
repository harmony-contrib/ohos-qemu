#!/usr/bin/env python3
"""Real source method/header host checks. No target/guest/HW acceptance."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,wave
from pathlib import Path
HERE=Path(__file__).resolve().parent
P='foundation/multimedia/player_framework';C='foundation/multimedia/av_codec'
def clean_env(output):
 env={k:v for k,v in os.environ.items()if not k.startswith('GIT_')}
 env['GIT_CEILING_DIRECTORIES']=str(output.parent);env['TMPDIR']=str(output/'tmp');(output/'tmp').mkdir(exist_ok=True)
 return env
def command(argv,output,name,commands,env=None):
 r=subprocess.run([str(x)for x in argv],text=True,capture_output=True,env=env)
 (output/(name+'.stdout.log')).write_text(r.stdout);(output/(name+'.stderr.log')).write_text(r.stderr)
 commands.append(dict(argv=[str(x)for x in argv],exit_code=r.returncode))
 if r.returncode:raise RuntimeError(name+' failed; original output preserved')
 return r.stdout
def prepare(repo,fixture,output,commands,env):
 meta=json.loads((fixture/'SOURCE505.json').read_text())
 for f in meta['source_files']:
  p=fixture/'before'/f['relative'];raw=p.read_bytes()
  if p.is_symlink()or len(raw)!=f['bytes']or hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('actual fixture differs: '+f['relative'])
 before=output/'before';after=output/'after';shutil.copytree(fixture/'before',before);shutil.copytree(before,after)
 for project in [P,C]:
  component=repo/'patches/common'/project/'audio_haptic_source_provenance'
  command([sys.executable,component/'verify_source.py','--source-root',after,'--check-prerequisites'],output,project.rsplit('/',1)[1]+'-prereq',commands,env)
  command([sys.executable,repo/'patches/lib/apply_exact_component.py','--component-dir',component,'--source-root',after],output,project.rsplit('/',1)[1]+'-generic',commands,env)
  command([sys.executable,component/'verify_source.py','--source-root',after,'--require-patched'],output,project.rsplit('/',1)[1]+'-require',commands,env)
 headers=list(after.rglob('qemu_audio_provenance505.h'))
 if len(headers)!=3 or any(hashlib.sha256(p.read_bytes()).hexdigest()!=meta['private_header_sha256']for p in headers):raise ValueError('three private headers differ')
 return before,after,headers[0].parent

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--compiler',default=os.environ.get('CXX','clang++'));p.add_argument('--repo-root',type=Path,default=HERE.parents[1]);a=p.parse_args()
 output=a.output.resolve();output.mkdir(parents=True,exist_ok=False);commands=[];results={};env=clean_env(output);repo=a.repo_root.resolve();fixture=repo/'ci/capability-audit/fixtures/audio_haptic_source_provenance'
 try:
  before,after,include=prepare(repo,fixture,output,commands,env)
  sys.path.insert(0,str(fixture));from extract505 import method
  sanitizer=dict(env,ASAN_OPTIONS='detect_leaks=1',LSAN_OPTIONS='suppressions='+str(fixture/'lsan-macos505.supp'))
  wav=output/'actual-input.wav'
  with wave.open(str(wav),'wb')as w:w.setparams((2,2,48000,0,'NONE','not compressed'));w.writeframes(bytes(range(128))*4)
  def compile_run(name,cpp,args=(),defines=()):
   source=output/(name+'.cpp');source.write_text(cpp);binary=output/(name+'.bin')
   argv=[a.compiler,'-std=c++17','-fno-exceptions','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',include,*defines,source,'-o',binary]
   command(argv,output,name+'-compile',commands,env)
   return command([binary,*args],output,name+'-run',commands,sanitizer)
  embedded=output/'embedded-source.bin';embedded.write_bytes(b'prefix!'+wav.read_bytes()+b'trailing!')
  header=(fixture/'header_host505.cpp').read_text();observed=json.loads(compile_run('header',header,[wav,embedded]));
  if observed['source_prefix_bytes']!=128 or observed['source_prefix_sha256']!=hashlib.sha256(bytes(range(128))).hexdigest():raise ValueError('actual source-FD WAV prefix SHA256 differs')
  hashes=command([output/'header.bin','hashes'],output,'header-hashlib',commands,sanitizer)
  for row in hashes.splitlines():
   amount,actual=row.split();expected=hashlib.sha256(bytes(range(128))[:int(amount)]).hexdigest()
   if actual!=expected:raise ValueError('SHA256/hashlib mismatch')
  results['header']={'NIST_and_hashlib_vectors':12,'real_FD_offset_unchanged':True,'interval_and_old_generation_edges':True,'bounded_observation_limit_unknown':True}
  for label,rel,owner,names,token,template in [
   ('normal',P+'/frameworks/native/audio_haptic/audio_haptic_sound_normal_impl.cpp','AudioHapticSoundNormalImpl',['StartSound'],'@REAL_METHOD@','normal_host505.cpp.in'),
   ('meta',P+'/services/engine/histreamer/player/hiplayer_impl.cpp','HiPlayerImpl',['SetAudioRendererParameter'],'@REAL_METHODS@','meta_host505.cpp.in'),
   ('plugin',C+'/services/media_engine/plugins/sink/audio_server_sink_plugin.cpp','AudioServerSinkPlugin',['DrainCacheData','CacheData','WriteAudioBuffer','Write','Flush'],'@REAL_METHODS@','plugin_host505.cpp.in')]:
   summary={}
   for state,tree in [('before',before),('after',after)]:
    raw=(tree/rel).read_text();selected=list(names)
    if state=='after':
     if label=='meta':selected+=['ApplyAudioSourceProvenance505']
     if label=='plugin':selected=['BindSourceProvenance505','DropCachedProvenance505',*selected]
    cpp=(fixture/template).read_text().replace(token,'\n\n'.join(method(raw,owner,n)for n in selected))
    if label=='plugin':
     constants=[]
     for key in ['DEFAULT_BUFFER_NUM','WRITE_WAIT_TIME']:
      matches=re.findall(r'^constexpr int32_t '+key+r' = \d+;',raw,re.M)
      if len(matches)!=1:raise ValueError('actual plugin constant not unique')
      constants+=matches
     cpp=cpp.replace('@ACTUAL_CONSTANTS@','\n'.join(constants))
    stdout=compile_run(label+'-'+state,cpp,[wav]if label=='normal'else[],['-DQAP505_AFTER='+str(int(state=='after'))]);summary[state]=[json.loads(row)for row in stdout.splitlines()]
   if summary['before']!=summary['after']:raise ValueError('original business outcomes differ: '+label)
   results[label]={'business_outcomes_identical':True,'business_cases':len(summary['after']),'scope':'actual extracted methods; controlled external dependencies'}
  oracle=[]
  for state,expected in [('before',1),('after',0)]:
   argv=[str(output/('normal-'+state+'.bin')),str(wav),'require-producer'];r=subprocess.run(argv,text=True,capture_output=True,env=sanitizer)
   (output/('producer-'+state+'.stdout.log')).write_text(r.stdout);(output/('producer-'+state+'.stderr.log')).write_text(r.stderr);commands.append(dict(argv=argv,exit_code=r.returncode,expected_exit_code=expected));oracle.append(r.returncode)
   if r.returncode!=expected:raise ValueError('actual native source producer finite oracle changed: '+state)
  results['actual_source_producer_probe']={'before_exit_code':oracle[0],'after_exit_code':oracle[1],'observation':'actual StartSound supplies valid WAV-FD descriptor through controlled Format surface'}
  relay_result=[]
  for state,expected in [('rejected505',1),('after513',0)]:
   tree=before if state=='rejected505'else after
   hip=tree/P/'services/engine/histreamer/player/hiplayer_impl.cpp'
   # The rejected helper is an exact real-source excerpt pinned to its rejected freeze.
   rejected=fixture/'rejected_full_meta_helper505.cpp';source_meta=json.loads((fixture/'SOURCE505.json').read_text())
   if hashlib.sha256(rejected.read_bytes()).hexdigest()!=source_meta['rejected505_excerpt']['sha256']:raise ValueError('rejected actual helper excerpt differs')
   helper=rejected.read_text()if state=='rejected505'else method(hip.read_text(),'HiPlayerImpl','ApplyAudioSourceProvenance505')
   ordinary=method((after/P/'services/engine/histreamer/player/hiplayer_impl.cpp').read_text(),'HiPlayerImpl','SetAudioRendererParameter')
   bodies=[ordinary,helper]
   for relative,owner,names in [
    (C+'/services/media_engine/filters/audio_sink_filter.cpp','AudioSinkFilter',['SetParameter']),
    (C+'/services/media_engine/modules/sink/audio_sink.cpp','AudioSink',['SetParameter']),
    (C+'/services/media_engine/plugins/sink/audio_server_sink_plugin.cpp','AudioServerSinkPlugin',['SetParameter','SetUpAudioInterruptModeSetter','SetUpAppUidSetter','SetInterruptMode'])]:
    raw=(tree/relative).read_text();bodies += [method(raw,owner,name)for name in names]
   cpp=(fixture/'relay_host513.cpp.in').read_text().replace('@REAL_METHODS@','\n\n'.join(bodies))
   compile_run('relay-'+state,cpp,defines=['-DQAP513_AFTER='+str(int(state=='after513'))])
   argv=[str(output/('relay-'+state+'.bin')),'require-no-replay'];r=subprocess.run(argv,text=True,capture_output=True,env=sanitizer)
   (output/('relay-probe-'+state+'.stdout.log')).write_text(r.stdout);(output/('relay-probe-'+state+'.stderr.log')).write_text(r.stderr);commands.append(dict(argv=argv,exit_code=r.returncode,expected_exit_code=expected));relay_result.append(r.returncode)
   if r.returncode!=expected:raise ValueError('actual native setter replay oracle differs: '+state)
  results['actual_private_relay']={'rejected505_probe_exit_code':relay_result[0],'after513_probe_exit_code':relay_result[1],'ordinary_interrupt_calls':2,'ordinary_uid_calls':1,'ordinary_range_updates':3,'private_late_additional_business_setters':0,'wrong_type_missing_sink_plugin_and_recreation':True,'multi_key_ordinary_path_preserved':True}
  status=0
 except BaseException as error:
  results['error']={'type':type(error).__name__,'message':str(error)};status=1
 value=dict(schema='audio-source-provenance505-host/v1',commands=commands,results=results,exit_code=status,scope='host source/method checks ONLY; no target service build or newly packaged runtime',suppression='exact macOS libobjc _fetchInitializingClassList only; all other leak detection active',compiled_with_exceptions=False,accepted=False,onset_proven=False,first_artifact_behavior_gate_passed=False)
 (output/'RESULT.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value,indent=2));return status
if __name__=='__main__':raise SystemExit(main())
