#!/usr/bin/env python3
"""Repair exact generated Mesa recipes after their base installers refresh them."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

COMPONENT = Path(__file__).resolve().parent
PROJECT = Path('device/qemu')
REVISION = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
MAPPING_GN_SHA = 'f1589da299160eda36104125459c7bebddf02b38cfb7ba1683cdb124e4d0b59e'
LIFETIME_INPUT_PATCH = COMPONENT / '0003-track-import-lifetime-backport-input.patch'
# Mixed exact states are legitimate: the base installer refreshes the Python
# payload while its GN action is already repaired. Unknown bytes are not.
FILES = (
    ('common/virt_full/hardware/gpu/build_qemu_mesa.py',
     '0f9925d65c70039182b8e299fced4c4dfc46870d03bed2dcb3fd69ea95b5cd79',
     '03e45a069e5aa14d4b710478971771d174fc4e7bd367a22376b1051cf210ed11',
     '0001-integrate-shared-64bit-mapping-backport.patch', False),
    ('common/virt_full/hardware/gpu/BUILD.gn',
     '6ce2236c14b20f4899507162363be49cb2bfa2f3b8a852434044eebcaa70bdb1',
     'b56b266c535d01bbb36c184bee26339a35af63221fcd93630ba9ee8212242af0',
     '0001-integrate-shared-64bit-mapping-backport.patch', False),
    ('arm_virt/linux_full_armv7a/build_armv7a_mesa.py',
     '9615946849f1973b595ded1b0c4225c4714d567132f8b1663c318b5bf84d8f0a',
     '22116ddc5d03bb440596e02c1336541761614c790b4a12bca67ce63eb5d10169',
     '0002-integrate-armv7a-mapping-backport.patch', True),
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def selected(root):
    result = []
    for relative, original, repaired, patch, optional in FILES:
        path = root / PROJECT / relative
        current = path
        while current != root:
            if current.is_symlink():
                raise ValueError('symlink in Mesa recipe inputs')
            current = current.parent
        if optional and not path.exists():
            continue  # The ARMv7 product has not been generated in this checkout.
        actual = digest(path)
        previous = (MAPPING_GN_SHA,) if relative.endswith('/BUILD.gn') else ()
        if actual not in (original, repaired) + previous:
            raise ValueError('unknown Mesa build recipe; preserving all source files: ' + relative)
        result.append((str(PROJECT / relative), actual, repaired, COMPONENT / patch))
    return result


def apply_file(root, relative, actual, repaired, patch):
    if actual == repaired:
        return
    if actual != MAPPING_GN_SHA:
        subprocess.run(['git', '-C', str(root), 'apply', '--include=' + relative,
                        '--whitespace=nowarn', str(patch)], check=True)
    if digest(root / relative) == MAPPING_GN_SHA:
        subprocess.run(['git', '-C', str(root), 'apply', '--include=' + relative,
                        '--whitespace=nowarn', str(LIFETIME_INPUT_PATCH)], check=True)


def apply(root):
    root = Path(root).resolve()
    if (root / PROJECT / '.git').exists():
        revision = subprocess.check_output(['git', '-C', str(root / PROJECT), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != REVISION:
            raise ValueError('requires pinned OpenHarmony 7.0 QEMU project')
    files = selected(root)  # All unknown inputs fail before mutation.
    with tempfile.TemporaryDirectory(prefix='qemu-mesa-recipes-') as temporary:
        staged = Path(temporary)
        for relative, original, repaired, patch in files:
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, target)
            apply_file(staged, relative, original, repaired, patch)
            if digest(target) != repaired:
                raise ValueError('Mesa recipe did not produce exact complete output: ' + relative)
        if selected(root) != files:
            raise ValueError('Mesa recipe inputs changed while preparing complete patches')
        for relative, original, repaired, patch in files:
            apply_file(root, relative, original, repaired, patch)
    if any(digest(root / relative) != repaired for relative, _, repaired, _ in files):
        raise ValueError('incomplete Mesa build recipe repair')
    print('verified common 64-bit and generated ARMv7a Mesa mapping recipes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    apply(args.source_root)
