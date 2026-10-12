#!/usr/bin/env python3
"""Compile fresh-R39 network repairs in real prepared product TUs, not guest proof."""
import argparse
import importlib.util
import json
from pathlib import Path

from compile_contact_sync_mode import ROOT, PRODUCTS, run, digest

BASE = ROOT / 'patches/common/foundation/communication/netmanager_ext'
PROJECT = 'foundation/communication/netmanager_ext/'
ROWS = {
    'ethernet': ('ethernet_business_error', 'frameworks/js/napi/ethernet/ethernet_module.cpp',
                 'frameworks/js/napi/ethernet/ethernet/ethernet_module.o'),
    'vpn-parcel': ('vpn_openvpn_fields', 'frameworks/native/netvpnclient/src/vpn_data_bean.cpp',
                  'frameworks/native/netvpnclient/src/networkvpn_parcel/vpn_data_bean.o'),
    'vpn-service': ('vpn_openvpn_fields', 'frameworks/native/netvpnclient/src/vpn_data_bean.cpp',
                   'frameworks/native/netvpnclient/src/net_vpn_manager/vpn_data_bean.o'),
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    parser.add_argument('--tu', choices=ROWS, required=True)
    args = parser.parse_args()
    component, source, target = ROWS[args.tu]
    prerequisites = {}
    if args.tu.startswith('vpn-'):
        spec = importlib.util.spec_from_file_location('parent_vpn_store', BASE / 'vpn_config_store/verify_source.py')
        parent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parent)
        if not parent.validate(args.source_root, require_patched=True):
            raise ValueError('real whole earlier VPN store preparation is required')
        prerequisites = {str(Path(parent.PROJECT) / name): digest(args.source_root / parent.PROJECT / name)
                         for name, _, _ in parent.FILES}
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('fresh network follow-up evidence path required')
    result = dict(status='fail', scope='actual_selected_full_product_TU_objects_NOT_link_or_guest',
                  first_artifact_behavior_gate_passed=False, tu=args.tu,
                  requested_products=args.product or list(PRODUCTS))
    try:
        result = run(args, component=BASE / component, source_file=Path(PROJECT + source),
                     target='obj/' + PROJECT + target, caller=__file__, overlay_component_headers=True)
        if prerequisites:
            if {name: digest(args.source_root / name) for name in prerequisites} != prerequisites:
                raise ValueError('prepared store source/header inputs changed during actual compilation')
            result['real_store_prerequisite_sha256'] = prerequisites
        feature = ('NETMANAGER_EXT_ETHERNET_ENABLE_DISABLE' if args.tu == 'ethernet' else 'SUPPORT_SYSVPN')
        enabled = bool(result['objects']) and all('-D' + feature in row['executed_argv']
                                                  for row in result['objects'])
        result['actual_required_feature_enabled'] = enabled
        if not enabled:
            raise ValueError('actual product command omitted the required feature: ' + feature)
    except Exception as error:
        result.update(status='fail', error=type(error).__name__ + ': ' + str(error))
    finally:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: result.get(name) for name in ('status', 'objects_count', 'actual_required_feature_enabled', 'error')}))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
