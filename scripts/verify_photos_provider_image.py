#!/usr/bin/env python3
"""Verify the actual source Photos HAP; offline checks are not guest acceptance."""
import argparse
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import tempfile
import zipfile

from ext_image_entries import dump_unique_file
from verify_preinstall_selection import verify_selection
from verify_alsa_config_image import debugfs_path, file_sha256

SIGNATURE = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
SIGNER_JAR_SHA = 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d'
ABIS = {'armv7a': ('armeabi-v7a', 1, 40), 'arm64': ('arm64-v8a', 2, 183),
        'x86_64': ('x86_64', 2, 62)}
EXTENSIONS = {
    'PrivacyStatementAbility': 'sys/commonUI', 'FormAbility': 'form',
    'FacardDataShareAbility': 'dataShare', 'AuthExtensionAbility': 'sys/commonUI',
    'RecentUIExtensionAbility': 'recentPhoto', 'PickerUIExtensionAbility': 'sysPicker/photoPicker',
    'DeleteUIExtensionAbility': 'sysDialog/common', 'SaveUIExtensionAbility': 'sysDialog/common',
    'BackupExtensionAbility': 'backup', 'MusicServiceAbility': 'service',
    'FACardServiceAbility': 'service', 'RecentPhotoInfoAbility': 'service',
    'SettingCardDataShareAbility': 'dataShare', 'GalleryCleanupUIExtensionAbility': 'sys/commonUI',
    'DefaultAlbumNameUIExtensionAbility': 'sysDialog/common',
}


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate Photos metadata key: ' + name)
        result[name] = value
    return result


