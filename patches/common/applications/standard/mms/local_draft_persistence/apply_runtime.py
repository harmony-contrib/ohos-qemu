#!/usr/bin/env python3
"""Upgrade the exact installed C45 draft component in scratch, then publish final bytes."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

import verify_source as baseline
from apply_exact_component import prepare_stack

COMPONENT = Path(__file__).resolve().parent
LEGACY_SHA256 = '6fa3e6a587228290cd24b7e1f7071a6969837a2435d409da6552bd0c60728982'


def replace(path, data, mode):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.mms-draft-exact-', delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def run(source):
    source = Path(source).resolve()
    if baseline.state(source) == 'final':
        return
    marker = source / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('component lock directory must not be a symlink')
    marker.mkdir(exist_ok=True)
    name = hashlib.sha256((baseline.PROJECT + '/' + COMPONENT.name).encode()).hexdigest() + '.lock'
    descriptor = os.open(marker / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock, tempfile.TemporaryDirectory(prefix='mms-local-draft-exact-') as temporary:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = baseline.state(source)
        if current == 'final':
            return
        temporary = Path(temporary)
        staged = temporary / 'ancestor'
        snapshots = {}
        modes = {}
        for relative, original, repaired in baseline.FILES:
            path = source / baseline.PROJECT / relative
            snapshots[relative] = path.read_bytes()
            modes[relative] = stat.S_IMODE(path.stat().st_mode)
            target = staged / baseline.PROJECT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if baseline.state(staged) != current:
            raise ValueError('MMS draft snapshot changed')
        if current == 'installed_c45':
            legacy = COMPONENT / 'legacy-installed-c45.patch'
            if legacy.is_symlink():
                raise ValueError('installed C45 predecessor patch must be regular')
            data = legacy.read_bytes()
            if hashlib.sha256(data).hexdigest() != LEGACY_SHA256:
                raise ValueError('installed C45 predecessor patch changed')
            reverse = temporary / 'legacy-installed-c45.patch'
            reverse.write_bytes(data)
            subprocess.run(['git', '-C', str(staged), 'apply', '-R', '--check', str(reverse)], check=True)
            subprocess.run(['git', '-C', str(staged), 'apply', '-R', str(reverse)], check=True)
        if baseline.state(staged) != 'original':
            raise ValueError('MMS draft scratch did not recover the exact original vector')
        # Reuse the existing allowed-target, whole-vector and patch-stack checks.
        prepared = temporary / 'prepared'
        prepared.mkdir()
        prepare_stack(staged, COMPONENT, baseline, prepared)
        final = prepared / 'source'
        baseline.validate(final, require_patched=True)
        if baseline.state(source) != current or any(
                (source / baseline.PROJECT / relative).read_bytes() != data or
                stat.S_IMODE((source / baseline.PROJECT / relative).stat().st_mode) != modes[relative]
                for relative, data in snapshots.items()):
            raise ValueError('MMS draft source changed during scratch preparation')
        written = []
        try:
            for relative, data in snapshots.items():
                path = source / baseline.PROJECT / relative
                after = (final / baseline.PROJECT / relative).read_bytes()
                if path.is_symlink() or path.read_bytes() != data or stat.S_IMODE(path.stat().st_mode) != modes[relative]:
                    raise ValueError('MMS draft source changed before replacement')
                if after != data:
                    replace(path, after, modes[relative])
                    written.append(relative)
            baseline.validate(source, require_patched=True)
        except BaseException:
            # Roll back only files still owned by this exact publication.
            for relative in reversed(written):
                path = source / baseline.PROJECT / relative
                after = (final / baseline.PROJECT / relative).read_bytes()
                if (not path.is_symlink() and path.read_bytes() == after and
                        stat.S_IMODE(path.stat().st_mode) == modes[relative]):
                    replace(path, snapshots[relative], modes[relative])
            raise
    print('verified exact MMS local draft compiler fixes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.source_root)
