#!/usr/bin/env python3
"""Actual fixed WebRTC source/three-ABI checks, not full ArkWeb acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_runtime_elf_contract import read_elf, verify_machine
from run_root_probe import validate_elf

REVISION = '0159a7bffb0a54551e9fa5dd25ff81f448419b05'
ARCHES = {'arm64': ('aarch64-linux-ohos', 183, []),
          'armv7a': ('arm-linux-ohos', 40, ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon']),
          'x86_64': ('x86_64-linux-ohos', 62, [])}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True, help='read-only M144 src')
    parser.add_argument('--sdk', type=Path, required=True, help='actual prepared API26 native SDK')
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    source, sdk, work = args.source_root.resolve(), args.sdk.resolve(), args.work.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('M144 source must be mounted read-only')
    if any(work == path or work.is_relative_to(path) or path.is_relative_to(work) for path in (source, sdk, ROOT)):
        raise ValueError('owned test workspace must be separate from all inputs')
    web = source / 'third_party/webrtc'
    head = subprocess.check_output(['git', '-C', str(web), 'rev-parse', 'HEAD'], text=True).strip()
    if head != REVISION:
        raise ValueError('actual WebRTC source revision differs')
    metadata = json.loads((sdk / 'oh-uni-package.json').read_text())
    if str(metadata.get('apiVersion')) != '26' or metadata.get('version') != '26.0.0.39':
        raise ValueError('actual release native SDK metadata differs')
    work.mkdir(parents=True, exist_ok=False)
    result = {'scope': 'real_WebRTC_three_ABI_objects_and_host_thread_identity_NOT_ArkWeb_or_package_acceptance',
              'status': 'fail', 'first_artifact_behavior_gate_passed': False,
              'webRTC_revision': head, 'native_sdk_metadata': metadata,
              'commands': [], 'artifacts': {}, 'failures': []}

    def run(command, name, expected_success=True):
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        output = work / (name + '.log')
        output.write_text(completed.stdout + completed.stderr)
        result['commands'].append({'argv': command, 'exit_code': completed.returncode,
                                   'log_sha256': sha(output), 'log': str(output)})
        if expected_success != (completed.returncode == 0):
            raise ValueError(name + ' returned an unexpected compile/test result')
        return completed

    try:
        header = work / 'rtc_base/platform_thread_types.h'
        header.parent.mkdir()
        shutil.copy2(web / 'rtc_base/platform_thread_types.h', header)
        pristine = work / 'pristine.cc'
        pristine.write_bytes(subprocess.check_output(['git', '-C', str(web), 'show', 'HEAD:rtc_base/platform_thread_types.cc']))
        candidate = work / 'candidate.cc'
        candidate.write_text(pristine.read_text().replace('#elif defined(WEBRTC_FUCHSIA)\n  return zx_thread_self();',
                                                        '#elif defined(OS_OHOS)\n  return gettid();\n#elif defined(WEBRTC_FUCHSIA)\n  return zx_thread_self();', 1))
        if candidate.read_bytes() != (web / 'rtc_base/platform_thread_types.cc').read_bytes():
            raise ValueError('actual applied source differs from the exact two-line candidate')
        probe = work / 'webrtc_thread_id.cpp'
        shutil.copy2(ROOT / 'ci/capability-audit/probes/webrtc_thread_id.cpp', probe)
        result['inputs'] = {path.name: sha(path) for path in (header, pristine, candidate, probe)}
        compiler22 = source / 'third_party/llvm-build/Release+Asserts/bin/clang++'
        compiler15 = sdk / 'llvm/bin/clang++'
        run([str(compiler22), '--version'], 'actual-clang22')
        common = ['-std=c++20', '-DWEBRTC_POSIX', '-DOS_OHOS', '-D_GNU_SOURCE', '-O2',
                  '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-I' + str(work)]
        for arch, (triple, machine, flags) in ARCHES.items():
            directory = work / arch
            directory.mkdir()
            cross = ['--target=' + triple, '--sysroot=' + str(sdk / 'sysroot'), *flags]
            original = directory / 'pristine.o'
            failed = run([str(compiler22), *cross, *common, '-c', str(pristine), '-o', str(original)], arch + '-pristine', False)
            if 'reinterpret_cast' not in failed.stderr or 'PlatformThreadId' not in failed.stderr:
                raise ValueError('baseline failed for a reason other than the actual thread ID defect')
            fixed = directory / 'candidate.o'
            run([str(compiler22), *cross, *common, '-c', str(candidate), '-o', str(fixed)], arch + '-candidate')
            verify_machine(read_elf(fixed), machine, fixed)
            executable = directory / 'webrtc-thread-id'
            run([str(compiler15), *cross, *common, '-fno-exceptions', '-fno-rtti', '-nostdlib++',
                 str(candidate), str(probe), '-pthread', '-o', str(executable)], arch + '-probe')
            validate_elf(executable, arch)
            result['artifacts'][arch] = {name: {'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size}
                                          for name, path in (('clang22_object', fixed), ('native_probe', executable))}
        host = work / 'host-thread-id'
        run(['g++', *common, str(candidate), str(probe), '-pthread', '-o', str(host)], 'real-source-host-compile')
        observed = json.loads(run([str(host)], 'real-source-host-runtime').stdout)
        if observed != {'case': 'real_webrtc_ohos_thread_id', 'cycles': 16, 'threads': 16, 'checks': 2176, 'errors': 0}:
            raise ValueError('real-source host concurrent thread identity checks failed')
        result['host_runtime'] = observed
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    (work / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'failures': result['failures'], 'first_artifact_behavior_gate_passed': False}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
