#!/usr/bin/env python3
"""Compile exact port storage, utility and all selected users; not guest proof."""
import argparse
import json
from pathlib import Path
import subprocess
from compile_contact_sync_mode import ROOT, PRODUCTS, run

BASE = 'foundation/communication/netmanager_base/'
EXT = 'foundation/communication/netmanager_ext/frameworks/js/napi/'
PORT = ROOT / ('patches/common/' + BASE + 'inet_addr_port')
VPN = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays'
INET_HEADER = BASE + 'interfaces/innerkits/include/inet_addr.h'
NAPI_HEADER = BASE + 'utils/napi_utils/include/napi_utils.h'
HEADERS = (INET_HEADER, NAPI_HEADER)
TUS = {
    'inet-addr': (PORT, BASE + 'frameworks/native/netconnclient/src/inet_addr.cpp',
                  BASE + 'frameworks/native/netconnclient/src/net_conn_parcel/inet_addr.o', (INET_HEADER,)),
    'napi-utils': (PORT, BASE + 'utils/napi_utils/src/napi_utils.cpp',
                   BASE + 'utils/napi_utils/src/napi_utils/napi_utils.o', (NAPI_HEADER,)),
}
for name in ('addnetworkroute', 'addvlanip', 'deletevlanip'):
    part = 'frameworks/js/napi/connection/async_context/src/'
    TUS[name] = (PORT, BASE + part + name + '_context.cpp',
                 BASE + part + 'connection_if/' + name + '_context.o', HEADERS)
for name, folder, stem, target in (
        ('vpn-setup', 'vpn', 'context/setup_context', 'context/vpn/setup_context'),
        ('vpn-store', 'vpn', 'vpn_config_utils', 'vpn/vpn_config_utils'),
        ('vpnext-setup', 'vpnext', 'context/setup_context_ext', 'context/vpnextension/setup_context_ext'),
        ('vpnext-store', 'vpnext', 'vpn_config_utils_ext', 'vpnextension/vpn_config_utils_ext')):
    TUS[name] = (VPN, EXT + folder + '/src/' + stem + '.cpp',
                 EXT + folder + '/src/' + target + '.o', HEADERS)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    parser.add_argument('--tu', choices=TUS, action='append')
    args = parser.parse_args()
    chosen = args.tu or list(TUS)
    if len(set(chosen)) != len(chosen):
        parser.error('distinct actual TUs required')
    args.output.mkdir(exist_ok=False, parents=True)
    report = dict(status='fail', scope='actual_selected_network_port_full_TUs_NOT_link_or_guest',
        objects_count=0, requested_tus=chosen, objects=[], failures=[], first_artifact_behavior_gate_passed=False)
    try:
        for name in chosen:
            component, source, target, headers = TUS[name]
            child_args = argparse.Namespace(source_root=args.source_root,
                output=args.output / (name + '.json'), product=args.product)
            child = run(child_args, component=component, source_file=Path(source), target='obj/' + target,
                caller=__file__, overlay_component_headers=True, required_candidate_headers=headers,
                additional_components=(PORT,) if component == VPN else ())
            child_args.output.write_text(json.dumps(child, indent=2) + '\n')
            report['objects'].extend(dict(tu=name, **item) for item in child['objects'])
            report['objects_count'] += child['objects_count']
        report['status'] = 'pass'
    except Exception as error:
        # The actual argv and diagnostics remain in per-TU query/compile logs.
        report['failures'].append(type(error).__name__ + ': ' +
            ('actual compilation failed; inspect retained per-TU logs' if isinstance(error, subprocess.CalledProcessError)
             else str(error)))
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'],
        first_artifact_behavior_gate_passed=False)))
    raise SystemExit(report['status'] != 'pass')
