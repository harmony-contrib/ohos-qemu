#!/usr/bin/env python3
"""Link a bounded load caller to the product's actual SAMGR/IPC libraries."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from build_rs_object_probe import PRODUCTS, compiler_arguments, linker_arguments, sha

UNIT = 'foundation/systemabilitymgr/samgr/services/samgr/native/source/service_registry.cpp'
TARGET = 'obj/foundation/systemabilitymgr/samgr/services/samgr/native/source/samgr_proxy/service_registry.o'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--arch', choices=PRODUCTS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parameter-policy', action='store_true',
                        help='build the read-only loaded-kernel Fusion parameter access-vector probe')
    args = parser.parse_args()
    root = args.source_root.resolve()
    cwd = root/'out'/PRODUCTS[args.arch]
    args.output.mkdir(parents=True, exist_ok=False)
    name = 'fusion-parameter-access' if args.parameter_policy else 'service-load'
    source = Path(__file__).with_name('probes')/('fusion_parameter_access.cpp' if args.parameter_policy else 'service_load.cpp')
    scope = ('actual_product_Fusion_parameter_AV_caller_build_NOT_guest' if args.parameter_policy
             else 'actual_product_SAMGR_caller_build_NOT_guest')
    report = {'status':'fail', 'scope':scope,
              'arch':args.arch, 'source_sha256':sha(source), 'commands':[],
              'first_artifact_behavior_gate_passed':False}
    def run(argv, label):
        argv = list(map(str, argv))
        log = args.output/(label+'.log')
        with log.open('x') as stream:
            result = subprocess.run(argv,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT)
        report['commands'].append({'argv':argv,'cwd':str(cwd),'exit_code':result.returncode,'log_sha256':sha(log)})
        if result.returncode:
            raise ValueError('actual SAMGR caller '+label+' failed')
    try:
        query = [str(root/'prebuilts/build-tools/linux-x86/bin/ninja'),'-w','dupbuild=warn',
                 '-C',str(cwd),'-t','commands','-s',TARGET]
        result = subprocess.run(query,capture_output=True,text=True,check=True)
        (args.output/'query.log').write_text(result.stdout+result.stderr)
        command = shlex.split(result.stdout.splitlines()[-1])
        if (cwd/command[command.index('-c')+1]).resolve() != root/UNIT:
            raise ValueError('unexpected actual SAMGR compiler unit')
        report['query_argv'] = query
        report['query_sha256'] = sha(args.output/'query.log')
        report['samgr_revision'] = subprocess.check_output(['git','-C',str(root/'foundation/systemabilitymgr/samgr'),
                                                          'rev-parse','HEAD'],text=True).strip()
        obj = args.output/(name+'.o')
        command = compiler_arguments(command,source,obj)
        if args.parameter_policy:
            command += ['-I'+str(root/'third_party/selinux/libselinux/include')]
        run(command,'compile')
        innerkits = cwd/'innerkits'/('ohos-'+{'armv7a':'arm'}.get(args.arch,args.arch))
        libraries = [cwd/'systemabilitymgr/samgr/libsamgr_proxy.z.so',
                     innerkits/'ipc/ipc_core/libipc_single.z.so',cwd/'commonlibrary/c_utils/libutils.z.so']
        if args.parameter_policy:
            libraries = [cwd/'thirdparty/selinux/libselinux.z.so']
        if any(not path.is_file() for path in libraries):
            raise ValueError('actual product SAMGR/IPC libraries missing')
        binary = args.output/name
        run([command[0],*linker_arguments(command),str(obj),*map(str,libraries),
             '-Wl,--allow-shlib-undefined','-o',str(binary)],'link')
        report['linked_product_libraries_sha256'] = {str(path):sha(path) for path in libraries}
        report['probe_sha256'] = sha(binary)
        report['object_sha256'] = sha(obj)
        if sha(source) != report['source_sha256']:
            raise ValueError('probe source changed during compilation')
        report['status'] = 'pass'
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        report['error'] = str(error)
    (args.output/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'error':report.get('error')}))
    return 0 if report['status']=='pass' else 1

if __name__ == '__main__':
    raise SystemExit(main())
