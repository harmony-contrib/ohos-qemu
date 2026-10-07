#!/usr/bin/env python3
"""Check every original Native gap in final images, not runtime behavior.

The fixed interface/sdk_c headers and NDK manifests supply the full symbol
contract. Optional undeclared features may remain absent, but actual declared,
official or explicitly requested capabilities may not be exempted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
sys.path.insert(0, str(ROOT / 'patches/lib'))
from audit_c_api_abi import (LIBRARY_RE, SYSCAP_RE, declared_function_names,
                             load_ndk_manifest_symbols)
from device_contract import active_official_requirements
from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_runtime_elf_contract import read_elf, verify_machine

LEDGER = ROOT / 'docs/capability-audit/native-arkts11-gap-ledger.json'
ARCHES = {'arm64': (2, 183, 'lib64'), 'armv7a': (1, 40, 'lib'), 'x86_64': (2, 62, 'lib64')}


def canonical_library(name):
    return ('lib' + name if not name.startswith('lib') else name).replace('.z.so', '.so')


def contracts(sdk_c, device):
    symbols, manifests = load_ndk_manifest_symbols(sdk_c)
    if not symbols or not manifests:
        raise ValueError('fixed-source C SDK NDK manifests required')
    requirements = json.loads(LEDGER.read_text())['devices'][device]['native_abi_gaps']
    result = []
    for gap in requirements:
        functions, inputs = set(), {}
        for header in sorted(sdk_c.rglob('*.h')):
            if 'zh-cn' in header.parts:
                continue
            text = header.read_text(encoding='utf-8', errors='replace')
            if (gap['syscap'] not in SYSCAP_RE.findall(text) or canonical_library(gap['library']) not in
                    {canonical_library(name) for name in LIBRARY_RE.findall(text)}):
                continue
            names = declared_function_names(text) & symbols.keys()
            if names:
                functions.update(names)
                inputs[header.relative_to(sdk_c).as_posix()] = file_sha256(header)
                for name in names:
                    manifest = sdk_c / symbols[name]['manifest']
                    inputs[symbols[name]['manifest']] = file_sha256(manifest)
        if (not set(gap['missing_symbols']) <= functions or
                len(functions) < gap['public_function_count']):
            raise ValueError('fixed C SDK does not cover the original whole ABI: ' + gap['library'])
        result.append({'id': 'native:' + gap['syscap'] + ':' + gap['library'],
            'syscap': gap['syscap'], 'library': gap['library'], 'functions': sorted(functions),
            'source_inputs_sha256': inputs, 'original_requirement': gap})
    return result


def declared_syscaps(document):
    result = set()
    for component in document.get('components', []):
        for name in component.get('syscap', []):
            if not isinstance(name, str) or not name.startswith('SystemCapability.'):
                raise ValueError('malformed actual image SysCap')
            result.add(name)
    if not result:
        raise ValueError('empty actual image SysCaps')
    return result


def required_contracts(rows, profile, declared):
    policy = profile['qemu_adaptations']
    required = active_official_requirements(policy) | set(policy['explicit_qemu_requirements'])
    enabled = set(policy['enabled_required_syscaps'])
    excluded = set(policy['excluded_unsupported_syscaps'])
    if (excluded & (required | enabled) or not (required | enabled) <= declared):
        raise ValueError('image cannot omit/exclude any active official or requested capability')
    result = []
    for contract in rows:
        cap = contract['syscap']
        needs_library = cap in declared or cap in required or cap in enabled
        if cap in excluded and cap in declared:
            raise ValueError('excluded capability is still falsely declared: ' + cap)
        result.append(dict(contract, declared_by_final_image=cap in declared,
            required_by_active_contract=cap in required or cap in enabled,
            needs_library=needs_library,
            scope='required_actual_native_ABI' if needs_library else 'optional_undeclared_NOT_implemented'))
    return result


def verify(image, sdk_c, profile, arch):
    if profile.get('device_type') not in ('phone', '2in1'):
        raise ValueError('actual full device profile required')
    source_lock = ROOT / 'scripts/openharmony_7_0_release_source_lock.json'
    pins = [row['revision'] for row in json.loads(source_lock.read_text())['projects']
            if row['path'] == 'interface/sdk_c']
    revision = subprocess.run(['git', '-c', 'safe.directory=*', '-C', str(sdk_c), 'rev-parse', 'HEAD'],
                              check=True, capture_output=True, text=True).stdout.strip()
    if pins != [revision]:
        raise ValueError('Native ABI contract source is not the fixed 7.0 Release SDK C commit')
    elf_class, machine, lib = ARCHES[arch]
    with tempfile.TemporaryDirectory(prefix='qemu-native-gap-abi-') as temporary:
        temporary = Path(temporary)
        syscap, identity = dump_unique_file(image, ('/etc/syscap.json', '/system/etc/syscap.json'),
                                            temporary, debugfs_path())
        if file_sha256(syscap) != profile['resolved_syscap_sha256']:
            raise ValueError('final image SysCaps differ from actual validated preloader profile')
        rows = required_contracts(contracts(sdk_c, profile['device_type']), profile,
                                 declared_syscaps(json.loads(syscap.read_text())))
        checked = []
        for row in rows:
            if not row['needs_library']:
                checked.append(dict(row, status='optional_undeclared', implemented=False))
                continue
            directory = temporary / row['library']
            directory.mkdir()
            names = tuple(f'{prefix}/{lib}/{subdir}{row["library"]}' for prefix in ('', '/system')
                          for subdir in ('ndk/', ''))
            library, located = dump_unique_file(image, names, directory, debugfs_path())
            header = library.read_bytes()[:64]
            if header[:7] != b'\x7fELF' + bytes((elf_class, 1, 1)):
                raise ValueError('wrong actual NDK ELF class/encoding: ' + row['library'])
            info = read_elf(library)
            verify_machine(info, machine, library)
            missing = sorted(set(row['functions']) - info.defined)
            if missing:
                raise ValueError('actual Native ABI is incomplete: ' + row['library'] + ': ' + ', '.join(missing))
            checked.append(dict(row, status='all_source_contract_symbols_present',
                                library_sha256=file_sha256(library), image_entry=located,
                                elf_machine=machine, behavior_validated=False))
        return {'contracts': checked, 'actual_syscap_image_entry': identity,
                'actual_syscap_sha256': file_sha256(syscap), 'device': profile['device_type'],
                'sdk_c_revision': revision, 'source_lock_sha256': file_sha256(source_lock)}


def verify_packaged_report(package, arch):
    """Portable recheck of immutable packaged evidence and real final DSOs."""
    from verify_native_gap_abi_results import validate_definitions
    profile_path = package / 'device-profile.json'
    profile = json.loads(profile_path.read_text())
    report = json.loads((package / 'native-gap-abi-image.json').read_text())
    rows = validate_definitions(report, profile['device_type'], arch)
    image = package / 'images/system.img'
    if (report['device_profile_sha256'] != file_sha256(profile_path) or
            report['system_image_sha256'] != file_sha256(image)):
        raise ValueError('packaged Native ABI evidence does not describe these actual profile/image bytes')
    elf_class, machine, lib = ARCHES[arch]
    with tempfile.TemporaryDirectory(prefix='qemu-native-gap-recheck-') as temporary:
        temporary = Path(temporary)
        syscap, _ = dump_unique_file(image, ('/etc/syscap.json', '/system/etc/syscap.json'), temporary, debugfs_path())
        if file_sha256(syscap) != report['actual_syscap_sha256'] or file_sha256(syscap) != profile['resolved_syscap_sha256']:
            raise ValueError('actual final image SysCaps changed')
        current = required_contracts(rows, profile, declared_syscaps(json.loads(syscap.read_text())))
        for original, actual in zip(rows, current):
            for key in ('needs_library', 'declared_by_final_image', 'required_by_active_contract', 'scope'):
                if original[key] != actual[key]:
                    raise ValueError('Native ABI requirement changed under the actual current profile')
            if not actual['needs_library']:
                continue
            directory = temporary / actual['library']
            directory.mkdir()
            library, identity = dump_unique_file(image, tuple(f'{prefix}/{lib}/{subdir}{actual["library"]}'
                for prefix in ('', '/system') for subdir in ('ndk/', '')), directory, debugfs_path())
            if (library.read_bytes()[:7] != b'\x7fELF' + bytes((elf_class, 1, 1)) or
                    file_sha256(library) != actual['library_sha256'] or identity != actual['image_entry']):
                raise ValueError('actual Native ABI provider changed: ' + actual['library'])
            info = read_elf(library)
            verify_machine(info, machine, library)
            if set(actual['functions']) - info.defined:
                raise ValueError('actual final DSO no longer supplies the whole fixed-source ABI')
    return {'status': 'pass', 'scope': 'offline_packaged_Native_ABI_recheck_NOT_behavior'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, help='recheck a complete package without a source checkout')
    for name in ('system-image', 'sdk-c-source', 'device-profile', 'output'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--arch', choices=tuple(ARCHES), required=True)
    args = parser.parse_args()
    if args.package:
        if any((args.system_image, args.sdk_c_source, args.device_profile, args.output)):
            parser.error('--package cannot be combined with build-output/source mode')
        try:
            print(json.dumps(verify_packaged_report(args.package, args.arch)))
            return 0
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            print(json.dumps({'status': 'fail', 'failures': [str(error)]}))
            return 1
    if not all((args.system_image, args.sdk_c_source, args.device_profile, args.output)):
        parser.error('source mode requires system image, SDK C source, device profile and output')
    report = {'schema_version': 1, 'status': 'fail', 'arch': args.arch,
        'scope': 'offline_actual_final_image_complete_original_Native_gap_ABI_NOT_behavior',
        'first_artifact_behavior_gate_passed': False, 'failures': [],
        'audit_baseline_sha256': file_sha256(LEDGER),
        'device_profile_sha256': file_sha256(args.device_profile)}
    try:
        before = args.system_image.stat()
        report['system_image_sha256'] = file_sha256(args.system_image)
        report.update(verify(args.system_image, args.sdk_c_source,
                             json.loads(args.device_profile.read_text()), args.arch))
        after = args.system_image.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('image changed while verifying the actual Native ABI')
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
