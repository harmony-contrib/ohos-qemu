#!/usr/bin/env python3
"""Guard the fixed Serial-only devnode metadata policy, never guest acceptance."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess

REVISION = 'cfc1d5b31a7438dbc87763f9222f00337221cf21'
FILE = 'sepolicy/ohos_policy/busmanager/serial_manager/system/serial_service.te'
ORIGINAL_SHA256 = '8dbe5797286ce668099cdb766312aa540902eb42bafa9986197b9fe7a5906321'
OLD = b'allow serial_service tty_device:chr_file { read write open lock ioctl };'
NEW = b'allow serial_service tty_device:chr_file { getattr read write open lock ioctl };'


def repaired(original):
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256 or original.count(OLD) != 1 or NEW in original:
        raise ValueError('unknown fixed Serial metadata policy input; preserving changes')
    return original.replace(OLD, NEW)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    source = root / 'base/security/selinux_adapter'
    target = source / FILE
    if source.is_symlink() or target.is_symlink() or not source.resolve().is_relative_to(root):
        raise SystemExit('Serial metadata policy requires an owned writable source copy')
    if not target.resolve().is_relative_to(source.resolve()):
        raise SystemExit('Serial policy input resolves outside its owned component')
    if os.statvfs(target).f_flag & os.ST_RDONLY:
        raise SystemExit('Serial metadata policy refuses read-only production input')
    git = ['git', '-c', 'safe.directory=' + str(source), '-C', str(source)]
    head = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
    if head != REVISION:
        raise SystemExit('Serial metadata policy requires fixed selinux_adapter ' + REVISION)
    original = subprocess.check_output(git + ['show', REVISION + ':' + FILE])
    expected = repaired(original)
    accepted = (expected,) if args.require_patched else (original, expected)
    if target.read_bytes() not in accepted:
        raise SystemExit('unknown Serial policy edits; preserving changes')
    print('fixed Serial-only getattr policy guard verified (not enforcing/runtime acceptance)')


if __name__ == '__main__':
    main()
