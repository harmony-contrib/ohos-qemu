#!/usr/bin/env python3
"""Prepare exact original/new privacy vectors; no feature or permission bypass."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import sys
HERE = Path(__file__).resolve().parent
PATCHES = next(p for p in HERE.parents if p.name == 'patches')
HELPER_SHA = 'afb7560daa888493878e6d107baf1487f48c09fb6fe028fd89b331842e2b83ee'
MANIFEST_SHA = 'ef7b0f0cfa6865f57d7e5101672cf34dec0eb5976fc3ac7cd9370f4cdf464f2a'
EXPECTED_PATHS = ('foundation/multimedia/audio_framework/services/audio_service/client/src/capturer_in_client.cpp', 'foundation/multimedia/audio_framework/services/audio_service/server/include/audio_privacy_ui_ext_connection.h', 'foundation/multimedia/audio_framework/services/audio_service/server/include/capturer_in_server.h', 'foundation/multimedia/audio_framework/services/audio_service/server/src/audio_server.cpp', 'foundation/multimedia/audio_framework/services/audio_service/server/src/capturer_in_server.cpp')
EXPECTED_PROJECTS = {'foundation/multimedia/audio_framework': '6932fa64335b8272ca4a59de7808ab0d6c9eae7a'}
helper_path = PATCHES / 'lib/guarded_source_vector579.py'
if hashlib.sha256(helper_path.read_bytes()).hexdigest() != HELPER_SHA:
    raise ValueError('exact original transactional source helper required')
old = sys.modules.get('guarded_source_vector579')
if old is not None and Path(old.__file__).resolve() != helper_path:
    raise ValueError('foreign cached transactional source helper')
sys.path.insert(0, str(PATCHES / 'lib'))
import guarded_source_vector579 as g
if Path(g.__file__).resolve() != helper_path or hashlib.sha256(helper_path.read_bytes()).hexdigest() != HELPER_SHA:
    raise ValueError('transactional source helper origin/bytes changed')


def observed(root, value):
    return {name: g.sha(g.target(root, name).read_bytes()) if g.target(root, name).exists() else None
            for name in value['files']}


def phase(root, value):
    actual = observed(root, value)
    for label, wanted in (('before', {n: p[0] for n, p in value['files'].items()}),
                          ('final', {n: p[1] for n, p in value['files'].items()}),
                          ('previous', value['previous_privacy_final'])):
        if actual == wanted:
            return label
    raise ValueError('unknown or mixed complete privacy source vector preserved')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--require-final', action='store_true')
    mode.add_argument('--rewind', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    if hashlib.sha256((HERE / 'source_states.json').read_bytes()).hexdigest() != MANIFEST_SHA:
        raise ValueError('fixed complete five-file source manifest changed')
    value = g.load(HERE)
    if set(value['files']) != set(EXPECTED_PATHS) or value['projects'] != EXPECTED_PROJECTS or set(value['previous_privacy_final']) != set(EXPECTED_PATHS):
        raise ValueError('exact five-file privacy source epoch required')
    previous = dict(value, files={n: [pair[0], value['previous_privacy_final'][n]]
                                 for n, pair in value['files'].items()})
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('source lock directory is linked')
    marker.mkdir(exist_ok=True)
    fd = os.open(marker / (g.sha(str(HERE).encode()) + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        g.heads(root, value)
        current = phase(root, value)
        if args.require_final:
            if current != 'final':
                raise ValueError('new complete final privacy source vector required; verify never migrates')
        elif args.rewind:
            if current != 'before':
                active = previous if current == 'previous' else value
                reverse = dict(active, files={n: list(reversed(pair)) for n, pair in active['files'].items()})
                patch = '0000-legacy-product-source.patch' if current == 'previous' else '0001-product-source.patch'
                g.apply(root, HERE, reverse, reverse=True, patch_name=patch)
            if phase(root, value) != 'before':
                raise ValueError('complete original source prefix not restored')
        elif current != 'final':
            upgrading = current == 'previous'
            if upgrading:
                reverse = dict(previous, files={n: list(reversed(pair)) for n, pair in previous['files'].items()})
                g.apply(root, HERE, reverse, reverse=True, patch_name='0000-legacy-product-source.patch')
            try:
                g.apply(root, HERE, value)
                if phase(root, value) != 'final':
                    raise ValueError('complete new privacy source transaction failed')
            except BaseException as error:
                if upgrading:
                    # The original helper restores its exact input on failure.
                    # Restore the prior known epoch only from complete before;
                    # unknown concurrent bytes are preserved and reported.
                    if phase(root, value) != 'before':
                        raise RuntimeError('privacy upgrade rollback incomplete; preserve unknown source') from error
                    g.apply(root, HERE, previous, patch_name='0000-legacy-product-source.patch')
                    if phase(root, value) != 'previous':
                        raise RuntimeError('complete previous privacy epoch not restored') from error
                raise
    print('Exact privacy source prepared; new-image compilation and QEMU acceptance remain pending')


if __name__ == '__main__':
    main()
