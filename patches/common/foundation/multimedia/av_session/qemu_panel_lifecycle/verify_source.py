#!/usr/bin/env python3
"""Exact four-file epochs; source preparation never accepts QEMU behavior."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

HERE = Path(__file__).resolve().parent
MANIFEST_SHA = '253854ec5d575b62a08e8f89c902b1ae3faeed81f950820f8ff4b838dd8f5819'
EXPECTED_PROJECTS = {'foundation/multimedia/av_session': '47a2014c7040a039303109f0ebe817ebc31bfe6b'}
EXPECTED_PATHS = ('foundation/multimedia/av_session/avvolumepanel/avvolumepanel.js', 'foundation/multimedia/av_session/frameworks/js/napi/session/include/napi_avcast_picker_helper.h', 'foundation/multimedia/av_session/frameworks/js/napi/session/src/napi_avcast_picker_helper.cpp', 'foundation/multimedia/av_session/frameworks/js/napi/session/src/napi_async_callback.cpp')
EXPECTED_READONLY = {'foundation/multimedia/av_session/frameworks/js/napi/session/include/napi_async_callback.h': '79c45cd07afe87cd92a2f3ca348ee4169b5279e58baf640b098ed6c65e3cb922'}


def manifest():
    body = (HERE / 'source_states.json').read_bytes()
    if hashlib.sha256(body).hexdigest() != MANIFEST_SHA:
        raise ValueError('Fixed complete AV panel source manifest changed')
    value = json.loads(body)
    if (value.get('schema') != 'avpanel579-source-vector/v1' or
            value['projects'] != EXPECTED_PROJECTS or set(value['files']) != set(EXPECTED_PATHS) or
            set(value['previous_panel_final']) != set(EXPECTED_PATHS) or
            set(value['previous_owned_final']) != set(EXPECTED_PATHS) or
            value['readonly'] != EXPECTED_READONLY):
        raise ValueError('Fixed complete four-source and async-prerequisite vector required')
    for name, hashes in value['files'].items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name or len(hashes) != 2 or hashes[0] == hashes[1]:
            raise ValueError('Finite exact source path/vector required: ' + name)
        if not any(name.startswith(project + '/') for project in value['projects']):
            raise ValueError('Source outside the actual AVSession project: ' + name)
        if any(re.fullmatch('[a-f0-9]{64}', item) is None for item in hashes):
            raise ValueError('Exact whole source digests required')
    return value


def target(root, name):
    path = root / name
    for parent in path.relative_to(root).parents:
        if (root / parent).is_symlink():
            raise ValueError('Source parent symlink rejected: ' + name)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Complete regular source missing: ' + name)
    return path


def heads(root, value):
    for project, expected in value['projects'].items():
        path = root / project
        if path.is_symlink() or not path.is_dir():
            raise ValueError('Actual regular project missing: ' + project)
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != expected:
            raise ValueError('Actual fixed project HEAD required: ' + project)


def prerequisites(root, value):
    for name, expected in value['readonly'].items():
        if hashlib.sha256(target(root, name).read_bytes()).hexdigest() != expected:
            raise ValueError('Actual async reference-storage prerequisite changed: ' + name)


def vector(root, value):
    observed = []
    for name, hashes in value['files'].items():
        digest = hashlib.sha256(target(root, name).read_bytes()).hexdigest()
        if digest not in hashes:
            raise ValueError('Unknown actual source bytes: ' + name)
        if hashes[0] != hashes[1]:
            observed.append(hashes.index(digest))
    if not observed or len(set(observed)) != 1:
        raise ValueError('Mixed AV panel source vector rejected')
    return 'before' if observed[0] == 0 else 'final'


def vector_state(root, value):
    heads(root, value)
    prerequisites(root, value)
    return vector(root, value)


def state(root, value=None):
    value = manifest() if value is None else value
    heads(root, value)
    prerequisites(root, value)
    actual = {name: hashlib.sha256(target(root, name).read_bytes()).hexdigest() for name in value['files']}
    for label, expected in (('before', {n: pair[0] for n, pair in value['files'].items()}),
                            ('final', {n: pair[1] for n, pair in value['files'].items()}),
                            ('previous', value['previous_panel_final']),
                            ('previous_owned', value['previous_owned_final'])):
        if actual == expected:
            return label
    raise ValueError('Unknown or mixed complete AV panel source epoch preserved')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    observed = state(args.source_root.resolve())
    if args.require_final and observed != 'final':
        raise ValueError('Complete new final AV panel source vector required; verify never migrates')
    print(json.dumps({'state': observed, 'scope': 'source_only_NOT_runtime_acceptance'}))


if __name__ == '__main__':
    main()
