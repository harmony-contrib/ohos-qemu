#!/usr/bin/env python3
"""Exercise debugfs on tiny ext2 fixtures with real dependency files; not QEMU acceptance."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'patches/lib'))
sys.path.insert(0, str(REPO / 'scripts'))
from avc_artifacts import LICENSES, MACHINES, validate
from verify_avc_backend_image import verify_image
from verify_alsa_config_image import debugfs_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--mke2fs', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs = validate(args.artifact_root, list(MACHINES))
    evidence = {'status': 'fail', 'scope': 'real debugfs/ELF dependency fixture only, no QEMU package or boot',
                'first_artifact_behavior_gate_passed': False, 'media_api_behavior_validated': False,
                'artifacts': {}, 'failures': []}
    try:
        for arch, (_, machine) in MACHINES.items():
            with tempfile.TemporaryDirectory(prefix='avc-ext2-fixture-') as directory:
                root = Path(directory)
                tree = root / 'tree'
                abi = tree / ('lib' if machine == 40 else 'lib64')
                notices = tree / 'etc/notice/qemu_avc'
                abi.mkdir(parents=True)
                notices.mkdir(parents=True)
                shutil.copy2(args.artifact_root / arch / 'libavcenc_ohos.z.so', abi)
                shutil.copy2(args.artifact_root / 'manifest.json', notices / 'provenance.json')
                for name in LICENSES: shutil.copy2(args.artifact_root / 'licenses' / name, notices / name)
                image = root / 'fixture.img'
                subprocess.run([args.mke2fs, '-t', 'ext2', '-F', '-q', '-d', str(tree), str(image), '8192'],
                               check=True, capture_output=True)
                observed = verify_image(image, machine, debugfs_path())
                if observed['backend'] != inputs[arch]: raise ValueError('fixture readback differs from real dependency')
                # Actual debugfs negative mutation, not a mocked zero exit.
                subprocess.run([debugfs_path(), '-w', '-R', 'rm /etc/notice/qemu_avc/compiler-rt-LICENSE.TXT', str(image)],
                               check=True, capture_output=True)
                refused = False
                try: verify_image(image, machine, debugfs_path())
                except ValueError: refused = True
                if not refused: raise ValueError('missing notice in actual ext2 image incorrectly accepted')
                evidence['artifacts'][arch] = dict(observed, missing_runtime_notice_rejected=True)
        evidence['status'] = 'pass'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        evidence['failures'].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
