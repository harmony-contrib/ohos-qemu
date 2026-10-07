#!/usr/bin/env python3
"""Reject unknown local Camera overrides rather than weakening overlay guards."""
import argparse
import json
from pathlib import Path

PART = 'drivers_peripheral_camera'
LOCAL = {'component': PART, 'features': ['drivers_peripheral_camera_v4l2_emulator=false']}
BOARD = {'component': PART, 'features': ['drivers_peripheral_camera_feature_usb = false']}
REPAIRED = {'component': PART, 'features': [LOCAL['features'][0], *BOARD['features']]}


def find(document):
    values = [c for s in document['subsystems'] if s['subsystem'] == 'hdf'
              for c in s['components'] if c['component'] == PART]
    if len(values) > 1:
        raise ValueError('duplicate Camera component')
    return values


def validate(root, patched=False):
    root = root.resolve()
    for product in ('qemu_arm64_linux_full', 'qemu_x86_64_linux_full', 'qemu_armv7a_linux_full', 'virt'):
        path = root / 'vendor/ohemu' / product / ('virt_common.json' if product == 'virt' else 'config.json')
        if product == 'qemu_armv7a_linux_full' and not path.exists():
            continue
        cursor = path
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError('Camera profile source contains a symlink')
            cursor = cursor.parent
        values = find(json.loads(path.read_text()))
        expected = [REPAIRED] if product == 'virt' else []
        accepted = [expected] if patched else [expected, [BOARD] if product == 'virt' else [LOCAL]]
        if values not in accepted:
            raise ValueError('unknown Camera board/local configuration; preserving ' + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append', default=[])
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
    print('Camera local/board inheritance checked (not device/frame acceptance)')


if __name__ == '__main__':
    main()
