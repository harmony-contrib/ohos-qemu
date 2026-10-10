#!/usr/bin/env python3
"""Compile both WPA completion paths, old/QEMU branches, all real product ABIs."""
import argparse
import json
from pathlib import Path
from compile_contact_sync_mode import run, PRODUCTS, ROOT


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=tuple(PRODUCTS), action='append')
    args = parser.parse_args()
    output = args.output
    if output.exists():
        raise ValueError('fresh evidence path required')
    prefix = 'third_party/wpa_supplicant/wpa_supplicant-2.9_standard/wpa_supplicant/'
    rows = []
    for branch, defines in (('existing', ()), ('qemu', ('CONFIG_QEMU_WPA_SCAN_EVENTS',))):
        for name in ('events', 'scan'):
            args.output = output.with_name(output.stem + '-' + branch + '-' + name + '.json')
            result = run(args, component=ROOT / 'patches/common/third_party/wpa_supplicant/scan_events',
                source_file=prefix + name + '.c', target='obj/' + prefix + 'wpa/' + name + '.o',
                caller=__file__, candidate_defines=defines, overlay_component_headers=True)
            args.output.write_text(json.dumps(result, indent=2) + '\n')
            rows.append(result)
    summary = dict(status='pass', scope='actual_full_TU_objects_NOT_guest_or_regenerated_GN_selection',
        objects_count=sum(row['objects_count'] for row in rows), results=rows,
        first_artifact_behavior_gate_passed=False)
    output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(status='pass', objects_count=summary['objects_count'])))
