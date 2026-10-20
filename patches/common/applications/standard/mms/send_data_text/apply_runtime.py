#!/usr/bin/env python3
"""Upgrade only exact original, legacy-text, or final MMS source states."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import tempfile
import subprocess
import stat

import verify_source

COMPONENT = Path(__file__).resolve().parent
LEGACY_PATCH_SHA256 = 'ce013527985c29208f0d60720572de4f877f3ae6ba92cd362cbe868f6ffd8106'


def run(source):
    source = Path(source)
    state = verify_source.state(source)
    source = source.resolve()
    if state == 'final':
        return
    lock_dir = source / '.ohos-qemu-patches'
    if lock_dir.is_symlink():
        raise ValueError('MMS lock directory must be owned')
    lock_dir.mkdir(exist_ok=True)
    descriptor = os.open(lock_dir / 'mms-send-data.exact.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock, tempfile.TemporaryDirectory(prefix='mms-send-data-exact-') as directory:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = verify_source.state(source)
        if state == 'final':
            return
        staged = Path(directory)
        names = [entry[0] for entry in verify_source.FILES]
        snapshots = {}
        for name in names:
            original = source / verify_source.PROJECT / name
            target = staged / verify_source.PROJECT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            snapshots[name] = original.read_bytes() if original.exists() else None
            if snapshots[name] is not None:
                target.write_bytes(snapshots[name])
        # Convert the exact previous complete text component in scratch only.
        # Unknown/partial states were refused before any source mutation.
        legacy = COMPONENT / 'legacy-text-receiver.patch'
        if hashlib.sha256(legacy.read_bytes()).hexdigest() != LEGACY_PATCH_SHA256:
            raise ValueError('legacy MMS reverse patch changed')
        if state == 'legacy_text':
            subprocess.run(['git', 'apply', '-R', '--check', str(legacy)], cwd=staged, check=True)
            subprocess.run(['git', 'apply', '-R', str(legacy)], cwd=staged, check=True)
        if verify_source.state(staged) != 'original':
            raise ValueError('MMS scratch original state differs')
        for patch in sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch')):
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=staged, check=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=staged, check=True)
        verify_source.validate(staged, require_patched=True)
        if verify_source.state(source) != state or any(
                ((source / verify_source.PROJECT / name).read_bytes()
                 if (source / verify_source.PROJECT / name).exists() else None) != value for name, value in snapshots.items()):
            raise ValueError('MMS source changed during exact preflight')
        for name in names:
            target = source / verify_source.PROJECT / name
            final = (staged / verify_source.PROJECT / name).read_bytes()
            if snapshots[name] == final:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.mms-exact-', delete=False) as output:
                temporary = Path(output.name)
                try:
                    output.write(final)
                    output.flush()
                    os.fchmod(output.fileno(), mode)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
        verify_source.validate(source, require_patched=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.source_root)
    print('verified exact MMS sharing component')


if __name__ == '__main__':
    main()
