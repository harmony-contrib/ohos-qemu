#!/usr/bin/env python3
"""Install only exact fixed sources and exact new files, with rollback on failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

COMPONENT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('unsafe source manifest path')
    target = root / relative
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('source symlink refused: ' + str(relative))
        cursor = cursor.parent
    return target


def load_manifest():
    manifest = json.loads((COMPONENT / 'manifest.json').read_text())
    patches = list(COMPONENT.glob('*.patch'))
    if len(patches) != 1 or sha(patches[0].read_bytes()) != manifest['patch_sha256']:
        raise ValueError('unknown component patch bytes')
    for row in manifest['files'].values():
        if sha(safe_path(COMPONENT, row['component_file']).read_bytes()) != row['sha256']:
            raise ValueError('unknown component file bytes')
    return manifest, patches[0]


def validate(root, manifest, require_patched=False, revision=True):
    root = Path(root).resolve()
    project = safe_path(root, manifest['project'])
    if revision and (project / '.git').exists():
        actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != manifest['revision']:
            raise ValueError('fixed upstream revision required')
    for relative, expected in manifest.get('dependencies', {}).items():
        if sha(safe_path(root, relative).read_bytes()) != expected:
            raise ValueError('fixed actual ABI dependency required')
    if revision:
        for relative, expected in manifest.get('projects', {}).items():
            directory = safe_path(root, relative)
            if (directory / '.git').exists():
                actual = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
                if actual != expected:
                    raise ValueError('fixed source project revision required: ' + relative)
    states = set()
    for relative, row in manifest['originals'].items():
        value = sha(safe_path(root, relative).read_bytes())
        if value == row['before']:
            states.add(0)
        elif value == row['after']:
            states.add(1)
        else:
            raise ValueError('unknown source bytes; preserving edits: ' + relative)
    for relative, row in manifest['files'].items():
        target = safe_path(root, relative)
        if not target.exists():
            states.add(0)
        elif target.is_file() and sha(target.read_bytes()) == row['sha256']:
            states.add(1)
        else:
            raise ValueError('unknown existing overlay; preserving edits: ' + relative)
    if len(states) != 1:
        raise ValueError('mixed patch state; preserving edits')
    repaired = states == {1}
    if require_patched and not repaired:
        raise ValueError('complete patch is required')
    return repaired


def atomic_write(target, data, mode):
    temporary = target.with_name('.' + target.name + '.qemu-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply(root):
    root = Path(root).resolve()
    manifest, patch = load_manifest()
    if validate(root, manifest):
        return {'status': 'already_applied', 'revision': manifest['revision']}
    original = {}
    for relative in [*manifest['originals'], *manifest['files']]:
        target = safe_path(root, relative)
        original[relative] = (target.read_bytes(), target.stat().st_mode & 0o777) if target.exists() else (None, 0o644)
    with tempfile.TemporaryDirectory(prefix='batch-system-exact-patch-') as temporary:
        candidate = Path(temporary)
        for relative in manifest['originals']:
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original[relative][0])
        for relative in manifest.get('dependencies', {}):
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(root, relative), target)
        subprocess.run(['git', '-C', str(candidate), 'apply', str(patch)], check=True)
        for relative, row in manifest['files'].items():
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(COMPONENT / row['component_file'], target)
        validate(candidate, manifest, require_patched=True, revision=False)
        written = []
        try:
            for relative, (_, mode) in original.items():
                target = safe_path(root, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                written.append(relative)
                atomic_write(target, (candidate / relative).read_bytes(), mode)
            validate(root, manifest, require_patched=True)
        except BaseException:
            for relative in reversed(written):
                target = root / relative
                data, mode = original[relative]
                if data is None:
                    target.unlink(missing_ok=True)
                else:
                    atomic_write(target, data, mode)
            raise
    return {'status': 'applied', 'revision': manifest['revision'],
            'patch_sha256': manifest['patch_sha256'], 'files': list(original)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.source_root)))
