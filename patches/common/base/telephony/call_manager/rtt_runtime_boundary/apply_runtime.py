#!/usr/bin/env python3
"""Apply one reviewed patch only after the complete actual source vector gate."""
import argparse
from pathlib import Path
import subprocess
from verify_source import HERE, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args(); root = args.source_root.resolve()
    if state(root) == 'before':
        subprocess.run(['patch', '--batch', '--forward', '-p1', '-i',
                        str(HERE / '0001-propagate-real-session-and-media-errors.patch')], cwd=root, check=True)
    if state(root) != 'final': raise ValueError('Final complete actual source vector required')
    print('RTT session/media error boundary: source candidate applied; runtime NOT accepted')


if __name__ == '__main__': main()
