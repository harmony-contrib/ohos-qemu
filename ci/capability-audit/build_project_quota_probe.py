#!/usr/bin/env python3
"""Build an isolated project-quota kernel test with the actual native SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ARCHES = {'arm64': ('aarch64-linux-ohos', 2, 183),
          'armv7a': ('arm-linux-ohos', 1, 40), 'x86_64': ('x86_64-linux-ohos', 2, 62)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True, help='native SDK directory')
    parser.add_argument('--arch', choices=ARCHES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, output = args.sdk.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name('probes') / 'project_quota_runtime.c'
    source_hash = digest(source)
    triple, elf_class, machine = ARCHES[args.arch]
    binary = output / 'project-quota-runtime'
    command = [str(sdk / 'llvm/bin/clang'), '--target=' + triple,
               '--sysroot=' + str(sdk / 'sysroot'), '-std=c11', '-O2', '-g',
               '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)]
    if args.arch == 'armv7a':
        command[1:1] = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon']
    report = {'status': 'fail', 'arch': args.arch, 'command': command,
              'source_sha256': source_hash, 'scope': 'SDK_compile_NOT_guest_or_Storage_API',
              'first_artifact_behavior_gate_passed': False}
    try:
        with (output / 'build.log').open('x') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
        header = binary.read_bytes()[:20]
        if (header[:6] != b'\x7fELF' + bytes([elf_class, 1]) or
                int.from_bytes(header[18:20], 'little') != machine or digest(source) != source_hash):
            raise ValueError('wrong ELF ABI or changed probe source')
        report.update(status='pass', probe_sha256=digest(binary))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
