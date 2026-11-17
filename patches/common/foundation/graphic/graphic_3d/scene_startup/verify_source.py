"""Exact fixed revision/source guard for scene adapter initialization repair."""
import argparse
import hashlib
from pathlib import Path
import subprocess

PROJECT = 'foundation/graphic/graphic_3d'
REVISION = 'b2d7af910f2d4b941697630020b0940245d5bd99'
HASHES = {
    PROJECT + '/3d_scene_adapter/src/scene_adapter.cpp': (
        '7526b5c062075bd73986b390a02b6ef9550ca61e948c6991a62fab6440d1d259',
        '96bc804ab887068cd3ccf717c0f146463a0deb9f7e4885b700d277e70d879aed'),
    PROJECT + '/kits/js/src/RenderContextJS.cpp': (
        'ac6d4decfe475cb03dc8fe54538b452ae4239e6bb988e79d118d2120fa0e5ef5',
        '38bdcbf842147ae7b4aaaa4e58da32c660b64f340f528341fe3d1d295f71e45c'),
}


def validate(root, require_patched=False):
    root = Path(root).resolve()
    project = root / PROJECT
    if (project / '.git').exists():
        actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != REVISION:
            raise ValueError('scene startup requires fixed graphic_3d revision')
    states = set()
    for relative, hashes in HASHES.items():
        target = root / relative
        cursor = target
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError('scene startup source contains a symlink')
            cursor = cursor.parent
        value = hashlib.sha256(target.read_bytes()).hexdigest()
        if value not in hashes:
            raise ValueError('unknown scene startup source; preserving edits: ' + relative)
        states.add(hashes.index(value))
    if len(states) != 1:
        raise ValueError('mixed scene startup patch state; preserving edits')
    repaired = states == {1}
    if require_patched and not repaired:
        raise ValueError('scene startup repair is required')
    return repaired


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
