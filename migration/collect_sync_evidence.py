#!/usr/bin/env python3
"""Verify completed mirror artifacts against remote refs and archive their evidence."""
import argparse
import collections
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import time
import zipfile

CONTROL = 'openharmony-qemu/mirror-sync'
BRANCH = 'refs/heads/OpenHarmony-7.0-Release-qemu'


def run(argv):
    for attempt in range(3):
        try:
            result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess(argv, 1, b'', b'request timed out')
        if result.returncode == 0:
            return result.stdout
        if attempt == 2:
            raise RuntimeError(result.stderr.decode()[-1500:])
        time.sleep(3 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--downloads', type=Path, required=True)
    parser.add_argument('--imports', type=Path, required=True)
    parser.add_argument('--only', nargs='+', required=True)
    parser.add_argument('--source-journal', type=Path)
    args = parser.parse_args()
    published = {}
    if args.source_journal and args.source_journal.exists():
        for record in map(json.loads, args.source_journal.read_text().splitlines()):
            if record.get('status') == 'published':
                published[record['name']] = record['qemu_commit']
    artifacts = json.loads(run(['gh', 'api', f'repos/{CONTROL}/actions/runs/{args.run_id}/artifacts?per_page=100']))['artifacts']
    args.archive.mkdir(parents=True, exist_ok=True)
    args.downloads.mkdir(parents=True, exist_ok=True)
    for name in args.only:
        if not re.fullmatch('[A-Za-z0-9_.-]+', name):
            raise ValueError('Invalid repository name')
        matching = [a for a in artifacts if a['name'] == 'mirror-evidence-' + name
                    or a['name'].startswith('mirror-evidence-' + name + '-attempt-')]
        if not matching:
            print(name + ': no completed artifact yet', flush=True)
            continue
        artifact = max(matching, key=lambda a: a['created_at'])
        download = args.downloads / (str(artifact['id']) + '.zip')
        if not download.exists():
            download.write_bytes(run(['gh', 'api', f'repos/{CONTROL}/actions/artifacts/{artifact["id"]}/zip']))
        with zipfile.ZipFile(download) as archive:
            results = [p for p in archive.namelist() if p.endswith('/result.json') or p == 'result.json']
            if not results:
                print(name + ': preparation artifact only; publication not verified', flush=True)
                continue
            report = json.loads(archive.read(results[0]))
            if report['repository'] != 'openharmony-qemu/' + name:
                raise ValueError('Artifact repository identity mismatch')
            remote = run(['git', 'ls-remote', '--heads', 'git@github.com:' + report['repository'] + '.git']).decode()
            observed = {ref: sha for sha, ref in (line.split() for line in remote.splitlines())}
            for row in report['results']:
                expected = row['old'] if row['status'] == 'conflict' else row['new']
                if observed.get(row['ref']) != expected:
                    raise ValueError('Published branch differs from artifact: ' + name + ' ' + row['ref'])
            receipt = args.imports / (name + '.json')
            if receipt.exists() or name in published:
                expected = published.get(name)
                if expected is None:
                    expected = json.loads(receipt.read_text())['qemu_commit']
                if observed.get(BRANCH) != expected:
                    raise ValueError('QEMU development branch changed during sync: ' + name)
            identity = dict(repository=report['repository'],
                workflow_url=f'https://github.com/{CONTROL}/actions/runs/{args.run_id}',
                artifact_id=artifact['id'], artifact_created_at=artifact['created_at'],
                upstream_branches=len(report['original_refs']),
                results=dict(collections.Counter(r['status'] for r in report['results'])),
                remote_refs_verified=True, qemu_branch_revision=observed.get(BRANCH),
                baseline_original_refs=report['baseline_original_refs'],
                baseline_hosted_refs={ref: report['hosted_refs'][ref] for ref in report['baseline_original_refs']},
                build_validated=False, runtime_validated=False)
            # Split compressed maps into bounded chunks so even very large source
            # histories can retain complete SHA conversion evidence in Git.
            maps = [p for p in archive.namelist() if p.endswith('commit-map.csv')]
            if maps:
                chunks = []
                digest = hashlib.sha256()
                directory = args.archive / 'commit-maps' / name
                directory.mkdir(parents=True, exist_ok=True)
                with archive.open(maps[0]) as mapping:
                    lines = []
                    for line in mapping:
                        digest.update(line)
                        lines.append(line)
                        if len(lines) == 100000:
                            chunks.append(write_chunk(directory, lines, len(chunks)))
                            lines = []
                    if lines:
                        chunks.append(write_chunk(directory, lines, len(chunks)))
                identity['commit_map'] = dict(sha256=digest.hexdigest(), chunks=chunks)
            (args.archive / (name + '-sync-' + args.run_id + '.json')).write_text(json.dumps(identity, indent=2) + '\n')
            (args.downloads / (name + '-result.json')).write_text(json.dumps(report, indent=2) + '\n')
            print(name + ': verified ' + json.dumps(identity['results']), flush=True)


def write_chunk(directory, lines, index):
    data = b''.join(lines)
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode='wb', mtime=0) as stream:
        stream.write(data)
    name = f'{index:05d}.csv.gz'
    (directory / name).write_bytes(compressed.getvalue())
    return dict(file=name, rows=len(lines), sha256=hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
