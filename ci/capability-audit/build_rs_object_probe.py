#!/usr/bin/env python3
"""Build a caller of the actual packaged private RS/IPC helper libraries.

Use the product's real Ninja compiler flags and current patched headers. An
optional completed TU record is only for isolated compile-only diagnostics;
that mode cannot link or be used as guest/first-package acceptance evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
UNIT = 'foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp'
TARGET = 'obj/foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rosen_ohos_sources/rs_ashmem_helper.o'
PRODUCTS = {'arm64': 'arm64_virt', 'armv7a': 'armv7a_virt', 'x86_64': 'x86_64_virt'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compiler_arguments(command, source, obj):
    command = list(command)
    if Path(command[0]).name == 'ccache':
        command.pop(0)
    if Path(command[0]).name != 'clang++':
        raise ValueError('expected the actual product C++ compiler')
    command[command.index('-c') + 1] = str(source)
    command[command.index('-o') + 1] = str(obj)
    command[command.index('-MF') + 1] = str(obj.with_suffix('.d'))
    return command


def linker_arguments(command):
    # Retain real ABI/toolchain/LTO choices, not compile-only warning flags
    # such as -fno-ident, which the actual OHOS driver rejects under -Werror
    # when given only object inputs. No host or SDK toolchain substitution.
    prefixes = ('--target=', '--sysroot=', '-march=', '-mfloat-abi=', '-mfpu=',
                '-stdlib=', '-rtlib=', '-unwindlib=', '-fuse-ld=', '-flto=',
                '--gcc-toolchain=', '--ld-path=', '-B')
    flags = []
    iterator = iter(command[1:])
    for value in iterator:
        if value in ('-B', '--sysroot', '--target'):
            flags.extend((value, next(iterator)))
        elif value.startswith(prefixes) or value in ('-static-libstdc++', '-nostdlib++', '-pthread'):
            flags.append(value)
    return flags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--arch', choices=PRODUCTS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compile-only', action='store_true')
    parser.add_argument('--translation-unit-evidence', type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    product = PRODUCTS[args.arch]
    source = Path(__file__).with_name('probes') / 'rs_object_encoding.cpp'
    args.output.mkdir(parents=True, exist_ok=False)
    record = {'scope': 'actual_product_headers_and_flags_compile_only_NOT_guest' if args.compile_only else
              'actual_packaged_RS_IPC_caller_build_NOT_guest', 'arch': args.arch,
              'status': 'fail', 'first_artifact_behavior_gate_passed': False,
              'source_sha256': sha(source), 'builder_sha256': sha(Path(__file__)), 'commands': []}
    try:
        if args.translation_unit_evidence:
            if not args.compile_only:
                raise ValueError('isolated compiler evidence is allowed only for compile-only diagnostics')
            evidence = json.loads(args.translation_unit_evidence.read_text())
            entries = [row for row in evidence.get('results', []) if row.get('product') == product and
                       row.get('source') == UNIT and row.get('exit_code') == 0]
            if evidence.get('status') != 'pass' or len(entries) != 1:
                raise ValueError('complete successful real three-ABI TU evidence required')
            row = entries[0]
            cwd, command = Path(row['generated_input_cwd']), row['argv']
            helper = Path(command[command.index('-c') + 1])
            if sha(helper) != row['patched_source_sha256']:
                raise ValueError('isolated actual helper changed after compilation')
            record['translation_unit_evidence_sha256'] = sha(args.translation_unit_evidence)
        else:
            subprocess.run(['python3', str(ROOT / 'patches/common/foundation/graphic/graphic_2d/async_caller_identity/verify_source.py'),
                            '--source-root', str(root), '--require-patched'], check=True)
            subprocess.run(['python3', str(ROOT / 'patches/common/foundation/communication/ipc/binder_object_safety/verify_source.py'),
                            '--source-root', str(root), '--require-patched'], check=True)
            cwd = root / 'out' / product
            query = [str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-w', 'dupbuild=warn',
                     '-C', str(cwd), '-t', 'commands', '-s', TARGET]
            queried = subprocess.run(query, capture_output=True, text=True, check=True)
            command = shlex.split(queried.stdout.splitlines()[-1])
            if (cwd / command[command.index('-c') + 1]).resolve() != root / UNIT:
                raise ValueError('Ninja source does not match the actual helper')
            record['query_command'] = query
            record['helper_sha256'] = sha(root / UNIT)
        obj = args.output / 'rs-object-encoding.o'
        command = compiler_arguments(command, source, obj)
        log = args.output / 'compile.log'
        with log.open('x') as stream:
            result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        record['commands'].append({'argv': command, 'cwd': str(cwd), 'exit_code': result.returncode,
                                   'log_sha256': sha(log)})
        if result.returncode:
            raise ValueError('actual RS caller compilation failed')
        record['object_sha256'] = sha(obj)
        if not args.compile_only:
            # Link to actual product innerkits, never copied helper objects or
            # SDK substitutes. Only the executable is later sent to the guest.
            innerkits = cwd / 'innerkits' / ('ohos-' + {'armv7a': 'arm'}.get(args.arch, args.arch))
            libraries = [innerkits / 'graphic_2d/librender_service_base/librender_service_base.z.so',
                         innerkits / 'ipc/ipc_core/libipc_single.z.so',
                         cwd / 'commonlibrary/c_utils/libutils.z.so']
            if any(not path.is_file() for path in libraries):
                raise ValueError('real newly built product RS/IPC innerkits are missing')
            flags = linker_arguments(command)
            binary = args.output / 'rs-object-encoding'
            link = [command[0], *flags, str(obj), *map(str, libraries),
                    '-Wl,--allow-shlib-undefined', '-o', str(binary)]
            log = args.output / 'link.log'
            with log.open('x') as stream:
                result = subprocess.run(link, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
            record['commands'].append({'argv': link, 'cwd': str(cwd), 'exit_code': result.returncode,
                                       'log_sha256': sha(log)})
            if result.returncode:
                raise ValueError('actual new product RS caller link failed')
            record['linked_product_libraries_sha256'] = {str(path): sha(path) for path in libraries}
            record['probe_sha256'] = sha(binary)
        if sha(source) != record['source_sha256'] or sha(Path(__file__)) != record['builder_sha256']:
            raise ValueError('RS caller inputs changed during compilation')
        record['status'] = 'pass'
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        record['error'] = str(error)
    (args.output / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'error': record.get('error')}))
    return 0 if record['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
