#!/usr/bin/env python3
"""Verify completed mirror artifacts against remote refs and archive their evidence."""
import argparse
import collections
import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import time
import zipfile
from component_heads import published_heads

CONTROL = 'openharmony-qemu/mirror-sync'
BRANCH = 'refs/heads/OpenHarmony-7.0-Release-qemu'


def verify_conflict_issues(report, fetch):
    conflicts = []
    for row in report['results']:
        if row['status'] != 'conflict':
            continue
        number = row.get('issue')
        if not isinstance(number, int) or number < 1:
            raise ValueError('Conflict has no central issue')
        issue = fetch(number)
        url = f'https://github.com/{CONTROL}/issues/{number}'
        marker = '<!-- mirror-conflict:' + hashlib.sha256(
            (report['repository'] + '\n' + row['ref']).encode()).hexdigest() + ' -->'
        body = issue.get('body') or ''
        expected = [marker, 'Repository: https://github.com/' + report['repository'],
                    'Ref: `' + row['ref'] + '`',
                    'Destination: `' + (row['old'] or 'missing') + '`',
                    'Incoming: `' + row['new'] + '`']
        if (issue.get('html_url') != url or issue.get('state') != 'open'
                or not all(value in body for value in expected)):
            raise ValueError('Central issue does not describe the preserved conflict')
        conflicts.append(dict(ref=row['ref'], old=row['old'], incoming=row['new'],
            issue_url=url, issue_verified=True,
            issue_body_sha256=hashlib.sha256(body.encode()).hexdigest()))
    return conflicts


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
    parser.add_argument('--source-journal', type=Path, action='append')
    args = parser.parse_args()
    published = published_heads(args.source_journal)
    pages = json.loads(run(['gh', 'api', '--paginate', '--slurp',
        f'repos/{CONTROL}/actions/runs/{args.run_id}/artifacts?per_page=100']))
    artifacts = [artifact for page in pages for artifact in page['artifacts']]
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
                checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                workflow_url=f'https://github.com/{CONTROL}/actions/runs/{args.run_id}',
                artifact_id=artifact['id'], artifact_created_at=artifact['created_at'],
                upstream_branches=len(report['original_refs']),
                results=dict(collections.Counter(r['status'] for r in report['results'])),
                remote_refs_verified=True, qemu_branch_revision=observed.get(BRANCH),
                baseline_original_refs=report['baseline_original_refs'],
                baseline_hosted_refs={ref: report['hosted_refs'][ref] for ref in report['baseline_original_refs']},
                build_validated=False, runtime_validated=False)
            identity['conflicts'] = verify_conflict_issues(report, lambda number: json.loads(
                run(['gh', 'api', f'repos/{CONTROL}/issues/{number}'])))
            # Split compressed maps into bounded chunks so even very large source
            # histories can retain complete SHA conversion evidence in Git.
            maps = [p for p in archive.namelist() if p.endswith('commit-map.csv')]
            if maps:
                chunks = []
                digest = hashlib.sha256()
                # Different runs may contain different upstream histories. Keep
                # every conversion map under its immutable artifact identity.
                directory = args.archive / 'commit-maps' / name / str(artifact['id'])
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
                identity['commit_map'] = dict(sha256=digest.hexdigest(), chunks=chunks,
                    directory=str(directory.relative_to(args.archive)))
            (args.archive / (name + '-sync-' + args.run_id + '.json')).write_text(json.dumps(identity, indent=2) + '\n')
            (args.downloads / (name + '-result.json')).write_text(json.dumps(report, indent=2) + '\n')
            print(name + ': verified ' + json.dumps(identity['results']), flush=True)


def write_chunk(directory, lines, index):
    data = b''.join(lines)
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode='wb', mtime=0) as stream:
        stream.write(data)
    name = f'{index:05d}.csv.gz'
    target = directory / name
    encoded = compressed.getvalue()
    if target.exists() and target.read_bytes() != encoded:
        raise ValueError('Archived conversion map changed; preserving existing evidence: ' + str(target))
    target.write_bytes(encoded)
    return dict(file=name, rows=len(lines), sha256=hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
