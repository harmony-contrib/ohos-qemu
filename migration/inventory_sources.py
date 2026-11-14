#!/usr/bin/env python3
"""Read-only inventory of the prepared Linux source tree for component export."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def git(root, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=*',
                                    '-c', 'filter.lfs.required=false',
                                    '-c', 'filter.lfs.clean=', '-c', 'filter.lfs.process=', '-C', str(root),
                                    *args], env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--retry-errors-from', type=Path)
    args = parser.parse_args()
    records = []
    prior = {}
    if args.retry_errors_from:
        data = json.loads(args.retry_errors_from.read_text())
        if data['root'] != str(args.root):
            raise ValueError('Retry must use the same read-only source tree')
        prior = {p['path']: p for p in data['projects']}
    for project in json.loads(args.lock.read_text())['projects']:
        if project['path'] in prior and 'error' not in prior[project['path']]:
            records.append(prior[project['path']])
            continue
        root = args.root / project['path']
        record = dict(project)
        try:
            record['head'] = git(root, 'rev-parse', 'HEAD').decode().strip()
            record['shallow'] = git(root, 'rev-parse', '--is-shallow-repository').decode().strip() == 'true'
            tracked = git(root, 'diff', '--name-only', '-z', 'HEAD').decode().split('\0')
            untracked = git(root, 'ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
            record['tracked_changes'] = [x for x in tracked if x]
            record['untracked'] = [{'path': x, 'size': (root / x).lstat().st_size}
                                   for x in untracked if x]
        except (subprocess.CalledProcessError, FileNotFoundError) as error:
            record['error'] = str(error)
        records.append(record)
    args.output.write_text(json.dumps({'scope': 'read_only_NOT_build_validation',
                                      'root': str(args.root), 'projects': records}, indent=2) + '\n')
    print(f'Inventoried {len(records)} repositories; errors: {sum("error" in x for x in records)}')


if __name__ == '__main__':
    main()
