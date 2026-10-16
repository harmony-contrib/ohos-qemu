#!/usr/bin/env python3
"""Pin all three telephony projects and exact whole-component file states."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

COMPONENT = Path(__file__).resolve().parent
PROJECT = ''
PROJECTS = {
    'base/telephony/core_service': '504dcba74da128ed446967e328e5c7162bfebbe2',
    'base/telephony/state_registry': '2327cba6f48f4274b269e530c48a919e2eed28b7',
    'base/telephony/ril_adapter': '81fac83292857fcd9bee90808a81d8ad7224b4e0',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    path = COMPONENT / 'source_states.json'
    if path.is_symlink():
        raise ValueError('communication manifest must be owned')
    data = json.loads(path.read_text())
    if data['projects'] != PROJECTS or len(set(data['files'])) != len(data['files']):
        raise ValueError('unexpected pinned telephony projects or duplicate target')
    for name in data['files']:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or not any(
                name.startswith(project + '/') for project in PROJECTS):
            raise ValueError('unsafe telephony source target')
    if set(data['states']) != {'original', 'final'} or any(
            set(state) != set(data['files']) for state in data['states'].values()):
        raise ValueError('incomplete communication whole-component states')
    patches = sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if {path.name for path in patches} != set(data['patches']):
        raise ValueError('unknown communication patch stack')
    for path in patches:
        if path.is_symlink() or digest(path.read_bytes()) != data['patches'][path.name]:
            raise ValueError('unknown communication patch bytes')
    return data


def validate(root, require_patched=False, check_revision=True):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('telephony source root must be owned')
    root = root.resolve()
    data = manifest()
    values = {}
    for name in data['files']:
        target = root / name
        cursor = target
        while cursor != root:
            if cursor.is_symlink() or (cursor != target and cursor.exists() and not cursor.is_dir()):
                raise ValueError('telephony input or ancestor is not owned: ' + name)
            cursor = cursor.parent
        if not target.is_file():
            raise ValueError('telephony input must be an owned regular file: ' + name)
        values[name] = digest(target.read_bytes())
    if check_revision:
        for project, revision in PROJECTS.items():
            head = subprocess.check_output(['git', '-C', str(root / project), 'rev-parse', 'HEAD'], text=True).strip()
            if head != revision:
                raise ValueError('communication component requires all pinned project HEADs')
    for name, state in data['states'].items():
        if values == state and (not require_patched or name == 'final'):
            return name
    raise ValueError('unknown or mixed communication source bytes; source preserved')
