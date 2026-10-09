#!/usr/bin/env python3
"""Build read-only display-service diagnostics with actual product headers/libs."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from build_rs_object_probe import PRODUCTS, compiler_arguments, linker_arguments, sha

UNIT = 'foundation/window/window_manager/dm/src/screen_manager.cpp'
TARGET = 'obj/foundation/window/window_manager/dm/src/libdm/screen_manager.o'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--arch', choices=PRODUCTS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cwd = root / 'out' / PRODUCTS[args.arch]
    source = Path(__file__).with_name('probes') / 'screen_modes_readback.cpp'
    report = dict(status='fail', arch=args.arch, commands=[], source_sha256=sha(source),
                  builder_sha256=sha(Path(__file__)), first_artifact_behavior_gate_passed=False,
                  scope='readonly_product_innerkit_caller_build_NOT_guest_or_ordinary_app')
    try:
        query = [str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-w', 'dupbuild=warn',
                 '-C', str(cwd), '-t', 'commands', '-s', TARGET]
        queried = subprocess.run(query, capture_output=True, text=True, check=True)
        (output / 'ninja-query.log').write_text(queried.stdout + queried.stderr)
        report.update(query=query, query_log_sha256=sha(output / 'ninja-query.log'))
        actual = shlex.split(queried.stdout.splitlines()[-1])
        if (cwd / actual[actual.index('-c') + 1]).resolve() != root / UNIT:
            raise ValueError('Ninja did not resolve the real display manager source')
        obj = output / 'screen-modes.o'
        compile_argv = compiler_arguments(actual, source, obj)
        innerkits = cwd / 'innerkits' / ('ohos-' + {'armv7a': 'arm'}.get(args.arch, args.arch))
        libraries = [innerkits / 'window_manager/libdm/libdm.z.so', cwd / 'commonlibrary/c_utils/libutils.z.so']
        if any(not path.is_file() for path in libraries):
            raise ValueError('real product display libraries missing')
        binary = output / 'screen-modes-readback'
        link_argv = [compile_argv[0], *linker_arguments(compile_argv), str(obj), *map(str, libraries),
                     '-Wl,--allow-shlib-undefined', '-o', str(binary)]
        for label, argv in (('compile', compile_argv), ('link', link_argv)):
            log = output / (label + '.log')
            with log.open('x') as stream:
                result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
            report['commands'].append(dict(argv=argv, cwd=str(cwd), exit_code=result.returncode,
                                           log_sha256=sha(log)))
            if result.returncode:
                raise ValueError('actual product screen probe failed: ' + label)
        if sha(source) != report['source_sha256'] or sha(Path(__file__)) != report['builder_sha256']:
            raise ValueError('screen probe inputs changed during compilation')
        report.update(status='pass', probe_sha256=sha(binary),
                      linked_product_libraries_sha256={str(path): sha(path) for path in libraries})
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'error': report.get('error')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
