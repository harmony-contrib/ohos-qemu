#!/usr/bin/env python3
"""Exact fixed SystemUI build inputs; actual packaged UI is a separate gate."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = 'applications/standard/systemui'
REVISION = 'd0f84037f1975dd9bf13ccbd279bd2d9b56e8a01'
FILES = (('BUILD.gn', None, '2c4f623b726b7555c8207e562c8c293c3b0281ea1075e1bac7f460ec55325bcd'), ('build-profile.json5', 'fd1608e1a8694d5ffd90fd7cb08c7f8199907f438afbabb2d56b1f80940d1cda', '73d0df791ab3ecc81843585fbc30abd1baf66aa388d276a70ac93c03cc6e6847'), ('oh-package.json5', 'b3c50e8ffdda75fcf6003d7190cc91d170f640d08c8293130510891a1528ab7a', 'e8018bb67b3b5e4fbc2c93e414611c972ce6515ab53474918b8fd5e006f29ef8'), ('hvigor/hvigor-config.json5', 'da6e3d8ecba56149225a1bfdc2609836133f2b9a075a1fef23a4e020a4fe3476', '322eaec60323114fe17400b00062d98b8ad23ca6f6310651ffc9756622d5869f'))

def _validate_original(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


# Read-only complete SystemUI profile-output ancestry. The unchanged original
# four-file guard remains the authority for the complete projected predecessor.
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile

_PROFILE580_BEFORE = '2c4f623b726b7555c8207e562c8c293c3b0281ea1075e1bac7f460ec55325bcd'
_PROFILE580_AFTER = '7822ece692807e3b4868af02c34854254d6c195e086b963515140a6dab965370'
_PROFILE580_ASSETS = {'source_states.json': {'sha256': '8ef2b3d6750a2270e59df536814bbac130715ee694537cf4a0197e01f811a916', 'bytes': 490}, '0001-isolate-profile-SystemUI-publication.patch': {'sha256': '08bc56d5ffa1dd69e6b9d1c058586e73afa4d5283005ebd7ed0ed8003b576206', 'bytes': 5531}, 'before/BUILD.gn': {'sha256': '2c4f623b726b7555c8207e562c8c293c3b0281ea1075e1bac7f460ec55325bcd', 'bytes': 2363}, 'verify_source.py': {'sha256': '5e7061ce0c97f4b658deb98665599c84a834a50808fac48750e46ac054f8484e', 'bytes': 4848}, 'apply.sh': {'sha256': '5ea3319dba72a74e9db3670197e16bc4c5b99d619c73e41d590f69d0a39cd820', 'bytes': 258}, 'README.md': {'sha256': '04d38050564d3c2164044251e7098d9afabfaef2d3f673cf249b666925886eb7', 'bytes': 1390}}


def _profile580_capture(path):
    path = Path(path)
    if (not path.is_absolute() or path.resolve() != path or
            any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError('unaliased exact SystemUI profile-output source required')
    first = path.stat()
    if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1 or
            first.st_size > 4 * 1024 * 1024):
        raise ValueError('bounded one-link SystemUI profile-output source required')
    data = path.read_bytes()
    last = path.stat()
    fields = ('st_dev', 'st_ino', 'st_nlink', 'st_mode', 'st_uid', 'st_gid',
              'st_size', 'st_mtime_ns', 'st_ctime_ns')
    identity = tuple(getattr(first, name) for name in fields)
    if len(data) != first.st_size or identity != tuple(getattr(last, name) for name in fields):
        raise ValueError('SystemUI profile-output source changed during read')
    return data, identity


def _profile580_head(root):
    project = root / PROJECT
    actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse',
                                      '--verify', 'HEAD^{commit}'], text=True).strip()
    top = subprocess.check_output(['git', '-C', str(project), 'rev-parse',
                                   '--show-toplevel'], text=True).strip()
    if actual != REVISION or Path(top).resolve() != project:
        raise ValueError('exact actual SystemUI project HEAD/toplevel required')


def _profile580_cut(patch):
    lines = patch.splitlines(keepends=True)
    name = (PROJECT + '/BUILD.gn').encode()
    if lines[:2] != [b'--- a/' + name + b'\n', b'+++ b/' + name + b'\n']:
        raise ValueError('exact one-file SystemUI profile-output patch required')
    match = re.fullmatch(rb'@@ -1,([0-9]+) \+1,([0-9]+) @@\n', lines[2])
    before, after = [], []
    for line in lines[3:]:
        if line[:1] not in (b'-', b'+'):
            raise ValueError('one complete SystemUI BUILD replacement required')
        (before if line[:1] == b'-' else after).append(line[1:])
    left, right = b''.join(before), b''.join(after)
    if (match is None or len(before) != int(match[1]) or len(after) != int(match[2]) or
            not left or not right or left == right):
        raise ValueError('complete SystemUI BUILD replacement counts differ')
    return left, right


def _profile580_preceding(root):
    root = Path(root)
    if (not root.is_absolute() or root.resolve() != root or
            any(p.is_symlink() for p in (root, *root.parents))):
        raise ValueError('actual canonical SystemUI profile-output root required')
    actual = {relative: _profile580_capture(root / PROJECT / relative)
              for relative, _, _ in FILES}
    assets_root = Path(__file__).resolve().parent.parent / 'profile_outputs580'
    saved = {}
    for name, expected in _PROFILE580_ASSETS.items():
        path = assets_root / name
        observed = _profile580_capture(path)
        if (len(observed[0]) != expected['bytes'] or
                hashlib.sha256(observed[0]).hexdigest() != expected['sha256']):
            raise ValueError('fixed complete SystemUI profile-output asset differs: ' + name)
        saved[path] = observed
    manifest = json.loads(saved[assets_root / 'source_states.json'][0])
    if (manifest['schema'] != 'systemui580-profile-output-vector/v1' or
            manifest['projects'] != {PROJECT: REVISION} or
            manifest['files'] != {PROJECT + '/BUILD.gn': [_PROFILE580_BEFORE, _PROFILE580_AFTER]}):
        raise ValueError('exact whole one-file SystemUI profile-output vector required')
    prefix = saved[assets_root / 'before/BUILD.gn'][0]
    left, right = _profile580_cut(saved[assets_root / '0001-isolate-profile-SystemUI-publication.patch'][0])
    if (left != prefix or hashlib.sha256(prefix).hexdigest() != _PROFILE580_BEFORE or
            hashlib.sha256(actual['BUILD.gn'][0]).hexdigest() != _PROFILE580_AFTER):
        raise ValueError('exact complete SystemUI predecessor and actual final required')
    _profile580_head(root)
    if prefix.count(left) != 1:
        raise ValueError('unique complete SystemUI BUILD forward cut required')
    current = prefix.replace(left, right, 1)
    if current != actual['BUILD.gn'][0] or current.count(right) != 1:
        raise ValueError('complete actual SystemUI profile-output postimage differs')
    if current.replace(right, left, 1) != prefix:
        raise ValueError('complete SystemUI profile-output inverse differs')
    with tempfile.TemporaryDirectory(prefix='systemui-profile-output-ancestor-') as directory:
        view = Path(directory).resolve()
        for relative, captured in actual.items():
            ancestor = view / PROJECT / relative
            ancestor.parent.mkdir(parents=True, exist_ok=True)
            ancestor.write_bytes(prefix if relative == 'BUILD.gn' else captured[0])
            os.chmod(ancestor, stat.S_IMODE(captured[1][3]))
        if _validate_original(view, require_patched=True) is not True:
            raise ValueError('complete original four-file SystemUI guard must accept exact ancestor')
    _profile580_head(root)
    if (any(_profile580_capture(root / PROJECT / relative) != captured
            for relative, captured in actual.items()) or
            any(_profile580_capture(path) != captured for path, captured in saved.items())):
        raise ValueError('actual four-file SystemUI source or fixed assets changed during readonly proof')
    return True


def validate(root, require_patched=False):
    # Unknown and all older states retain the complete original rejection rules.
    path = Path(root) / PROJECT / 'BUILD.gn'
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != _PROFILE580_AFTER:
        return _validate_original(root, require_patched)
    return _profile580_preceding(root)
