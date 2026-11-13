#!/usr/bin/env python3
"""Audit created repositories and QEMU branch identities without changing refs."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import time

BRANCH = 'OpenHarmony-7.0-Release-qemu'


def graphql(query):
    for attempt in range(3):
        try:
            result = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=' + query],
                                    capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess([], 1, '', 'request timed out')
        if result.returncode == 0:
            value = json.loads(result.stdout)
            if value.get('errors'):
                raise RuntimeError(str(value['errors']))
            return value['data']
        if attempt == 2:
            raise RuntimeError(result.stderr[-1500:])
        time.sleep(3 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--created', type=Path, required=True)
    parser.add_argument('--imported', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-journal', type=Path)
    args = parser.parse_args()
    published = {}
    if args.source_journal and args.source_journal.exists():
        for record in map(json.loads, args.source_journal.read_text().splitlines()):
            if record.get('status') == 'published':
                published[record['name']] = record['qemu_commit']
    created = {r['name'] for r in map(json.loads, args.created.read_text().splitlines())
               if r['status'] == 'created'}
    projects = json.loads(args.catalog.read_text())['repositories']
    selected = [p for p in projects if p['name'] in created]
    observations = []
    for start in range(0, len(selected), 20):
        batch = selected[start:start + 20]
        fields = [f'r{i}: repository(owner: "openharmony-qemu", name: {json.dumps(p["name"])}) '
                  '{ name defaultBranchRef { name } '
                  f'ref(qualifiedName: "refs/heads/{BRANCH}") '
                  '{ target { ... on Commit { oid } } } }'
                  for i, p in enumerate(batch)]
        remote = graphql('query { ' + '\n'.join(fields) + ' }')
        for i, project in enumerate(batch):
            actual = remote[f'r{i}']
            if not actual:
                raise ValueError('Created repository is no longer accessible: ' + project['name'])
            baseline = {r['revision'] for r in project['inputs']}
            receipt = args.imported / (project['name'] + '.json')
            expected = (json.loads(receipt.read_text())['qemu_commit'] if receipt.exists()
                        else next(iter(baseline)) if len(baseline) == 1 else None)
            expected = published.get(project['name'], expected)
            revision = actual['ref']['target']['oid'] if actual['ref'] else None
            observations.append(dict(name=project['name'], qemu_revision=revision,
                default_branch=(actual['defaultBranchRef'] or {}).get('name'),
                expected_revision=expected, matches_expected=bool(expected and revision == expected),
                shared_baseline_requires_reconciliation=len(baseline) != 1))
        print(f'Verified {min(start + 20, len(selected))}/{len(selected)} repositories', flush=True)
    report = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        catalog_repositories=len(projects), created_repositories=len(selected),
        published_qemu_branches=sum(bool(r['qemu_revision']) for r in observations),
        expected_revision_matches=sum(r['matches_expected'] for r in observations),
        qemu_default_branches=sum(r['default_branch'] == BRANCH for r in observations),
        missing_repositories=[p['name'] for p in projects if p['name'] not in created],
        repositories=observations, build_validated=False, runtime_validated=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('repositories', 'missing_repositories')}))


if __name__ == '__main__':
    main()
