#!/usr/bin/env python3
"""Compile actual scan monitor/service with their patched private header."""
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
    prefix = 'foundation/communication/wifi/wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_scan/'
    rows = []
    for name in ('scan_monitor', 'scan_service'):
        args.output = output.with_name(output.stem + '-' + name + '.json')
        result = run(args,
            component=ROOT / 'patches/common/foundation/communication/wifi/wpa_scan_lifecycle',
            source_file=prefix + name + '.cpp',
            target='obj/' + prefix + 'wifi_scan_service/' + name + '.o',
            caller=__file__, prepare_component_wifi_hdi=True, overlay_component_headers=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        rows.append(result)
    summary = dict(status='pass', scope='actual_full_TU_objects_NOT_guest',
                   objects_count=sum(row['objects_count'] for row in rows), results=rows,
                   first_artifact_behavior_gate_passed=False)
    output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(status='pass', objects_count=summary['objects_count'])))
