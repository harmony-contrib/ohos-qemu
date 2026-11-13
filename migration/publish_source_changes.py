#!/usr/bin/env python3
"""Commit explicitly selected, reviewed component source exports with local git."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from component_heads import published_heads

BRANCH = 'OpenHarmony-7.0-Release-qemu'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exports', type=Path, required=True)
    parser.add_argument('--objects', type=Path, required=True)
    parser.add_argument('--imports', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--parent-journal', type=Path, action='append')
    parser.add_argument('--only', nargs='+', required=True)
    args = parser.parse_args()
    for name in ('exports', 'objects', 'imports', 'journal'):
        setattr(args, name, getattr(args, name).resolve())
    previous = {}
    parents = published_heads(args.parent_journal)
    if args.journal.exists():
        previous = {x['name']: x for x in map(json.loads, args.journal.read_text().splitlines())}
    args.objects.mkdir(parents=True, exist_ok=True)
    for name in args.only:
        export = args.exports / name
        metadata = json.loads((export / 'export.json').read_text())
        fingerprint = hashlib.sha256(((export / 'export.json').read_bytes() +
                                      (export / 'tracked.patch').read_bytes())).hexdigest()
        if previous.get(name, {}).get('status') == 'published':
            if previous[name]['export_sha256'] != fingerprint:
                raise ValueError('Published source export changed; explicit update review required: ' + name)
            continue
        objects = args.objects / (name + '.git')
        record = dict(name=name, export_sha256=fingerprint, upstream_revision=metadata['upstream_revision'],
                      scope='source_commit_only_NOT_build_or_runtime_validation')
        try:
            def git(*argv, data=None):
                result = subprocess.run(['git', '-C', str(objects), *argv], input=data,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env=dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1'), timeout=600)
                if result.returncode:
                    raise RuntimeError('git ' + ' '.join(argv) + '\n' + result.stderr.decode()[-1500:])
                return result.stdout
            if not (objects / 'HEAD').exists():
                subprocess.run(['git', 'init', '--bare', str(objects)], check=True, stdout=subprocess.DEVNULL)
            remote = 'git@github.com:openharmony-qemu/' + name + '.git'
            if b'origin' not in git('remote').splitlines():
                git('remote', 'add', 'origin', remote)
            git('fetch', '--no-tags', '--filter=blob:none', '--depth=1', 'origin',
                'refs/heads/' + BRANCH + ':refs/remotes/origin/' + BRANCH)
            parent = git('rev-parse', 'refs/remotes/origin/' + BRANCH).decode().strip()
            message = git('show', '-s', '--format=%B', parent).decode()
            if 'Source export SHA-256: ' + fingerprint in message.splitlines():
                record.update(status='published', qemu_commit=parent, observation='verified_existing_source_commit')
            else:
                allowed = {metadata['upstream_revision']}
                imported = args.imports / (name + '.json')
                if imported.exists():
                    allowed.add(json.loads(imported.read_text())['qemu_commit'])
                if name in parents:
                    allowed = {parents[name]}
                if parent not in allowed:
                    raise ValueError('Remote QEMU branch has other changes; preserve for merge review')
                git('read-tree', parent)
                if metadata['tracked']:
                    # Fetch changed source blobs together instead of triggering
                    # one network round trip per file through the promisor remote.
                    entries = git('ls-tree', '-r', parent, '--', *metadata['tracked']).decode().splitlines()
                    blobs = sorted({line.split()[2] for line in entries if line.split()[1] == 'blob'})
                    if blobs:
                        git('-c', 'fetch.negotiationAlgorithm=noop', 'fetch', 'origin', '--no-tags',
                            '--no-write-fetch-head', '--recurse-submodules=no', '--filter=blob:none',
                            '--stdin', data=('\n'.join(blobs) + '\n').encode())
                patch = export / 'tracked.patch'
                if patch.stat().st_size:
                    git('apply', '--cached', '--binary', '--whitespace=nowarn', str(patch))
                    git('apply', '--cached', '--reverse', '--check', str(patch))
                for entry in metadata['added']:
                    source = export / 'files' / entry['path']
                    if 'symlink' in entry:
                        data, mode = entry['symlink'].encode(), '120000'
                    else:
                        if digest(source) != entry['sha256']:
                            raise ValueError('Exported source bytes changed: ' + entry['path'])
                        data = source.read_bytes()
                        if data.startswith((b'\x7fELF', b'\xcf\xfa\xed\xfe')):
                            admitted = entry.get('existing_tracked_asset')
                            original = (subprocess.check_output(['git', 'cat-file', 'blob',
                                admitted['original_git_blob']]) if admitted else None)
                            if original != data:
                                raise ValueError('Compiled output was not admitted as source: ' + entry['path'])
                        mode = '100755' if int(entry['mode'], 8) & 0o111 else '100644'
                    blob = git('hash-object', '-w', '--stdin', data=data).decode().strip()
                    git('update-index', '--add', '--cacheinfo', mode + ',' + blob + ',' + entry['path'])
                record.update(migration_state='selected_source_changes_imported',
                    tracked_files=metadata['tracked'], added_files=[x['path'] for x in metadata['added']],
                    omitted=metadata['omitted'],
                    validation=['git apply --cached', 'reverse application check', 'added file SHA-256'],
                    build_validated=False, runtime_validated=False)
                tree = git('write-tree', '--missing-ok').decode().strip()
                message = ('qemu: integrate OpenHarmony 7.0 component source adaptations\n\n'
                    'Move the reviewed source changes into their owning component.\n'
                    'Upstream: ' + metadata['upstream_revision'] + '\n'
                    'Source export SHA-256: ' + fingerprint + '\n'
                    'Source application verified; packaging/runtime validation is deferred.\n')
                commit = git('commit-tree', '-S', tree, '-p', parent,
                             data=message.encode()).decode().strip()
                git('update-ref', 'refs/heads/' + BRANCH, commit)
                git('push', 'origin', commit + ':refs/heads/' + BRANCH)
                observed = git('ls-remote', 'origin', 'refs/heads/' + BRANCH).decode().split()[0]
                if observed != commit:
                    raise ValueError('Published component commit differs')
                record.update(status='published', qemu_commit=commit, parent=parent,
                              changed_files=len(metadata['tracked']) + len(metadata['added']))
        except (RuntimeError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            record.update(status='failed', error=str(error))
        with args.journal.open('a') as stream:
            stream.write(json.dumps(record, sort_keys=True) + '\n')
        print(name + ': ' + record['status'], flush=True)
        if record['status'] == 'failed':
            print(record['error'][-1500:], flush=True)


if __name__ == '__main__':
    main()
