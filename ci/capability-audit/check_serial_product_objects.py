#!/usr/bin/env python3
"""Compile changed Serial objects with actual isolated product GN commands.

This reads Ninja's commands but writes only separate diagnostic object/depfile
outputs. It is not a dependency build, library link, SDK-only check, or runtime
acceptance. Missing real generated inputs remain failures, never substitutes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

TARGETS = (
    'obj/base/busmanager/serial_manager/services/native/src/serialservice/serial_right_manager.o',
    'obj/base/busmanager/serial_manager/services/native/src/serialservice/serial_service.o',
    'obj/base/busmanager/serial_manager/test/unittest/serial_service/SerialRightTest/serial_authorization_boundary_test.o',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--scratch-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), default='arm64_virt')
    args = parser.parse_args()
    root, staged, output = (path.resolve() for path in (args.source_root, args.scratch_source, args.output))
    if any(path == root or path.is_relative_to(root) or root.is_relative_to(path) for path in (staged, output)):
        raise ValueError('diagnostic source/output must be separate from production')
    if output == staged or output.is_relative_to(staged) or staged.is_relative_to(output):
        raise ValueError('diagnostic outputs must not overlap the compiling scratch tree')
    for path in (root, root / 'out'):
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError('production source and output must remain read-only')
    if output.exists():
        raise ValueError('refusing to overwrite prior diagnostic outputs')
    product_output = staged / 'out' / args.product
    if 'device_type = "2in1"' not in (product_output / 'args.gn').read_text():
        raise ValueError('actual GN product must select 2in1')
    output.mkdir(parents=True)
    ninja = root / 'prebuilts/build-tools/linux-x86/bin/ninja'
    rows = []
    for index, target in enumerate(TARGETS):
        query = [str(ninja), '-w', 'dupbuild=warn', '-C', str(product_output), '-t', 'commands', '-s', target]
        selected = subprocess.run(query, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        lines = selected.stdout.strip().splitlines()
        if len(lines) != 1:
            raise ValueError('expected one actual product compiler command, not a replacement')
        command = shlex.split(lines[0])
        if Path(command[0]).name != 'clang++' or '-c' not in command or '-o' not in command:
            raise ValueError('unexpected actual product C++ compiler command')
        source = (product_output / command[command.index('-c') + 1]).resolve()
        if not source.is_relative_to(staged / 'base/busmanager/serial_manager'):
            raise ValueError('compiler source is not the imported isolated Serial candidate')
        object_path = output / (str(index) + '-' + Path(target).name)
        command[command.index('-o') + 1] = str(object_path)
        if '-MF' in command:
            command[command.index('-MF') + 1] = str(object_path) + '.d'
        log = output / (str(index) + '-compile.log')
        with log.open('x') as stream:
            compiled = subprocess.run(command, cwd=product_output, stdout=stream, stderr=subprocess.STDOUT)
        row = {'target': target, 'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'actual_GN_command': lines[0], 'diagnostic_command': command, 'exit_code': compiled.returncode,
               'compile_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(), 'object': str(object_path)}
        if object_path.is_file():
            row['object_sha256'] = hashlib.sha256(object_path.read_bytes()).hexdigest()
        rows.append(row)
    result = {'scope': 'actual_GN_product_commands_object_only_NOT_library_link_or_runtime_acceptance',
              'product': args.product, 'scratch_source': str(staged), 'objects': rows,
              'all_changed_objects_compiled': all(row['exit_code'] == 0 for row in rows),
              'product_component_compile_passed': False, 'first_package_gate_passed': False}
    (output / 'serial-product-object-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'objects'}, indent=2))
    for row in rows:
        print(row['target'], row['exit_code'])
    return 0 if result['all_changed_objects_compiled'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
