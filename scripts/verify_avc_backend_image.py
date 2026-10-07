#!/usr/bin/env python3
"""Check real AVC backend/provenance in system.img; not media API acceptance."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches/lib'))
from avc_artifacts import LICENSES, validate
from verify_alsa_config_image import debugfs_path, file_sha256

ARCHES = {40: 'arm', 183: 'arm64', 62: 'x86_64'}


def verify_image(image, machine, executable):
    if machine not in ARCHES: raise ValueError('unsupported QEMU AVC architecture')
    arch = ARCHES[machine]
    abi = 'lib' if machine == 40 else 'lib64'
    with tempfile.TemporaryDirectory(prefix='qemu-avc-image-') as directory:
        staged = Path(directory)

        def dump(source, target):
            subprocess.run([executable, '-R', f'dump {source} {target}', str(image)],
                           check=True, capture_output=True)
            return target.is_file() and target.stat().st_size > 0

        root = None
        binary = staged / arch / 'libavcenc_ohos.z.so'
        binary.parent.mkdir()
        for index, prefix in enumerate(('', '/system')):
            candidate = staged / f'candidate-{index}.so'
            if dump(f'{prefix}/{abi}/libavcenc_ohos.z.so', candidate):
                if root is not None: raise ValueError('ambiguous AVC backend in system image')
                binary.write_bytes(candidate.read_bytes())
                root = prefix
        if root is None: raise ValueError('system.img lacks the real native-ABI AVC backend')
        notice_root = root + '/etc/notice/qemu_avc'
        if not dump(notice_root + '/provenance.json', staged / 'manifest.json'):
            raise ValueError('system.img lacks software AVC dependency provenance')
        (staged / 'licenses').mkdir()
        for name in LICENSES:
            if not dump(notice_root + '/' + name, staged / 'licenses' / name):
                raise ValueError('system.img lacks required AVC/runtime notice: ' + name)
        observed = validate(staged, [arch])[arch]
        return {'image_library': root + '/' + abi + '/libavcenc_ohos.z.so',
                'machine': machine, 'backend': observed,
                'provenance_sha256': file_sha256(staged / 'manifest.json'),
                'licenses': json.loads((staged / 'manifest.json').read_text())['licenses']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--machine', type=int, choices=tuple(ARCHES), required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline software AVC dependency/ABI packaging only',
              'media_api_behavior_validated': False, 'first_artifact_behavior_gate_passed': False,
              'system_image': str(args.system_image.resolve()), 'failures': []}
    try:
        before = args.system_image.stat()
        result['system_image_sha256'] = file_sha256(args.system_image)
        result.update(verify_image(args.system_image, args.machine, debugfs_path()))
        after = args.system_image.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('system image changed during AVC verification; use the completed package')
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
