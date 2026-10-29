#!/usr/bin/env python3
"""Rebuild the API26 SDK's ARM64 archives with real BTI instructions.

Same SDK Clang15 and exact LLVM source commit; no fabricated ELF notes, relaxed
linker/security flags, public SDK replacement or unrelated runtime version.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

REVISION = '3f002d04ba6b3a7659c601207c89d3a896b82546'
ARCHIVES = ('llvm/lib/aarch64-linux-ohos/libunwind.a',
            'llvm/lib/clang/15.0.4/lib/aarch64-linux-ohos/libclang_rt.builtins.a')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member_source(name, unwind):
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:c|cpp|S)\.o', name):
        raise ValueError('unsafe/unknown SDK archive member: ' + name)
    if unwind:
        return 'libunwind/src/' + name[:-2], []
    outline = re.fullmatch(r'outline_atomic_(cas|swp|ldadd|ldclr|ldeor|ldset)(1|2|4|8|16)_([1-4])\.S\.o', name)
    if outline:
        op, size, model = outline.groups()
        if size == '16' and op != 'cas':
            raise ValueError('invalid outline atomic size')
        return 'compiler-rt/lib/builtins/aarch64/lse.S', ['-DL_' + op, '-DSIZE=' + size, '-DMODEL=' + model]
    return 'compiler-rt/lib/builtins/' + name[:-2], []


def defined_symbols(nm, archive):
    text = subprocess.check_output([str(nm), '--extern-only', '--defined-only', str(archive)], text=True)
    return sorted(set(match[1] for line in text.splitlines()
                      if (match := re.fullmatch(r'[0-9a-fA-F]+\s+[A-Za-z]\s+(\S+)', line.strip()))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--original-sdk', type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    source, sdk, original = (path.resolve() for path in (args.source, args.sdk, args.original_sdk))
    if not os.statvfs(source).f_flag & os.ST_RDONLY or not os.statvfs(original).f_flag & os.ST_RDONLY:
        raise ValueError('fixed runtime sources and original SDK must be read-only')
    if (sdk == original or sdk.is_relative_to(original) or original.is_relative_to(sdk) or
            sdk.parent.name != 'qemu-core-sdk-api26'):
        raise ValueError('runtime destination must be the owned private core SDK')
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('LLVM source does not match the existing SDK compiler commit')
    if subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only', 'HEAD'], text=True).strip():
        raise ValueError('runtime source has local changes')
    compiler = sdk / 'llvm/bin/clang'
    version = subprocess.check_output([str(compiler), '--version'], text=True)
    if 'clang version 15.0.4' not in version or REVISION not in version or sha(compiler) != sha(original / 'llvm/bin/clang'):
        raise ValueError('rebuild must use the exact API26 SDK Clang15 binary')
    metadata = json.loads((sdk / 'oh-uni-package.json').read_text())
    if metadata.get('apiVersion') != '26' or metadata.get('version') != '26.0.0.39':
        raise ValueError('private SDK release identity differs')
    evidence = sdk.parent / 'bti-runtime-evidence.json'
    if evidence.exists():
        previous = json.loads(evidence.read_text())
        if (previous.get('status') != 'pass' or previous.get('source_revision') != REVISION or
                previous.get('builder_sha256') != sha(Path(__file__)) or
                any(sha(sdk / name) != previous['archives'][name]['sha256'] or
                    sha(original / name) != previous['archives'][name]['original_sha256'] for name in ARCHIVES)):
            raise ValueError('existing private BTI runtime evidence/archives differ')
        print('private SDK ARM64 BTI archives already verified')
        return
    for name in ARCHIVES:
        if (sdk / name).is_symlink() or sha(sdk / name) != sha(original / name):
            raise ValueError('refusing to replace an unknown private runtime: ' + name)
    work = Path(tempfile.mkdtemp(prefix='bti-runtime-', dir=sdk.parent))
    report = {'status': 'fail', 'scope': 'same_API26_SDK_ARM64_real_BTI_runtime_build_NOT_guest_acceptance',
              'source_revision': REVISION, 'compiler_version': version, 'compiler_sha256': sha(compiler),
              'builder_sha256': sha(Path(__file__)), 'commands': [], 'archives': {}, 'failures': [],
              'first_artifact_behavior_gate_passed': False}
    ar, nm, readelf = (sdk / 'llvm/bin' / name for name in ('llvm-ar', 'llvm-nm', 'llvm-readelf'))
    try:
        staged = []
        for name in ARCHIVES:
            unwind = name.endswith('/libunwind.a')
            members = subprocess.check_output([str(ar), 't', str(original / name)], text=True).splitlines()
            if not members or len(set(members)) != len(members):
                raise ValueError('empty or duplicate original runtime archive members')
            directory = work / ('unwind' if unwind else 'builtins')
            directory.mkdir()

            def compile_member(member):
                relative, definitions = member_source(member, unwind)
                input_path = source / relative
                if not input_path.is_file() or input_path.is_symlink():
                    raise ValueError('exact SDK runtime source missing: ' + relative)
                output = directory / member
                cpp = relative.endswith('.cpp')
                argv = [str(compiler) + ('++' if cpp else ''), '--target=aarch64-linux-ohos',
                        '--sysroot=' + str(sdk / 'sysroot'), '-O2', '-fPIC',
                        '-mbranch-protection=pac-ret+b-key+bti', '-fno-stack-protector']
                if unwind:
                    argv += ['-D_LIBUNWIND_IS_NATIVE_ONLY', '-D_LIBUNWIND_HIDE_SYMBOLS',
                             '-D_LIBUNWIND_TARGET_LINUX', '-D_LIBUNWIND_USE_FRAME_HEADER_CACHE',
                             '-I' + str(source / 'libunwind/include'), '-I' + str(source / 'libunwind/src')]
                    argv += ['-fno-exceptions', '-fno-rtti', '-std=c++11'] if cpp else ['-fexceptions']
                else:
                    argv += ['-ffreestanding', '-fno-builtin', '-fvisibility=hidden', '-DCOMPILER_RT_HAS_FLOAT16',
                             '-I' + str(source / 'compiler-rt/lib/builtins'), *definitions]
                argv += ['-c', str(input_path), '-o', str(output)]
                result = subprocess.run(argv, capture_output=True, timeout=120)
                log = directory / (member + '.log')
                log.write_bytes(result.stdout + result.stderr)
                record = {'argv': argv, 'exit_code': result.returncode, 'log': str(log), 'log_sha256': sha(log),
                          'source': relative, 'source_sha256': sha(input_path)}
                if result.returncode:
                    raise ValueError('BTI runtime compilation failed: ' + member + ' (see ' + str(log) + ')')
                header = output.read_bytes()[:64]
                if header[:7] != b'\x7fELF\x02\x01\x01' or struct.unpack_from('<HH', header, 16) != (1, 183):
                    raise ValueError('runtime object is not actual ARM64 ELF: ' + member)
                notes = subprocess.check_output([str(readelf), '--notes', str(output)], text=True)
                if 'aarch64 feature: BTI' not in notes:
                    raise ValueError('runtime object lacks real compiler/assembly BTI property: ' + member)
                record.update(object_sha256=sha(output), bti_note=True)
                return record

            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                report['commands'] += list(pool.map(compile_member, members))
            archive = directory / Path(name).name
            subprocess.run([str(ar), 'rcsD', str(archive), *(str(directory / item) for item in members)], check=True)
            old_symbols = defined_symbols(nm, original / name)
            new_symbols = defined_symbols(nm, archive)
            # C++ weak template instantiations vary with inlining; they are not
            # libunwind's extern-C ABI. Preserve every C symbol and record the
            # exact internal-codegen differences rather than claiming all
            # symbol tables identical. Builtins contains only the C ABI.
            old_c = [symbol for symbol in old_symbols if not symbol.startswith('_Z')]
            new_c = [symbol for symbol in new_symbols if not symbol.startswith('_Z')]
            if (subprocess.check_output([str(ar), 't', str(archive)], text=True).splitlines() != members or
                    new_c != old_c or (not unwind and new_symbols != old_symbols)):
                raise ValueError('recompiled runtime members or defined C ABI symbol surface differs')
            report['archives'][name] = {'sha256': sha(archive), 'original_sha256': sha(original / name),
                                        'members': members, 'all_objects_BTI': True,
                                        'defined_C_symbols_match_original': True,
                                        'internal_symbols_new_only': sorted(set(new_symbols) - set(old_symbols)),
                                        'internal_symbols_old_only': sorted(set(old_symbols) - set(new_symbols))}
            staged.append((name, archive))
        # Validate all libraries first. Preserve the exact original private
        # copies before atomically replacing only these two owned archives.
        for name, archive in staged:
            target = sdk / name
            backup = target.with_name(target.name + '.pre-qemu-bti')
            if backup.exists() or backup.is_symlink():
                raise ValueError('runtime backup already exists; manual review required')
            shutil.copy2(target, backup)
            os.replace(archive, target)
        report['status'] = 'pass'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    (work / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] != 'pass':
        raise ValueError('BTI runtime build failed; retained evidence: ' + str(work / 'evidence.json'))
    evidence.write_text(json.dumps(report, indent=2) + '\n')
    print('private API26 SDK ARM64 BTI runtime archives built and verified')


if __name__ == '__main__':
    main()
