#!/usr/bin/env python3
"""Check fixed ALSA config closure in vendor.img; no runtime audio claims."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from verify_runtime_elf_contract import read_elf, verify_machine

INVENTORY = Path(__file__).resolve().parents[1] / 'patches/common/third_party/alsa-lib/config_install/config_inventory.json'


def validate_inventory(document):
    if (type(document.get('schema_version')) is not int or document['schema_version'] != 1 or
            document.get('project') != 'third_party/alsa-lib' or
            document.get('source_revision') != 'dececa15b19fba7445fbdb5559b60e88f53f6960' or
            document.get('manifest_revision') != 'f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549' or
            document.get('runtime_directory') != '/vendor/etc/audio/alsa/share'):
        raise ValueError('ALSA inventory must describe the pinned 7.0 project/configuration')
    files = document.get('files')
    required = {'alsa.conf', 'smixer.conf', 'cards/aliases.conf', 'cards/ENS1370.conf',
                'pcm/default.conf', 'ctl/default.conf'}
    if not isinstance(files, dict) or len(files) != 79 or not required.issubset(files):
        raise ValueError('incomplete fixed ALSA config dependency inventory')
    for name, digest in files.items():
        if (not isinstance(name, str) or re.fullmatch(r'(?:[A-Za-z0-9_-]+/)?[A-Za-z0-9_-]+\.conf', name) is None or
                not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None):
            raise ValueError('unsafe or invalid ALSA config inventory entry')
    return files


def check_file(path, expected):
    if not path.is_file() or not path.stat().st_size:
        raise ValueError('ALSA image is missing config: ' + path.name)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError('ALSA image config differs from pinned source: ' + path.name)
    return actual


def debugfs_path():
    executable = shutil.which('debugfs')
    if executable:
        return executable
    for path in ('/opt/homebrew/opt/e2fsprogs/sbin/debugfs', '/usr/local/opt/e2fsprogs/sbin/debugfs'):
        if Path(path).is_file(): return path
    raise ValueError('debugfs is required for ALSA image validation')


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_image(image, machine, inventory, executable):
    if machine not in (40, 62, 183): raise ValueError('unsupported QEMU ALSA architecture')
    files = validate_inventory(inventory)
    with tempfile.TemporaryDirectory(prefix='qemu-alsa-config-image-') as directory:
        staged = Path(directory)

        def dump(source, target):
            subprocess.run([executable, '-R', f'dump {source} {target}', str(image)],
                           check=True, capture_output=True)

        root = None
        for candidate in ('/etc/audio/alsa/share', '/vendor/etc/audio/alsa/share'):
            target = staged / ('root-etc.conf' if candidate.startswith('/etc') else 'root-vendor.conf')
            dump(candidate + '/alsa.conf', target)
            if target.is_file() and target.stat().st_size:
                if root is not None: raise ValueError('ambiguous ALSA config roots in image')
                check_file(target, files['alsa.conf'])
                root = candidate
        if root is None: raise ValueError('vendor.img has no ALSA config at its runtime path')
        observed = {}
        for index, (name, expected) in enumerate(sorted(files.items())):
            target = staged / f'config-{index}.conf'
            dump(root + '/' + name, target)
            observed[name] = check_file(target, expected)
        abi = 'lib' if machine == 40 else 'lib64'
        library = None
        for prefix in ('', '/vendor'):
            target = staged / ('lib-vendor.so' if prefix else 'lib-root.so')
            dump(f'{prefix}/{abi}/libasound.so', target)
            if target.is_file() and target.stat().st_size:
                if library is not None: raise ValueError('ambiguous libasound in vendor image')
                library = target
        if library is None: raise ValueError('vendor.img is missing native-ABI libasound.so')
        data = library.read_bytes()
        info = read_elf(library)
        verify_machine(info, machine, library)
        if data[4] != (1 if machine == 40 else 2): raise ValueError('wrong ALSA ELF class')
        if not {'snd_ctl_open', 'snd_pcm_open', 'snd_ohos_enable_global_config'}.issubset(info.defined):
            raise ValueError('ALSA library lacks actual hardware/config entry points')
        if b'/vendor/etc/audio/alsa/share\0' not in data:
            raise ValueError('ALSA library compiled config path differs from packaged location')
        return {'config_files': observed, 'image_config_root': root,
                'libasound_sha256': hashlib.sha256(data).hexdigest(), 'machine': machine}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor-image', type=Path, required=True)
    parser.add_argument('--machine', type=int, choices=(40, 62, 183), required=True)
    parser.add_argument('--inventory', type=Path, default=INVENTORY)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline fixed ALSA config/ABI packaging only',
              'audio_behavior_validated': False, 'first_artifact_behavior_gate_passed': False,
              'vendor_image': str(args.vendor_image.resolve()), 'failures': []}
    try:
        before = args.vendor_image.stat()
        result['vendor_image_sha256'] = file_sha256(args.vendor_image)
        result['inventory_sha256'] = hashlib.sha256(args.inventory.read_bytes()).hexdigest()
        result.update(verify_image(args.vendor_image, args.machine, json.loads(args.inventory.read_text()), debugfs_path()))
        after = args.vendor_image.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('vendor image changed during ALSA verification; use the completed package')
        result['status'] = 'pass'
    except (OSError, ValueError, TypeError, KeyError, struct.error, subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
