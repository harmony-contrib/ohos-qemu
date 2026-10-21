"""Exact existing Photos package inspector applied to actual guest readback.

Constants/unique_object/inspect_hap body are copied verbatim from the existing
source-pinned scripts/verify_photos_provider_image.py. No module selection or
new offline acceptance claim; original package/source guards still apply.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import zipfile


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


