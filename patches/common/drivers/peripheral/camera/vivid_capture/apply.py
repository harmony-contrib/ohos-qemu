#!/usr/bin/env python3
"""Install a bounded real-node selector; preserve fixed upstream USB filtering."""
import argparse
from pathlib import Path
import shutil
import subprocess

REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
PREFIX = 'camera/vdi_base/usb_camera/adapter/platform/v4l2/src/driver_adapter'
HEADER = PREFIX + '/src/qemu_v4l2_capture.h'


def transforms():
    return {
        'camera/camera.gni': [(b'  drivers_peripheral_camera_feature_usb = false\n',
                              b'  drivers_peripheral_camera_feature_usb = false\n  drivers_peripheral_camera_qemu_vivid_capture = false\n')],
        'camera/bundle.json': [(b'      "drivers_peripheral_camera_feature_usb",\n',
                               b'      "drivers_peripheral_camera_feature_usb",\n      "drivers_peripheral_camera_qemu_vivid_capture",\n')],
        PREFIX + '/BUILD.gn': [(b'    defines += [ "CAMERA_BUILT_ON_USB" ]\n  }\n',
                               b'    defines += [ "CAMERA_BUILT_ON_USB" ]\n  }\n  if (drivers_peripheral_camera_qemu_vivid_capture) {\n    defines += [ "QEMU_VIVID_CAPTURE_ENABLED" ]\n  }\n')],
        PREFIX + '/src/v4l2_uvc.cpp': [
            (b'#include "usb_device_filter.h"\n', b'#include "usb_device_filter.h"\n#include "qemu_v4l2_capture.h"\n'),
            (b'if (!((cap.capabilities & V4L2_CAP_VIDEO_CAPTURE) && (cap.capabilities & V4L2_CAP_STREAMING)))',
             b'if (!QemuStreamingCapture(cap) || !QemuCaptureDriverMatches(cap, "uvcvideo"))'),
            (b'if (!((capability.capabilities & V4L2_CAP_VIDEO_CAPTURE) && (capability.capabilities & V4L2_CAP_STREAMING)))',
             b'if (!QemuStreamingCapture(capability))'),
            (b'if (cameraId != std::string(reinterpret_cast<char*>(capability.driver)))',
             b'if (!QemuCaptureDriverMatches(capability, cameraId))'),
        ],
    }


def repaired(original, substitutions):
    for old, new in substitutions:
        if original.count(old) != 1:
            raise ValueError('unknown pinned QEMU capture source structure')
        original = original.replace(old, new)
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append', default=[])
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    root = args.source_root.resolve()
    source = root / 'drivers/peripheral'
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise SystemExit('virtual Camera requires pinned 7.0 peripheral source')
    for name in (*transforms(), HEADER):
        cursor = source / name
        while cursor != root:
            if cursor.is_symlink():
                raise SystemExit('virtual Camera source symlink; preserving inputs')
            cursor = cursor.parent
    for name, substitutions in transforms().items():
        original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + name])
        expected = repaired(original, substitutions)
        if (source / name).read_bytes() not in ((original, expected) if args.check_only else (expected,)):
            raise SystemExit('unknown Camera capture edits; preserving ' + name)
    header = source / HEADER
    template = Path(__file__).parent / 'files/qemu_v4l2_capture.h'
    if header.exists() and header.read_bytes() != template.read_bytes():
        raise SystemExit('unknown existing virtual Camera selector; preserving header')
    if args.check_only:
        print('virtual Camera selector/source preflight passed (not captured frames)')
        return
    shutil.copyfile(template, header)
    print('installed real V4L2 capture selector (not public Camera acceptance)')


if __name__ == '__main__':
    main()
