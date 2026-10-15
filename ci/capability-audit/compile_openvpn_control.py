#!/usr/bin/env python3
"""Compile complete private OpenVPN control TUs using real product commands.

The netsys feature selection is an explicit diagnostic define corresponding
to the reviewed QEMU-only GN predicate. This does not regenerate GN, link the
service, activate the backend or prove new-package behavior.
"""
import argparse
import json
from pathlib import Path

from compile_contact_sync_mode import PRODUCTS, ROOT, run

UNITS = {
    'netsys': (
        'foundation/communication/netmanager_base/qemu_openvpn_control',
        'foundation/communication/netmanager_base/services/netmanagernative/src/netsys/system_vpn_wrapper.cpp',
        'obj/foundation/communication/netmanager_base/services/netmanagernative/src/netsys/netsys_native_manager/system_vpn_wrapper.o'),
    'controller': (
        'foundation/communication/netmanager_ext/openvpn_lifecycle',
        'foundation/communication/netmanager_ext/services/vpnmanager/src/open_vpn_ctl.cpp',
        'obj/foundation/communication/netmanager_ext/services/vpnmanager/src/net_vpn_manager/open_vpn_ctl.o'),
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--product', choices=PRODUCTS, action='append', required=True)
    parser.add_argument('--unit', choices=UNITS, required=True)
    args = parser.parse_args()
    component, source, target = UNITS[args.unit]
    result = run(args, component=ROOT / 'patches/common' / component,
                 source_file=Path(source), target=target, caller=__file__,
                 candidate_defines=('OHOS_QEMU_OPENVPN',) if args.unit == 'netsys' else (),
                 overlay_component_headers=args.unit == 'controller',
                 prepare_component_idl=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'objects': result['objects_count'],
                      'first_artifact_behavior_gate_passed': False}))
