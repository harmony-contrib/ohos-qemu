#!/usr/bin/env python3
"""Exact complete historical states only; E provenance remains separately pinned."""
from pathlib import Path
import hashlib
import json
import stat
import subprocess
PROJECT = 'base/theme/wallpaper_mgr'
REVISION = '42256bdeaa504da4ae4d038c24d42a4601e3a6cf'
MANIFEST_SHA256 = 'ad58161650eb8b754eda9cfd26da577f948ea123816f5a77910b9092c993027d'


def manifest():
    path = Path(__file__).resolve().parent / 'lifecycle/manifest-18.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError('reviewed exact renderer lifecycle manifest changed')
    value = json.loads(raw)
    if value['project'] != PROJECT or value['revision'] != REVISION:
        raise ValueError('renderer project/revision differs')
    return value


FILES = tuple((name, digest, manifest()['states']['F'][name])
              for name, digest in manifest()['states']['pristine'].items())


def state(root, require_patched=False, check_revision=True):
    root = Path(root).absolute()
    if root.resolve() != root or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('canonical source root required')
    project = root / PROJECT
    if check_revision and (project / '.git').exists():
        actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != REVISION: raise ValueError('pinned OpenHarmony project revision required')
    states = manifest()['states']; actual = {}
    for name in states['F']:
        target = project / name
        for parent in (target, *target.parents):
            if parent == root.parent: break
            if parent.is_symlink(): raise ValueError('aliased component input: ' + name)
        if not target.exists(): actual[name] = None; continue
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('single-link regular component input required: ' + name)
        actual[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    matches = [key for key, expected in states.items() if actual == expected]
    if len(matches) != 1 or (require_patched and matches[0] != 'F'):
        raise ValueError('unknown/incomplete renderer component state; preserving all source files')
    return matches[0]


def validate(root, require_patched=False):
    return state(root, require_patched=require_patched) == 'F'