def inspect_hap(hap):
    with zipfile.ZipFile(hap) as archive:
        seen = set()
        if len(archive.infolist()) > 10000 or sum(item.file_size for item in archive.infolist()) > 512 * 1024 * 1024:
            raise ValueError('Photos HAP exceeds the bounded source provider size')
        for entry in archive.infolist():
            name = PurePosixPath(entry.filename)
            if (entry.filename in seen or name.is_absolute() or '..' in name.parts or
                    '\\' in entry.filename or name.as_posix() != entry.filename.rstrip('/') or
                    entry.flag_bits & 1 or entry.file_size > 256 * 1024 * 1024 or
                    ((entry.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('unsafe/duplicate/oversized Photos HAP member')
            seen.add(entry.filename)
        if not {'module.json', 'ets/modules.abc', 'resources.index'} <= seen:
            raise ValueError('Photos HAP lacks real compiled module/resources')
        if not archive.read('ets/modules.abc') or not archive.read('resources.index'):
            raise ValueError('empty compiled Photos provider')
        module = json.loads(archive.read('module.json'), object_pairs_hook=unique_object)
        if (module.get('app', {}).get('bundleName') != 'com.ohos.photos' or
                module.get('module', {}).get('name') != 'phone_photos' or
                module['module'].get('type') != 'entry' or
                set(module['module'].get('deviceTypes', [])) != {'default', 'tablet'}):
            raise ValueError('unexpected Photos bundle/module/device profile')
        extensions = module['module'].get('extensionAbilities', [])
        actual = {entry['name']: entry['type'] for entry in extensions}
        if len(actual) != len(extensions) or actual != EXTENSIONS:
            raise ValueError('Photos provider extensions missing, duplicated or incompatible')
        machines = {}
        for abi, elf_class, machine in ABIS.values():
            for library in ('libImageEditor.so', 'libc++_shared.so'):
                member = 'libs/' + abi + '/' + library
                raw = archive.read(member)
                if (len(raw) < 64 or raw[:7] != b'\x7fELF' + bytes((elf_class, 1, 1)) or
                        struct.unpack_from('<HH', raw, 16) != (3, machine)):
                    raise ValueError('Photos native library has wrong ABI/type: ' + member)
                machines[member] = {'elf_machine': machine, 'sha256': hashlib.sha256(raw).hexdigest()}
        return {'bundle': 'com.ohos.photos', 'extensions': actual, 'native_libraries': machines,
                'hap_sha256': file_sha256(hap)}


def stage_signature_hap(hap, scratch):
    """Retain the exact input bytes under a .hap name for the fixed signer."""
    before = hap.stat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    identity = lambda value: tuple(getattr(value, key) for key in fields)
    if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
        raise ValueError('signature input must be a nonempty regular HAP')
    staged = scratch / 'signature-input.hap'
    digest = hashlib.sha256(); remaining = before.st_size
    with hap.open('rb') as source, staged.open('xb') as output:
        if identity(os.fstat(source.fileno())) != identity(before):
            raise ValueError('signature input changed before staging')
        while True:
            block = source.read(min(65536, remaining + 1))
            if not block:
                break
            if len(block) > remaining:
                raise ValueError('signature input grew during staging')
            digest.update(block); output.write(block); remaining -= len(block)
        if identity(os.fstat(source.fileno())) != identity(before):
            raise ValueError('signature input changed during staging')
    if (remaining or identity(hap.stat()) != identity(before) or
            staged.stat().st_size != before.st_size or file_sha256(staged) != digest.hexdigest()):
        raise ValueError('staged .hap differs from original signature input')
    return staged


def verify_signature(hap, source, scratch,
                     profile_relative='applications/standard/photos/signature/photos.p7b'):
    dist = source / 'developtools/hapsigner/dist'
    jar = dist / 'hap-sign-tool.jar'
    if file_sha256(jar) != SIGNER_JAR_SHA:
        raise ValueError('Photos signer tool does not match the fixed release')
    signature_hap = stage_signature_hap(hap, scratch)
    profile = scratch / 'embedded-profile.p7b'
    chain = scratch / 'app-chain.cer'
    completed = subprocess.run(['java', '-jar', str(jar), 'verify-app', '-inFile', str(signature_hap),
                                '-outCertChain', str(chain), '-outProfile', str(profile)],
                               check=True, capture_output=True, text=True, timeout=120)
    output = completed.stdout + completed.stderr
    required = ('verify codesign success', 'Digest verify result: true',
                'verify permission sign success', 'verify-app success')
    if 'skip code signing verify' in output:
        raise ValueError('source HAP verifier skipped code signing')
    missing_markers = [marker for marker in required if marker not in output]
    if missing_markers:
        raise ValueError('source HAP verification missing required markers: ' + ', '.join(missing_markers))
    leaf = re.split(r'certificate #0\b', output, maxsplit=1)
    if len(leaf) != 2:
        raise ValueError('Photos HAP verification lacks the actual signing leaf')
    match = re.search(r'SHA256:\s*([0-9A-Fa-f:]+)', re.split(r'certificate #1\b', leaf[1], maxsplit=1)[0])
    identity_checks = {
        'application_leaf': bool(match and match[1].replace(':', '').upper() == SIGNATURE),
        'certificate_chain_output': chain.is_file(),
        'exact_source_profile': profile.is_file() and profile.read_bytes() == (source / profile_relative).read_bytes(),
    }
    if not all(identity_checks.values()):
        raise ValueError('source HAP signing identity/profile mismatch: ' +
                         ', '.join(name for name, passed in identity_checks.items() if not passed))
    return {'application_signer_sha256': SIGNATURE, 'embedded_profile_sha256': file_sha256(profile),
            'signature_input_sha256': file_sha256(signature_hap), 'code_signing_skip_rejected': True,
            'digest_codesign_permission_verification': 'pass'}


def verify_source(source):
    verifier = Path(__file__).resolve().parents[1] / 'patches/common/applications/standard/photos/source_provider/verify_source.py'
    spec = importlib.util.spec_from_file_location('photos_source_guard', verifier)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.validate(source, require_patched=True)
    policy = json.loads((source / 'vendor/ohemu/virt/preinstall-config/install_list_capability.json').read_text(),
                        object_pairs_hook=unique_object)
    entries = [item for item in policy['install_list'] if item.get('bundleName') == 'com.ohos.photos']
    if len(entries) != 1 or entries[0].get('app_signature') != [SIGNATURE]:
        raise ValueError('Photos preinstall policy does not pin the exact OS signer')
    return guard.REVISION


def verify_preinstall_policies(source, image=None, scratch=None):
    """Check both certificate pins, including the actual image's grant file."""
    component = Path(__file__).resolve().parents[1] / 'patches/common/vendor/ohemu/virt/photos_provider/prepare.py'
    spec = importlib.util.spec_from_file_location('photos_preinstall_guard', component)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    result = {}
    for name, permissions in (('install_list_capability.json', False), ('install_list_permissions.json', True)):
        path = source / 'vendor/ohemu/virt/preinstall-config' / name
        canonical = guard.prepare(path, require_patched=True, permissions=permissions)
        item = {'source_sha256': file_sha256(path), 'application_signer_sha256': SIGNATURE}
        if image is not None:
            directory = scratch / name
            directory.mkdir()
            actual, identity = dump_unique_file(image, ('/etc/app/' + name, '/system/etc/app/' + name),
                                               directory, debugfs_path())
            if guard.prepare(actual, require_patched=True, permissions=permissions) != canonical:
                raise ValueError('actual packaged Photos preinstall policy differs from validated source: ' + name)
            item.update(identity)
            item['image_file_sha256'] = file_sha256(actual)
        result[name] = item
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--system-image', type=Path)
    group.add_argument('--hap', type=Path)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--arch', choices=tuple(ABIS), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline source Photos provider/ABI/signature only',
              'arch': args.arch, 'first_artifact_behavior_gate_passed': False,
              'provider_runtime_validated': False, 'cloud_provider_validated': False, 'failures': []}
    try:
        result['source_revision'] = verify_source(args.source_root)
        with tempfile.TemporaryDirectory(prefix='photos-image-') as directory:
            scratch = Path(directory)
            result['install_selection'] = verify_selection(args.source_root, 'com.ohos.photos', args.system_image, scratch)
            hap = args.hap
            if args.system_image:
                hap, identity = dump_unique_file(args.system_image,
                    ('/app/com.ohos.photos/Photos.hap', '/system/app/com.ohos.photos/Photos.hap'),
                    scratch, debugfs_path())
                result.update(identity)
                result['system_image_sha256'] = file_sha256(args.system_image)
            result.update(inspect_hap(hap))
            result.update(verify_signature(hap, args.source_root, scratch))
            result['preinstall_policies'] = verify_preinstall_policies(args.source_root, args.system_image, scratch)
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, struct.error, zipfile.BadZipFile,
            subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'failures': result['failures']}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
