#!/usr/bin/env python3
"""Verify published adaptation bytes against the manifest ownership index."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

from component_heads import published_heads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--objects', type=Path, required=True)
    parser.add_argument('--journal', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    index = json.loads(args.index.read_text())
    heads = published_heads(args.journal)
    owners = {}
    for entry in index['files']:
        for part in entry['parts']:
            expected = (part['sha256'], entry['mode'])
            files = owners.setdefault(part['repository'], {})
            if part['path'] in files and files[part['path']] != expected:
                raise ValueError('Inconsistent indexed payload: ' + part['path'])
            files[part['path']] = expected
    if index.get('materializer'):
        tool = index['materializer']
        owners.setdefault(tool['repository'], {})[tool['path']] = (tool['sha256'], tool['mode'])
    results = []
    environment = dict(os.environ, GIT_LFS_SKIP_SMUDGE='1', GIT_TERMINAL_PROMPT='0')
    for name, files in sorted(owners.items()):
        result = dict(repository=name, expected_files=len(files), verified_files=0)
        try:
            if name not in heads:
                raise ValueError('No published component commit')
            sha = heads[name]
            objects = args.objects / (name + '.git')

            def git(*argv, data=None):
                return subprocess.check_output(['git', '-C', str(objects), *argv],
                    input=data, env=environment, stderr=subprocess.PIPE, timeout=300)

            remote = git('ls-remote', 'git@github.com:openharmony-qemu/' + name + '.git',
                         'refs/heads/OpenHarmony-7.0-Release-qemu').decode().split()
            if not remote or remote[0] != sha:
                raise ValueError('Remote branch differs from the publication journals')
            result['qemu_commit'] = sha
            entries = {}
            for line in git('ls-tree', '-r', '-z', sha, '--', *files).split(b'\0'):
                if not line:
                    continue
                metadata, path = line.decode().split('\t', 1)
                mode, kind, oid = metadata.split()
                entries[path] = (mode, kind, oid)
            missing = set(files) - entries.keys()
            if missing:
                raise ValueError('Missing component payloads: ' + ', '.join(sorted(missing)))
            blobs = git('cat-file', '--batch', data=('\n'.join(entries[p][2] for p in files) + '\n').encode())
            offset = 0
            for path, (digest, mode) in files.items():
                newline = blobs.index(b'\n', offset)
                oid, kind, size = blobs[offset:newline].decode().split()
                start = newline + 1
                data = blobs[start:start + int(size)]
                offset = start + int(size) + 1
                if (entries[path] != (mode, 'blob', oid) or kind != 'blob' or
                        hashlib.sha256(data).hexdigest() != digest):
                    raise ValueError('Component payload bytes or mode differ: ' + path)
                result['verified_files'] += 1
            if offset != len(blobs):
                raise ValueError('Unexpected object stream content')
            result['status'] = 'verified'
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            result.update(status='incomplete', error=str(error))
        results.append(result)
        print(name + ': ' + result['status'], flush=True)
    report = dict(schema_version=1, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        index_sha256=hashlib.sha256(args.index.read_bytes()).hexdigest(),
        complete=all(r['status'] == 'verified' for r in results),
        files=len(index['files']), component_repositories=len(owners), repositories=results,
        build_validated=False, runtime_validated=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if report['complete'] else 1)


if __name__ == '__main__':
    main()
