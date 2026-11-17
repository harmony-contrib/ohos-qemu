#!/usr/bin/env python3
"""Prepare only the fixed Serial SIG dependency needed by the 2in1 profile."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from prepare_m144_release_cache import fetch

REVISION = 'c05fbbf156230982aa576373da6ee04378b09ca0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    target = args.repository.absolute()
    if target.is_symlink() or args.evidence.exists() or args.evidence.is_symlink():
        raise ValueError('unsafe Serial cache or existing evidence; preserve it')
    name = target.name.removesuffix('.git')
    if not target.name.endswith('.git') or re.fullmatch(r'[A-Za-z0-9_.-]+', name) is None:
        raise ValueError('Serial cache must be a named git repository, not a broad directory')
    record = None
    if target.is_dir():
        result = subprocess.run(['git', '-c', 'safe.directory=' + str(target), '-C', str(target),
            'rev-parse', REVISION + '^{commit}'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip() == REVISION:
            record = {'revision': REVISION, 'cache': str(target), 'status': 'reused_exact_commit'}
        else:
            raise ValueError('existing Serial repository lacks the fixed commit; preserve and review it')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        record = fetch({'name': name, 'revision': REVISION,
            'mirror_url': 'https://github.com/openharmony-sig/busmanager_serial_manager.git',
            'upstream_url': 'https://gitcode.com/openharmony-sig/busmanager_serial_manager.git'}, target.parent)
    with args.evidence.open('x') as stream:
        json.dump({'schema_version': 1, 'scope': 'fixed_Serial_source_cache_NOT_guest_acceptance',
            'status': 'fail' if record['status'] == 'failed' else 'pass', 'record': record}, stream, indent=2)
        stream.write('\n')
    if record['status'] == 'failed':
        raise SystemExit('failed to fetch the fixed Serial commit from both exact-commit remotes')
    print('Serial fixed source dependency ready')


if __name__ == '__main__':
    main()
