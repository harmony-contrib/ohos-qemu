#!/usr/bin/env python3
"""Exact complete six-file RTT boundary guard; no compilation/runtime proof."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def state(root):
    manifest = json.loads((HERE / 'source_states.json').read_text())
    project = root / manifest['project']
    head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    if head != manifest['revision']: raise ValueError('Fixed actual CallManager revision required')
    states = []
    for name, hashes in manifest['files'].items():
        target = project / name
        if target.is_symlink() or not target.is_file(): raise ValueError('Complete regular source required: ' + name)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest not in hashes: raise ValueError('Unknown actual source bytes: ' + name)
        states.append(hashes.index(digest))
    if len(set(states)) != 1: raise ValueError('Mixed RTT boundary vector rejected')
    return 'before' if states[0] == 0 else 'final'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args(); result = state(args.source_root.resolve())
    if args.require_final and result != 'final': raise ValueError('Complete final RTT boundary vector required')
    print(json.dumps({'state': result, 'scope': 'source_only_NOT_runtime_acceptance'}))


if __name__ == '__main__': main()
