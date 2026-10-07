#!/usr/bin/env python3
"""Apply a whole exact-state component once, including overlapping patch files."""
import argparse
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def apply_stack(root, patches):
    for patch in patches:
        subprocess.run(['git', '-C', str(root), 'apply', '--check', str(patch)], check=True)
        subprocess.run(['git', '-C', str(root), 'apply', '--whitespace=nowarn', str(patch)], check=True)


def prepare_stack(root, component, baseline, temporary):
    """Check all overlapping diffs in scratch before changing any source file."""
    staged = temporary / 'source'
    allowed = {str(Path(baseline.PROJECT) / entry[0]) for entry in baseline.FILES}
    for relative in allowed:
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if (root / relative).exists():
            shutil.copy2(root / relative, target)
    patches = []
    for original in sorted(component.glob('[0-9][0-9][0-9][0-9]-*.patch')):
        copied = temporary / original.name
        shutil.copy2(original, copied)
        statistics = subprocess.check_output(['git', 'apply', '--numstat', str(copied)], text=True)
        if not statistics.strip() or any(line.split('\t')[-1] not in allowed
                                         for line in statistics.splitlines()):
            raise ValueError('component patch changes a file outside its exact baseline')
        patches.append(copied)
    if not patches:
        raise ValueError('exact component has no numbered patch stack')
    if baseline.validate(staged):
        raise ValueError('source changed while preparing the original component snapshot')
    apply_stack(staged, patches)
    baseline.validate(staged, require_patched=True)
    return patches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component-dir', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    component = args.component_dir.resolve()
    spec = importlib.util.spec_from_file_location('exact_component_baseline', component / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    root = args.source_root.resolve()
    # Unknown/partial edits fail before any mutation. The final whole-file
    # hashes are stronger than reverse-checking earlier overlapping hunks.
    if not baseline.validate(root):
        marker_dir = root / '.ohos-qemu-patches'
        if marker_dir.is_symlink():
            raise ValueError('component lock directory must not be a symlink')
        marker_dir.mkdir(exist_ok=True)
        lock_name = hashlib.sha256((baseline.PROJECT + '/' + component.name).encode()).hexdigest() + '.lock'
        descriptor = os.open(marker_dir / lock_name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not baseline.validate(root):
                with tempfile.TemporaryDirectory(prefix='ohos-exact-component-') as scratch:
                    patches = prepare_stack(root, component, baseline, Path(scratch))
                    # Legacy per-patch marker files never authorize a skip.
                    if baseline.validate(root):
                        raise ValueError('source changed before the verified component application')
                    apply_stack(root, patches)
    baseline.validate(root, require_patched=True)
    print('verified complete exact component: ' + component.name)


if __name__ == '__main__':
    main()
