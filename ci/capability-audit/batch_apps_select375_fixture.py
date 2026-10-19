"""Materialize reviewed actual-source bytes in a caller-owned host scratch only."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/settings/share_picker_choose'


def installer():
    spec = importlib.util.spec_from_file_location('select375_installer', COMPONENT / 'apply.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def materialize(root, historical=False):
    root = Path(root)
    if not root.is_dir() or root.resolve() != root:
        raise ValueError('canonical owned scratch directory required')
    name = 'predecessor-v1.json' if historical else 'predecessor.json'
    value = json.loads((COMPONENT / 'tests' / name).read_bytes())
    for relative, row in value['files'].items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('unsafe retained source path')
        data = gzip.decompress(base64.b64decode(row['gzip_base64'], validate=True))
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('retained actual-source fixture changed')
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            raise ValueError('source fixture never overwrites an existing path')
        target.write_bytes(data)
    return value
