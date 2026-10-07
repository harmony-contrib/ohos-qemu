#!/usr/bin/env python3
"""Scratch-compile exact gralloc repair with real product flags; not guest pixels."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/device/qemu/virtio_yuv_buffer'
spec = importlib.util.spec_from_file_location('qemu_yuv_repair', COMPONENT / 'verify_source.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    for path in (root, root / 'out'):
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError('gralloc diagnosis requires read-only production source/output')
    if args.output.exists() or args.output.resolve().is_relative_to(root):
        raise ValueError('refuse to overwrite prior evidence or production source')
    repair.validate(root)
    project = root / 'device/qemu'
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + repair.FILE]).decode()
    target = 'obj/device/qemu/common/virt_full/hardware/display/src/display_gralloc/libhigbm_vendor/hi_gbm.o'
    cwd = root / 'out' / args.product
    commands = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
        check=True, capture_output=True, text=True)
    lines = commands.stdout.strip().splitlines()
    if len(lines) != 1:
        raise ValueError('need exactly one actual product gralloc compiler command')
    command = shlex.split(lines[0])
    if Path(command[0]).name == 'ccache':
        command.pop(0)
    if Path(command[0]).name != 'clang++' or any(token in command for token in ('&&', ';', '|')):
        raise ValueError('unexpected product gralloc compiler')
    index = command.index('-c') + 1
    if (cwd / command[index]).resolve() != project / repair.FILE:
        raise ValueError('wrong actual gralloc source')
    with tempfile.TemporaryDirectory(prefix='qemu-yuv-storage-compile-') as directory:
        staged = Path(directory)
        source_dir = Path(repair.FILE).parent
        shutil.copytree(project / source_dir, staged / source_dir)
        candidate = staged / repair.FILE
        candidate.write_text(repair.repaired_source(original))
        object_path = staged / 'hi_gbm.o'
        command[index] = str(candidate)
        command[command.index('-o') + 1] = str(object_path)
        command[command.index('-MF') + 1] = str(staged / 'hi_gbm.d')
        # Keep the actual product warnings, including its existing -Werror.
        # Appending -Wextra would re-enable pre-existing legacy initializer
        # warnings which the real target explicitly disables.
        subprocess.run(command, cwd=cwd, check=True)
        result = {'status': 'pass', 'product': args.product,
            'scope': 'real_product_gralloc_object_only_NOT_library_link_or_guest_YUV_pixels',
            'first_artifact_behavior_gate_passed': False, 'source_revision': repair.REVISION,
            'source_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
            'patch_sha256': hashlib.sha256((COMPONENT / '0001-allocate-cpu-yuv-byte-storage-on-virtio-gpu.patch').read_bytes()).hexdigest(),
            'object_sha256': hashlib.sha256(object_path.read_bytes()).hexdigest(),
            'actual_compiler_command': lines[0], 'diagnostic_command': command}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
