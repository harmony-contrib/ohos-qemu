#!/usr/bin/env python3
"""Compare discarded/empty-finished AudioSpeed epochs with fresh converters; host only."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from audio_write_queue_native_host import prepare,dependencies,FIX

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--compiler',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    tree,env,applied=prepare(out);dependencies(out,tree)
    (out/'driver.cpp').write_bytes((FIX/'speed_flush_harness545.cpp.in').read_bytes())
    flags=['-DSONIC_ENABLE','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',
           '-fno-omit-frame-pointer','-I'+str(out)]
    commands=[
        [str(a.compiler.with_name('clang')),*flags,'-DsonicCreateStream=sonicCreateStreamActual545',
         '-DsonicDestroyStream=sonicDestroyStreamActual545','-c',str(out/'sonic.c'),'-o',str(out/'sonic.o')],
        [str(a.compiler),'-std=c++20','-fno-exceptions',*flags,str(out/'audio_speed.cpp'),
         str(out/'driver.cpp'),str(out/'sonic.o'),'-o',str(out/'driver')],
        [str(out/'driver')]]
    rows=[]
    for i,cmd in enumerate(commands):
        run=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        stdout=f'{i}.stdout.log';stderr=f'{i}.stderr.log'
        (out/stdout).write_text(run.stdout);(out/stderr).write_text(run.stderr)
        rows.append(dict(argv=cmd,exit=run.returncode,stdout=stdout,stderr=stderr))
        if run.returncode:break
    sources={n:hashlib.sha256((out/n).read_bytes()).hexdigest()for n in ('audio_speed.cpp','audio_speed.h','sonic.c','sonic.h','driver.cpp')}
    value=dict(commands=[applied,*rows],sources=sources,
        scope='complete AudioSpeed and certified Sonic; five formats, one/two/eight channels, four speeds, three Sonic pitches, unread/finished histories, repeated flush, initial/post-flush/repeated empty Finish, real short input Finish, invalid-configuration recovery and explicit create failure dependency seam; PCM utility/logging host shims; no target ABI/IPC/real allocation pressure/hardware',
        target_build_passed=False,runtime_passed=False,onset_proven=False,first_artifact_behavior_gate_passed=False)
    (out/'RESULT.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps([r['exit']for r in rows]))
    assert len(rows)==3 and all(r['exit']==0 for r in rows)
if __name__=='__main__':main()
