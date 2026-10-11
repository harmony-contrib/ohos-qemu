#!/usr/bin/env python3
"""Compile the real feature-enabled Ethernet TU; not linking or guest proof."""
import argparse
import json
from pathlib import Path
from compile_contact_sync_mode import ROOT, PRODUCTS, run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    args = parser.parse_args()
    folder = 'foundation/communication/netmanager_ext/services/ethernetmanager/'
    report = run(args,
        component=ROOT / 'patches/common/foundation/communication/netmanager_ext/ethernet_control',
        source_file=Path(folder + 'src/ethernet_management.cpp'),
        target='obj/' + folder + 'src/ethernet_manager/ethernet_management.o', caller=__file__,
        overlay_component_headers=True)
    enabled = bool(report['objects']) and all(
        '-DNETMANAGER_EXT_ETHERNET_ENABLE_DISABLE' in item['executed_argv'] for item in report['objects'])
    report['actual_control_feature_enabled'] = enabled
    if not enabled:
        report.update(status='fail', error='actual GN command did not compile the Ethernet control feature')
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'],
        actual_control_feature_enabled=enabled, first_artifact_behavior_gate_passed=False)))
    raise SystemExit(report['status'] != 'pass')
