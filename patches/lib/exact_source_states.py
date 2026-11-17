#!/usr/bin/env python3
"""Fail closed on unknown/partial component edits before applying any file."""
import hashlib
from pathlib import Path
import subprocess


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_component(root, project_name, revision, files, require_patched=False):
    root = Path(root).resolve()
    project = root / project_name
    if (project / '.git').exists():
        actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != revision:
            raise ValueError('component requires the pinned OpenHarmony 7.0 project commit')
    states = []
    for relative, original_sha, repaired_sha in files:
        target = project / relative
        cursor = target
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError('component input contains a symlink: ' + relative)
            cursor = cursor.parent
        if original_sha is None and not target.exists():
            if require_patched:
                raise ValueError('missing patched component file: ' + relative)
            states.append(False)
            continue
        value = digest(target.read_bytes())
        if value == repaired_sha:
            states.append(True)
        elif value == original_sha and not require_patched:
            states.append(False)
        else:
            raise ValueError('unknown/incomplete component edit; preserving source: ' + relative)
    if len(set(states)) != 1:
        raise ValueError('partial component state; preserving all source files')
    return states[0]
