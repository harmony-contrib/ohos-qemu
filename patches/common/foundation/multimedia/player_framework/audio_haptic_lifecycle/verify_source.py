#!/usr/bin/env python3
"""Require one complete pinned upstream, B4 or incarnation component state."""
import argparse
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('audio_haptic_local_install', Path(__file__).with_name('install.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
PROJECT = installer.PROJECT
REVISION = installer.REVISION
FILES = tuple((name, installer.MANIFEST['states']['upstream'][name],
               installer.MANIFEST['states']['incarnation'][name]) for name in installer.MANIFEST['files'])


def validate(root, require_patched=False):
    return installer.state(root, require_patched) == 'incarnation'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('AudioHaptic incarnation repair present: ' + str(validate(args.source_root, args.require_patched)))
