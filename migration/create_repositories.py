#!/usr/bin/env python3
"""Create the reviewed QEMU component forks/mirrors using the local gh CLI.

This is a migration utility, not part of the package build. It never deletes
repositories, changes existing refs, or treats repository creation as validation.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import time


def run(argv):
    try:
        return subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=180)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, 'local CLI network timeout')


def matches(metadata, project):
    expected = project.get('github_upstream')
    if expected:
        return metadata.get('parent', {}).get('full_name', '').lower() == expected.lower()
    return (not metadata.get('fork') and metadata.get('description') ==
            'QEMU OpenHarmony 7.0 source mirror; upstream: ' + project['upstream_url'])


def disable_component_actions(name):
    endpoint = 'repos/openharmony-qemu/' + name + '/actions/permissions'
    changed = run(['gh', 'api', '--method', 'PUT', endpoint, '-F', 'enabled=false'])
    if changed.returncode:
        raise SystemExit('Cannot disable inherited component workflows: ' + changed.stdout)
    checked = run(['gh', 'api', endpoint])
    if checked.returncode or json.loads(checked.stdout).get('enabled') is not False:
        raise SystemExit('Component Actions policy was not verified: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--priority', nargs='*', default=[])
    args = parser.parse_args()
    args.catalog = args.catalog.resolve()
    args.journal = args.journal.resolve()
    catalog = json.loads(args.catalog.read_text())
    projects = catalog['repositories']
    priorities = {name: index for index, name in enumerate(args.priority)}
    unknown = set(priorities) - {p['name'] for p in projects}
    if unknown:
        raise ValueError('Unknown priority repositories: ' + ', '.join(sorted(unknown)))
    projects = sorted(projects, key=lambda p: priorities.get(p['name'], len(priorities)))
    if not args.apply:
        print(json.dumps(projects, indent=2))
        return
    args.journal.parent.mkdir(parents=True, exist_ok=True)
    listed = run(['gh', 'repo', 'list', 'openharmony-qemu', '--limit', '2000', '--json', 'name'])
    if listed.returncode:
        raise SystemExit(listed.stdout)
    existing = {item['name'] for item in json.loads(listed.stdout)}
    done = set()
    if args.journal.exists():
        for line in args.journal.read_text().splitlines():
            record = json.loads(line)
            if record.get('status') == 'created':
                done.add(record['name'])
    for index, project in enumerate(projects, 1):
        name = project['name']
        if name in done:
            continue
        if name in existing:
            checked = run(['gh', 'api', 'repos/openharmony-qemu/' + name])
            if checked.returncode:
                raise SystemExit(checked.stdout)
            metadata = json.loads(checked.stdout)
            expected = project.get('github_upstream')
            if not matches(metadata, project):
                raise SystemExit('Existing repository requires ownership review: ' + name)
            disable_component_actions(name)
            with args.journal.open('a') as stream:
                stream.write(json.dumps(dict(name=name, status='created',
                    observation='verified_existing_fork', parent=expected, actions_disabled=True)) + '\n')
            print(f'{index}/{len(projects)} {name}: verified existing fork', flush=True)
            continue
        if project.get('github_upstream'):
            argv = ['gh', 'api', '--method', 'POST',
                    'repos/' + project['github_upstream'] + '/forks',
                    '-f', 'organization=openharmony-qemu', '-f', 'name=' + name,
                    '-F', 'default_branch_only=false', '--silent']
        else:
            # An upstream that is absent from GitHub needs an independent mirror.
            argv = ['gh', 'repo', 'create', 'openharmony-qemu/' + name, '--public',
                    '--description', 'QEMU OpenHarmony 7.0 source mirror; upstream: ' + project['upstream_url']]
        started = time.monotonic()
        for attempt in range(5):
            result = run(argv)
            if not result.returncode:
                break
            # A timed-out POST may already have succeeded. Read back ownership
            # before retrying, so retries cannot create a second repository.
            transient = any(term in result.stdout.lower() for term in
                            ('timeout', 'timed out', 'connection reset', 'eof', 'connection refused'))
            if transient or 'Name already exists' in result.stdout:
                checked = run(['gh', 'api', 'repos/openharmony-qemu/' + name])
                if checked.returncode == 0 and matches(json.loads(checked.stdout), project):
                    result = subprocess.CompletedProcess(argv, 0, 'Verified completed repository creation')
                    break
            if not transient:
                break
            print(f'{name}: transient network error, retry {attempt + 1}/5', flush=True)
            time.sleep(10 * (attempt + 1))
        if result.returncode == 0:
            disable_component_actions(name)
        record = dict(name=name, command=argv, exit_code=result.returncode,
                      status='created' if result.returncode == 0 else 'failed',
                      actions_disabled=result.returncode == 0,
                      timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      output=result.stdout.strip())
        with args.journal.open('a') as stream:
            stream.write(json.dumps(record, sort_keys=True) + '\n')
        print(f'{index}/{len(projects)} {name}: {record["status"]}', flush=True)
        if result.returncode:
            print(result.stdout, flush=True)
            # Stop on permission, service and rate-limit failures. Resume only
            # after reviewing the response; do not evade server rate limits.
            raise SystemExit(result.returncode)
        time.sleep(max(0, 20 - (time.monotonic() - started)))


if __name__ == '__main__':
    main()
