#!/usr/bin/env python3
"""Resume explicitly reviewed publication phases after source baselines arrive."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from component_heads import published_heads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    selection = json.loads(args.selection.read_text())
    journals = [workspace / phase['journal'] for phase in selection['phases']]
    available = set(published_heads(journals))
    available.update(path.stem for path in (workspace / 'imported').glob('*.json'))
    baseline = workspace / 'baseline-publication.jsonl'
    if baseline.exists():
        for row in map(json.loads, baseline.read_text().splitlines()):
            if row['status'] in ('published', 'preserved_existing'):
                available.add(row['name'])
    for phase in selection['phases']:
        ready = [name for name in phase['repositories'] if name in available]
        pending = sorted(set(phase['repositories']) - available)
        print(phase['journal'] + ': ' + str(len(ready)) + ' ready; waiting for ' + ', '.join(pending), flush=True)
        if not ready:
            continue
        command = [sys.executable, str(Path(__file__).with_name('publish_source_changes.py')),
            '--exports', str(workspace / phase['exports']), '--objects', str(workspace / 'source-commits'),
            '--imports', str(workspace / 'imported'), '--journal', str(workspace / phase['journal'])]
        for journal in journals:
            if journal.exists():
                command += ['--parent-journal', str(journal)]
        subprocess.run(command + ['--only', *ready], check=True)


if __name__ == '__main__':
    main()
