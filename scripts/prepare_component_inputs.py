#!/usr/bin/env python3
"""Retrieve component-owned adaptation inputs; never apply patches or build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(argv, **kwargs):
    return subprocess.check_output(argv, env=dict(os.environ,
        GIT_LFS_SKIP_SMUDGE='1', GIT_TERMINAL_PROMPT='0'), **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True,
                        help='Local checkout of openharmony-qemu/manifest')
    parser.add_argument('--cache', type=Path, default=ROOT / '.qemu/components')
    parser.add_argument('--output', type=Path, default=ROOT / '.qemu/component-inputs')
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    documents = {}
    for name in ('adaptations.json', 'components.lock.json'):
        content = (manifest / name).read_bytes()
        committed = run(['git', '-C', str(manifest), 'show', 'HEAD:' + name])
        if content != committed:
            raise ValueError('Manifest input differs from its committed version: ' + name)
        documents[name] = json.loads(content)
    index, lock = documents['adaptations.json'], documents['components.lock.json']
    if not lock.get('complete'):
        raise ValueError('Component publication is incomplete; see manifest/migration-status.json')
    if lock.get('adaptations_sha256') != hashlib.sha256((manifest / 'adaptations.json').read_bytes()).hexdigest():
        raise ValueError('Component lock belongs to a different ownership index')
    heads = {r['name']: r['qemu_revision'] for r in lock['repositories']}
    tool = index['materializer']
    owners = set(index['repositories']) | {tool['repository']}
    if args.output.exists():
        raise ValueError('Output already exists; preserve it and select a fresh --output directory')
    args.cache.mkdir(parents=True, exist_ok=True)
    for name in sorted(owners):
        revision = heads.get(name, '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not re.fullmatch(r'[0-9a-f]{40}', revision):
            raise ValueError('Missing or invalid locked component: ' + name)
        checkout = args.cache / name / 'files'
        remote = 'https://github.com/openharmony-qemu/' + name + '.git'
        if not checkout.exists():
            checkout.parent.mkdir(parents=True, exist_ok=True)
            run(['git', 'clone', '--depth=1', '--filter=blob:none', '--no-checkout', '--single-branch',
                 '--branch', index['baseline_branch'], remote, str(checkout)])
        elif (run(['git', '-C', str(checkout), 'remote', 'get-url', 'origin']).decode().strip() != remote
              or run(['git', '-C', str(checkout), 'status', '--porcelain']).strip()):
            raise ValueError('Unexpected or modified component cache; preserving it: ' + name)
        run(['git', '-C', str(checkout), 'fetch', '--no-tags', '--depth=1', '--filter=blob:none',
             'origin', revision])
        run(['git', '-C', str(checkout), 'sparse-checkout', 'set', '--no-cone', '/.qemu/'])
        run(['git', '-C', str(checkout), 'checkout', '--detach', revision])
        print('Retrieved ' + name + ' ' + revision, flush=True)
    materializer = args.cache / tool['repository'] / 'files' / tool['path']
    if hashlib.sha256(materializer.read_bytes()).hexdigest() != tool['sha256']:
        raise ValueError('Component-owned materializer differs from the manifest')
    subprocess.run([sys.executable, str(materializer), '--index', str(manifest / 'adaptations.json'),
                    '--payload-root', str(args.cache.resolve()), '--output', str(args.output.resolve())], check=True)
    # Legacy entry points share relative imports with retained host/package tools.
    # Links preserve those interfaces without copying their implementation.
    migrated = {entry['path'] for entry in index['files']}
    for source in (ROOT / 'scripts').rglob('*'):
        relative = source.relative_to(ROOT)
        if str(relative) in migrated or not source.is_file() or '__pycache__' in relative.parts:
            continue
        destination = args.output / relative
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(os.path.relpath(source, destination.parent))
    receipt = dict(manifest_commit=run(['git', '-C', str(manifest), 'rev-parse', 'HEAD']).decode().strip(),
                   component_lock_sha256=hashlib.sha256((manifest / 'components.lock.json').read_bytes()).hexdigest(),
                   generated=True, editable=False, build_validated=False, runtime_validated=False)
    (args.output / '.component-inputs.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Component inputs are ready at ' + str(args.output) + '; no build or package was started.')


if __name__ == '__main__':
    main()
