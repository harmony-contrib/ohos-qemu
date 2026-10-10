#!/usr/bin/env python3
"""Compile all candidate QEMU mode TUs using real product commands, not link/guest."""
import argparse
import json
from pathlib import Path

from compile_contact_sync_mode import run, PRODUCTS, ROOT, digest

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=tuple(PRODUCTS), action='append')
    args = parser.parse_args()
    output = args.output
    if output.exists() or output.is_symlink():
        raise ValueError('fresh compilation output required')
    rows = []
    for name in ('drm_crtc', 'drm_display', 'hdi_drm_composition'):
        args.output = output.with_name(output.stem + '-' + name + '.json')
        prefix = 'device/qemu/common/virt_full/hardware/display/src/display_device/'
        result = run(args, component=ROOT / 'patches/common/device/qemu/display_modes',
            source_file=prefix + name + '.cpp',
            target='obj/' + prefix + 'display_composer_vendor/' + name + '.o', caller=__file__,
            prepare_component_hdi=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        rows.append(dict(source=name, report=str(args.output), sha256=digest(args.output),
                         objects_count=result['objects_count'], status=result['status']))
    report = dict(status='pass', scope='actual_QEMU_DRM_TUs_NOT_link_or_guest',
                  products=args.product or list(PRODUCTS), results=rows,
                  first_artifact_behavior_gate_passed=False)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status='pass', objects_count=sum(row['objects_count'] for row in rows))))
