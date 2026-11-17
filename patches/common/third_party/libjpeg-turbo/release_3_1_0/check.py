#!/usr/bin/env python3
"""Require the exact fixed libjpeg source/archive and complete known repairs."""
import argparse
import hashlib
from pathlib import Path
import subprocess

REVISION = '19603e5c6d67d7bf73cfafe097182f6d029ac571'
ARCHIVE = 'libjpeg-turbo-3.1.0.tar.gz'
ARCHIVE_SHA256 = 'cb3892683edb7a964d4ef39d1ed8d908504f426bd096d21acf7bff08e3cdaace'
HASHES = {
    'jconfig.h': ('39a55ebc3c6aba412bd5723fdfae659272c0794abd5ad6b5617e457b702b8ce6', 'f83a19c606d666528d97f662839020a4b2d6faa617aed4ac45e2c15c6f118880'),
    'jconfigint.h': ('5181dcb2ad57c246651775b1ea8f7917aad5009305b95ae65708080721a432d7', 'e572fc297434a15c4cd72b1d8a1811ee3fe05251a92122165ab84e59b18c60eb'),
    'install.py': ('010b9a04eb169186a2a6d3bee3c5ee20ba6c56d6e58eb665a93d438d3aeeddc8', 'c0bb1cebf59bf8c779261bbf86ccb535f923e54e0e9c5c0347fe7b620877d7b6'),
    'BUILD.gn': ('f0724075bb4697837d4a1fca56ae91429f53a8eefda3292f91f636396ecc8db2', 'ba26a72f37301f278c4f45dea0abda24bb53bba65025dcb4722281cc0833bc88'),
    'libjpeg-turbo-3.1.0-compat.patch': (None, '28b81fffe355e835a75425d5bbb4c3ff9ac914eb2fec6475a35eb94900a422a9'),
    'Add-loongarch64.patch': ('0921c5e353b7e2016d1afec9675a9d2aa576074d510af59155c84316f8c02089', 'ddb62c491e8b7ab590795f845f9532c05817bbc0f8983ab38394602b81d4ad9c'),
    'liteos_adapting.patch': ('b965352c76e98dd39d02799179acd72f2cf2cb81a63d69373c52a84d81753193', '30dd9f2380643befb011971f7533cdcb94a59e868d9f9a59dc91bcc8eac20ec2'),
    'libjpeg-turbo-2.1.x-bugfix.patch': ('45c444e93c82ea515af5524ead2ff75be66021411c6f2fbfd5b3c6b415e03869', '8e64e3398dd2786baaee9021c451bda1d7883e446981690e719abd744c7e0baa'),
}


def checked_file(source, name):
    path = source / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('libjpeg input must be a real file: ' + name)
    return path.read_bytes()


def validate(source, require_patched=False):
    if source.is_symlink() or source.parent.is_symlink():
        raise ValueError('libjpeg repair requires a real writable source copy')
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != REVISION:
        raise ValueError('libjpeg repair requires fixed 7.0 revision ' + REVISION)
    if hashlib.sha256(checked_file(source, ARCHIVE)).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('unknown libjpeg 3.1.0 archive')
    for name, (original_hash, repaired_hash) in HASHES.items():
        if original_hash is not None:
            original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + name])
            if hashlib.sha256(original).hexdigest() != original_hash:
                raise ValueError('unexpected pinned libjpeg file: ' + name)
        elif not (source / name).exists() and not (source / name).is_symlink() and not require_patched:
            continue
        actual_hash = hashlib.sha256(checked_file(source, name)).hexdigest()
        accepted = (repaired_hash,) if require_patched else (original_hash, repaired_hash)
        if actual_hash not in accepted:
            raise ValueError('unknown libjpeg edits; preserving source: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    source = args.source_root.resolve() / 'third_party/libjpeg-turbo'
    validate(source, args.require_patched)
    print('fixed libjpeg 3.1.0 patch/installer contract verified; not guest Camera acceptance')


if __name__ == '__main__':
    main()
