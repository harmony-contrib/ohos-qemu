#!/usr/bin/env python3
"""Build a read-only WPA control caller from the real API26 native SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

SOURCE = Path(__file__).with_name('probes') / 'wpa_frequency_readback.c'
TARGETS = {'arm64': ('aarch64-linux-ohos', []),
           'armv7a': ('arm-linux-ohos', ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon']),
           'x86_64': ('x86_64-linux-ohos', [])}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, output = args.sdk.resolve(), args.output.resolve()
    metadata = sdk / 'native/oh-uni-package.json'
    version = json.loads(metadata.read_text())
    if version.get('apiVersion') != '26' or version.get('releaseType') != 'Release':
        raise ValueError('actual API26 Release SDK required')
    output.mkdir(exist_ok=False)
    compiler = sdk / 'native/llvm/bin/clang'
    inputs = dict(source=sha(SOURCE), compiler=sha(compiler), sdk_metadata=sha(metadata))
    rows = []
    for arch, (triple, flags) in TARGETS.items():
        binary = output / ('wpa-frequency-readback-' + arch)
        argv = [str(compiler), '--target=' + triple, *flags,
                '--sysroot=' + str(sdk / 'native/sysroot'), '-std=c11',
                '-Wall', '-Wextra', '-Werror', '-O2', str(SOURCE), '-o', str(binary)]
        log = output / (arch + '-compile.log')
        with log.open('x') as stream:
            subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=True)
        rows.append(dict(arch=arch, triple=triple, argv=argv, binary=str(binary),
                         binary_sha256=sha(binary), log_sha256=sha(log)))
    if inputs != dict(source=sha(SOURCE), compiler=sha(compiler), sdk_metadata=sha(metadata)):
        raise ValueError('read-only probe build inputs changed')
    report = dict(status='pass', scope='read_only_WPA_control_caller_BUILD_NOT_guest_or_WLAN_acceptance',
                  inputs_sha256=inputs, sdk=version, outputs=rows,
                  first_artifact_behavior_gate_passed=False)
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], architectures=len(rows))))


if __name__ == '__main__':
    main()
