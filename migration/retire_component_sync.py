#!/usr/bin/env python3
"""Remove this migration's legacy sync files, preserving source trees and history."""
import argparse
import json
import os
from pathlib import Path
import subprocess

BRANCH = 'OpenHarmony-7.0-Release-qemu'
OWNED = ['.github/scripts/sync_upstream.py', '.github/workflows/sync-upstream.yml',
         'UPSTREAM.json', 'README.qemu.md']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    if args.name not in ('global_i18n', 'developtools_smartperf_host', 'device_soc_rockchip'):
        raise ValueError('Only reviewed legacy installations may be retired by this utility')
    repository = 'openharmony-qemu/' + args.name
    args.directory.mkdir(parents=True, exist_ok=True)
    def git(*argv, data=None):
        return subprocess.check_output(['git', '-C', str(args.directory), *argv], input=data,
            env=dict(os.environ, GIT_LFS_SKIP_SMUDGE='1', GIT_TERMINAL_PROMPT='0')).decode().strip()
    if not (args.directory / 'HEAD').exists():
        git('init', '--bare')
        git('remote', 'add', 'origin', 'git@github.com:' + repository + '.git')
    git('fetch', '--no-tags', '--filter=blob:none', '--depth=1', 'origin', 'refs/heads/' + BRANCH)
    current = git('rev-parse', 'FETCH_HEAD')
    paths = set(git('ls-tree', '-r', '--name-only', current, '--', *OWNED).splitlines())
    if not paths:
        print(repository + ': already retired')
        return
    if paths != set(OWNED):
        raise ValueError('Partial legacy installation requires review')
    script = git('show', current + ':.github/scripts/sync_upstream.py')
    if 'qemu-upstream' not in script or 'upstream/baseline-7.0' not in script:
        raise ValueError('Unexpected script ownership')
    config = json.loads(git('show', current + ':UPSTREAM.json'))
    git('read-tree', current)
    git('update-index', '--index-info', data=''.join('0 ' + '0' * 40 + '\t' + path + '\n'
                                                   for path in OWNED).encode())
    tree = git('write-tree', '--missing-ok')
    message = ('ci: move mirror synchronization to the central repository\n\n'
        'Synchronization, upstream configuration and provenance are maintained at\n'
        'https://github.com/openharmony-qemu/mirror-sync\n'
        'Preserve the component source and QEMU development history.\n')
    commit = git('commit-tree', '-S', tree, '-p', current, data=message.encode())
    changed = git('diff-tree', '--no-commit-id', '--name-status', '-r', current, commit)
    if sorted(changed.splitlines()) != sorted('D\t' + path for path in OWNED):
        raise ValueError('Retirement must only delete the four owned files')
    git('push', 'origin', commit + ':refs/heads/' + BRANCH)
    if git('ls-remote', 'origin', 'refs/heads/' + BRANCH).split()[0] != commit:
        raise ValueError('Remote branch verification failed')
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(dict(repository=repository, previous_commit=current,
        cleanup_commit=commit, removed=OWNED, previous_upstream_config=config,
        source_tree_unchanged=True), indent=2) + '\n')
    endpoint = 'repos/' + repository + '/actions/workflows/sync-upstream.yml'
    state = json.loads(subprocess.check_output(['gh', 'api', endpoint]))['state']
    if state == 'active':
        subprocess.run(['gh', 'workflow', 'disable', 'sync-upstream.yml', '--repo', repository], check=True)
    state = json.loads(subprocess.check_output(['gh', 'api', endpoint]))['state']
    if state == 'active':
        raise ValueError('Legacy workflow is still active')
    print(repository + ': ' + commit)


if __name__ == '__main__':
    main()
