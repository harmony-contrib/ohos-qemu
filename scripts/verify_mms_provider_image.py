#!/usr/bin/env python3
"""Verify the signed source MMS HAP and its original signer-bound image policy."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches/lib'))
import mms_provider as provider
from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_photos_provider_image import verify_signature


def inspect_hap(hap, source_module):
    with zipfile.ZipFile(hap) as archive:
        entries = archive.infolist();names = [p.filename for p in entries]
        if (len(entries) > 10000 or len(set(names)) != len(names) or
                sum(p.file_size for p in entries) > 256 * 1024 * 1024):
            raise ValueError('MMS HAP member count/size/duplicates invalid')
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename or
                    path.as_posix() != entry.filename.rstrip('/') or entry.flag_bits & 1 or
                    entry.file_size > 64 * 1024 * 1024 or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('unsafe MMS HAP member')
        if not {'module.json', 'ets/modules.abc', 'resources.index'} <= set(names):
            raise ValueError('MMS compiled module/resources missing')
        abc, resources = archive.read('ets/modules.abc'), archive.read('resources.index')
        if not abc or not resources: raise ValueError('MMS compiled implementation empty')
        value = json.loads(archive.read('module.json'), object_pairs_hook=provider.unique)
        if value.get('app', {}).get('bundleName') != 'com.ohos.mms' or value['app'].get('debug') is not False:
            raise ValueError('MMS bundle/debug identity differs')
        module = value['module']
        for key in ('name', 'type', 'deviceTypes', 'mainElement'):
            if module.get(key) != source_module.get(key): raise ValueError('MMS compiled module differs: ' + key)
        requests = [r['name'] for r in module.get('requestPermissions', [])]
        expected = [r['name'] for r in source_module.get('requestPermissions', [])]
        if len(set(requests)) != len(requests) or requests != expected:
            raise ValueError('MMS compiled permission surface differs from exact source')
        for kind in ('abilities', 'extensionAbilities'):
            actual, desired = module.get(kind, []), source_module.get(kind, [])
            if [r['name'] for r in actual] != [r['name'] for r in desired]:
                raise ValueError('MMS compiled entrypoint surface differs')
            for entry, source in zip(actual, desired):
                for key in ('permissions', 'skills', 'launchType', 'type'):
                    if entry.get(key) != source.get(key): raise ValueError('MMS entrypoint contract differs: ' + key)
                for key in ('visible', 'exported'):
                    if entry.get(key) != source.get(key) or type(entry.get(key)) is not type(source.get(key)):
                        raise ValueError('MMS entrypoint export boundary differs')
        main = next(r for r in module['abilities'] if r['name'] == 'com.ohos.mms.MainAbility')
        if not any('ohos.want.action.sendData' in r.get('actions', []) and {'type': 'text/plain'} in r.get('uris', [])
                   for r in main.get('skills', [])):
            raise ValueError('real MMS text draft receiver skill missing')
        return {'bundle': 'com.ohos.mms', 'hap_sha256': file_sha256(hap), 'compiled_abc_bytes': len(abc),
                'permissions': requests, 'abilities': [r['name'] for r in module['abilities']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--system-image', type=Path);group.add_argument('--hap', type=Path)
    parser.add_argument('--source-root', type=Path, required=True);parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline_actual_source_MMS_HAP_signer_existing_grants_ONLY',
              'first_artifact_behavior_gate_passed': False, 'provider_runtime_validated': False, 'failures': []}
    try:
        provider.verify(args.source_root)
        # The product Python build environment already uses JSON5 for the
        # exact same application manifest and build-profile inputs.
        import json5
        source_module = json5.loads((args.source_root / provider.PROJECT / 'entry/src/main/module.json5').read_text(),
                                    allow_duplicate_keys=False)['module']
        with tempfile.TemporaryDirectory(prefix='mms-provider-image-') as temporary:
            scratch = Path(temporary);hap = args.hap
            if args.system_image:
                hap, inode = dump_unique_file(args.system_image, tuple(prefix + '/app/com.ohos.mms/Mms.hap'
                    for prefix in ('', '/system')), scratch, debugfs_path())
                result.update(inode);result['system_image_sha256'] = file_sha256(args.system_image)
            result.update(inspect_hap(hap, source_module))
            result.update(verify_signature(hap, args.source_root, scratch, provider.PROJECT + '/signature/mms.p7b'))
            if args.system_image:
                directory = scratch / 'install_list.json';directory.mkdir()
                path, inode = dump_unique_file(args.system_image, tuple(prefix + '/etc/app/install_list.json'
                    for prefix in ('', '/system')), directory, debugfs_path())
                provider.install_entry(path.read_bytes())
                result['image_install_entry'] = {**inode, 'sha256': file_sha256(path),
                                                'entry': provider.install_entry(path.read_bytes())}
                for name, expected in (('install_list_capability.json', provider.CAPABILITY),
                                       ('install_list_permissions.json', provider.GRANTS)):
                    directory = scratch / name;directory.mkdir()
                    path, inode = dump_unique_file(args.system_image, tuple(prefix + '/etc/app/' + name
                        for prefix in ('', '/system')), directory, debugfs_path())
                    source = args.source_root / 'vendor/ohemu/virt/preinstall-config' / name
                    if provider.policy(path.read_bytes(), expected, True) != provider.policy(source.read_bytes(), expected, True):
                        raise ValueError('packaged MMS policy differs from original source grants')
                    result.setdefault('image_policies', {})[name] = {**inode, 'sha256': file_sha256(path)}
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        result['failures'].append(str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'failures')}))
    return result['status'] != 'pass'


if __name__ == '__main__': raise SystemExit(main())
