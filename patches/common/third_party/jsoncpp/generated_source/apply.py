#!/usr/bin/env python3
"""Apply the exact fixed installer stack, including overlapping numbered diffs."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess

from check import FIRST_PATCH_SHA256, ORIGINAL_SHA256, data, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append')
    args = parser.parse_args()
    root = args.source_root.resolve()
    source = root / 'third_party/jsoncpp'
    validate(source)
    descriptor = os.open(source / '.ohos-qemu-generator.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        component = Path(__file__).resolve().parent
        for digest, filename in ((ORIGINAL_SHA256, '0001-fail-closed-generation-without-source-writes.patch'),
                                 (FIRST_PATCH_SHA256, '0002-accept-only-empty-gn-output-skeleton.patch')):
            # Exact whole-file/revision/archive checks replace unsafe reverse
            # checks of an earlier overlapping hunk after the complete stack.
            validate(source)
            if hashlib.sha256(data(source, 'install.py')).hexdigest() == digest:
                patch = component / filename
                subprocess.run(['git', '-C', str(root), 'apply', '--check', str(patch)], check=True)
                subprocess.run(['git', '-C', str(root), 'apply', '--whitespace=nowarn', str(patch)], check=True)
        validate(source, require_patched=True)
    print('verified complete fixed JSONCPP generator stack')


if __name__ == '__main__':
    main()
