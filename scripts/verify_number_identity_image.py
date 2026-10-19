#!/usr/bin/env python3
"""Offline signed NumberIdentity public-local-subset image guard; no runtime claim."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import struct
import subprocess
import tempfile
import zipfile
import zlib

from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_photos_provider_image import verify_signature
from verify_preinstall_selection import verify_selection
from verify_runtime_elf_contract import read_elf

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'base/telephony/number_identity'
REVISION = '50e1330646432ce166e7981c577f25f46c90e7ac'
BUNDLE = 'com.ohos.numberidentity'
INSTALL_ID = 'com.ohos.numberidentityability'
PROFILE = PROJECT + '/signature/NumberIdentity.hapRelease.p7b'
SOURCE_MODULE_SHA = 'e0fe578838c3c3036421dd0049b783bad86764bf23a58b7be09cb11a9ed78fa9'
ARCHES = {'arm64': (2, 183, 'lib64'), 'armv7a': (1, 40, 'lib'), 'x86_64': (2, 62, 'lib64')}
HAP_ABIS = {'arm64': 'arm64-v8a', 'armv7a': 'armeabi-v7a', 'x86_64': 'x86_64'}
LIBRARIES = ('libnumber_identity.z.so', 'module/telephony/libnumberidentity.z.so',
             'module/contact/libnumberlookup.z.so')


def need(value, message):
    if not value:
        raise ValueError(message)


def unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, 'duplicate NumberIdentity JSON key')
        value[key] = item
    return value


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def decode(data):
    need(len(data) <= 4 * 1024 * 1024, 'bounded NumberIdentity JSON required')
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def module_contract(module):
    need(hashlib.sha256(encode(module).encode()).hexdigest() == SOURCE_MODULE_SHA,
         'NumberIdentity source module differs from fixed public module')


def entry_path(row):
    entries = [row[key] for key in ('srcEntry', 'srcEntrance') if key in row]
    need(entries and all(type(item) is str and item and item == entries[0] for item in entries),
         'NumberIdentity entry is missing or ambiguous')
    return entries[0]


def inspect_hap(hap, source_module, arch):
    module_contract(source_module)
    need(Path(hap).stat().st_size <= 512 * 1024 * 1024, 'NumberIdentity HAP file too large')
    with zipfile.ZipFile(hap) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        need(len(entries) <= 10000 and len(set(names)) == len(names) and
             sum(entry.file_size for entry in entries) <= 256 * 1024 * 1024,
             'NumberIdentity HAP duplicates/count/size invalid')
        for entry in entries:
            path = PurePosixPath(entry.filename)
            need(not path.is_absolute() and '..' not in path.parts and '\\' not in entry.filename and
                 path.as_posix() == entry.filename.rstrip('/') and not entry.flag_bits & 1 and
                 entry.file_size <= 64 * 1024 * 1024 and
                 (entry.external_attr >> 16) & 0o170000 != 0o120000,
                 'unsafe NumberIdentity HAP member')
        need({'module.json', 'ets/modules.abc', 'resources.index'} <= set(names), 'compiled NumberIdentity HAP missing')
        native_member = 'libs/' + HAP_ABIS[arch] + '/' + LIBRARIES[0]
        need(sorted(name for name in names if name.startswith('libs/') and not name.endswith('/')) == [native_member] and
             sorted(name for name in names if name.endswith('.so')) == [native_member],
             'NumberIdentity must bundle exactly its native provider for the selected ABI')
        native_bytes = archive.read(native_member)
        need(len(native_bytes) >= 64, 'NumberIdentity bundled native provider is empty/truncated')
        abc, resources = archive.read('ets/modules.abc'), archive.read('resources.index')
        need(len(abc) >= 60 and abc[:8] == b'PANDA\0\0\0' and
             struct.unpack_from('<I', abc, 16)[0] == len(abc) and
             struct.unpack_from('<I', abc, 8)[0] == zlib.adler32(abc[12:]) & 0xffffffff,
             'NumberIdentity compiled ABC header/checksum invalid')
        need(len(resources) >= 140 and resources.startswith(b'Restool') and
             struct.unpack_from('<I', resources, 128)[0] == len(resources) and
             struct.unpack_from('<I', resources, 132)[0] > 0,
             'NumberIdentity compiled resource index invalid')
        value = decode(archive.read('module.json'))
        need(value.get('app', {}).get('bundleName') == BUNDLE and value['app'].get('debug') is False,
             'NumberIdentity bundle/debug identity differs')
        actual = value['module']
        for key in ('name', 'type', 'deviceTypes', 'mainElement'):
            need(encode(actual.get(key)) == encode(source_module.get(key)), 'NumberIdentity module differs: ' + key)
        need(entry_path(actual) == entry_path(source_module), 'NumberIdentity stage entry differs')
        permissions = actual.get('requestPermissions', [])
        expected = source_module['requestPermissions']
        need([p['name'] for p in permissions] == [p['name'] for p in expected] and
             len({p['name'] for p in permissions}) == len(permissions), 'NumberIdentity permissions differ')
        for actual_permission, expected_permission in zip(permissions, expected):
            need(encode(actual_permission.get('usedScene')) == encode(expected_permission.get('usedScene')),
                 'NumberIdentity permission scene differs')
        for kind in ('abilities', 'extensionAbilities'):
            rows, wanted = actual.get(kind, []), source_module.get(kind, [])
            need([r['name'] for r in rows] == [r['name'] for r in wanted], 'NumberIdentity extension surface differs')
            for row, original in zip(rows, wanted):
                need(entry_path(row) == entry_path(original),
                     'NumberIdentity extension entry differs')
                for key in ('name', 'type', 'exported', 'visible', 'uri', 'readPermission',
                            'writePermission', 'permissions', 'skills', 'srcLanguage'):
                    need(encode(row.get(key)) == encode(original.get(key)),
                         'NumberIdentity extension boundary differs: ' + key)
        return {'bundle': BUNDLE, 'module': actual['name'], 'hap_sha256': file_sha256(hap),
                'compiled_abc_bytes': len(abc), 'resource_index_bytes': len(resources),
                'bundled_native_provider': {'member': native_member, 'bytes': len(native_bytes),
                    'sha256': hashlib.sha256(native_bytes).hexdigest()}}


def inspect_elf(path, arch, library):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 128 * 1024 * 1024,
         'bounded regular NumberIdentity ELF required')
    data = path.read_bytes()
    cls, machine, _ = ARCHES[arch]
    need(64 <= len(data) <= 128 * 1024 * 1024 and data[:7] == b'\x7fELF' + bytes((cls, 1, 1)) and
         struct.unpack_from('<HH', data, 16) == (3, machine), 'NumberIdentity ELF ABI/type invalid: ' + library)
    if cls == 2:
        offset = struct.unpack_from('<Q', data, 32)[0]
        size, count = struct.unpack_from('<HH', data, 54)
        fmt = '<IIQQQQQQ'
    else:
        offset = struct.unpack_from('<I', data, 28)[0]
        size, count = struct.unpack_from('<HH', data, 42)
        fmt = '<IIIIIIII'
    need(0 < count <= 1024 and size >= struct.calcsize(fmt) and offset + count * size <= len(data),
         'NumberIdentity ELF program table missing/truncated')
    executable = dynamic = False
    for index in range(count):
        row = struct.unpack_from(fmt, data, offset + index * size)
        kind, start, length, flags = (row[0], row[2], row[5], row[1]) if cls == 2 else (row[0], row[1], row[4], row[6])
        need(start + length <= len(data), 'NumberIdentity ELF segment truncated')
        dynamic |= kind == 2 and length > 0
        executable |= kind == 1 and bool(flags & 1) and length > 0 and any(data[start:start + length])
    symbols = read_elf(path)
    need(executable and dynamic and symbols.defined, 'empty/stub NumberIdentity shared library')
    if library.startswith('module/'):
        need('napi_module_register' in symbols.undefined and b'telephony.numberidentity\0' in data and
             b'contact.numberlookup\0' in data, 'NumberIdentity actual NAPI registration missing')
    else:
        need(any('Telephony' in symbol and 'Number' in symbol for symbol in symbols.defined),
             'NumberIdentity native implementation exports missing')
    return {'sha256': file_sha256(path), 'elf_class': cls, 'elf_machine': machine, 'elf_type': 3}


def compare_policy(name, source_data, image_data):
    source, actual = decode(source_data), decode(image_data)
    need(encode(actual) == encode(source), 'typed actual NumberIdentity image policy differs: ' + name)
    if name in ('install_list_capability.json', 'install_list_permissions.json'):
        rows = source if type(source) is list else source.get('install_list') if type(source) is dict else None
        need(type(rows) is list and all(type(row) is dict for row in rows) and
             not any(row.get('bundleName') == BUNDLE for row in rows),
             'NumberIdentity must not gain a capability/grant entry')


def load_guard(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_image(source, image, arch, scratch):
    native = load_guard('patches/common/base/telephony/number_identity/local_provider/verify_source.py',
                        'number_identity_native_guard')
    native.validate(source, require_patched=True)
    manifest = load_guard('patches/common/base/telephony/number_identity/native_manifest/verify_source.py',
                          'number_identity_native_manifest_guard')
    manifest.validate(source, require_patched=True)
    packaging = load_guard('patches/common/base/telephony/number_identity/native_package_identity/verify_source.py',
                           'number_identity_native_package_guard')
    packaging.validate(source, require_patched=True)
    loader = load_guard('patches/common/foundation/ability/ability_runtime/number_identity_loader/verify_source.py',
                        'number_identity_loader_guard')
    loader.validate(source, require_patched=True)
    selection = load_guard('patches/common/vendor/ohemu/virt/number_identity_local/configure.py',
                           'number_identity_selection_guard')
    selection.configure(source, require_patched=True)
    helper = load_guard('patches/lib/number_identity_provider.py', 'number_identity_source_guard')
    source_report = helper.verify(source)
    need(source_report.get('state') == 'authenticated_renewed' and source_report.get('bundle') == BUNDLE,
         'authenticated NumberIdentity source profile required')
    import json5
    source_module = json5.loads((source / PROJECT / 'entry/src/main/module.json5').read_text(),
                                allow_duplicate_keys=False)['module']
    module_contract(source_module)
    result = {'source_revision': REVISION, 'source_profile': source_report,
              'install_selection': verify_selection(source, INSTALL_ID, image, scratch, removable=False)}
    directory = scratch / 'hap';directory.mkdir()
    hap, inode = dump_unique_file(image, tuple(p + '/app/' + INSTALL_ID + '/NumberIdentity.hap'
                                 for p in ('', '/system')), directory, debugfs_path())
    result.update(inspect_hap(hap, source_module, arch));result['hap_image'] = inode
    result['signature'] = verify_signature(hap, source, scratch, profile_relative=PROFILE)
    result['image_policies'] = {}
    for name in ('install_list.json', 'uninstall_list.json', 'install_list_capability.json', 'install_list_permissions.json'):
        directory = scratch / name;directory.mkdir()
        actual, inode = dump_unique_file(image, tuple(p + '/etc/app/' + name for p in ('', '/system')),
                                         directory, debugfs_path())
        original = source / 'vendor/ohemu/virt/preinstall-config' / name
        compare_policy(name, original.read_bytes(), actual.read_bytes())
        result['image_policies'][name] = {**inode, 'sha256': file_sha256(actual)}
    result['native_libraries'] = {}
    for index, library in enumerate(LIBRARIES):
        directory = scratch / ('elf-' + str(index));directory.mkdir()
        relative = '/' + ARCHES[arch][2] + '/' + library
        actual, inode = dump_unique_file(image, tuple(p + relative for p in ('', '/system')),
                                         directory, debugfs_path())
        result['native_libraries'][library] = {**inode, **inspect_elf(actual, arch, library)}
    need(result['bundled_native_provider']['sha256'] ==
         result['native_libraries'][LIBRARIES[0]]['sha256'],
         'NumberIdentity bundled provider differs from the validated installed native implementation')
    result['system_image_sha256'] = file_sha256(image)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--arch', choices=tuple(ARCHES), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    result = {'status': 'fail', 'scope': 'offline_public_local_subset_HAP_profile_ELF_image_policy_only',
              'provider_runtime_validated': False, 'local_subset_runtime_validated': False,
              'aggregate_provider_supported': False, 'full_number_library_supported': False,
              'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        with tempfile.TemporaryDirectory(prefix='number-identity-image-') as temporary:
            result.update(verify_image(args.source_root, args.system_image, args.arch, Path(temporary)))
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, ImportError, struct.error,
            zipfile.BadZipFile, subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
