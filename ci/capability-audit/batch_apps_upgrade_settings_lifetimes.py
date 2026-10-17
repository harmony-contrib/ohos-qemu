#!/usr/bin/env python3
"""Upgrade only the complete, pinned previous Settings lifetime components.

Run before the normal source preparation. Original and current component states
are no-ops. Every component is checked before mutation; unknown, partial and
symlink states fail while preserving source. This never restores a checkout.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = ROOT / 'ci/capability-audit/fixtures/batch_apps/settings_lifetime_previous/provenance.json'
SETTINGS = ROOT / 'patches/common/applications/standard/settings'
COMPONENTS = ('accessibility_service_completion', 'share_picker')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_component(name):
    spec = importlib.util.spec_from_file_location('settings_lifetime_' + name, SETTINGS / name / 'verify_source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify(root, module, previous):
    try:
        return 'current' if module.validate(root) else 'original'
    except ValueError:
        current = module.FILES
        module.FILES = tuple((name, before, previous.get(module.PROJECT + '/' + name, after))
                             for name, before, after in current)
        try:
            module.validate(root, require_patched=True)
        finally:
            module.FILES = current
        return 'previous'


def upgrade(root):
    root = Path(root).resolve(strict=True)
    previous = json.loads(PREVIOUS.read_text())['sha256']
    modules = {name: load_component(name) for name in COMPONENTS}
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('component lock directory must not be a symlink')
    marker.mkdir(exist_ok=True)
    with ExitStack() as stack:
        # Use the same per-component locks as apply_exact_component.py. The root
        # agent still owns the source preparation lease and runs this serially.
        for name, module in modules.items():
            lock_name = sha((module.PROJECT + '/' + name).encode()) + '.lock'
            descriptor = os.open(marker / lock_name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            lock = stack.enter_context(os.fdopen(descriptor, 'a'))
            fcntl.flock(lock, fcntl.LOCK_EX)
        states = {name: classify(root, module, previous) for name, module in modules.items()}
        updates = {}
        with tempfile.TemporaryDirectory(prefix='batch-apps-lifetime-upgrade-') as temporary:
            staged = Path(temporary)
            for name, state in states.items():
                if state != 'previous':
                    continue
                module = modules[name]
                expected = {module.PROJECT + '/' + relative: after
                            for relative, _, after in module.FILES
                            if module.PROJECT + '/' + relative in previous}
                patches = sorted((SETTINGS / name).glob('0002-*.patch'))
                if len(patches) != 1:
                    raise ValueError('expected exactly one lifetime upgrade patch: ' + name)
                patch = patches[0]
                stat = subprocess.check_output(['git', 'apply', '--numstat', str(patch)], text=True)
                changed = {row.split('\t')[-1] for row in stat.splitlines()}
                if changed != set(expected):
                    raise ValueError('upgrade patch target differs from pinned previous files')
                for relative in expected:
                    target = staged / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(root / relative, target)
                subprocess.run(['git', '-C', str(staged), 'apply', '--check', str(patch)], check=True)
                subprocess.run(['git', '-C', str(staged), 'apply', str(patch)], check=True)
                for relative, after in expected.items():
                    data = (staged / relative).read_bytes()
                    if sha(data) != after:
                        raise ValueError('upgrade did not produce the exact final source: ' + relative)
                    updates[relative] = data
            # Recheck every whole component under both locks before replacing
            # any source file. No root/source/out work runs concurrently.
            if states != {name: classify(root, module, previous) for name, module in modules.items()}:
                raise ValueError('component source changed during upgrade preparation')
            for relative, data in updates.items():
                target = root / relative
                if target.is_symlink() or sha(target.read_bytes()) != previous[relative]:
                    raise ValueError('source changed before exact lifetime upgrade: ' + relative)
            for relative, data in updates.items():
                target = root / relative
                descriptor, temporary_name = tempfile.mkstemp(prefix='.' + target.name + '.', dir=target.parent)
                try:
                    with os.fdopen(descriptor, 'wb') as output:
                        output.write(data)
                    os.chmod(temporary_name, target.stat().st_mode & 0o777)
                    os.replace(temporary_name, target)
                finally:
                    if os.path.exists(temporary_name):
                        os.unlink(temporary_name)
            for name, state in states.items():
                if state == 'previous':
                    modules[name].validate(root, require_patched=True)
        return {'states_before': states, 'upgraded_files': sorted(updates), 'source_root': str(root)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(upgrade(args.source_root), indent=2))


if __name__ == '__main__':
    main()
