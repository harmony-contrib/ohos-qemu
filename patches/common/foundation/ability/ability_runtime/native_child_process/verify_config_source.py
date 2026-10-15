"""Exact config source after existing argument patches and after boundary repair."""
import hashlib
from pathlib import Path
import subprocess

PROJECT = 'foundation/ability/ability_runtime'
REVISION = '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'
RELATIVE = 'frameworks/native/child_process/src/native_child_process.cpp'
ORIGINAL = 'c30d5fbf870d6e34d7080585c7b5a8f4aa1b0423c5924f2f07917596884cfaba'
REPAIRED = 'f8f844ed08e8dd8e72f79f1b39958e832a7c290c9a3132df0201aea8e6e7b05f'


def validate(root, require_patched=False):
    root = Path(root).resolve(); project = root/PROJECT; target = project/RELATIVE
    if (project/'.git').exists():
        actual = subprocess.check_output(['git','-C',str(project),'rev-parse','HEAD'],text=True).strip()
        if actual != REVISION:raise ValueError('child config requires pinned ability_runtime revision')
    cursor = target
    while cursor != root:
        if cursor.is_symlink():raise ValueError('child config source contains a symlink')
        cursor = cursor.parent
    value = hashlib.sha256(target.read_bytes()).hexdigest()
    if value == REPAIRED:return True
    if value == ORIGINAL and not require_patched:return False
    raise ValueError('unknown child config source; preserving user edits')


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--require-patched',action='store_true')
    args=parser.parse_args();validate(args.source_root,args.require_patched)
