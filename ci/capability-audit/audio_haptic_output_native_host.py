#!/usr/bin/env python3
"""ASan/UBSan host execution of exact HPAE queue methods; no target/HDI/HW claim."""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
COMP=ROOT/'patches/common/foundation/multimedia/audio_framework/audio_haptic_sync_id'
FIX=HERE/'fixtures/audio_haptic_sync_id'
REL='foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp'
METHODS=('DoProcess','ReadDataAndConvertFormat','RenderFrameForAuxiliarySink','Reset','ResetAll',
         'RenderSinkFlush','RenderSinkReset','RenderSinkPause','RenderSinkResume','RenderSinkStart','RenderSinkStop',
         'RenderSinkDeInit','GetRenderSinkInstance')

def function(text,name):
    match=re.search(r'(?:void|bool|int32_t) HpaeSinkOutputNode::'+re.escape(name)+r'\([^;{}]*\)\n\{',text)
    if not match:raise ValueError('literal source method missing: '+name)
    start=match.start();i=match.end()-1;depth=0;mode='code'
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
    raise ValueError('unterminated literal source method')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--compiler',type=Path,required=True);p.add_argument('--hook-pcm',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    state=json.loads((COMP/'source_states.json').read_bytes());patch=COMP/state['patch'];tree=out/'source'
    shutil.copytree(FIX/'before',tree)
    for source in tree.rglob('*'):
        if source.is_file():source.chmod(0o644)
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env.update(PYTHONDONTWRITEBYTECODE='1',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',
        GIT_CEILING_DIRECTORIES=str(out),TMPDIR=str(out),ASAN_OPTIONS='detect_leaks=1',
        LSAN_OPTIONS='suppressions='+str(FIX/'lsan-macos495.supp')+':print_suppressions=1')
    argv=['bash',str(COMP/'apply.sh'),'--source-root',str(tree)]
    proc=subprocess.run(argv,capture_output=True,text=True,env=env)
    (out/'apply.log').write_text(proc.stdout+proc.stderr)
    results=[dict(stage='original-generic-apply',argv=argv,exit_code=proc.returncode)]
    if proc.returncode:raise RuntimeError('generic exact installation failed')
    for variant,source in [('before',FIX/'before'/REL),('after',tree/REL)]:
        text=source.read_text();methods=METHODS+(()if variant=='before'else('ResetPendingRenderData',))
        bodies='\n\n'.join(function(text,name)for name in methods)
        cpp=out/(variant+'.cpp');cpp.write_text((FIX/'output_harness512.cpp.in').read_text().replace('@REAL_FUNCTIONS@',bodies))
        binary=out/(variant+'.bin');argv=[str(a.compiler),'-std=c++17','-O1','-g','-fsanitize=address,undefined',
            '-fno-omit-frame-pointer','-pthread',str(cpp),'-o',str(binary)]
        if variant=='before':argv.insert(1,'-DBEFORE512=1')
        if a.hook_pcm:argv.insert(1,'-DENABLE_HOOK_PCM=1')
        proc=subprocess.run(argv,capture_output=True,text=True,env=env)
        (out/(variant+'-compile.log')).write_text(proc.stdout+proc.stderr)
        results.append(dict(stage=variant+'-compile',argv=argv,exit_code=proc.returncode,
            product_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),extracted_method_count=len(methods)))
        if proc.returncode:raise RuntimeError(variant+' extracted method compilation failed')
        proc=subprocess.run([str(binary)],capture_output=True,text=True,env=env)
        (out/(variant+'-run.log')).write_text(proc.stdout+proc.stderr)
        expected=1 if variant=='before'else 0
        results.append(dict(stage=variant+'-run',argv=[str(binary)],exit_code=proc.returncode,expected_exit=expected))
        if proc.returncode!=expected:raise RuntimeError(variant+' extracted method result differs')
    value=dict(scope='literal product queue methods in explicit host dependency model ONLY',commands=results,
        host_lsan_suppression=dict(path=str(FIX/'lsan-macos495.supp'),
            sha256=hashlib.sha256((FIX/'lsan-macos495.supp').read_bytes()).hexdigest()),
        target_compiled=False,real_HDI_tested=False,onset_proven=False,first_artifact_behavior_gate_passed=False)
    (out/'RESULT.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value,indent=2))
if __name__=='__main__':main()
