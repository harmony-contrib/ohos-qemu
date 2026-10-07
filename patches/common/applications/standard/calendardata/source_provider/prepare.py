#!/usr/bin/env python3
"""Migrate only the exact QEMU-owned legacy-resource BUILD, never unknown edits."""
import argparse
import hashlib
from pathlib import Path

LEGACY_BUILD_SHA256 = 'bc5f8c2631abe876725387d42311178f6d3d2d9d2854b9482d82729614c3eb77'
COMPONENT = Path(__file__).resolve().parent


def desired_build():
    patch = (COMPONENT / '0001-build-calendar-provider-from-source.patch').read_text()
    section = patch.split('diff --git ', 2)[1]
    lines = section.split('@@ -0,0 +1,23 @@\n', 1)[1].splitlines()
    if len(lines) != 23 or any(not line.startswith('+') for line in lines):
        raise ValueError('unexpected owned CalendarData BUILD patch payload')
    return ('\n'.join(line[1:] for line in lines) + '\n').encode()


def prepare(root):
    path = root / 'applications/standard/calendardata/BUILD.gn'
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('refuse symlink CalendarData BUILD path')
    if not path.exists():
        return  # New checkout: the numbered patch creates the desired file.
    current, desired = path.read_bytes(), desired_build()
    if current == desired:
        return
    if hashlib.sha256(current).hexdigest() != LEGACY_BUILD_SHA256:
        raise ValueError('unknown CalendarData BUILD edits; refusing replacement')
    path.write_bytes(desired)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product')
    args = parser.parse_args()
    prepare(args.source_root)
