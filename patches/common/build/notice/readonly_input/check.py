#!/usr/bin/env python3
"""Guard the exact fixed-source NOTICE read-only change before/after patching."""
import argparse
from pathlib import Path
import subprocess

REVISION = '5c0623072ed9c2ee93ab909a7a01f428fee95082'
FILE = 'ohos/notice/collect_module_notice_file.py'
OLD = b'os.open(notice_file, os.O_RDWR | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR)'
NEW = b'os.open(notice_file, os.O_RDONLY)'


def repaired(original):
    if original.count(OLD) != 1 or NEW in original:
        raise ValueError('unknown pinned NOTICE input-read structure')
    return original.replace(OLD, NEW)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    source = args.source_root.resolve() / 'build'
    target = source / FILE
    if source.is_symlink() or target.is_symlink():
        raise SystemExit('NOTICE repair requires a real writable build copy, not a source symlink')
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != REVISION:
        raise SystemExit('NOTICE read-only repair requires fixed 7.0 build ' + REVISION)
    original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + FILE])
    expected = repaired(original)
    accepted = (expected,) if args.require_patched else (original, expected)
    if target.read_bytes() not in accepted:
        raise SystemExit('unknown NOTICE collector edits; preserving source')
    print('fixed NOTICE collector input contract verified (not package/runtime acceptance)')


if __name__ == '__main__':
    main()
