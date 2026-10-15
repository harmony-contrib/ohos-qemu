"""Reject unknown or mixed native child callback sources before patch 0004."""
import argparse
import hashlib
from pathlib import Path
import subprocess

PROJECT = 'foundation/ability/ability_runtime'
REVISION = '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'
BASE = PROJECT + '/frameworks/native/child_process/'
HASHES = {
    BASE + 'src/native_child_process.cpp': (
        'f8f844ed08e8dd8e72f79f1b39958e832a7c290c9a3132df0201aea8e6e7b05f',
        '07ac43284cb4c6da5b1085f33367458484e3e90bb23dbf58ed4b1c91a18834cb'),
    BASE + 'src/native_child_callback.cpp': (
        'b67464e24de268e234913e1b8719f6b4e62f04e82115eaccc03086f85a6d8c89',
        '19a959d9964b71e60f2fd14cd5a264166c57092480b51a1fa0bf3e0c66535679'),
    BASE + 'include/native_child_callback.h': (
        'fbf29076f2c6eaf440e3be54edab6ede957eee7f4906e229e7d68d2e4ce0db7e',
        'fe77e1d13bfd9dc9ddfcd8a1468b07c777dee604922dd86d5266d549d677353f'),
}


def validate(root, require_patched=False):
    root = Path(root).resolve()
    project = root / PROJECT
    if (project / '.git').exists():
        revision = subprocess.check_output(
            ['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != REVISION:
            raise ValueError('child callback requires pinned ability_runtime revision')
    states = set()
    for relative, hashes in HASHES.items():
        target = root / relative
        cursor = target
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError('child callback source contains a symlink')
            cursor = cursor.parent
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest not in hashes:
            raise ValueError('unknown child callback source; preserving user edits: ' + relative)
        states.add(hashes.index(digest))
    if len(states) != 1:
        raise ValueError('mixed child callback patch state; preserving user edits')
    repaired = states == {1}
    if require_patched and not repaired:
        raise ValueError('child callback lifecycle patch is required')
    return repaired


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
