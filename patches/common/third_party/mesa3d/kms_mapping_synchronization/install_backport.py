#!/usr/bin/env python3
"""Install a verified historical-source backport, not a patch for Mesa 25."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

COMPONENT = Path(__file__).resolve().parent
MESA_HEAD = '952a438c56ce20610d88f0c4d8c673485aefeff7'
QEMU_HEAD = 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'
HISTORICAL = '995d2506d18924b48db0cf40e6ad7de04fc4e558'
ORIGINAL_SHA = 'b8b8736f347fb473a718c610abf3099bfb72d5a9f28bf75e3620fb72f8592194'
DESTINATION = Path('device/qemu/common/virt_full/hardware/gpu/mesa_kms_mapping')
PREVIOUS_HELPER_SHA = 'b627b3bb969a0a691c0d8ab36cdf7753a5f665fc9cc2a5d298187011743856b6'
MAPPING_ONLY_HELPER_SHA = '0ab55a500ef0eca395929f1181c8d90fec70f9a1174934438fdea045b2f6bc5a'


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
             (COMPONENT / '0001-serialize-displaytarget-mapping.patch', 0o644),
             (COMPONENT / '0002-serialize-import-reference-and-final-destroy.patch', 0o644))
    destination = root / DESTINATION
    check_no_symlink(destination, root)
    for source, mode in pairs:
        target = destination / source.name
        known_previous = (source.name == 'apply_mesa_kms_mapping.py' and target.is_file()
                          and hashlib.sha256(target.read_bytes()).hexdigest() in
                          (PREVIOUS_HELPER_SHA, MAPPING_ONLY_HELPER_SHA))
        if target.is_symlink() or (target.exists() and target.read_bytes() != source.read_bytes()
                                   and not known_previous):
            raise ValueError('unknown installed mapping recipe; preserving source')
    destination.mkdir(parents=True, exist_ok=True)
    for source, mode in pairs:
        target = destination / source.name
        if not target.exists() or target.read_bytes() != source.read_bytes():
            replacement_name = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination, prefix='.mapping-recipe-',
                                                 delete=False) as replacement:
                    replacement_name = Path(replacement.name)
                    with source.open('rb') as payload:
                        shutil.copyfileobj(payload, replacement)
                    os.fchmod(replacement.fileno(), mode)
                    replacement.flush()
                    os.fsync(replacement.fileno())
                os.replace(replacement_name, target)
            finally:
                if replacement_name is not None:
                    replacement_name.unlink(missing_ok=True)
    print('installed exact historical Mesa mapping backport; no Mesa 25 source changes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    install(args.source_root)
