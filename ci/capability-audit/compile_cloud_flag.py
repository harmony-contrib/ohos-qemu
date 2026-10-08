#!/usr/bin/env python3
"""Real cached product ABC commands on private JS; not fresh GN/link/guest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
SOURCE='foundation/distributeddatamgr/relational_store/frameworks/js/napi/cloud_extension/cloud_extension_stub.js'
TARGET='obj/foundation/distributeddatamgr/relational_store/frameworks/js/napi/cloud_extension/cloud_extension.abc'
COMPONENT=ROOT/'patches/common/foundation/distributeddatamgr/relational_store/api26_cloud_flag'
PRODUCTS=('arm64_virt','armv7a_virt','x86_64_virt')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--products',choices=PRODUCTS,nargs='+',default=list(PRODUCTS))
    args=parser.parse_args()
    if len(args.products)!=len(set(args.products)):
        parser.error('duplicate requested product')
    source=args.source_root.resolve()
    if not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (source,source/'out')):
        raise ValueError('source and product outputs must be read-only')
    args.output.mkdir(exist_ok=False)
    patch=COMPONENT/'0001-export-existing-cloud-record-operation-flag.patch'
    caller=Path(__file__).with_name('cloud_flag_public_probe.cjs')
    inputs=[patch,COMPONENT/'apply.sh',caller,Path(__file__),ROOT/'patches/lib/apply_patch.sh']
    before={str(path):digest(path) for path in inputs}
    original_sha=digest(source/SOURCE)
    report={'status':'fail','scope':'actual_cached_product_cloudExtension_ABC_and_host_JS_enum_NOT_GN_link_guest',
            'first_artifact_behavior_gate_passed':False,'objects':[],'failures':[],
            'recipe_sha256':before,'original_source_sha256':original_sha,
            'requested_products':args.products}
    try:
        with tempfile.TemporaryDirectory(prefix='cloud-flag-private-') as temporary:
            stage=Path(temporary)
            staged=stage/SOURCE;staged.parent.mkdir(parents=True)
            staged.write_bytes((source/SOURCE).read_bytes())
            for attempt in (1,2):
                with (args.output/('apply-'+str(attempt)+'.log')).open('x') as stream:
                    subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(stage)],
                                   stdout=stream,stderr=subprocess.STDOUT,check=True)
            report['patched_source_sha256']=digest(staged)
            with (args.output/'actual-module-evaluation.log').open('x') as stream:
                node=source/'prebuilts/build-tools/common/nodejs/node-v18.20.1-linux-x64/bin/node'
                if not node.is_file():
                    raise ValueError('fixed source Node prebuilt is missing')
                report['host_JS_node_sha256']=digest(node)
                subprocess.run([str(node),'--experimental-vm-modules',str(caller),str(staged)],
                               stdout=stream,stderr=subprocess.STDOUT,check=True)
            report['host_JS_module_check_sha256']=digest(args.output/'actual-module-evaluation.log')
            for product in args.products:
                cwd=source/'out'/product
                query=subprocess.run([str(source/'prebuilts/build-tools/linux-x86/bin/ninja'),
                    '-w','dupbuild=warn','-C',str(cwd),'-t','commands','-s',TARGET],
                    check=True,capture_output=True,text=True)
                log=args.output/(product+'-query.log');log.write_text(query.stdout+query.stderr)
                argv=shlex.split(query.stdout.splitlines()[-1])
                src_path=Path(argv[argv.index('--src-js')+1]) if '--src-js' in argv else Path()
                cached_root=src_path
                for _ in Path(SOURCE).parts:
                    cached_root=cached_root.parent
                if (len(argv)<2 or argv[0]!='/usr/bin/env' or
                    Path(argv[1]).name!='generate_js_bytecode.py' or argv.count('--src-js')!=1 or
                    argv.count('--dst-file')!=1 or argv.count('--frontend-tool-path')!=1 or
                    argv.count('--module')!=1 or
                    cached_root not in (source,Path('/openharmony')) or
                    not cached_root.samefile(source) or not src_path.samefile(source/SOURCE) or
                    Path(argv[argv.index('--dst-file')+1])!=cached_root/'out'/product/TARGET or
                    Path(argv[argv.index('--frontend-tool-path')+1])!=
                        cached_root/'out'/product/'clang_x64/arkcompiler/ets_frontend'):
                    raise ValueError('unexpected actual product bytecode command')
                original=list(argv)
                output=stage/(product+'.abc')
                argv[argv.index('--src-js')+1]=str(staged)
                argv[argv.index('--dst-file')+1]=str(output)
                compile_log=args.output/(product+'-compile.log')
                with compile_log.open('x') as stream:
                    subprocess.run(argv,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,check=True)
                header=output.read_bytes()[:32]
                if output.stat().st_size<128 or header[:8]!=b'PANDA\0\0\0':
                    raise ValueError('compiler did not produce real Ark bytecode')
                report['objects'].append({'product':product,'original_command':original,
                    'executed_command':argv,'abc_sha256':digest(output),'abc_bytes':output.stat().st_size,
                    'query_sha256':digest(log),'log_sha256':digest(compile_log)})
            if (digest(source/SOURCE)!=original_sha or before!={str(path):digest(path) for path in inputs}):
                raise ValueError('source or candidate inputs changed')
        report.update(status='pass',source_and_output_mounts_read_only=True,actual_source_inputs_unchanged=True)
    except Exception as error:
        report['failures'].append(str(error));raise
    finally:
        (args.output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'objects':len(report['objects']),'scope':report['scope']}))


if __name__=='__main__':main()
