#!/usr/bin/env python3
"""Compile exact VPN store/parcel/service/NAPI TUs; NOT database/guest proof."""
import argparse
import json
from pathlib import Path
from compile_contact_sync_mode import ROOT, PRODUCTS, run

PROJECT = 'foundation/communication/netmanager_ext/'
INCLUDE = PROJECT + 'interfaces/innerkits/netvpnclient/include/'
ROWS = (
    ('parcel', 'frameworks/native/netvpnclient/src/vpn_data_bean.cpp',
     'frameworks/native/netvpnclient/src/networkvpn_parcel/vpn_data_bean.o',
     (INCLUDE + 'vpn_data_bean.h', INCLUDE + 'vpn_network_config.h')),
    ('service-bean', 'frameworks/native/netvpnclient/src/vpn_data_bean.cpp',
     'frameworks/native/netvpnclient/src/net_vpn_manager/vpn_data_bean.o',
     (INCLUDE + 'vpn_data_bean.h', INCLUDE + 'vpn_network_config.h')),
    ('database', 'services/vpnmanager/src/vpn_database_helper.cpp',
     'services/vpnmanager/src/net_vpn_manager/vpn_database_helper.o',
     (INCLUDE + 'vpn_data_bean.h', PROJECT + 'services/vpnmanager/include/vpn_database_defines.h')),
    ('napi', 'frameworks/js/napi/vpn/src/vpn_exec.cpp',
     'frameworks/js/napi/vpn/src/vpn/vpn_exec.o', None),
)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('fresh VPN store compilation report required')
    reports = []
    summary = dict(status='fail', first_artifact_behavior_gate_passed=False,
        scope='actual_selected_VPN_store_TU_candidates_NOT_link_database_or_guest', results=reports)
    try:
        for name, source, target, headers in ROWS:
            selected = argparse.Namespace(source_root=args.source_root, product=args.product,
                output=args.output.parent / (args.output.stem + '-' + name + '.json'))
            result = run(selected,
                component=ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_store',
                source_file=Path(PROJECT + source), target='obj/' + PROJECT + target, caller=__file__,
                overlay_component_headers=headers is not None, required_candidate_headers=headers)
            selected.output.write_text(json.dumps(result, indent=2) + '\n')
            reports.append(result)
        summary.update(status='pass', objects_count=sum(result['objects_count'] for result in reports),
            all_three_products_checked=all(result['all_three_products_checked'] for result in reports))
    except Exception as error:
        summary['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        args.output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: summary[key] for key in ('status', 'objects_count', 'all_three_products_checked')}))
