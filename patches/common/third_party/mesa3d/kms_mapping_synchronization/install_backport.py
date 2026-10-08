#!/usr/bin/env python3
"""Install a verified historical-source backport, not a patch for Mesa 25."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess

COMPONENT = Path(__file__).resolve().parent
MESA_HEAD = '952a438c56ce20610d88f0c4d8c673485aefeff7'
QEMU_HEAD = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
HISTORICAL = '995d2506d18924b48db0cf40e6ad7de04fc4e558'
ORIGINAL_SHA = 'b8b8736f347fb473a718c610abf3099bfb72d5a9f28bf75e3620fb72f8592194'
DESTINATION = Path('device/qemu/common/virt_full/hardware/gpu/mesa_kms_mapping')


def check_no_symlink(path, root):
    while path != root:
        if path.is_symlink():
            raise ValueError('symlink in backport installation path')
        path = path.parent


def install(root):
    root = Path(root).resolve()
    for relative, expected in (('third_party/mesa3d', MESA_HEAD), ('device/qemu', QEMU_HEAD)):
        actual = subprocess.check_output(['git', '-C', str(root / relative), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != expected:
            raise ValueError('requires pinned OpenHarmony 7.0 build projects')
    original = subprocess.check_output(['git', '-C', str(root / 'third_party/mesa3d'), 'show',
        HISTORICAL + ':src/gallium/winsys/sw/kms-dri/kms_dri_sw_winsys.c'])
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA:
        raise ValueError('historical Mesa mapping baseline differs')
    version = subprocess.check_output(['git', '-C', str(root / 'third_party/mesa3d'),
        'show', HISTORICAL + ':VERSION'], text=True).strip()
    if version != '21.3.3':
        raise ValueError('historical Mesa revision is not 21.3.3')
    pairs = ((COMPONENT / 'files/apply_mesa_kms_mapping.py', 0o755),
             (COMPONENT / '0001-serialize-displaytarget-mapping.patch', 0o644))
    destination = root / DESTINATION
    check_no_symlink(destination, root)
    for source, mode in pairs:
        target = destination / source.name
        if target.is_symlink() or (target.exists() and target.read_bytes() != source.read_bytes()):
            raise ValueError('unknown installed mapping recipe; preserving source')
    destination.mkdir(parents=True, exist_ok=True)
    for source, mode in pairs:
        target = destination / source.name
        if not target.exists():
            shutil.copyfile(source, target)
            target.chmod(mode)
    print('installed exact historical Mesa mapping backport; no Mesa 25 source changes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    install(args.source_root)
