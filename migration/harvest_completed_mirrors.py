#!/usr/bin/env python3
"""Verify completed sync jobs and initialize independent mirrors' QEMU branches."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--runs', nargs='+', required=True)
    parser.add_argument('--evidence-workers', type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    catalog = {row['name']: row for row in json.loads(args.catalog.read_text())['repositories']}
    archive = workspace / 'manifest/migration-evidence/mirror-sync'
    scripts = Path(__file__).resolve().parent
    journals = [workspace / (name + '-publication.jsonl') for name in
                ('source', 'recipe', 'arkweb-source', 'helper', 'restored-input')]
    for run in args.runs:
        pages = json.loads(subprocess.check_output(['gh', 'api', '--paginate', '--slurp',
            'repos/openharmony-qemu/mirror-sync/actions/runs/' + run + '/jobs?per_page=100'], text=True))
        complete = []
        for job in (job for page in pages for job in page['jobs']):
            match = re.fullmatch(r'synchronize \(([A-Za-z0-9_.-]+)\)', job['name'])
            if match and job['conclusion'] == 'success':
                complete.append(match[1])
            elif match and job['conclusion'] in ('failure', 'timed_out'):
                print('REVIEW FAILED JOB ' + run + ' ' + match[1] + ' ' + str(job['id']), flush=True)
        complete = list(dict.fromkeys(complete))
        missing = [name for name in complete if not (archive / (name + '-sync-' + run + '.json')).exists()]

        def collect(names):
            command = [sys.executable, str(scripts / 'collect_sync_evidence.py'), '--run-id', run,
                '--archive', str(archive), '--downloads', str(workspace / 'sync-artifacts'),
                '--imports', str(workspace / 'imported'), '--only', *names]
            for journal in journals:
                if journal.exists():
                    command += ['--source-journal', str(journal)]
            result = subprocess.run(command)
            if result.returncode:
                print('Evidence collection needs retry for run ' + run, flush=True)

        # Each reader owns distinct repository reports and artifact IDs. Remote
        # ref checks can run concurrently; branch initialization stays serialized.
        if missing:
            groups = [missing[i::args.evidence_workers] for i in range(args.evidence_workers)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.evidence_workers) as pool:
                for _ in pool.map(collect, (group for group in groups if group)):
                    pass
        for name in complete:
            if name not in catalog:
                raise ValueError('Unknown completed mirror: ' + name)
            receipt = workspace / 'imported' / (name + '.json')
            if (catalog[name].get('github_upstream') or receipt.exists() or
                    not (archive / (name + '-sync-' + run + '.json')).exists()):
                continue
            result = subprocess.run([sys.executable, str(scripts / 'import_mirror_baseline.py'),
                '--repository', 'openharmony-qemu/' + name, '--catalog', str(args.catalog.resolve()),
                '--directory', str(workspace / 'imported' / name), '--evidence', str(receipt)])
            if result.returncode:
                print('Baseline import needs retry: ' + name, flush=True)


if __name__ == '__main__':
    main()
