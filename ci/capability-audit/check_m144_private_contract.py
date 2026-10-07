#!/usr/bin/env python3
"""Real private adapter objects and mock-SDK boundaries, NOT full-core acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ARKWEB_REVISION = 'f3d904432cc1c57468f2b7fe01979d25e0157581'
CPP = ('graphic_adapter/native_image_adapter_impl.cpp',
       'graphic_adapter/native_window_adapter_impl.cpp',
       'hiviewdfx_adapter/hitrace_adapter_impl.cpp')
FILES = (*CPP, 'graphic_adapter/native_image_adapter_impl.h',
         'graphic_adapter/native_window_adapter_impl.h', 'interfaces/graphic_adapter.h',
         'interfaces/hitrace_adapter.h', 'hiviewdfx_adapter/hitrace_adapter_impl.h',
         'ndk_callback_wrapper/callback_shared_wrapper.h', 'utils/include/sys_param.h')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def virtuals(text, name):
    start = re.search(r'\bclass\s+' + re.escape(name) + r'\s*\{', text)
    if start is None:
        raise ValueError('missing interface: ' + name)
    body = text[start.end():text.index('\n};', start.end())]
    return [' '.join(item.split()) for item in re.findall(r'virtual\s+[^;]+;', body)]


def official_flags(ninja_file):
    values = {}
    for line in ninja_file.read_text().splitlines():
        match = re.match(r'^(defines|include_dirs|cflags|cflags_cc) = (.*)$', line)
        if match:
            values[match[1]] = shlex.split(match[2])
    if set(values) != {'defines', 'include_dirs', 'cflags', 'cflags_cc'}:
        raise ValueError('missing genuine official adapter GN flags')
    return sum((values[key] for key in ('defines', 'include_dirs', 'cflags', 'cflags_cc')), [])


def cross_flags(flags, triple, work):
    result = []
    for flag in flags:
        if flag.startswith('--target='):
            result.append('--target=' + triple)
        elif flag.startswith('-fcrash-diagnostics-dir='):
            result.append('-fcrash-diagnostics-dir=' + str(work))
        elif triple != 'aarch64-linux-ohos' and (flag.startswith('-mbranch-protection=') or flag == '-mno-outline'):
            continue
        elif triple == 'x86_64-linux-ohos' and flag == '-D__ARM_NEON__=1':
            continue
        else:
            result.append(flag)
    if triple == 'arm-linux-ohos':
        result += ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--securec', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    source, sdk, securec, work = (path.resolve() for path in (args.source_root, args.sdk, args.securec, args.work))
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('source must be read-only')
    for path in (source, sdk, securec, ROOT):
        if work == path or work.is_relative_to(path) or path.is_relative_to(work):
            raise ValueError('owned work directory overlaps inputs')
    head = subprocess.check_output(['git', '-C', str(source / 'arkweb'), 'rev-parse', 'HEAD'], text=True).strip()
    if head != ARKWEB_REVISION:
        raise ValueError('ArkWeb pin differs')
    metadata = json.loads((sdk / 'oh-uni-package.json').read_text())
    if str(metadata.get('apiVersion')) != '26' or metadata.get('version') != '26.0.0.39':
        raise ValueError('release SDK differs')
    work.mkdir(parents=True, exist_ok=False)
    result = {'status': 'fail', 'scope': 'actual_private_CPP_three_ABI_compile_and_mock_SDK_boundaries_NOT_full_core_or_guest',
              'first_artifact_behavior_gate_passed': False, 'arkweb_revision': head,
              'sdk_metadata': metadata, 'commands': [], 'artifacts': {}, 'inputs': {}, 'failures': []}

    def run(argv, name, cwd=None):
        completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=240)
        log = work / (name + '.log')
        log.write_text(completed.stdout + completed.stderr)
        result['commands'].append({'argv': argv, 'cwd': str(cwd) if cwd else None,
                                   'exit_code': completed.returncode, 'log': str(log), 'log_sha256': sha(log)})
        if completed.returncode:
            raise ValueError(name + ' failed')
        return completed

    try:
        adapter = source / 'arkweb/ohos_adapter_ndk'
        canonical = source / 'third_party/ohos_ndk/includes/ohos_adapter'
        contracts = {}
        for header, names in (('graphic_adapter.h', ('BufferRequestConfigAdapter', 'BufferFlushConfigAdapter',
                                                   'FrameAvailableListener', 'WindowAdapter')),
                              ('hitrace_adapter.h', ('HiTraceAdapter',))):
            private, public = (adapter / 'interfaces' / header).read_text(), (canonical / header).read_text()
            pristine = subprocess.check_output(['git', '-C', str(source / 'arkweb'),
                'show', 'HEAD:ohos_adapter_ndk/interfaces/' + header], text=True)
            for name in names:
                if virtuals(private, name) != virtuals(public, name):
                    raise ValueError('private/release virtual layout differs: ' + name)
                contracts[name] = {'matches_release': True, 'baseline_matched': virtuals(pristine, name) == virtuals(public, name),
                                   'virtuals': virtuals(public, name)}
        for name in ('BufferRequestConfigAdapter', 'FrameAvailableListener', 'HiTraceAdapter'):
            if contracts[name]['baseline_matched']:
                raise ValueError('expected true baseline contract defect was not present: ' + name)
        result['virtual_contracts'] = contracts
        stage = work / 'candidate'
        staged_adapter = stage / 'arkweb/ohos_adapter_ndk'
        for name in FILES:
            target = staged_adapter / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(adapter / name, target)
            result['inputs'][str(target.relative_to(stage))] = sha(target)
        for header in ('graphic_adapter.h', 'hitrace_adapter.h'):
            target = stage / 'third_party/ohos_ndk/includes/ohos_adapter' / header
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(canonical / header, target)
            result['inputs'][str(target.relative_to(stage))] = sha(target)
        sdk_alias = stage / 'ohos_sdk/openharmony/native'
        sdk_alias.parent.mkdir(parents=True)
        sdk_alias.symlink_to(sdk)
        native_out = source / 'out/rk3568_64'
        ninja_file = native_out / 'obj/arkweb/ohos_adapter_ndk/adapter_ndk.ninja'
        result['official_gn_flags_sha256'] = sha(ninja_file)
        result['cross_compile_scope'] = 'real_Clang22_and_SDK26_with_official_arm64_GN_common_feature_flags_NOT_three_full_GN_builds'
        flags = official_flags(ninja_file)
        compiler = source / 'third_party/llvm-build/Release+Asserts/bin/clang++'
        for arch, triple in (('arm64', 'aarch64-linux-ohos'), ('armv7a', 'arm-linux-ohos'), ('x86_64', 'x86_64-linux-ohos')):
            directory = work / arch
            directory.mkdir()
            records = {}
            allocator_include = None
            if arch != 'arm64':
                # Genuine per-architecture GN buildflags from the pinned V8
                # bootstrap, not edited 64-bit headers or disabled raw_ptr checks.
                generated = source / ('out/m144_arm/gen' if arch == 'armv7a' else 'out/m144_x86_64/gen')
                allocator_include = generated / 'base/allocator/partition_allocator/src'
                header = allocator_include / 'partition_alloc/buildflags.h'
                if not header.is_file():
                    raise ValueError('missing genuine architecture allocator buildflags')
                result['inputs'][str(header.relative_to(source))] = sha(header)
            for name in CPP:
                output = directory / (Path(name).stem + '.o')
                run([str(compiler), '-I' + str(stage), '-I' + str(securec / 'include'),
                     *(['-I' + str(generated), '-I' + str(allocator_include)] if allocator_include else []),
                     *cross_flags(flags, triple, directory), '-c', str(staged_adapter / name), '-o', str(output)],
                    arch + '-' + Path(name).stem, native_out)
                # Chromium's pinned compiler distribution does not ship llvm-dis.
                # Have that same Clang22 read its own genuine thin-LTO bitcode.
                ir = run([str(compiler), '--target=' + triple, '-S', '-emit-llvm', '-x', 'ir',
                          *(['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'] if arch == 'armv7a' else []),
                          str(output), '-o', '-'], arch + '-' + Path(name).stem + '-triple').stdout
                actual = re.search(r'^target triple = "([^"]+)"', ir, re.MULTILINE)
                expected_cpu = {'arm64': {'aarch64'}, 'armv7a': {'armv7', 'armv7a'}, 'x86_64': {'x86_64'}}[arch]
                if not actual or actual[1].split('-')[0] not in expected_cpu or not actual[1].endswith('-linux-ohos'):
                    raise ValueError('actual bitcode target ABI differs: ' + name)
                records[name] = {'path': str(output), 'sha256': sha(output), 'size': output.stat().st_size, 'triple': triple}
            result['artifacts'][arch] = records
        # Host-only dependency seams: SDK declarations, production CPPs, public
        # caller headers, and callback registry are real. No GPU/service claims.
        mocks = work / 'host-mocks'
        seams = {'base/memory/raw_ptr.h': '''#pragma once
#include <cstddef>
template<class T> class raw_ptr { T* ptr_; public:
raw_ptr(T* ptr=nullptr):ptr_(ptr){} raw_ptr& operator=(T* ptr){ptr_=ptr;return *this;}
operator T*() const{return ptr_;} T* get() const{return ptr_;} };
''', 'arkweb/ohos_nweb/src/nweb_hilog.h': '#pragma once\n#define WVLOG_E(...)\n#define WVLOG_I(...)\n',
            'arkweb/ohos_adapter_ndk/interfaces/ohos_adapter_helper.h': '#pragma once\n'}
        for name, content in seams.items():
            target = mocks / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        result['host_mocked_dependencies'] = list(seams)
        result['host_availability_metadata'] = 'GNU_host_only_strips_Clang_availability_annotations_SDK_declarations_unchanged'
        probes = []
        for name in ('m144_private_contract_host.cpp', 'm144_private_contract_public.cpp'):
            target = work / name
            shutil.copy2(ROOT / 'ci/capability-audit/probes' / name, target)
            probes.append(str(target))
            result['inputs'][name] = sha(target)
        binary = work / 'private-contract-host'
        run(['g++', '-std=c++20', '-DOS_OHOS', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-D__availability__(...)=',
             '-Wno-unused-parameter', '-Wno-attributes', '-Wno-narrowing',
             '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
             '-I' + str(mocks), '-I' + str(stage), '-I' + str(securec / 'include'),
             '-idirafter', str(sdk / 'sysroot/usr/include'),
             *(str(staged_adapter / name) for name in CPP), *probes, '-pthread', '-o', str(binary)], 'host-compile')
        observed = json.loads(run([str(binary)], 'host-runtime').stdout)
        if observed != {'case': 'actual_m144_private_contract_mock_sdk', 'destroy_cycles': 100,
                        'timestamp_boundaries': 4, 'separate_release_header_caller': True, 'errors': 0}:
            raise ValueError('actual private adapter boundary test differs')
        result['host_runtime'] = observed
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    (work / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'failures', 'first_artifact_behavior_gate_passed')}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
