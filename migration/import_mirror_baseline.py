#!/usr/bin/env python3
"""Create a missing QEMU branch from a centrally synchronized source baseline.

Existing development branches are preserved. No CI, configuration or metadata is
added to the component tree. Commit identity is recorded outside the mirror.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

BRANCH = 'OpenHarmony-7.0-Release-qemu'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    if not args.repository.startswith('openharmony-qemu/'):
        raise ValueError('QEMU organization repository required')
    entry = next(x for x in json.loads(args.catalog.read_text())['repositories']
                 if x['name'] == args.repository.split('/')[1])
    revisions = {x['revision'] for x in entry['inputs']}
    if len(revisions) != 1:
        raise ValueError('Reconcile multiple source baselines before selecting a QEMU branch')
    args.directory.mkdir(parents=True, exist_ok=True)
    def git(*argv):
        return subprocess.check_output(['git', '-C', str(args.directory), *argv],
            env=dict(os.environ, GIT_LFS_SKIP_SMUDGE='1', GIT_TERMINAL_PROMPT='0')).decode().strip()
    if not (args.directory / '.git').exists():
        git('init', '-b', BRANCH)
    remote = 'git@github.com:' + args.repository + '.git'
    observed = git('ls-remote', remote, 'refs/heads/' + BRANCH)
    if observed and args.evidence.exists():
        print(args.repository + ': preserve existing QEMU branch ' + observed.split()[0])
        return
    baseline = 'refs/heads/upstream/baseline-7.0'
    git('fetch', '--no-tags', '--filter=blob:none', '--depth=1', remote, baseline)
    source = git('rev-parse', 'FETCH_HEAD')
    if observed and observed.split()[0] != source:
        raise ValueError('Existing QEMU branch differs from the hosted baseline; no import receipt created')
    if not observed:
        git('push', remote, source + ':refs/heads/' + BRANCH)
    if git('ls-remote', remote, 'refs/heads/' + BRANCH).split()[0] != source:
        raise ValueError('Remote branch verification failed')
    subprocess.run(['gh', 'repo', 'edit', args.repository, '--default-branch', BRANCH], check=True)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(dict(repository=args.repository, qemu_commit=source,
        upstream_revision=next(iter(revisions)), hosted_upstream_revision=source,
        scope='source_migration_only', build_validated=False, runtime_validated=False), indent=2) + '\n')
    print(args.repository + ': initialized ' + source)


if __name__ == '__main__':
    main()
