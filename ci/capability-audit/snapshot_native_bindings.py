#!/usr/bin/env python3
"""Snapshot actual bindings sources, including user edits, into an owned test tree.

Do not let per-module List rewrites, signer caches or ABI builds mutate the
user's checkout. Old binaries/build caches are not copied as fresh test input.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

EXCLUDED_DIRECTORIES = {'.git', 'target', 'node_modules', 'oh_modules', 'build',
                        '.hvigor', '.tools', 'dist', '__pycache__'}
REQUIRED = ('Cargo.toml', 'Cargo.lock', 'pnpm-lock.yaml', 'examples-ui/package.json',
            'examples-ui/scripts/run-ohostest.sh',
            'examples-ui/scripts/verify-ohostest-results.py',
            'examples-ui/entry/src/ohosTest/ets/test/List.test.ets')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def files(source):
    result = {}
    for directory, children, names in os.walk(source, followlinks=False):
        parent = Path(directory)
        children[:] = sorted(child for child in children if child not in EXCLUDED_DIRECTORIES and
            (parent / child).relative_to(source).as_posix() != 'examples-ui/entry/libs')
        for name in children:
            if (parent / name).is_symlink():
                raise ValueError('source directory symlink requires explicit source resolution: ' + str(parent / name))
        for name in sorted(names):
            if name in ('.List.full.bak', '.DS_Store') or name.endswith(('.pyc', '.pyo')):
                continue
            path = parent / name
            if path.is_symlink() or not path.is_file():
                raise ValueError('source snapshot only accepts regular source inputs: ' + str(path))
            result[path.relative_to(source).as_posix()] = sha(path)
    return result


def snapshot(source, output):
    source, output = source.resolve(strict=True), output.absolute()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('owned snapshot must not overlap the original workspace')
    for name in REQUIRED:
        if not (source / name).is_file() or (source / name).is_symlink():
            raise ValueError('complete actual test workspace input missing: ' + name)
    before = files(source)
    output.mkdir(parents=True, exist_ok=False)
    copied = output / 'source'
    copied.mkdir()
    for name, expected in before.items():
        original, destination = source / name, copied / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        if sha(destination) != expected:
            raise ValueError('source changed during copy: ' + name)
    if files(source) != before:
        raise ValueError('original test sources changed during snapshot; do not use this attempt')
    revision = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, check=False)
    evidence = {'schema_version': 1, 'status': 'pass',
        'scope': 'source_snapshot_only_NOT_compilation_or_E2E', 'source': str(source),
        'snapshot': str(copied), 'source_revision': revision.stdout.strip() if revision.returncode == 0 else None,
        'includes_uncommitted_sources': True, 'file_count': len(before), 'files_sha256': before,
        'tree_sha256': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        'excluded_generated_directories': sorted(EXCLUDED_DIRECTORIES),
        'old_ABI_libraries_copied': False, 'first_artifact_behavior_gate_passed': False}
    (output / 'source-snapshot.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = snapshot(args.source, args.output)
    print(json.dumps({key: result[key] for key in ('status', 'scope', 'snapshot', 'file_count', 'tree_sha256')}))
