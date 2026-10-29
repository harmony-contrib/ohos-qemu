#!/usr/bin/env python3
"""Stage and verify all4 fixed sources, then atomic per-file commit or rollback."""
import argparse
import hashlib
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from verify_source import HERE, heads, manifest, state, target, vector, vector_state


def digest(content):
    return hashlib.sha256(content).hexdigest()


def identity(path):
    observed = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(observed.st_mode):
        raise ValueError('Regular owned source changed: ' + str(path))
    return (observed.st_dev, observed.st_ino, stat.S_IMODE(observed.st_mode), observed.st_uid, observed.st_gid)


def replace(path, content, original, installed, name):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.avpanel579-', dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            observed = os.fstat(output.fileno())
            if (observed.st_uid, observed.st_gid) != original['identity'][3:]:
                os.fchown(output.fileno(), original['identity'][3], original['identity'][4])
            os.fchmod(output.fileno(), original['identity'][2])
            os.fsync(output.fileno())
            # Record ownership before replace so an interrupt immediately after
            # replace still leaves enough identity for a guarded rollback.
            installed[name] = identity(temporary)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def rollback(root, value, originals, installed):
    failures = []
    for name in reversed(list(value['files'])):
        try:
            path = target(root, name)
            current = path.read_bytes()
            original = originals[name]
            if current == original['bytes'] and identity(path)[2:] == original['identity'][2:]:
                continue
            if name not in installed or identity(path) != installed[name] or digest(current) != value['files'][name][1]:
                raise ValueError('Concurrent/unknown bytes or inode preserved, not overwritten: ' + name)
            replace(path, original['bytes'], original, {}, name)
        except BaseException as error:
            failures.append(name + ': ' + str(error))
    try:
        if vector_state(root, value) != 'before':
            raise ValueError('Rollback did not restore the complete actual before vector')
        for name, original in originals.items():
            if identity(target(root, name))[2:] != original['identity'][2:]:
                raise ValueError('Rollback source mode/owner differs: ' + name)
    except BaseException as error:
        failures.append(str(error))
    if failures:
        raise RuntimeError('Source rollback incomplete; preserved unexpected changes: ' + '; '.join(failures))


def apply_vector(root, value, *, reverse=False, patch_name='0001-connect-actual-panels-and-guard-session-events.patch'):
    if vector_state(root, value) == 'final':
        return
    originals = {}
    for name in value['files']:
        path = target(root, name)
        observed = identity(path)
        content = path.read_bytes()
        if identity(path) != observed or digest(content) != value['files'][name][0]:
            raise ValueError('Actual source changed during snapshot: ' + name)
        originals[name] = {'bytes': content, 'identity': observed}
    with tempfile.TemporaryDirectory(prefix='avpanel579-source-') as directory:
        scratch = Path(directory)
        for name, original in originals.items():
            path = scratch / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original['bytes'])
        # Scratch is only an exact finite byte copy, never a forged Git tree.
        # The AVSession HEAD are checked against the actual live repositories.
        heads(root, value)
        if vector(scratch, value) != 'before':
            raise ValueError('Complete scratch preimage required')
        subprocess.run(['patch', '--binary', '--batch', '--reverse' if reverse else '--forward', '--fuzz=0', '-p1', '-i',
            str(HERE / patch_name)], cwd=scratch, check=True)
        if vector(scratch, value) != 'final':
            raise ValueError('Complete final scratch vector required')
        if {p.relative_to(scratch).as_posix() for p in scratch.rglob('*') if p.is_file()} != set(value['files']):
            raise ValueError('Unexpected scratch file/reject/original output')
        finals = {name: target(scratch, name).read_bytes() for name in value['files']}
        if vector_state(root, value) != 'before':
            raise ValueError('Actual source vector changed before commit')
        for name, original in originals.items():
            path = target(root, name)
            if identity(path) != original['identity'] or path.read_bytes() != original['bytes']:
                raise ValueError('Source inode/metadata changed before commit: ' + name)
        installed = {}
        try:
            for name, original in originals.items():
                path = target(root, name)
                if identity(path) != original['identity'] or path.read_bytes() != original['bytes']:
                    raise ValueError('Source changed during finite commit: ' + name)
                replace(path, finals[name], original, installed, name)
            if vector_state(root, value) != 'final':
                raise ValueError('Complete final live vector required')
            for name, original in originals.items():
                if identity(target(root, name))[2:] != original['identity'][2:]:
                    raise ValueError('Final source mode/owner differs: ' + name)
        except BaseException:
            rollback(root, value, originals, installed)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--rewind', action='store_true')
    mode.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    value = manifest()
    previous = dict(value, files={name: [pair[0], value['previous_panel_final'][name]]
                                 for name, pair in value['files'].items()})
    previous_owned = dict(value, files={name: [pair[0], value['previous_owned_final'][name]]
                                       for name, pair in value['files'].items()})
    epochs = {'previous': (previous, '0000-legacy-panel-lifecycle.patch'),
              'previous_owned': (previous_owned, '0003-previous-owned-panel-lifecycle.patch')}
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('Source lock directory is linked')
    marker.mkdir(exist_ok=True)
    fd = os.open(marker / (digest(str(HERE).encode()) + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = state(root, value)
        if args.require_final:
            if current != 'final':
                raise ValueError('New complete final AV panel source required; verify never migrates')
        elif args.rewind:
            if current != 'before':
                active, patch = epochs.get(current, (value, '0001-connect-actual-panels-and-guard-session-events.patch'))
                reverse = dict(active, files={n: list(reversed(pair)) for n, pair in active['files'].items()})
                apply_vector(root, reverse, reverse=True, patch_name=patch)
            if state(root, value) != 'before':
                raise ValueError('Complete original AV panel prefix not restored')
        elif current != 'final':
            upgrading = current in epochs
            if upgrading:
                active, legacy_patch = epochs[current]
                reverse = dict(active, files={n: list(reversed(pair)) for n, pair in active['files'].items()})
                apply_vector(root, reverse, reverse=True, patch_name=legacy_patch)
            try:
                apply_vector(root, value)
                if state(root, value) != 'final':
                    raise ValueError('Complete new AV panel source vector required')
            except BaseException as error:
                if upgrading:
                    if state(root, value) != 'before':
                        raise RuntimeError('Upgrade rollback incomplete; unknown source preserved') from error
                    apply_vector(root, active, patch_name=legacy_patch)
                    if state(root, value) != current:
                        raise RuntimeError('Complete previous AV panel vector not restored') from error
                raise
    print('AV panel source transaction complete; build/runtime NOT accepted')


if __name__ == '__main__':
    main()
