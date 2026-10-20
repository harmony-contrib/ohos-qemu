#!/usr/bin/env python3
"""Compile exact extracted before/after functions; controlled dependencies only."""
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, unittest
from pathlib import Path
from test_audio_haptic_sync_id_component import git_environment
from audio_write_queue_native_host import extract

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
COMP=ROOT/'patches/common/foundation/multimedia/audio_framework/audio_haptic_sync_id'
FIX=HERE/'fixtures/audio_haptic_sync_id'
S=json.loads((COMP/'source_states.json').read_text());REL=S['project']+'/'+S['files'][0]['relative']
FUNCS=('StartInnerDuringStandby','StartInner')

def function(text,name,owner='RendererInServer'):
 # Lexically skip C++ strings/comments when balancing braces.
 m=re.search(r'int32_t '+re.escape(owner)+'::'+name+r'\([^\n]*\)\n\{',text)
 if not m:raise ValueError('literal real function missing: '+name)
 start=m.start();i=m.end()-1;depth=0;mode='code'
 while i<len(text):
  c=text[i];n=text[i:i+2]
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
   if depth==0:return text[start:i+1]
  i+=1
 raise ValueError('unterminated real function')

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--compiler',required=True,type=Path);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 before=(FIX/'before'/REL).read_text()
 tree=out/'source';shutil.copytree(FIX/'before',tree)
 for source in tree.rglob('*'):
  if source.is_file():source.chmod(0o644)
 apply_argv=['bash',str(COMP/'apply.sh'),'--source-root',str(tree)]
 apply_run=subprocess.run(apply_argv,capture_output=True,text=True,env=git_environment(out))
 (out/'generic-apply.log').write_text(apply_run.stdout+apply_run.stderr)
 if apply_run.returncode:raise RuntimeError('original generic component application failed')
 after=(tree/REL).read_text()
 residues=[]
 for phase,text in (('before',before),('after',after)):
  for name in FUNCS:text=text.replace(function(text,name),'@'+name+'@',1)
  # These four exact methods are the only additional server edits delegated to 528.
  copy=('void' if phase=='before' else 'int32_t')+' RendererInServer::CopyDataToInputBuffer('
  for i,sig in enumerate(('BufferDesc RendererInServer::PrepareOutputBuffer(',
      'int32_t RendererInServer::WriteData()',copy,'int32_t RendererInServer::WriteData(int8_t *inputData')):
   # extract requires only read_bytes and does not normalize source line endings.
   class Source:
    def read_bytes(self):return text.encode()
   text=text.replace(extract(Source(),sig),'@COPY_PUBLISH_'+str(i)+'@',1)
  residues.append(text)
 if residues[0]!=residues[1]:raise ValueError('candidate changed source outside two Start and four finite copy/publish methods')
 # Preserve actual lifecycle/setter bytes as an explicit source constraint;
 # these are not runtime concurrency checks of the full renderer service.
 for name in ('Pause','Flush','Stop','StopInner','Release','SetAudioHapticsSyncId'):
  if function(before,name)!=function(after,name):raise ValueError('lifecycle/setter changed: '+name)
 results=[dict(stage='original-generic-apply',argv=apply_argv,exit_code=apply_run.returncode)]
 for state in ('before','after'):
  text=before if state=='before' else after;bodies='\n\n'.join(function(text,n) for n in FUNCS)
  source=(FIX/'host_harness495.cpp.in').read_text().replace('@REAL_FUNCTIONS@',bodies)
  cpp=out/(state+'.cpp');cpp.write_text(source);binary=out/(state+'.bin')
  cmd=[str(a.compiler),'-std=c++17','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread',str(cpp),'-o',str(binary)]
  proc=subprocess.run(cmd,capture_output=True,text=True);(out/(state+'-compile.log')).write_text(proc.stdout+proc.stderr)
  results.append(dict(stage=state+'-compile',argv=cmd,exit_code=proc.returncode))
  if proc.returncode:raise RuntimeError('real extracted host function compilation failed; see log')
  modes=[([],0),(['--probe-propagation'],1)] if state=='before' else [(['--expect-propagation'],0),(['--probe-propagation'],0)]
  for index,(args,expected) in enumerate(modes):
   cmd=[str(binary),*args];proc=subprocess.run(cmd,capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1',LSAN_OPTIONS='suppressions='+str(FIX/'lsan-macos495.supp')+':print_suppressions=1'))
   (out/(state+'-run-'+str(index)+'.log')).write_text(proc.stdout+proc.stderr)
   results.append(dict(stage=state+'-run-'+str(index),argv=cmd,exit_code=proc.returncode,expected_exit_code=expected,
     host_lsan_suppression=dict(path=str(FIX/'lsan-macos495.supp'),sha256=hashlib.sha256((FIX/'lsan-macos495.supp').read_bytes()).hexdigest())))
   if proc.returncode!=expected:raise RuntimeError('actual regression/behavior exit differs; see log')
 # The newly reachable positive-ID HPAE backend must preserve Start's effect
 # volume/boot side effects, including its original nonzero-error ordering.
 backend_rel=S['project']+'/'+S['files'][1]['relative']
 backend_before=(FIX/'before'/backend_rel).read_text();backend_after=(tree/backend_rel).read_text()
 owner='HpaeRendererStreamImpl';backend_functions=('Start','StartWithSyncId')
 if function(backend_before,'Start',owner)!=function(backend_after,'Start',owner):raise ValueError('ordinary HPAE Start changed')
 residues=[text.replace(function(text,'StartWithSyncId',owner),'@StartWithSyncId@',1)for text in (backend_before,backend_after)]
 if residues[0]!=residues[1]:raise ValueError('backend changed outside StartWithSyncId')
 for state,text in (('before',backend_before),('after',backend_after)):
  bodies='\n\n'.join(function(text,n,owner)for n in backend_functions)
  source=(FIX/'hpae_start_harness496.cpp.in').read_text().replace('@REAL_FUNCTIONS@',bodies)
  cpp=out/('backend-'+state+'.cpp');cpp.write_text(source);binary=out/('backend-'+state+'.bin')
  cmd=[str(a.compiler),'-std=c++17','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread',str(cpp),'-o',str(binary)]
  proc=subprocess.run(cmd,capture_output=True,text=True);(out/('backend-'+state+'-compile.log')).write_text(proc.stdout+proc.stderr)
  results.append(dict(stage='backend-'+state+'-compile',argv=cmd,exit_code=proc.returncode))
  if proc.returncode:raise RuntimeError('actual extracted backend functions failed compilation')
  modes=[([],0),(['--probe-equivalent-effects'],1)]if state=='before'else[(['--expect-equivalent-effects'],0),(['--probe-equivalent-effects'],0)]
  for index,(args,expected)in enumerate(modes):
   cmd=[str(binary),*args];proc=subprocess.run(cmd,capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1',LSAN_OPTIONS='suppressions='+str(FIX/'lsan-macos495.supp')+':print_suppressions=1'))
   (out/('backend-'+state+'-run-'+str(index)+'.log')).write_text(proc.stdout+proc.stderr)
   results.append(dict(stage='backend-'+state+'-run-'+str(index),argv=cmd,exit_code=proc.returncode,expected_exit_code=expected,
    host_lsan_suppression=dict(path=str(FIX/'lsan-macos495.supp'),sha256=hashlib.sha256((FIX/'lsan-macos495.supp').read_bytes()).hexdigest())))
   if proc.returncode!=expected:raise RuntimeError('actual backend side-effect behavior exit differs')
 value=dict(scope='four actual source functions ASan/UBSan host behavior plus original generic exact-file installation ONLY',
  commands=results,
  mirror_was_not_used_as_actual_preimage=True,accepted=False,onset_proven=False,
  native_target_compilation_performed=False,full_service_concurrency_tested=False,first_artifact_behavior_gate_passed=False)
 (out/'RESULT.json').write_text(json.dumps(value,indent=2)+'\n')
 print(json.dumps(value,indent=2))

if __name__=='__main__':main()
