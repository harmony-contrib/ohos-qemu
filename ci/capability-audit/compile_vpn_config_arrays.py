#!/usr/bin/env python3
"""Compile real full VPN serializer TUs across ABIs; no guest/store claim."""
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
    folder = 'foundation/communication/netmanager_ext/frameworks/js/napi/vpn/'
    report = run(args,
        component=ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays',
        source_file=Path(folder + 'src/vpn_config_utils.cpp'),
        target='obj/' + folder + 'src/vpn/vpn_config_utils.o', caller=__file__)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'],
                         first_artifact_behavior_gate_passed=False)))
