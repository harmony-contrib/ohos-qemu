#!/usr/bin/env python3
"""Exact profile-output successor; no compilation, signing or runtime claim."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/systemui'
REVISION = 'd0f84037f1975dd9bf13ccbd279bd2d9b56e8a01'
BEFORE = '2c4f623b726b7555c8207e562c8c293c3b0281ea1075e1bac7f460ec55325bcd'
AFTER = '7822ece692807e3b4868af02c34854254d6c195e086b963515140a6dab965370'
FILES = (('BUILD.gn', BEFORE, AFTER),)
ASSETS = {'source_states.json': {'sha256': '8ef2b3d6750a2270e59df536814bbac130715ee694537cf4a0197e01f811a916', 'bytes': 490}, '0001-isolate-profile-SystemUI-publication.patch': {'sha256': '08bc56d5ffa1dd69e6b9d1c058586e73afa4d5283005ebd7ed0ed8003b576206', 'bytes': 5531}, 'before/BUILD.gn': {'sha256': '2c4f623b726b7555c8207e562c8c293c3b0281ea1075e1bac7f460ec55325bcd', 'bytes': 2363}}


def capture(path):
    path = Path(path)
    if (not path.is_absolute() or path.resolve() != path or
            any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError('unaliased exact SystemUI profile-output input required')
    first = path.stat()
    if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1 or
            first.st_size > 4 * 1024 * 1024):
        raise ValueError('bounded one-link SystemUI profile-output input required')
    raw = path.read_bytes()
    last = path.stat()
    fields = ('st_dev', 'st_ino', 'st_nlink', 'st_mode', 'st_uid', 'st_gid',
              'st_size', 'st_mtime_ns', 'st_ctime_ns')
    identity = tuple(getattr(first, name) for name in fields)
    if len(raw) != first.st_size or identity != tuple(getattr(last, name) for name in fields):
        raise ValueError('SystemUI profile-output input changed during read')
    return raw, identity


def proof():
    here = Path(__file__).resolve().parent
    saved = {}
    for name, expected in ASSETS.items():
        path = here / name
        observed = capture(path)
        if len(observed[0]) != expected['bytes'] or hashlib.sha256(observed[0]).hexdigest() != expected['sha256']:
            raise ValueError('fixed SystemUI profile-output asset differs: ' + name)
        saved[path] = observed
    value = json.loads(saved[here / 'source_states.json'][0])
    if (value['schema'] != 'systemui580-profile-output-vector/v1' or
            value['projects'] != {PROJECT: REVISION} or
            value['files'] != {PROJECT + '/BUILD.gn': [BEFORE, AFTER]}):
        raise ValueError('complete exact SystemUI profile-output vector required')
    prefix = saved[here / 'before/BUILD.gn'][0]
    lines = saved[here / '0001-isolate-profile-SystemUI-publication.patch'][0].splitlines(keepends=True)
    name = (PROJECT + '/BUILD.gn').encode()
    if lines[:2] != [b'--- a/' + name + b'\n', b'+++ b/' + name + b'\n']:
        raise ValueError('single exact SystemUI BUILD patch required')
    match = re.fullmatch(rb'@@ -1,([0-9]+) \+1,([0-9]+) @@\n', lines[2])
    before, after = [], []
    for line in lines[3:]:
        if line[:1] not in (b'-', b'+'):
            raise ValueError('one complete SystemUI BUILD replacement required')
        (before if line[:1] == b'-' else after).append(line[1:])
    left, right = b''.join(before), b''.join(after)
    if (match is None or len(before) != int(match[1]) or len(after) != int(match[2]) or
            left != prefix or not left or not right or left == right or
            hashlib.sha256(left).hexdigest() != BEFORE or
            hashlib.sha256(right).hexdigest() != AFTER):
        raise ValueError('complete SystemUI BUILD predecessor/postimage differs')
    if prefix.count(left) != 1:
        raise ValueError('unique complete SystemUI BUILD forward cut required')
    current = prefix.replace(left, right, 1)
    if current != right or current.count(right) != 1 or current.replace(right, left, 1) != prefix:
        raise ValueError('complete SystemUI BUILD forward/inverse closure required')
    return saved


def validate(root, require_patched=False):
    saved = proof()
    observed = validate_component(root, PROJECT, REVISION, FILES, require_patched)
    if any(capture(path) != before for path, before in saved.items()):
        raise ValueError('fixed SystemUI profile-output assets changed during validation')
    return observed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    state = validate(args.source_root.resolve(), args.require_patched)
    print(json.dumps({'state': 'final' if state else 'before', 'scope': 'source_only_NOT_runtime_acceptance'}))
