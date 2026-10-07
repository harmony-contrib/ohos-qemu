#!/usr/bin/env python3
"""Compile all three complete Camera TUs, opt-in/off, with actual three-ABI flags.

No product files or guest libraries are replaced. Explicit isolated feature
defines test the new branches; they do not attest regenerated GN or a package.
"""
import argparse
import json
from pathlib import Path

from compile_contact_sync_mode import PRODUCTS, run

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/drivers/peripheral/camera/jpeg_capture'
PREFIX = 'drivers/peripheral/camera/vdi_base/usb_camera/'
SOURCES = (
    ('metadata', PREFIX + 'adapter/platform/v4l2/src/device_manager/v4l2_device_manager.cpp',
     'obj/' + PREFIX + 'adapter/platform/v4l2/src/device_manager/usb_camera_device_manager/v4l2_device_manager.o'),
    ('pipeline', PREFIX + 'adapter/platform/v4l2/src/pipeline_core/nodes/uvc_node/uvc_node.cpp',
     'obj/' + PREFIX + 'adapter/platform/v4l2/src/pipeline_core/nodes/uvc_node/usb_camera_pipeline_core/uvc_node.o'),
    ('codec', PREFIX + 'pipeline_core/src/node/codec_node.cpp',
     'obj/' + PREFIX + 'pipeline_core/src/node/usb_camera_pipeline_core/codec_node.o'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(exist_ok=False)
    reports = []
    for name, source, target in SOURCES:
        for enabled in (False, True):
            output = args.work / (name + ('-opt-in' if enabled else '-upstream') + '.json')
            checks = argparse.Namespace(source_root=args.source_root, output=output, product=list(PRODUCTS))
            result = run(checks, COMPONENT, Path(source), target, Path(__file__),
                         ('QEMU_VIVID_CAPTURE_ENABLED',) if enabled else ())
            output.write_text(json.dumps(result, indent=2) + '\n')
            reports.append(result)
    document = {'status': 'pass', 'scope': 'three_actual_full_Camera_TUs_three_ABIs_both_compile_branches_NOT_GN_or_guest',
                'objects_count': sum(item['objects_count'] for item in reports),
                'reports': reports, 'first_artifact_behavior_gate_passed': False}
    (args.work / 'evidence.json').write_text(json.dumps(document, indent=2) + '\n')
    print('three complete Camera TUs, three ABIs, opt-in/off compiled; not GN or guest acceptance')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
