#!/usr/bin/env python3
"""Accept only the exact fixed Camera revision and known whole-file repair."""
import argparse
import hashlib
from pathlib import Path
import subprocess

REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
FILE = 'camera/vdi_base/usb_camera/pipeline_core/src/node/codec_node.cpp'
ROTATION_FINAL_SHA256 = 'f18c171cd503703567ceb86ebd7017cc26205d1df481a92df2423ac1b87dc0d6'
CAPTURE_QUALITY_FINAL_SHA256 = 'd7cef95e6edebb4f6d50f93b4be103d6c23158c34c3624468123458b48c10b23'


def repaired(original):
    replacements = (
        (b'    JCOPY_OPTION copyoption;\n    jpeg_transform_info transformoption;\n',
         b'    const JCOPY_OPTION copyoption = JCOPYOPT_ALL;\n    jpeg_transform_info transformoption = {};\n'),
        (b'    jpeg_mem_src(&inputInfo, inputImg, inputSize);\n'
         b'    jpeg_mem_dest(&outInfo, outImg, (unsigned long *)outSize);\n',
         b'    jpeg_mem_src(&inputInfo, inputImg, inputSize);\n'),
        (b'        CAMERA_LOGE("%s: transformation is not perfect", __func__);\n'
         b'        return;\n    }\n\n    src_coef_arrays = jpeg_read_coefficients(&inputInfo);\n',
         b'        CAMERA_LOGE("%s: transformation is not perfect", __func__);\n'
         b'        jpeg_destroy_compress(&outInfo);\n'
         b'        jpeg_destroy_decompress(&inputInfo);\n'
         b'        return;\n    }\n\n'
         b'    jpeg_mem_dest(&outInfo, outImg, (unsigned long *)outSize);\n'
         b'    src_coef_arrays = jpeg_read_coefficients(&inputInfo);\n'),
    )
    for old, new in replacements:
        if original.count(old) != 1:
            raise ValueError('unknown pinned Camera JPEG transform structure')
        original = original.replace(old, new)
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append', default=[])
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    peripheral = root / 'drivers/peripheral'
    cursor = peripheral / FILE
    while cursor != root:
        if cursor.is_symlink():
            raise SystemExit('Camera JPEG source contains a symlink; preserving input')
        cursor = cursor.parent
    revision = subprocess.check_output(['git', '-C', str(peripheral), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise SystemExit('Camera JPEG repair requires pinned peripheral ' + REVISION)
    original = subprocess.check_output(['git', '-C', str(peripheral), 'show', 'HEAD:' + FILE])
    expected = repaired(original)
    actual = (peripheral / FILE).read_bytes()
    # The separately ordered JPEG-capture component adds one exact quality
    # repair to this same TU. Repeat application of the full plan must accept
    # that *known final* state without accepting arbitrary source drift.
    downstream = (hashlib.sha256(expected).hexdigest() == ROTATION_FINAL_SHA256 and
                  hashlib.sha256(actual).hexdigest() == CAPTURE_QUALITY_FINAL_SHA256)
    accepted = (expected,) if args.require_patched else (original, expected)
    if actual not in accepted and not downstream:
        raise SystemExit('unknown Camera JPEG source edits; preserving ' + FILE)
    print('pinned Camera JPEG source checked (not packaged Camera acceptance)')


if __name__ == '__main__':
    main()
