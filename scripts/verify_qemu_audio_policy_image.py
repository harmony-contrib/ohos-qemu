#!/usr/bin/env python3
"""Require the actual chip_prod AudioPolicy XML; not live PCM acceptance."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from verify_alsa_config_image import debugfs_path, file_sha256

CONTRACT_PATH = (Path(__file__).resolve().parents[1] /
                 'patches/common/vendor/ohemu/audio_policy_7/check.py')
spec = importlib.util.spec_from_file_location('qemu_audio_policy_contract', CONTRACT_PATH)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def verify_image(image, executable):
    with tempfile.TemporaryDirectory(prefix='qemu-audio-policy-image-') as directory:
        staged = Path(directory)
        observed = []
        for index, root in enumerate(('/etc/audio/audio_policy_config.xml',
                                      '/chip_prod/etc/audio/audio_policy_config.xml')):
            target = staged / f'policy-{index}.xml'
            subprocess.run([executable, '-R', f'dump {root} {target}', str(image)],
                           check=True, capture_output=True)
            # debugfs returns zero even when an image entry is absent.
            if target.is_file() and target.stat().st_size:
                data = target.read_bytes()
                observed.append({'image_path': root, 'xml_sha256': hashlib.sha256(data).hexdigest(),
                                 'configuration': contract.validate_document(data)})
        if len(observed) != 1:
            raise ValueError('chip_prod must contain one unambiguous repaired AudioPolicy runtime XML')
        return observed[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chip-prod-image', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline 7.0 AudioPolicy XML/map packaging only',
              'first_artifact_behavior_gate_passed': False, 'pcm_behavior_validated': False,
              'capturer_validated': False, 'chip_prod_image': str(args.chip_prod_image.resolve()),
              'failures': []}
    try:
        before = args.chip_prod_image.stat()
        result['chip_prod_image_sha256'] = file_sha256(args.chip_prod_image)
        result.update(verify_image(args.chip_prod_image, debugfs_path()))
        after = args.chip_prod_image.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('chip_prod image changed during AudioPolicy verification; use a completed package')
        result['status'] = 'pass'
    except (OSError, ValueError, TypeError, ET.ParseError, subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
