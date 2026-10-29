#!/usr/bin/env python3
"""Guard fixed GPL Vivid producer defaults; not capture/API acceptance."""
import argparse
from pathlib import Path
import subprocess

REVISION = '14c77f1541a53e814d89ad6dea5f7f211f9895a6'
FILE = 'drivers/media/test-drivers/vivid/vivid-core.c'


def repaired(original):
    pairs = [
        (b'\t[0 ... (VIVID_MAX_DEVS - 1)] = 0xe1d3d\n', b'\t[0 ... (VIVID_MAX_DEVS - 1)] = 0x1\n'),
        (b'static unsigned num_inputs[VIVID_MAX_DEVS] = { [0 ... (VIVID_MAX_DEVS - 1)] = 4 };\n',
         b'static unsigned num_inputs[VIVID_MAX_DEVS] = { [0 ... (VIVID_MAX_DEVS - 1)] = 1 };\n'),
    ]
    for old, new in pairs:
        if original.count(old) != 1:
            raise ValueError('unknown pinned Vivid capture defaults')
        original = original.replace(old, new)
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append', default=[])
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    source = root / 'kernel/linux/linux-6.6'
    cursor = source / FILE
    while cursor != root:
        if cursor.is_symlink():
            raise SystemExit('Vivid source symlink; preserving input')
        cursor = cursor.parent
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise SystemExit('Vivid capture requires pinned 7.0 Linux 6.6 source')
    original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + FILE])
    expected = repaired(original)
    if (source / FILE).read_bytes() not in ((expected,) if args.require_patched else (original, expected)):
        raise SystemExit('unknown Vivid producer edits; preserving input')
    print('real Vivid capture-only defaults checked (not streamed frames)')


if __name__ == '__main__':
    main()
