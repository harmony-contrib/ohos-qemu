#!/usr/bin/env python3
"""Migrate only the complete known CallSetting15 legacy product vector.

Ordinary source preparation only. No SDK, compiler, test or guest acceptance.
The existing guarded_source_vector579 performs scratch, atomic replacement and
rollback for the exact two changed files. Full15 and readonly guards run before
and after it. Unknown/mixed states are never rewritten or hash-projected.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import importlib.util
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PATCHES = HERE.parents[4]
sys.path.insert(0, str(PATCHES / 'lib'))
from guarded_source_vector579 import apply, target

LEGACY = {
    'CallSetting/product/default/src/main/ets/CallSettingDialogAbility/GeneralCallSettingDialogAbility.ets':
        '84f9603f9151b47d3f8dc0ef18634c6146611130372a942daf28c9bbcaad6988',
    'CallSetting/product/default/src/main/ets/pages/SystemApnDialogPage.ets':
        'c77d5bd4b5faa84f2c3a3b98aa8211f6fc4d2aa1aba80dcc8e06d2cd8baa76fe',
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def source_guard():
    path = HERE / 'verify_source.py'
    spec = importlib.util.spec_from_file_location('_callsetting579_product_guard', path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    need(guard.PROJECT == 'applications/standard/call' and
         guard.REVISION == '8383e1930ffb28b512929b913eadf266a4e3a55a' and
         len(guard.FILES) == 15 and len({r[0] for r in guard.FILES}) == 15 and
         set(LEGACY) <= {r[0] for r in guard.FILES}, 'complete fixed CallSetting15 guard required')
    return guard


def whole_state(root, guard):
    actual_head = subprocess.check_output(['git', '-C', str(root / guard.PROJECT), 'rev-parse', 'HEAD'],
                                         text=True).strip()
    need(actual_head == guard.REVISION, 'actual fixed CallSetting project HEAD required')
    guard.prerequisites(root)
    observed = []
    for relative, _, _ in guard.FILES:
        path = target(root, str(Path(guard.PROJECT) / relative))
        observed.append(hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None)
    before = [r[1] for r in guard.FILES]
    final = [r[2] for r in guard.FILES]
    legacy = [LEGACY.get(r[0], r[2]) for r in guard.FILES]
    if observed == before:
        return 'pristine'
    if observed == final:
        return 'final'
    if observed == legacy:
        return 'legacy'
    raise ValueError('unknown/mixed CallSetting15 source preserved; no migration authorized')


def migrate(root):
    root = Path(root).resolve()
    guard = source_guard()
    marker = root / '.ohos-qemu-patches'
    need(not marker.is_symlink(), 'source marker directory must not be linked')
    marker.mkdir(exist_ok=True)
    # Same ordinary component lock as the existing exact-component applier.
    name = hashlib.sha256((guard.PROJECT + '/' + HERE.name).encode()).hexdigest() + '.lock'
    fd = os.open(marker / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = whole_state(root, guard)
        if state == 'legacy':
            pairs = {str(Path(guard.PROJECT) / relative): [LEGACY[relative], final]
                     for relative, _, final in guard.FILES if relative in LEGACY}
            need(len(pairs) == 2 and all(pair[0] != pair[1] for pair in pairs.values()),
                 'exact two typed-object source deltas required')
            value = dict(schema='guarded-product-source-vector579/v1',
                projects={guard.PROJECT: guard.REVISION}, files=pairs)
            apply(root, HERE, value, patch_name='legacy/0001-typed-object-literals.patch')
            need(whole_state(root, guard) == 'final', 'complete CallSetting15 postimage required')
            guard.validate(root, require_patched=True)
        else:
            # The normal original full-stack applier handles pristine -> final;
            # a complete new final is a source-only no-op, never a runtime pass.
            guard.validate(root, require_patched=(state == 'final'))
    print('CallSetting15 exact source migration: ' + state + '; runtime acceptance remains pending')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    migrate(args.source_root)
