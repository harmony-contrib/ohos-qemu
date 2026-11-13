#!/usr/bin/env python3
"""Replace verified legacy source inputs with links to generated component inputs.

Original files are retained in an ignored backup. No build, checkout, commit or
source-tree patch application is performed here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--verification', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    generated = root / '.qemu/component-inputs'
    index = json.loads(args.index.read_text())
    verification = json.loads(args.verification.read_text())
    if not verification.get('complete') or verification['index_sha256'] != digest(args.index):
        raise ValueError('Complete remote component verification for this exact index is required')
    if subprocess.check_output(['git', '-C', str(root), 'branch', '--show-current'], text=True).strip() != 'codex/ohos7-integrated-development':
        raise ValueError('Use the existing integrated development branch')
    for entry in index['files']:
        path = Path(entry['path'])
        if path.is_absolute() or '..' in path.parts or path.parts[0] not in ('patches', 'scripts'):
            raise ValueError('Unexpected migration path')
        original, replacement = root / path, generated / path
        if original.is_symlink() or replacement.is_symlink():
            raise ValueError('Expected original and materialized regular files: ' + str(path))
        if digest(original) != entry['sha256'] or digest(replacement) != entry['sha256']:
            raise ValueError('Source input differs; preserving it: ' + str(path))
        mode = int(entry['mode'], 8) & 0o777
        if (original.stat().st_mode & 0o777) != mode or (replacement.stat().st_mode & 0o777) != mode:
            raise ValueError('Source input mode differs: ' + str(path))
    tracked = set(subprocess.check_output(['git', '-C', str(root), 'ls-files', 'patches'], text=True).splitlines())
    indexed = {entry['path'] for entry in index['files'] if entry['path'].startswith('patches/')}
    if tracked != indexed:
        raise ValueError('Ownership index does not cover the complete tracked patch tree')
    backup_root = root / '.tmp/organization-migration'
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='retired-source-inputs-', dir=backup_root))
    # Preserve the complete original patch directory, including ignored files.
    (root / 'patches').rename(backup / 'patches')
    (root / 'patches').symlink_to('.qemu/component-inputs/patches')
    for entry in index['files']:
        if not entry['path'].startswith('scripts/'):
            continue
        original = root / entry['path']
        saved = backup / entry['path']
        saved.parent.mkdir(parents=True, exist_ok=True)
        original.rename(saved)
        original.symlink_to(os.path.relpath(generated / entry['path'], original.parent))
    receipt = dict(index_sha256=digest(args.index), original_backup=str(backup),
                   original_files_preserved=True, generated_input_root=str(generated),
                   build_validated=False, runtime_validated=False)
    (backup / 'cutover.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
