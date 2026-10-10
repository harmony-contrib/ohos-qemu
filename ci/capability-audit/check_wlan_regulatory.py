#!/usr/bin/env python3
"""Validate real pinned regulatory assets and an isolated idempotent patch stack."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/device/qemu/wlan_regulatory'


def module(name):
    spec = importlib.util.spec_from_file_location(name, COMPONENT / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    assets, source = module('verify_assets'), module('verify_source')
    verified = assets.verify(args.source_root)
    source.validate(args.source_root)
    with tempfile.TemporaryDirectory(prefix='qemu-regdb-stack-') as directory:
        staged = Path(directory)
        for relative, original, _ in source.FILES:
            if original is not None:
                target = staged / source.PROJECT / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(args.source_root / source.PROJECT / relative, target)
        for name in assets.ASSETS:
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.source_root / name, target)
        for arch in ('arm', 'arm64', 'x86_64'):
            relative = Path('device/qemu/common/virt_full/kernel/' + arch + '_virt_defconfig')
            shutil.copy2(args.source_root / relative, staged / relative)
        commands = []
        for index in (1, 2):
            argv = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)]
            log = args.output / ('apply-' + str(index) + '.log')
            with log.open('x') as stream:
                subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=True)
            commands.append(dict(argv=argv, log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
        source.validate(staged, require_patched=True)
        config = json.loads((staged / source.PROJECT / source.FILES[1][0]).read_text())
        assert config == {'jobs': [{'name': 'pre-init', 'cmds': [
            'write /sys/module/firmware_class/parameters/path /system/lib/firmware']}]}
        # Corrupt only our private copy. An invalid dependency must fail before
        # even an already-applied component is allowed to report success.
        database = staged / next(iter(assets.ASSETS))
        database.write_bytes(database.read_bytes() + b'corrupt')
        rejected = subprocess.run(argv, capture_output=True, text=True)
        (args.output / 'tamper-rejected.log').write_text(rejected.stdout + rejected.stderr)
        if rejected.returncode == 0 or 'unknown regulatory input' not in rejected.stderr:
            raise ValueError('tampered regulatory database was not rejected')
        source.validate(staged, require_patched=True)
    report = dict(status='pass', scope='signed_assets_and_exact_patch_NOT_guest_regulatory_acceptance',
                  assets_sha256=verified, commands=commands, tampered_dependency_rejected=True,
                  idempotent=True, kernel_signature_enforcement_configs=3,
                  first_artifact_behavior_gate_passed=False)
    (args.output / 'check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status='pass', scope=report['scope'])))


if __name__ == '__main__':
    main()
