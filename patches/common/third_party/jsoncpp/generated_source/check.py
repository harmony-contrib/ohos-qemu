#!/usr/bin/env python3
"""Guard the fixed 7.0 jsoncpp dependency before any mutation."""
import argparse
import hashlib
from pathlib import Path
import subprocess

REVISION = 'ea808a0b6318fbe1fee1d3acb8cb0fa36d4748d0'
ARCHIVE = 'jsoncpp-1.9.6.tar.gz'
ARCHIVE_SHA256 = 'f93b6dd7ce796b13d02c108bc9f79812245a82e577581c4c9aabe57075c90ea2'
ORIGINAL_SHA256 = 'dc287c0dbc6d9f4aaedc1801b8486fc2026e57080f4a8284f303c48d588ac8e2'
FIRST_PATCH_SHA256 = '2589a7e1ff0fe3cf6dcbb5d8aece792af1cd03b25a5cc2d29fa7ce4f28453d05'
REPAIRED_SHA256 = '31d602cb122bf1b2a0635b1b63319c4ada731bdeda5e9cbbfe612147c8af22d4'


def data(source, name):
    path = source / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('jsoncpp input must be a real file: ' + name)
    return path.read_bytes()


def validate(source, require_patched=False):
    if source.is_symlink() or source.parent.is_symlink():
        raise ValueError('jsoncpp repair requires a real writable source copy')
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('jsoncpp repair requires fixed 7.0 revision ' + REVISION)
    original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:install.py'])
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('unknown pinned jsoncpp installer')
    if hashlib.sha256(data(source, ARCHIVE)).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('unknown jsoncpp archive')
    accepted = (REPAIRED_SHA256,) if require_patched else (ORIGINAL_SHA256, FIRST_PATCH_SHA256, REPAIRED_SHA256)
    if hashlib.sha256(data(source, 'install.py')).hexdigest() not in accepted:
        raise ValueError('unknown jsoncpp edits; preserving source')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root.resolve() / 'third_party/jsoncpp', args.require_patched)
    print('fixed jsoncpp generation contract verified; not guest API acceptance')


if __name__ == '__main__':
    main()
