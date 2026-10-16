#!/usr/bin/env python3
"""Accept only exact whole-project component states at the pinned project HEAD."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

COMPONENT = Path(__file__).resolve().parent
PROJECT = 'base/location/location'
REVISION = '5a0c49c2adb0623fdac73f76e4f98f2e57674c00'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    path = COMPONENT / 'source_states.json'
    if path.is_symlink():
        raise ValueError('location state manifest must be an owned file')
    data = json.loads(path.read_text())
    if data['project'] != PROJECT or data['revision'] != REVISION:
        raise ValueError('unexpected pinned location project')
    if len(set(data['files'])) != len(data['files']):
        raise ValueError('duplicate location source target')
    for name in data['files']:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:
            raise ValueError('unsafe location source target')
    if set(data['states']) != {'original', 'prefix_1', 'prefix_2', 'final'} or any(
            set(state) != set(data['files']) for state in data['states'].values()):
        raise ValueError('incomplete location whole-component state')
    patches = sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if {path.name for path in patches} != set(data['patches']):
        raise ValueError('unknown location patch stack')
    for path in patches:
        if path.is_symlink() or digest(path.read_bytes()) != data['patches'][path.name]:
            raise ValueError('unknown location patch bytes: ' + path.name)
    return data


def validate(root, require_patched=False, check_revision=True):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('location source root must be an owned directory')
    root = root.resolve()
    data = manifest()
    project = root / PROJECT
    values = {}
    for name in data['files']:
        target = project / name
        cursor = target
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError('location input contains a symlink: ' + name)
            cursor = cursor.parent
        if not target.is_file() or not target.resolve().is_relative_to(root):
            raise ValueError('location input must be an owned regular file: ' + name)
        values[name] = digest(target.read_bytes())
    if check_revision:
        if not (project / '.git').exists():
            raise ValueError('location project Git HEAD is required')
        head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if head != REVISION:
            raise ValueError('location component requires the pinned OpenHarmony project HEAD')
    for state, expected in data['states'].items():
        if values == expected and (not require_patched or state == 'final'):
            return state
    raise ValueError('unknown or mixed location component bytes; source preserved')
