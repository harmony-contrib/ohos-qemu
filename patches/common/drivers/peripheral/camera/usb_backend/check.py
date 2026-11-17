#!/usr/bin/env python3
"""Guard the pinned real-USB Camera x86 selection change."""
import argparse
import hashlib
from pathlib import Path
import subprocess

REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
FILE = 'camera/BUILD.gn'
OLD = b'if (target_cpu == "x86_64" && !is_emulator) {'
NEW = b'if (target_cpu == "x86_64" && !is_emulator && !drivers_peripheral_camera_feature_usb) {'
CONFIG = 'camera/vdi_base/usb_camera/camera_config/BUILD.gn'
PIPELINE = 'camera/vdi_base/usb_camera/pipeline_core/BUILD.gn'
ADAPTER = 'camera/vdi_base/common/adapter/platform/v4l2/src/driver_adapter/BUILD.gn'


def repaired(original):
    if original.count(OLD) != 2 or NEW in original:
        raise ValueError('unknown fixed Camera HAL x86 selection structure')
    return original.replace(OLD, NEW)


def generated_config(original):
    start = original.index(b'action("copy_source") {\n')
    end = original.index(b'hc_gen("build_ipp_algo_config") {\n', start)
    original = original[:start] + original[end:]
    old = b'    ":config.c",\n    ":ipp_algo_config.hcb",\n    ":params.c",\n'
    new = b'    ":generate_source",\n    ":ipp_algo_config.hcb",\n'
    if original.count(old) != 1:
        raise ValueError('unknown USB pipeline config dependencies')
    return original.replace(old, new)


def generated_pipeline(original):
    old = (b'    "$camera_path_usb/pipeline_core/pipeline_impl/src/strategy/config/config.c",\n'
           b'    "$camera_path_usb/pipeline_core/pipeline_impl/src/strategy/config/params.c",\n')
    anchor = b'ohos_shared_library("usb_camera_pipeline_core") {\n'
    new = (anchor + b'  camera_config_gen_dir =\n'
           b'      get_label_info("$camera_path_usb/camera_config:generate_source",\n'
           b'                     "target_gen_dir")\n')
    deps = b'    "$camera_path_usb/camera_config:config.c",\n    "$camera_path_usb/camera_config:params.c",\n'
    include = b'  include_dirs = [\n'
    if any(original.count(value) != 1 for value in (old, anchor, deps, include)):
        raise ValueError('unknown USB pipeline source/header/dependency structure')
    return original.replace(old, b'    "$camera_config_gen_dir/config.c",\n    "$camera_config_gen_dir/params.c",\n').replace(
        anchor, new).replace(include, include + b'    camera_config_gen_dir,\n').replace(
        deps, b'    "$camera_path_usb/camera_config:generate_source",\n')


def adapter_defines(original):
    old = b'  if (!is_emulator) {\n    defines = []\n'
    if original.count(old) != 1:
        raise ValueError('unknown Camera adapter defines initialization')
    return original.replace(old, b'  if (!is_emulator || !defined(defines)) {\n    defines = []\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append', default=[])
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    source = root / 'drivers/peripheral'
    for name in (FILE, CONFIG, PIPELINE, ADAPTER):
        cursor = source / name
        while cursor != root:
            if cursor.is_symlink():
                raise SystemExit('Camera source contains a symlink; preserving input')
            cursor = cursor.parent
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != REVISION:
        raise SystemExit('Camera USB repair requires pinned 7.0 peripheral ' + REVISION)
    for name, transform in ((FILE, repaired), (CONFIG, generated_config), (PIPELINE, generated_pipeline),
                            (ADAPTER, adapter_defines)):
        original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + name])
        expected = transform(original)
        actual = (source / name).read_bytes()
        # A repeat of the aggregate plan sees the later exact JPEG component.
        # Accept only its known whole-file postimage over our known generated
        # configuration preimage, never arbitrary additional GN edits.
        jpeg_successor = (name == PIPELINE and
            hashlib.sha256(expected).hexdigest() ==
                '274ed2eba3892cd9d64e86cfa0bab6868c40a3f1a7a4a96bfcc7ec8f3946cd3f' and
            hashlib.sha256(actual).hexdigest() ==
                '58e71f433a1d0c6425aab75d101e41283e045bb44cc4e25319686210132f9eed')
        if not jpeg_successor and actual not in ((expected,) if args.require_patched else (original, expected)):
            raise SystemExit('unknown Camera source edits; preserving ' + name)
    print('pinned Camera USB/x86 source structure checked (not frame acceptance)')


if __name__ == '__main__':
    main()
