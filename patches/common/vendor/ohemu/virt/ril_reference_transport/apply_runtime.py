#!/usr/bin/env python3
"""Apply the fixed QEMU-only RIL wiring; parent schedules the source resource."""
import argparse
from pathlib import Path
import subprocess
from verify_source import HERE, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    if state(root) == 'before':
        subprocess.run(['patch', '--batch', '--forward', '-p1', '-i',
                        str(HERE / '0001-enable-existing-reference-ril.patch')], cwd=root, check=True)
    if state(root) != 'final':
        raise ValueError('Complete final QEMU RIL wiring vector required')
    print('QEMU reference RIL wiring source applied; runtime NOT accepted')


if __name__ == '__main__':
    main()
