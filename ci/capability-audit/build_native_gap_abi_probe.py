#!/usr/bin/env python3
"""Compile a real SDK C loader probe from the final package's whole ABI table."""
import argparse
import json
from pathlib import Path
import subprocess

from const_enum_contracts import sha256
from verify_native_gap_abi_results import runtime_path, validate_definitions


def generate(rows, arch):
    source = []
    for index, row in enumerate(rows):
        source.append('static const char *const FUNCTIONS_' + str(index) + '[] = {' +
                      ','.join(json.dumps(name) for name in row['functions']) + '};')
    source.append('static const struct AbiContract CONTRACTS[] = {')
    for index, row in enumerate(rows):
        source.append('{' + ','.join((json.dumps(row['id']), json.dumps(row['library']),
            json.dumps(runtime_path(row, arch)), 'true' if row['needs_library'] else 'false',
            str(len(row['functions'])), 'FUNCTIONS_' + str(index))) + '},')
    source.append('};')
    return '\n'.join(source) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'definitions', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    args = parser.parse_args()
    rows = validate_definitions(json.loads(args.definitions.read_text()), args.device, args.arch)
    args.output.mkdir(parents=True, exist_ok=False)
    header = args.output / 'native_gap_abi_contracts.h'
    header.write_text(generate(rows, args.arch))
    source = Path(__file__).with_name('probes') / 'native_gap_abi.c'
    triple = {'arm64': 'aarch64-linux-ohos', 'armv7a': 'arm-linux-ohos', 'x86_64': 'x86_64-linux-ohos'}[args.arch]
    binary = args.output / 'native-gap-abi'
    command = [str(args.sdk / 'llvm/bin/clang'), '--target=' + triple, '--sysroot=' + str(args.sdk / 'sysroot'),
        '-std=c11', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-I', str(args.output), str(source),
        '-ldl', '-o', str(binary)]
    if args.arch == 'armv7a':
        command[1:1] = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon']
    subprocess.run(command, check=True)
    (args.output / 'build.json').write_text(json.dumps({'scope': 'actual_C_SDK_compile_NOT_runtime',
        'arch': args.arch, 'device': args.device, 'command': command,
        'definitions': str(args.definitions.resolve()), 'definitions_sha256': sha256(args.definitions),
        'source_sha256': sha256(source), 'generated_header_sha256': sha256(header),
        'probe_sha256': sha256(binary)}, indent=2) + '\n')
    print(binary)


if __name__ == '__main__':
    main()
