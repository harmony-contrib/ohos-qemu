#!/usr/bin/env python3
"""Compile the real root producer and independent token observer for one product.

Source and product outputs must be read-only. No product or package is built.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from audio_capture_contract import sha, verify_elf

HERE = Path(__file__).resolve().parent
TARGETS = {'arm64': ('arm64_virt', 'aarch64-linux-ohos', 'ohos-arm64'),
           'armv7a': ('armv7a_virt', 'arm-linux-ohos', 'ohos-arm'),
           'x86_64': ('x86_64_virt', 'x86_64-linux-ohos', 'ohos-x86_64')}


def build(root, output, arch):
    root, output = Path(root).resolve(), Path(output).resolve()
    if any(not os.statvfs(p).f_flag & os.ST_RDONLY for p in (root, root / 'out')):
        raise ValueError('source and product output must be read-only')
    output.mkdir(parents=True, exist_ok=False)
    product, triple, innerkit = TARGETS[arch]
    native = root / 'prebuilts/ohos-sdk/linux/26.0.0/native'
    system = root / 'prebuilts/clang/ohos/linux-x86_64/llvm'
    out = root / 'out' / product
    alsa = root / 'third_party/alsa-lib/include'
    token = root / 'base/security/access_token/interfaces/innerkits/accesstoken/include'
    common = ['--target=' + triple]
    if arch == 'armv7a':
        common += ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon']
    sources = {'alsa_inject': HERE / 'batch_media_alsa_inject.c',
               'audio_capture_token': HERE / 'probes/audio_capture_token.cpp'}
    libraries = {'alsa_inject': out / 'thirdparty/alsa-lib/libasound.so',
                 'audio_capture_token': out / 'security/access_token/libaccesstoken_sdk.z.so'}
    commands = {
        'alsa_inject': [str(native / 'llvm/bin/clang'), *common, '--sysroot=' + str(native / 'sysroot'),
            '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I' + str(alsa), str(sources['alsa_inject']),
            str(libraries['alsa_inject']), '-o', str(output / 'alsa_inject')],
        'audio_capture_token': [str(system / 'bin/clang++'), *common,
            '--sysroot=' + str(out / 'obj/third_party/musl'), '-std=c++17', '-O2', '-g', '-Wall',
            '-Wextra', '-Werror', '-fno-exceptions', '-fno-rtti', '-I' + str(token),
            '-I' + str(out / 'innerkits' / innerkit / 'c_utils/utils/include'),
            str(sources['audio_capture_token']), str(libraries['audio_capture_token']),
            '-L' + str(system / 'lib' / triple), '-Wl,--allow-shlib-undefined',
            '-o', str(output / 'audio_capture_token')],
    }
    inputs = [*sources.values(), *libraries.values(), Path(__file__).resolve(),
              *sorted((alsa / 'alsa').glob('*.h')), *sorted(token.glob('*.h'))]
    before = {str(p): sha(p) for p in inputs}
    report = {'status': 'fail', 'scope': 'real_root_PCM_producer_and_independent_AccessToken_tools_ONLY',
              'arch': arch, 'product': product, 'inputs_sha256': before, 'tools': {},
              'first_artifact_behavior_gate_passed': False}
    for name, argv in commands.items():
        row = {'command': argv, 'status': 'fail'}
        try:
            verify_elf(libraries[name].read_bytes(), arch)
            with (output / (name + '.log')).open('xb') as log:
                result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            row.update(exit_code=result.returncode, log_sha256=sha(output / (name + '.log')))
            if result.returncode:
                raise ValueError('complete tool compile/link failed')
            verify_elf((output / name).read_bytes(), arch)
            row.update(status='pass', binary_sha256=sha(output / name), source_sha256=sha(sources[name]),
                       linked_library_sha256=sha(libraries[name]))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            row['error'] = str(error)
        report['tools'][name] = row
        (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    report['inputs_unchanged'] = all(sha(Path(p)) == value for p, value in before.items())
    if report['inputs_unchanged'] and all(row['status'] == 'pass' for row in report['tools'].values()):
        report['status'] = 'pass'
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arch', choices=TARGETS, required=True)
    args = parser.parse_args()
    result = build(args.source_root, args.output, args.arch)
    print(json.dumps({'status': result['status'], 'tools': result['tools']}))
    raise SystemExit(result['status'] != 'pass')
