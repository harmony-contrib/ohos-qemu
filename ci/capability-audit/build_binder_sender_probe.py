#!/usr/bin/env python3
"""Compile raw Binder tests against the fixed kernel UAPI and real C SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HEADER_SHA256 = 'f3390d6920a899b5ac0223d6f18c99e94c0147e5e064daae22fed807c822f4e9'
REVISION = '14c77f1541a53e814d89ad6dea5f7f211f9895a6'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project = args.source_root.resolve() / 'kernel/linux/linux-6.6'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('raw Binder probe requires the fixed main-system kernel project')
    original = project / 'include/uapi/linux/android/binder.h'
    if digest(original) != HEADER_SHA256:
        raise ValueError('unknown actual Binder UAPI; do not invent ioctl/layout definitions')
    args.output.mkdir(parents=True, exist_ok=False)
    header = args.output / 'include/linux/android/binder.h'
    header.parent.mkdir(parents=True)
    shutil.copy2(original, header)
    source = Path(__file__).with_name('probes') / 'binder_async_sender.c'
    binary = args.output / 'binder-async-sender'
    triple = {'arm64': 'aarch64-linux-ohos', 'armv7a': 'arm-linux-ohos', 'x86_64': 'x86_64-linux-ohos'}[args.arch]
    command = [str(args.sdk / 'llvm/bin/clang'), '--target=' + triple, '--sysroot=' + str(args.sdk / 'sysroot'),
        '-std=c11', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-I', str(args.output / 'include'),
        str(source), '-o', str(binary)]
    if args.arch == 'armv7a':
        command[1:1] = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon']
    subprocess.run(command, check=True)
    (args.output / 'build.json').write_text(json.dumps({'scope': 'actual_C_SDK_compile_only_NOT_guest',
        'arch': args.arch, 'kernel_revision': REVISION, 'command': command,
        'header_sha256': digest(header), 'source_sha256': digest(source),
        'probe_sha256': digest(binary), 'first_artifact_behavior_gate_passed': False}, indent=2) + '\n')
    print(binary)


if __name__ == '__main__':
    main()
