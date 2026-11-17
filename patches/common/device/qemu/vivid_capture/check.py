#!/usr/bin/env python3
"""Validate exact known media selections; leave other kernel repairs intact."""
import argparse
from pathlib import Path
import re
import subprocess

REVISION = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
POST = {'CONFIG_MEDIA_SUPPORT': 'y', 'CONFIG_MEDIA_TEST_SUPPORT': 'y',
        'CONFIG_VIDEO_DEV': 'y', 'CONFIG_V4L_TEST_DRIVERS': 'y',
        'CONFIG_VIDEO_VIVID': 'y', 'CONFIG_VIDEO_VIVID_MAX_DEVS': '1'}
PRE = {
    'arm64_virt_defconfig': {'CONFIG_MEDIA_SUPPORT': 'm', 'CONFIG_MEDIA_TEST_SUPPORT': 'n', 'CONFIG_VIDEO_DEV': 'm'},
    'arm_virt_defconfig': {'CONFIG_MEDIA_SUPPORT': 'n'},
    'x86_64_virt_defconfig': {'CONFIG_MEDIA_SUPPORT': 'y', 'CONFIG_MEDIA_TEST_SUPPORT': 'y', 'CONFIG_VIDEO_DEV': 'y',
                            'CONFIG_V4L_TEST_DRIVERS': 'n'},
}


def selections(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(CONFIG_[A-Z0-9_]+)=(.+)', line)
        disabled = re.fullmatch(r'# (CONFIG_[A-Z0-9_]+) is not set', line)
        if not match and not disabled:
            continue
        name, value = (match[1], match[2]) if match else (disabled[1], 'n')
        if name in result:
            raise ValueError('duplicate kernel selection: ' + name)
        result[name] = value
    return result


def validate(name, text, patched=False):
    values = selections(text)
    observed = {key: values[key] for key in POST if key in values}
    if observed not in ([POST] if patched else [PRE[name], POST]):
        raise ValueError('unknown or incomplete virtual Camera kernel selection: ' + name)
    if patched and any(values.get(key) != 'y' for key in ('CONFIG_FB', 'CONFIG_HAS_DMA')):
        raise ValueError('real Vivid framebuffer/DMA dependencies missing: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append', default=[])
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    source = root / 'device/qemu'
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise SystemExit('virtual Camera kernels require pinned 7.0 QEMU source')
    for name in PRE:
        path = source / 'common/virt_full/kernel' / name
        cursor = path
        while cursor != root:
            if cursor.is_symlink():
                raise SystemExit('virtual Camera kernel source symlink; preserving input')
            cursor = cursor.parent
        validate(name, path.read_text(), args.require_patched)
    print('three real Vivid kernel selections checked (not olddefconfig/compile/boot)')


if __name__ == '__main__':
    main()
