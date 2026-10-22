#!/usr/bin/env python3
"""Finite M01 normal-source transaction; no compiler/SDK/runtime operation."""
from pathlib import Path
import argparse
import fcntl
import json
import os
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_source as checked
sys.path.insert(0, str(HERE.parents[4] / 'lib'))
from guarded_source_vector579 import identity, matches, replace


def publish(root, desired, *, edits, index, projects, component_before, expected_state, expected_assets, assets, wanted_source):
    """Stage every delta first, publish only unchanged owned preimages, rollback.

    Byte-identical paths retain inode/mtime. Unknown concurrent content is
    preserved and reported; rollback never overwrites another writer's bytes.
    """
    checked.need(wanted_source in ('before', 'final') and len(desired) == 474,
                 'fixed complete474 source/asset transaction required')
    originals = {}
    for name in desired:
        path = checked.source(root, name)
        originals[name] = {'bytes': checked.file_raw(path), 'identity': identity(path)} if path.exists() else None
    changed = [name for name, raw in desired.items() if originals[name] is None or originals[name]['bytes'] != raw]
    installed, directories = {}, []
    with tempfile.TemporaryDirectory(prefix='m01-source579-stage-') as temporary:
        staged = Path(temporary)
        for name in changed:
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(desired[name]); stream.flush(); os.fsync(stream.fileno())
            checked.need(checked.file_raw(path) == desired[name], 'complete staged M01 bytes changed')
        checked.project_heads(root, projects)
        checked.need(checked.component_identity(index) == component_before, 'component changed before transaction')
        checked.need(checked.complete_state(checked.vectors(root, edits), edits) == expected_state, 'source vector changed before publish')
        checked.need(checked.asset_epoch(root, index, assets) == expected_assets, 'complete443 asset vector changed before publish')
        checked.need(all(matches(checked.source(root, name), original) for name, original in originals.items()), 'actual source/input changed before commit')
        try:
            for name in changed:
                path = checked.source(root, name); original = originals[name]
                checked.need(matches(path, original), 'actual source inode/bytes changed before replacement: ' + name)
                missing = []; parent = path.parent
                while not parent.exists():
                    missing.append(parent); parent = parent.parent
                for directory in reversed(missing):
                    directory.mkdir(); s = directory.lstat(); directories.append((directory, (s.st_dev, s.st_ino)))
                replace(path, checked.file_raw(staged / name), original['identity'] if original else None, installed, name)
            checked.need(all(checked.file_raw(checked.source(root, n)) == raw for n, raw in desired.items()), 'complete published M01 byte vector differs')
            checked.project_heads(root, projects)
            checked.need(checked.component_identity(index) == component_before, 'component changed during transaction')
            checked.need(checked.complete_state(checked.vectors(root, edits), edits) == wanted_source and
                         checked.assets_state(root, assets) == 'final', 'complete committed source31/current443 vector differs')
        except BaseException as error:
            rollback_errors = []
            interrupted = error if not isinstance(error, Exception) else None
            for name in reversed(changed):
                original = originals[name]
                try:
                    path = checked.source(root, name)
                    if matches(path, original):
                        continue
                    checked.need(name in installed and path.exists() and identity(path) == installed[name] and
                                 checked.file_raw(path) == desired[name], 'unknown concurrent source preserved: ' + name)
                    if original is None:
                        path.unlink()
                    else:
                        replace(path, original['bytes'], original['identity'], {}, name)
                except BaseException as rollback_error:
                    rollback_errors.append(name + ': ' + repr(rollback_error))
                    if not isinstance(rollback_error, Exception) and interrupted is None:
                        interrupted = rollback_error
            for directory, inode in reversed(directories):
                try:
                    st = directory.lstat()
                    checked.need((st.st_dev, st.st_ino) == inode and directory.is_dir() and not directory.is_symlink(), 'created directory identity changed')
                    directory.rmdir()
                except BaseException as rollback_error:
                    rollback_errors.append(str(directory) + ': ' + str(rollback_error))
                    if not isinstance(rollback_error, Exception) and interrupted is None:
                        interrupted = rollback_error
            if rollback_errors:
                if interrupted is not None:
                    print('M01 rollback uncertain while preserving original interruption: ' + repr(rollback_errors), file=sys.stderr)
                    raise interrupted
                raise RuntimeError('M01 rollback incomplete; unknown bytes preserved: ' + repr(rollback_errors)) from error
            try:
                restored = all(matches(checked.source(root, n), original) if original is None else
                               checked.file_raw(checked.source(root, n)) == original['bytes'] and
                               identity(checked.source(root, n))[2:] == original['identity'][2:]
                               for n, original in originals.items())
            except BaseException as verification_error:
                if not isinstance(verification_error, Exception) and interrupted is None:
                    interrupted = verification_error
                restored = False
            if not restored:
                if interrupted is not None:
                    print('M01 restoration unconfirmed; original interruption retained', file=sys.stderr)
                    raise interrupted
                raise RuntimeError('full source preimage restoration failed') from error
            raise
    return changed


