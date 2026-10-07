#!/usr/bin/env python3
"""Actual debugfs DSP/security-runtime readback; not a QEMU package or PCM test."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
from verify_audio_suite_dsp_image import ARM_UNWIND_RUNTIME, LIBRARY, SANITIZER, verify_image
from verify_alsa_config_image import debugfs_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--machine', type=int, choices=(40, 183, 62), required=True)
    parser.add_argument('--mke2fs', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = {'status': 'fail', 'scope': 'actual ELF/security closure in tiny ext2 fixture only',
                'first_artifact_behavior_gate_passed': False, 'AudioSuite_behavior_validated': False,
                'failures': []}
    try:
        with tempfile.TemporaryDirectory(prefix='audiosuite-dsp-ext2-fixture-') as directory:
            root = Path(directory)
            tree = root / 'tree'
            abi = 'lib' if args.machine == 40 else 'lib64'
            library_dir, config_dir = tree / abi, tree / 'etc/audio'
            (library_dir / 'platformsdk').mkdir(parents=True)
            config_dir.mkdir(parents=True)
            for name in (LIBRARY, 'libc.so'):
                shutil.copyfile(args.artifact_root / name, library_dir / name)
            if args.machine == 40:
                shutil.copyfile(args.artifact_root / ARM_UNWIND_RUNTIME, library_dir / ARM_UNWIND_RUNTIME)
            shutil.copyfile(args.artifact_root / SANITIZER, library_dir / 'platformsdk' / SANITIZER)
            shutil.copyfile(args.artifact_root / 'audio_suite_capabilities.xml', config_dir / 'audio_suite_capabilities.xml')
            image = root / 'fixture.img'
            # ARM EHABI's fixed prebuilt libc++ can retain debug sections.
            # Size the disposable filesystem from actual inputs, not a small
            # ARM64-only constant; do not strip or substitute runtime evidence.
            total = sum(path.stat().st_size for path in tree.rglob('*') if path.is_file())
            blocks = max(8192, (total * 5 // 4 + 8 * 1024 * 1024 + 1023) // 1024)
            subprocess.run([args.mke2fs, '-t', 'ext2', '-b', '1024', '-F', '-q', '-d', str(tree), str(image), str(blocks)],
                           check=True, capture_output=True)
            evidence['actual_readback'] = verify_image(image, args.machine, debugfs_path())
            subprocess.run([debugfs_path(), '-w', '-R', f'rm /{abi}/platformsdk/{SANITIZER}', str(image)],
                           check=True, capture_output=True)
            try:
                verify_image(image, args.machine, debugfs_path())
            except ValueError as error:
                if 'missing DSP security/math runtime' not in str(error):
                    raise
                evidence['missing_security_runtime_rejected'] = str(error)
            else:
                raise ValueError('missing security runtime in real ext2 image incorrectly accepted')
        evidence['status'] = 'pass'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        evidence['failures'].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
