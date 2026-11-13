#!/usr/bin/env python3
"""Update the independent mirror-sync registry; never install component workflows.

This only prepares a reviewable registry change. Commit/push it from the separate
mirror-sync checkout after granting its App/PAT access to the enabled targets.
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--created', type=Path, required=True)
    parser.add_argument('--mirror-sync', type=Path, required=True)
    args = parser.parse_args()
    target = args.mirror_sync / 'repositories.json'
    existing = ({row['name']: row for row in json.loads(target.read_text())['repositories']}
                if target.exists() else {})
    created = {x['name'] for x in map(json.loads, args.created.read_text().splitlines())
               if x['status'] == 'created'}
    entries = []
    for project in json.loads(args.catalog.read_text())['repositories']:
        if not project.get('auto_sync'):
            continue
        entries.append(dict(name=project['name'], upstream_url=project['upstream_url'],
            baseline_revisions=list(dict.fromkeys(x['revision'] for x in project['inputs'])),
            large_files='git-lfs', enabled=project['name'] in created))
        if 'bounded_transfer' in existing.get(project['name'], {}):
            value = existing[project['name']]['bounded_transfer']
            if not isinstance(value, bool):
                raise ValueError('bounded_transfer must be boolean: ' + project['name'])
            entries[-1]['bounded_transfer'] = value
    target.write_text(json.dumps(dict(schema_version=1, organization='openharmony-qemu',
        repositories=entries), indent=2) + '\n')
    print(f'{target}: {len(entries)} mirrors, {sum(x["enabled"] for x in entries)} enabled')


if __name__ == '__main__':
    main()
