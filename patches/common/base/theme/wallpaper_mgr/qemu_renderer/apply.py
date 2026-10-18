#!/usr/bin/env python3
"""Atomic exact pristine/E/F-parent/final-F migration; never discard unknown edits."""
import argparse
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
_guard_spec = importlib.util.spec_from_file_location('qemu_renderer_lifecycle_guard', Path(__file__).with_name('verify_source.py'))
guard = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(guard)


def snapshot(root, names):
    result = {}
    for name in names:
        path = root / guard.PROJECT / name
        for parent in (path, *path.parents):
            if parent == root.parent: break
            if parent.is_symlink(): raise ValueError('aliased component input: ' + name)
        if not path.exists():
            result[name] = None
            continue
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('single-link regular component input required: ' + name)
        result[name] = (path.read_bytes(), stat.S_IMODE(info.st_mode), info.st_dev, info.st_ino)
    return result


def same(root, original, names):
    if snapshot(root, names) != {name: original[name] for name in names}:
        raise ValueError('component bytes/mode/alias/inode changed after preflight; preserving external edits')


def atomic(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data); stream.flush(); os.fchmod(stream.fileno(), mode); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary): os.unlink(temporary)


def apply(root):
    root = root.absolute()
    if root.resolve() != root or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('canonical source root required')
    component = Path(__file__).resolve().parent
    manifest = guard.manifest()
    state = guard.state(root)
    if state == 'F': return
    names = list(manifest['states']['F'])
    original = snapshot(root, names)
    with tempfile.TemporaryDirectory(prefix='qemu-wallpaper-migrate-') as temporary:
        staged = Path(temporary).resolve()
        for name, before in original.items():
            if before is not None:
                target = staged / guard.PROJECT / name
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(before[0]); target.chmod(before[1])
        patches = ['0003-scope-legacy-extension-retry-to-stock-renderer.patch']
        if state in ('pristine', 'E'):
            patches.insert(0, '0002-recover-real-renderer-after-public-desktop-updates.patch')
        if state == 'pristine': patches.insert(0, '0001-real-wallpaper-settings-and-renderer.patch')
        for name in patches:
            patch = component / name
            if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest['patch_sha256'][name]:
                raise ValueError('reviewed component patch changed')
            subprocess.run(['git', '-C', str(staged), 'apply', '--check', str(patch)], check=True)
            subprocess.run(['git', '-C', str(staged), 'apply', '--whitespace=nowarn', str(patch)], check=True)
        guard.state(staged, require_patched=True, check_revision=False)
        final = {name: (staged / guard.PROJECT / name).read_bytes() for name in names}
        changed = [name for name in names if original[name] is None or original[name][0] != final[name]]
        written = {}
        same(root, original, names)
        if guard.state(root) != state: raise ValueError('component revision/state changed before writing')
        try:
            for name in changed:
                # Check ALL still-unwritten dependencies/targets before each write.
                # Never roll back an outside edit to a file this transaction did not write.
                same(root, original, [key for key in names if key not in written])
                for key, own in written.items():
                    same(root, {key: own}, [key])
                path = root / guard.PROJECT / name
                mode = original[name][1] if original[name] is not None else 0o644
                atomic(path, final[name], mode)
                written[name] = snapshot(root, [name])[name]
            same(root, original, [key for key in names if key not in written])
            for key, own in written.items(): same(root, {key: own}, [key])
            guard.state(root, require_patched=True)
        except BaseException as error:
            failures = []
            for name, own in reversed(list(written.items())):
                try:
                    same(root, {name: own}, [name])
                    target = root / guard.PROJECT / name
                    if original[name] is None: target.unlink()
                    else: atomic(target, original[name][0], original[name][1])
                except BaseException as rollback_error:
                    failures.append(name + ': ' + str(rollback_error))
            if failures:
                raise RuntimeError('migration failed; outside edits preserved during rollback: ' + repr(failures)) from error
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.absolute()
    if root.resolve() != root or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('canonical source root required')
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink(): raise ValueError('aliased component lock directory')
    marker.mkdir(exist_ok=True)
    descriptor = os.open(marker / 'qemu-wallpaper-renderer-lifecycle.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        apply(root)
    print('verified complete exact QEMU renderer lifecycle component; no runtime claim')
    return 0


if __name__ == '__main__': raise SystemExit(main())
