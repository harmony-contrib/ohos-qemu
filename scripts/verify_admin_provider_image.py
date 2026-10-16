#!/usr/bin/env python3
"""Check the real signed provisioning HAP and its exact image authorization."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches/lib'))
import admin_provider as provider
from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_photos_provider_image import verify_signature


def inspect_hap(hap, profile):
    with zipfile.ZipFile(hap) as archive:
        entries = archive.infolist()
        names = [p.filename for p in entries]
        if (len(entries) > 5000 or len(set(names)) != len(names) or
                sum(p.file_size for p in entries) > 256 * 1024 * 1024):
            raise ValueError('unexpected provisioning HAP member count/size/duplicates')
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (name.is_absolute() or '..' in name.parts or '\\' in entry.filename or
                    name.as_posix() != entry.filename.rstrip('/') or entry.flag_bits & 1 or
                    entry.file_size > 64 * 1024 * 1024 or
                    ((entry.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('unsafe/oversized provisioning HAP member')
        if not {'module.json', 'ets/modules.abc', 'resources.index'} <= set(names):
            raise ValueError('compiled provisioning module/resources missing')
        if not archive.read('ets/modules.abc') or not archive.read('resources.index'):
            raise ValueError('empty provisioning HAP implementation')
        module = json.loads(archive.read('module.json'), object_pairs_hook=provider.unique)
        if module.get('app', {}).get('bundleName') != provider.BUNDLE or module['app'].get('debug') is not False:
            raise ValueError('wrong provisioning application or debug HAP')
        provider.validate(module['module'], profile, provider.SIGNATURE, provider.SIGNATURE)
        return {'hap_sha256': file_sha256(hap), 'bundle': provider.BUNDLE,
                'compiled_abc_bytes': len(archive.read('ets/modules.abc')),
                'abilities': [a['name'] for a in module['module']['abilities']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--system-image', type=Path)
    group.add_argument('--hap', type=Path)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline source AdminProvisioning HAP/signature/authorization ONLY',
              'provider_runtime_validated': False, 'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        profile = provider.verify(args.source_root)
        with tempfile.TemporaryDirectory(prefix='admin-provider-image-') as temporary:
            scratch = Path(temporary)
            hap = args.hap
            if args.system_image:
                hap, inode = dump_unique_file(args.system_image, tuple(prefix + '/app/' + provider.BUNDLE +
                    '/adminprovisioning.hap' for prefix in ('', '/system')), scratch, debugfs_path())
                result.update(inode)
                result['system_image_sha256'] = file_sha256(args.system_image)
            result.update(inspect_hap(hap, profile))
            result.update(verify_signature(hap, args.source_root, scratch,
                'applications/standard/admin_provisioning/signature/adminprovisioning.p7b'))
            if args.system_image:
                for name in provider.POLICIES:
                    directory = scratch / name
                    directory.mkdir()
                    path, inode = dump_unique_file(args.system_image, tuple(prefix + '/etc/app/' + name
                        for prefix in ('', '/system')), directory, debugfs_path())
                    expected = args.source_root / 'vendor/ohemu/virt/preinstall-config' / name
                    if provider.policy_bytes(path, name) != provider.policy_bytes(expected, name):
                        raise ValueError('packaged provisioning authorization differs from source: ' + name)
                    result.setdefault('image_policies', {})[name] = {**inode, 'sha256': file_sha256(path)}
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        result['failures'].append(str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'failures')}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
