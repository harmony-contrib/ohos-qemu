#!/usr/bin/env python3
"""Fetch exact sources of existing GN/SDK tools, never a moving branch.

GitHub mirrors are preferred. A sparse partial checkout retains Git provenance
without downloading LLVM's unrelated tests, frontends or tool implementations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from prepare_m144_release_cache import git

TOOLS = {
    'gn': {'revision': '6e0b557db44b3c164094e57687d20ba036a80667',
           'url': 'https://github.com/timniederhausen/gn.git', 'paths': None,
           'initial_tag': 'f0be552ab5313bb64a75c9365af22155d979949f'},
    'sdk-llvm15': {'revision': '3f002d04ba6b3a7659c601207c89d3a896b82546',
                   'url': 'https://github.com/openharmony/third_party_llvm-project.git',
                   'paths': ['/libunwind/include/', '/libunwind/src/', '/libunwind/cmake/',
                             '/libunwind/CMakeLists.txt', '/compiler-rt/include/',
                             '/compiler-rt/lib/builtins/', '/compiler-rt/cmake/',
                             '/compiler-rt/CMakeLists.txt', '/llvm/cmake/',
                             '/llvm/CMakeLists.txt', '/cmake/']},
}


def run(root, *arguments, timeout=240):
    result = git(root, *arguments, timeout=timeout)
    if result.returncode:
        raise ValueError('fixed tool-source Git operation failed: ' + result.stderr[-2000:])
    return result.stdout.strip()


def prepare(root, name, no_fetch=False):
    spec = TOOLS[name]
    target = root / name
    if root.is_symlink() or target.is_symlink():
        raise ValueError('tool source root/checkout must not alias another location')
    if not target.exists():
        if no_fetch:
            raise ValueError('fixed tool source absent while fetch is disabled: ' + name)
        target.mkdir()
        run(target, 'init')
        run(target, 'remote', 'add', 'origin', spec['url'])
        run(target, 'fetch', '--no-tags', '--depth=1', '--filter=blob:none',
            'origin', spec['revision'], timeout=600)
        if spec['paths']:
            run(target, 'sparse-checkout', 'set', '--no-cone', *spec['paths'])
        run(target, 'checkout', '--detach', spec['revision'], timeout=600)
    if (run(target, 'rev-parse', 'HEAD') != spec['revision'] or
            run(target, 'remote', 'get-url', 'origin') != spec['url'] or
            run(target, 'status', '--porcelain', '--untracked-files=all')):
        raise ValueError('unknown, dirty or differently pinned tool source: ' + name)
    if name == 'gn':
        # The official version generator needs the real fixed ancestry/tag,
        # not a fabricated commit-position header in a shallow checkout.
        if run(target, 'rev-parse', '--is-shallow-repository') == 'true':
            if no_fetch:
                raise ValueError('GN ancestry absent while fetch is disabled')
            run(target, 'fetch', '--unshallow', '--no-tags', 'origin', spec['revision'], timeout=600)
        tag = git(target, 'rev-parse', 'refs/tags/initial-commit', timeout=30)
        if tag.returncode or tag.stdout.strip() != spec['initial_tag']:
            if no_fetch:
                raise ValueError('GN fixed initial tag absent/different while fetch is disabled')
            run(target, 'fetch', '--no-tags', 'origin',
                spec['initial_tag'] + ':refs/tags/initial-commit', timeout=240)
        if (run(target, 'rev-parse', 'refs/tags/initial-commit') != spec['initial_tag'] or
                run(target, 'describe', 'HEAD', '--abbrev=12', '--match', 'initial-commit') !=
                'initial-commit-2304-g6e0b557db44b'):
            raise ValueError('GN fixed version ancestry differs')
    observed = {}
    for relative in run(target, 'ls-files').splitlines():
        path = target / relative
        if path.is_file() and not path.is_symlink():
            observed[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'source': str(target), 'revision': spec['revision'], 'remote': spec['url'],
            'materialized_files': observed, 'scope': 'fixed_existing_tool_sources_NOT_guest_acceptance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--no-fetch', action='store_true')
    parser.add_argument('tools', choices=tuple(TOOLS), nargs='+')
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        raise ValueError('tool-source evidence already exists')
    args.root.mkdir(parents=True, exist_ok=True)
    records = {name: prepare(args.root, name, args.no_fetch) for name in args.tools}
    args.evidence.write_text(json.dumps({'tools': records, 'first_artifact_behavior_gate_passed': False}, indent=2) + '\n')
    print('fixed GN/SDK tool sources prepared: ' + ', '.join(records))


if __name__ == '__main__':
    main()
