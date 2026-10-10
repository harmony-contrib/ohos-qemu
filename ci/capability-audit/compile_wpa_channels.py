#!/usr/bin/env python3
"""Compile real channel helper with software and original branches for each ABI."""
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
        raise ValueError('fresh evidence required')
    prefix = 'foundation/communication/wifi/wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_common/'
    rows = []
    for name, defines in (('software-candidate', ('WIFI_SOFTWARE_SCAN_BACKEND',)), ('original', ())):
        args.output = output.with_name(output.stem + '-' + name + '.json')
        result = run(args, component=ROOT / 'patches/common/foundation/communication/wifi/wpa_channels',
            source_file=prefix + 'wifi_channel_helper.cpp',
            target='obj/' + prefix + 'wifi_common_service/wifi_channel_helper.o',
            caller=__file__, prepare_component_wifi_hdi=True, candidate_defines=defines)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        rows.append(result)
    summary = dict(status='pass', scope='actual_full_TU_both_branches_NOT_GN_selection_or_guest',
        objects_count=sum(row['objects_count'] for row in rows), results=rows,
        first_artifact_behavior_gate_passed=False)
    output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(status='pass', objects_count=summary['objects_count'])))
