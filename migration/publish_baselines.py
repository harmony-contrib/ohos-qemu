#!/usr/bin/env python3
"""Publish exact baseline refs through local Git/GitHub CLIs without overwrites.

Run after repository creation. Missing source commits are recorded for local
cache/upstream recovery. A baseline ref is not a migrated patch or build result.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess

BRANCH = 'OpenHarmony-7.0-Release-qemu'


def run(argv):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=240,
                            env=dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--created', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--objects', type=Path, required=True)
    parser.add_argument('--method', choices=('github-cli', 'git'), default='github-cli')
    args = parser.parse_args()
    args.catalog = args.catalog.resolve()
    args.created = args.created.resolve()
    args.journal = args.journal.resolve()
    args.objects = args.objects.resolve()
    records = [json.loads(line) for line in args.created.read_text().splitlines()]
    created = {r['name'] for r in records if r['status'] == 'created'}
    previous = {}
    if args.journal.exists():
        previous = {r['name']: r for r in map(json.loads, args.journal.read_text().splitlines())}
    args.objects.mkdir(parents=True, exist_ok=True)
    projects = json.loads(args.catalog.read_text())['repositories']
    for project in projects:
        name = project['name']
        old = previous.get(name, {})
        if name not in created or (old.get('status') in ('published', 'preserved_existing')
                                   and old.get('default_branch_configured')):
            continue
        # Shared system/ArkWeb revision differences need an explicit resolution,
        # not an accidental choice of the first manifest entry.
        revisions = {item['revision'] for item in project['inputs']}
        if len(revisions) != 1 or not project.get('github_upstream'):
            continue
        revision = next(iter(revisions))
        remote = f'git@github.com:openharmony-qemu/{name}.git'
        if args.method == 'github-cli':
            endpoint = 'repos/openharmony-qemu/' + name + '/git/'
            observed = run(['gh', 'api', endpoint + 'ref/heads/' + BRANCH])
            record = dict(name=name, baseline_revision=revision, branch=BRANCH,
                          timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat())
            if observed.returncode == 0:
                actual = json.loads(observed.stdout)['object']['sha']
                record.update(status='preserved_existing', remote_revision=actual,
                              matches_baseline=actual == revision)
            elif '404' in observed.stdout:
                result = run(['gh', 'api', '--method', 'POST', endpoint + 'refs',
                              '-f', 'ref=refs/heads/' + BRANCH, '-f', 'sha=' + revision])
                if result.returncode == 0:
                    actual = json.loads(result.stdout)['object']['sha']
                    if actual != revision:
                        raise ValueError('Server returned a different baseline revision')
                    record.update(status='published', remote_revision=actual)
                else:
                    record.update(status='failed', operation='create-ref', output=result.stdout)
            else:
                record.update(status='failed', operation='read-ref', output=observed.stdout)
            if record['status'] in ('published', 'preserved_existing'):
                default = run(['gh', 'repo', 'edit', 'openharmony-qemu/' + name,
                               '--default-branch', BRANCH])
                record['default_branch_configured'] = default.returncode == 0
            with args.journal.open('a') as stream:
                stream.write(json.dumps(record, sort_keys=True) + '\n')
            print(name + ': ' + record['status'], flush=True)
            if record['status'] == 'failed':
                print(record['output'][-500:], flush=True)
            continue
        # A partial clone's promisor remote belongs to exactly one component.
        # Sharing that configuration across unrelated repositories can fetch a
        # missing tree from the wrong upstream during pack generation.
        objects = args.objects / (name + '.git')
        if not (objects / 'HEAD').exists():
            result = run(['git', 'init', '--bare', str(objects)])
            if result.returncode:
                raise SystemExit(result.stdout)
        git = ['git', '-C', str(objects)]
        observed = run(git + ['ls-remote', remote, 'refs/heads/' + BRANCH])
        record = dict(name=name, baseline_revision=revision, branch=BRANCH,
                      timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat())
        if observed.returncode:
            record.update(status='failed', operation='ls-remote', output=observed.stdout)
        elif observed.stdout.strip():
            actual = observed.stdout.split()[0]
            record.update(status='preserved_existing', remote_revision=actual,
                          matches_baseline=actual == revision)
        else:
            result = run(git + ['fetch', '--no-tags', '--depth=1', '--filter=tree:0',
                                f'https://github.com/openharmony-qemu/{name}.git', revision])
            if result.returncode:
                record.update(status='failed', operation='fetch', output=result.stdout)
            else:
                result = run(git + ['push', remote, revision + ':refs/heads/' + BRANCH])
                record.update(status='published' if result.returncode == 0 else 'failed',
                              operation='push', output=result.stdout)
                if result.returncode == 0:
                    checked = run(git + ['ls-remote', remote, 'refs/heads/' + BRANCH])
                    if checked.returncode or checked.stdout.split()[0] != revision:
                        record.update(status='failed', operation='verify', output=checked.stdout)
                    else:
                        record['remote_revision'] = revision
        with args.journal.open('a') as stream:
            stream.write(json.dumps(record, sort_keys=True) + '\n')
        print(name + ': ' + record['status'], flush=True)
        if record['status'] == 'failed':
            print(record['output'][-1000:], flush=True)


if __name__ == '__main__':
    main()
