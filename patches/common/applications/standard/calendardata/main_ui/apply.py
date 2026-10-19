#!/usr/bin/env python3
"""Stage the complete predecessor before publishing the reminder viewer."""
import argparse
import fcntl
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

COMPONENT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('calendar_main_source', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def replace(target, data, mode):
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.calendar-main-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(name, mode)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def apply(root, publish=replace):
    root = Path(root).resolve()
    # Reject unfamiliar source bytes and every symlink before creating a lock.
    if baseline.validate(root):
        return
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('component lock directory must not be a symlink')
    marker.mkdir(exist_ok=True)
    descriptor = os.open(marker / 'calendar-main.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if baseline.validate(root):
            return
        rows = {row[0] for row in baseline.FILES}
        rows.update(row[0] for row in baseline.load('event_editor').FILES)
        rows.update(row[0] for row in baseline.load('editor_callback_dispatch').FILES)
        rows.add('AppScope/app.json5')
        with tempfile.TemporaryDirectory(prefix='calendar-main-stage-') as temporary:
            stage = Path(temporary)
            for relative in rows:
                source = root / baseline.PROJECT / relative
                if source.exists():
                    target = stage / baseline.PROJECT / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            state = baseline.source_state(stage)
            if state == 'final':
                raise ValueError('source changed during staging')
            patches = sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
            if state == 'prefix1':
                patches = [COMPONENT / '0002-bind-viewer-to-ability-local-storage.patch',
                           COMPONENT / '0003-integrate-calendar-browsing-and-explicit-user-crud.patch']
            elif state == 'prefix2':
                patches = [COMPONENT / '0003-integrate-calendar-browsing-and-explicit-user-crud.patch']
            for patch in patches:
                subprocess.run(['git', '-C', str(stage), 'apply', '--check', str(patch)], check=True)
                subprocess.run(['git', '-C', str(stage), 'apply', '--whitespace=nowarn', str(patch)], check=True)
            baseline.validate(stage, require_patched=True)
            if baseline.validate(root):
                raise ValueError('source changed before publication')
            originals = {}
            for relative, _, _ in baseline.FILES:
                target = root / baseline.PROJECT / relative
                originals[relative] = (target.read_bytes(), target.stat().st_mode & 0o777) if target.exists() else None
            attempted = []
            try:
                for relative, _, _ in baseline.FILES:
                    attempted.append(relative)
                    mode = originals[relative][1] if originals[relative] else 0o644
                    publish(root / baseline.PROJECT / relative,
                            (stage / baseline.PROJECT / relative).read_bytes(), mode)
                baseline.validate(root, require_patched=True)
            except BaseException:
                for relative in reversed(attempted):
                    target = root / baseline.PROJECT / relative
                    previous = originals[relative]
                    if previous is None:
                        target.unlink(missing_ok=True)
                    else:
                        replace(target, previous[0], previous[1])
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    apply(args.source_root)
    print('verified complete exact CalendarData reminder viewer; runtime still required')


if __name__ == '__main__':
    main()
