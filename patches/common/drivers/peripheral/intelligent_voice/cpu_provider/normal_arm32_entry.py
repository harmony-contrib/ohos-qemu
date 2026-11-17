#!/usr/bin/env python3
"""Fixed normal pre-GN ARM32 tool; invoke in the already-held Owner35 container.

No Docker/Owner/resource constructors. The Root-owned normal shell supplies its
actual selection and one immutable DATA Ref. Other products never compile here.
"""
from pathlib import Path
import argparse,json,re,subprocess,sys,time
from produce_arm32 import checked,doc,ref,need,produce


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--inputs',type=Path,required=True);p.add_argument('--inputs-sha256',required=True)
 p.add_argument('--product',choices=('armv7a_virt',),required=True);p.add_argument('--device',choices=('phone','2in1'),required=True)
 p.add_argument('--source-root',type=Path,required=True);a=p.parse_args()
 need(sys.platform.startswith('linux'),'normal Linux build container tool only')
 input_ref={'path':str(a.inputs),'sha256':a.inputs_sha256};value=doc(input_ref)
 need(set(value)=={'schema','normal_source','representative_gate','sdk_native','source_root','product','device','normal_build_run_id'} and
  value['schema']=='media579-arm32-held-normal-build-inputs/v1','fixed normal DATA only; no executable, role or callback selector')
 need(value['product']==a.product=='armv7a_virt' and value['device']==a.device and value['source_root']==str(a.source_root) and
  type(value['normal_build_run_id'])is str and re.fullmatch('[a-f0-9]{32}',value['normal_build_run_id']),
  'actual Root normal product/device/source and original build run selection')
 root=a.source_root;parent=root/'out/media579-cpu-arm32'/value['normal_build_run_id'];out=parent/a.device
 need(root.is_absolute() and root.resolve()==root and not out.exists(),'fresh selected normal ARM32 build output')
 # No directory or subprocess is created until real global-gate and complete
 # source-apply checks in produce() return to this fixed literal callback.
 report_path=parent/(a.device+'-entry.json');commands=[]
 def call(argv,label):
  need(label=='media579_cpu_arm32_normal_source_production' and argv[:2]==['python3','-B'] and
   Path(argv[2])==Path(__file__).resolve().with_name('build_arm32.py'),'fixed normal compiler entry only')
  parent.mkdir(parents=True,exist_ok=True);need(not report_path.exists(),'one normal entry attempt per original run/device')
  stdout=parent/(a.device+'-entry.stdout');stderr=parent/(a.device+'-entry.stderr')
  row={'argv':argv,'label':label,'exit_code':None,'timed_out':False,'started_monotonic_ns':time.monotonic_ns()};commands.append(row)
  try:
   with stdout.open('xb') as so,stderr.open('xb') as se:
    result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=so,stderr=se,timeout=22000)
   row['exit_code']=result.returncode
  except subprocess.TimeoutExpired:row['timed_out']=True;raise
  finally:
   row.update(stdout=ref(stdout),stderr=ref(stderr),finished_monotonic_ns=time.monotonic_ns())
  return row
 report={'schema':'media579-arm32-held-normal-entry-result/v1','inputs':input_ref,'product':a.product,'device':a.device,
  'normal_build_run_id':value['normal_build_run_id'],'original_owner_container_identity':'retained by the enclosing original Owner35 normal build command, not asserted from DATA',
  'commands':commands,'runtime_pass':False,'first_artifact_behavior_gate_passed':False}
 try:
  result=produce(normal_source=value['normal_source'],representative_gate=value['representative_gate'],sdk_native=value['sdk_native'],
   source_root=str(root),build_dir=str(out),call=call)
  report.update(status='actual_normal_ARM32_compile_link_ONLY',production=result)
 except BaseException as error:report.update(status='failed',error=repr(error));raise
 finally:
  # Failed input/gate checks have no compiler side effects; their error reaches
  # the original outer stdout/stderr even when no per-build output was created.
  if commands:
   with report_path.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
 if report['status']=='actual_normal_ARM32_compile_link_ONLY':print(json.dumps({'entry':ref(report_path),'build':result['build'],'runtime_pass':False}))
 return 0


if __name__=='__main__':raise SystemExit(main())
