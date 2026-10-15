#!/usr/bin/env python3
"""Compile repaired full child C API TU with real GN command; not runtime."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from run_root_probe import digest

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/foundation/ability/ability_runtime/native_child_process'
TARGET='obj/foundation/ability/ability_runtime/frameworks/native/child_process/src/child_process/native_child_process.o'
PRODUCTS={'arm64_virt':'aarch64-linux-ohos','armv7a_virt':'arm-linux-ohos','x86_64_virt':'x86_64-linux-ohos'}


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    root=args.source_root.resolve()
    if not os.statvfs(root).f_flag & os.ST_RDONLY:raise ValueError('readonly pinned source required')
    spec=importlib.util.spec_from_file_location('child_config_baseline',COMPONENT/'verify_config_source.py')
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    if baseline.validate(root):raise ValueError('prerepair source needed for isolated candidate compile')
    source=root/baseline.PROJECT/baseline.RELATIVE
    before=digest(source);rows=[]
    with tempfile.TemporaryDirectory(prefix='child-config-full-tu-') as temp:
        isolated=Path(temp);candidate=isolated/baseline.PROJECT/baseline.RELATIVE
        candidate.parent.mkdir(parents=True);candidate.write_bytes(source.read_bytes())
        for attempt in (1,2):
            with (args.output/f'apply-{attempt}.log').open('xb') as log:
                subprocess.run(['bash',str(ROOT/'patches/lib/apply_patch.sh'),str(isolated),
                    str(COMPONENT/'0003-validate-config-boundaries.patch')],stdout=log,stderr=subprocess.STDOUT,check=True)
        baseline.validate(isolated,True)
        for product in args.product:
            cwd=root/'out'/product
            query=subprocess.run([str(root/'prebuilts/build-tools/linux-x86/bin/ninja'),
                '-w','dupbuild=warn','-C',str(cwd),'-t','commands','-s',TARGET],capture_output=True,text=True,check=True)
            (args.output/(product+'-query.log')).write_text(query.stdout+query.stderr)
            argv=shlex.split(query.stdout.splitlines()[-1])
            if Path(argv[0]).name=='ccache':argv.pop(0)
            if (Path(argv[0]).name!='clang++' or '--target='+PRODUCTS[product] not in argv or
                any(t in argv for t in ('&&',';','|')) or argv.count('-c')!=1 or argv.count('-o')!=1 or
                argv.count('-MF')!=1 or (cwd/argv[argv.index('-c')+1]).resolve()!=source):
                raise ValueError('exact real GN C API compilation command required')
            original=argv[:];object_path=args.output/(product+'.o');dep=args.output/(product+'.d')
            argv[argv.index('-c')+1]=str(candidate);argv[argv.index('-o')+1]=str(object_path)
            argv[argv.index('-MF')+1]=str(dep)
            # Quoted local headers retain their original source-directory lookup.
            argv.insert(1,'-iquote'+str(source.parent))
            with (args.output/(product+'-compile.log')).open('xb') as log:
                subprocess.run(argv,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True)
            rows.append(dict(product=product,original_argv=original,candidate_argv=argv,
                object_sha256=digest(object_path),bytes=object_path.stat().st_size))
        if digest(source)!=before:raise ValueError('readonly source changed')
        result=dict(status='pass_full_TU_compile_only',first_artifact_behavior_gate_passed=False,
            runtime_tested=False,source_revision=baseline.REVISION,source_sha256=before,
            patched_sha256=digest(candidate),patch_sha256=digest(COMPONENT/'0003-validate-config-boundaries.patch'),
            objects=rows)
    (args.output/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],objects=len(rows))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--product',choices=PRODUCTS,action='append',required=True)
    run(parser.parse_args())
