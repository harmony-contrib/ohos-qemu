#!/usr/bin/env python3
"""Compile all four real Wi-Fi NAPI variants for three ABIs in scratch only."""
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
    prefix = 'foundation/communication/wifi/wifi/frameworks/js/napi/src/'
    rows = []
    for variant in ('wifi', 'wifiext', 'wifimanager', 'wifimanagerext'):
        args.output = output.with_name(output.stem + '-' + variant + '.json')
        rows.append(run(args, component=ROOT / 'patches/common/foundation/communication/wifi/business_error',
            source_file=prefix + 'wifi_napi_errcode.cpp',
            target='obj/' + prefix + variant + '/wifi_napi_errcode.o', caller=__file__))
    summary = dict(status='pass', scope='actual_full_TU_objects_NOT_guest',
        objects_count=sum(row['objects_count'] for row in rows), results=rows,
        first_artifact_behavior_gate_passed=False)
    output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(status='pass', objects_count=summary['objects_count'])))
