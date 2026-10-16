#!/usr/bin/env python3
"""Verify real signed Contacts and selected Wallpaper HAPs, not guest behavior."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches/lib'))
import contacts_theme_providers as provider
from ext_image_entries import dump_unique_file
from preinstall_selection import same_json
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_photos_provider_image import verify_signature
from verify_preinstall_selection import verify_selection


def inspect_hap(hap, source_module, name, device):
    config = provider.PROFILES[name]
    with zipfile.ZipFile(hap) as archive:
        entries = archive.infolist();names = [item.filename for item in entries]
        if (len(entries) > 10000 or len(names) != len(set(names)) or
                sum(item.file_size for item in entries) > 256 * 1024 * 1024):
            raise ValueError('Contacts/Wallpaper archive size or duplicate member')
        for item in entries:
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename or
                    path.as_posix() != item.filename.rstrip('/') or item.flag_bits & 1 or
                    item.file_size > 64 * 1024 * 1024 or
                    ((item.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('unsafe Contacts/Wallpaper HAP member')
        if not {'module.json', 'ets/modules.abc', 'resources.index'} <= set(names):
            raise ValueError('compiled Contacts/Wallpaper implementation missing')
        abc, resources = archive.read('ets/modules.abc'), archive.read('resources.index')
        if not abc or not resources: raise ValueError('empty compiled Contacts/Wallpaper implementation')
        value = json.loads(archive.read('module.json'), object_pairs_hook=provider.unique)
        if value.get('app', {}).get('bundleName') != config['bundle'] or value['app'].get('debug') is not False:
            raise ValueError('Contacts/Wallpaper bundle/debug identity differs')
        module = value['module']
        for key in ('name', 'type', 'deviceTypes', 'mainElement', 'deliveryWithInstall', 'installationFree'):
            if not same_json(module.get(key), source_module.get(key)):
                raise ValueError('compiled Contacts/Wallpaper module differs: ' + key)
        requests = [item['name'] for item in module.get('requestPermissions', [])]
        if (len(requests) != len(set(requests)) or
                requests != [item['name'] for item in source_module.get('requestPermissions', [])]):
            raise ValueError('Contacts/Wallpaper permission surface differs')
        for kind in ('abilities', 'extensionAbilities'):
            actual, desired = module.get(kind, []), source_module.get(kind, [])
            if [item['name'] for item in actual] != [item['name'] for item in desired]:
                raise ValueError('Contacts/Wallpaper entrypoint surface differs')
            for entry, source in zip(actual, desired):
                for key in ('srcEntry', 'srcEntrance', 'type', 'launchType', 'permissions', 'skills',
                            'visible', 'exported', 'extensionProcessMode'):
                    if not same_json(entry.get(key), source.get(key)):
                        raise ValueError('Contacts/Wallpaper entrypoint boundary differs: ' + key)
        if module.get('dependencies', []) != []:
            raise ValueError('unexpected compiled external HSP dependency')
        if name == 'contacts':
            picker = next(item for item in module['extensionAbilities'] if item['name'] == 'ContactUiExtentionAbility')
            if (picker.get('type') != 'sys/commonUI' or picker.get('exported') is not True or
                    picker.get('permissions', []) != [] or picker.get('extensionProcessMode') != 'instance'):
                raise ValueError('real Contacts modal picker contract missing')
        else:
            expected = ('pad_wallpaper', ['tablet']) if device == '2in1' else ('phone_wallpaper', ['default'])
            if ((module['name'], module['deviceTypes']) != expected or module.get('type') != 'feature' or
                    module.get('abilities', []) != [] or
                    requests != ['ohos.permission.GET_WALLPAPER', 'ohos.permission.READ_USER_STORAGE']):
                raise ValueError('wrong Wallpaper renderer/device/permission profile')
            extension = module['extensionAbilities']
            if (len(extension) != 1 or extension[0].get('name') != 'WallpaperExtAbility' or
                    extension[0].get('type') != 'wallpaper' or extension[0].get('visible') is not True or
                    extension[0].get('srcEntrance') != './ets/WallpaperExtAbility/WallpaperExtAbility.ts'):
                raise ValueError('real Wallpaper extension entrypoint missing')
        return {'bundle': config['bundle'], 'hap_sha256': file_sha256(hap),
                'compiled_abc_bytes': len(abc), 'module': module['name'], 'permissions': requests,
                'extension_abilities': [item['name'] for item in module.get('extensionAbilities', [])]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'actual source signed Contacts/Wallpaper image policy ONLY',
              'first_artifact_behavior_gate_passed': False, 'provider_runtime_validated': False,
              'device': args.device, 'failures': [], 'providers': {}}
    try:
        provider.verify(args.source_root)
        import json5
        with tempfile.TemporaryDirectory(prefix='contacts-theme-image-') as temporary:
            scratch = Path(temporary)
            for name, config in provider.PROFILES.items():
                directory = scratch / name;directory.mkdir()
                relative = ('entry/src/main/module.json5' if name == 'contacts' else
                            'product/' + ('pad' if args.device == '2in1' else 'phone') + '/src/main/module.json5')
                source_module = json5.loads((args.source_root / config['project'] / relative).read_text(),
                                           allow_duplicate_keys=False)['module']
                selection = verify_selection(args.source_root, config['bundle'], args.system_image,
                                             directory, config['removable'])
                filename = 'Contacts.hap' if name == 'contacts' else 'Wallpaper.hap'
                hap, inode = dump_unique_file(args.system_image, tuple(prefix + '/app/' + config['bundle'] + '/' + filename
                    for prefix in ('', '/system')), directory, debugfs_path())
                row = inspect_hap(hap, source_module, name, args.device)
                row.update(inode);row['install_selection'] = selection
                row.update(verify_signature(hap, args.source_root, directory, config['project'] + '/' + config['profile']))
                result['providers'][name] = row
            for name, expected in provider.POLICIES.items():
                directory = scratch / name;directory.mkdir()
                path, inode = dump_unique_file(args.system_image, tuple(prefix + '/etc/app/' + name
                    for prefix in ('', '/system')), directory, debugfs_path())
                source = args.source_root / 'vendor/ohemu/virt/preinstall-config' / name
                if provider.policy(path.read_bytes(), expected, True) != provider.policy(source.read_bytes(), expected, True):
                    raise ValueError('packaged Contacts policy differs from original source grants')
                result.setdefault('image_policies', {})[name] = {**inode, 'sha256': file_sha256(path)}
            result['system_image_sha256'] = file_sha256(args.system_image)
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, StopIteration, ImportError, subprocess.SubprocessError,
            zipfile.BadZipFile) as error:
        result['failures'].append(str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'failures')}))
    return result['status'] != 'pass'


if __name__ == '__main__': raise SystemExit(main())
