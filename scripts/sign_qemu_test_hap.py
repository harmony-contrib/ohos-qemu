#!/usr/bin/env python3
"""Adapt ordinary QEMU E2E signing to OHOS 7's actual code-sign verifier.

This is deliberately not a general signing service. Only the native-bindings
test bundle and normal development privileges are accepted. It uses the
fixed-release public test credentials, never production keys or privileged
ACLs. The source test project's supported HAP_SIGN override selects it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
IMAGE = 'ohos-qemu-m144-build-env:7.0-release'
SOURCE_VOLUME = 'ohos-qemu-7_0-release-source'
BUNDLE = 'com.richerfu.ohos_example'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def signing_command(args):
    if args.unsigned.is_symlink():
        raise ValueError('unsigned input must not be an alias')
    unsigned = args.unsigned.resolve(strict=True)
    output = args.output.absolute()
    if (unsigned.is_symlink() or not unsigned.is_file() or output.is_symlink() or
            output.resolve() == unsigned or not output.parent.is_dir()):
        raise ValueError('distinct regular unsigned input and existing output directory required')
    if (args.bundle_name != BUNDLE or re.fullmatch(r'[0-9a-fA-F]{64}', args.device_id) is None or
            args.compatible_version != '17' or not args.force):
        raise ValueError('only the unchanged ordinary bindings test contract and concrete guest UDID are supported')
    return ['docker', 'run', '--rm', '--platform', 'linux/amd64',
        '--mount', 'type=volume,src=' + os.environ.get('QEMU_TEST_SOURCE_VOLUME', SOURCE_VOLUME) + ',dst=/ohos,readonly',
        '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
        '--mount', 'type=bind,src=' + str(unsigned) + ',dst=/unsigned.hap,readonly',
        '--mount', 'type=bind,src=' + str(output.parent.resolve()) + ',dst=/signed',
        os.environ.get('QEMU_TEST_DOCKER_IMAGE', IMAGE),
        'python3', '/work/ci/capability-audit/sign_web_probe.py',
        '--signer-dist', '/ohos/developtools/hapsigner/dist',
        '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
        '--unsigned', '/unsigned.hap', '--output', '/signed/' + output.name,
        '--bundle-name', BUNDLE, '--udid', args.device_id, '--sign-code', '1']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('sign',))
    parser.add_argument('unsigned', type=Path)
    parser.add_argument('--bundle-name', required=True)
    parser.add_argument('--device-id', required=True)
    parser.add_argument('--compatible-version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    command = signing_command(args)
    unsigned_sha = sha(args.unsigned)
    result = subprocess.run(command, check=False)
    if result.returncode:
        return result.returncode
    if sha(args.unsigned) != unsigned_sha:
        raise ValueError('unsigned input changed during signing')
    evidence = {'schema_version': 1, 'status': 'pass',
        'scope': 'ordinary_dev_HAP_code_sign_and_verify_NOT_device_execution',
        'command': command, 'unsigned_sha256': unsigned_sha,
        'signed_sha256': sha(args.output), 'bundle': BUNDLE, 'guest_udid': args.device_id,
        'normal_app': True, 'privileged_ACLs_added': False,
        'first_artifact_behavior_gate_passed': False}
    args.output.with_suffix('.sign-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