def prepare(root, *, rewind=False, require_final=False):
    root = checked.root_path(root)
    if require_final:
        checked.require_final(root)
        return dict(state='complete_final_verified', runtime_pass=False)
    edits, index, projects = checked.metadata()
    marker = root / '.ohos-qemu-patches'
    checked.need(not marker.is_symlink() and (not marker.exists() or marker.is_dir()), 'actual source lock directory')
    marker.mkdir(exist_ok=True)
    fd = os.open(marker / 'm01-cpu-provider-source579.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if rewind:
            plan = checked.rewind_plan(root)
            if plan is None:
                return dict(state='no_M01_source_or_asset_migration_needed_defer_to_original_hooks',
                            M01_source_verified=False, runtime_pass=False)
            component_before = checked.component_identity(index)
            changed = publish(root, plan['desired'], edits=edits, index=index, projects=projects,
                              component_before=component_before, expected_state=plan['source_state'],
                              expected_assets=plan['asset_state'], assets=plan['assets'], wanted_source='before')
            checked.need(checked.complete_state(checked.vectors(root, edits), edits) == 'before', 'complete31 prefix rewind required')
            return dict(state='complete31_before_current443_prepared', source_endpoint=plan['source_state'],
                        asset_endpoint=plan['asset_state'], previous_asset_migrated=plan['asset_state'] in ('previous', 'previous_c23', 'previous_c24', 'previous_c28', 'previous_c29'), changed=changed, runtime_pass=False)
        component_before = checked.component_identity(index)
        checked.project_heads(root, projects)
        state = checked.complete_state(checked.vectors(root, edits), edits)
        checked.need(state not in ('previous_final', 'previous_c22_final'), 'previous complete31 must first rewind through the original prefix')
        assets = checked.payloads(index)
        asset_state = checked.asset_epoch(root, index, assets)
        checked.need(asset_state not in ('previous', 'previous_c23', 'previous_c24', 'previous_c28', 'previous_c29'), 'previous complete443 must first migrate through the original prefix')
        if state == 'final':
            checked.need(asset_state == 'current', 'complete final requires every current fixed product input')
            checked.require_final(root)
            return dict(state='complete_final_unchanged', changed=[], runtime_pass=False)
        checked.need(state == 'before' and asset_state in ('current', 'absent'), 'fixed late source-before/current-or-absent443 required')
        desired = dict(assets)
        for row in edits['files']:
            text = checked.file_raw(checked.source(root, row['path'])).decode()
            for cut in row['cuts']:
                checked.need(text.count(cut['before']) == 1, 'unique actual reviewed source cut')
                text = text.replace(cut['before'], cut['after'], 1)
            raw = text.encode()
            checked.need(checked.sha(raw) == row['after_sha256'] and checked.inverse(raw, row) == checked.file_raw(checked.source(root, row['path'])), 'whole source successor/inverse differs')
            checked.need(row['path'] not in desired, 'new source/edit destination overlap')
            desired[row['path']] = raw
        changed = publish(root, desired, edits=edits, index=index, projects=projects,
                          component_before=component_before, expected_state='before',
                          expected_assets=asset_state, assets=assets, wanted_source='final')
        checked.require_final(root)
        return dict(state='complete_final_prepared', changed=changed, runtime_pass=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--rewind', action='store_true')
    mode.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    result = prepare(args.source_root, rewind=args.rewind, require_final=args.require_final)
    result.update(schema='media579-normal-source-preparation-result/v1', first_artifact_behavior_gate_passed=False)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
