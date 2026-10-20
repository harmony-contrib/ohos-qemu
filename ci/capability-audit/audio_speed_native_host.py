#!/usr/bin/env python3
"""Bounded, continuing normal audio through complete AudioSpeed and the separately certified defined-arithmetic Sonic."""
import argparse,json,hashlib
from pathlib import Path
from audio_write_queue_native_host import prepare,dependencies,compile_and_run,FIX
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
tree,env,applied=prepare(out);dependencies(out,tree)
(out/'driver.cpp').write_bytes((FIX/'speed_harness528.cpp.in').read_bytes())
rows=compile_and_run(out,a.compiler,env)
value=dict(commands=[applied,*rows],scope='complete AudioSpeed and unmodified the separately certified defined-arithmetic Sonic; PCM conversion/logging utilities are explicit host shims; 120 regular +384 full-scale S16 bounded-read vs full-read byte comparisons plus finish/reconfigure; no old failing capacity probe, target ABI or real audio device',target_build_passed=False,runtime_passed=False,onset_proven=False,first_artifact_behavior_gate_passed=False)
(out/'RESULT.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps([r['exit']for r in rows]));assert len(rows)==3 and all(r['exit']==0 for r in rows)
