#!/usr/bin/env python3
"""Compile four actual WPA scan TUs for each product; not guest acceptance."""
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
    prefix = 'foundation/communication/wifi/wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_native/'
    sources = ('wifi_hal_interface/wifi_supplicant_hal_interface.cpp',
               'wifi_hal_interface/wifi_sta_hal_interface.cpp',
               'client/hdi_client/wifi_hdi_wpa_callback.cpp',
               'client/hdi_client/wifi_hdi_wpa_client.cpp')
    rows = []
    for relative in sources:
        args.output = output.with_name(output.stem + '-' + Path(relative).stem + '.json')
        result = run(args,
            component=ROOT / 'patches/common/foundation/communication/wifi/wpa_scan',
            source_file=prefix + relative,
            target='obj/' + prefix + str(Path(relative).parent) + '/wifi_native/' +
                   Path(relative).stem + '.o',
            caller=__file__, prepare_component_wifi_hdi=True)
        for item in result['objects']:
            command = item['executed_argv']
            if '-DHDI_WPA_INTERFACE_SUPPORT' not in command or '-DHDI_CHIP_INTERFACE_SUPPORT' in command:
                raise ValueError('actual QEMU product must compile the non-chip WPA path')
        result['actual_non_chip_wpa_feature_selection_verified'] = True
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        rows.append(result)
    summary = dict(status='pass', scope='actual_full_TU_objects_NOT_guest',
                   objects_count=sum(row['objects_count'] for row in rows), results=rows,
                   first_artifact_behavior_gate_passed=False)
    output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(status='pass', objects_count=summary['objects_count'])))
