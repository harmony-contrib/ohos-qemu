#!/usr/bin/env python3
"""Compile exact VPN family sources with real TU commands; not linking/guest proof."""
import argparse
import json
from pathlib import Path
import subprocess
from compile_contact_sync_mode import ROOT, PRODUCTS, run
from compile_network_port import PORT, HEADERS

COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/vpn_config_arrays'
PREFIX = 'foundation/communication/netmanager_ext/frameworks/js/napi/'
TUS = {
    'vpn-setup': ('vpn/src/context/setup_context.cpp', 'vpn/src/context/vpn/setup_context.o'),
    'vpn-store': ('vpn/src/vpn_config_utils.cpp', 'vpn/src/vpn/vpn_config_utils.o'),
    'vpnext-setup': ('vpnext/src/context/setup_context_ext.cpp', 'vpnext/src/context/vpnextension/setup_context_ext.o'),
    'vpnext-store': ('vpnext/src/vpn_config_utils_ext.cpp', 'vpnext/src/vpnextension/vpn_config_utils_ext.o'),
}


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
    report = dict(status='fail', scope='actual_selected_VPN_family_full_TUs_NOT_link_or_guest',
                  objects_count=0, requested_tus=chosen, objects=[], failures=[], first_artifact_behavior_gate_passed=False)
    try:
        for name in chosen:
            source, target = TUS[name]
            child_args = argparse.Namespace(source_root=args.source_root,
                output=args.output / (name + '.json'), product=args.product)
            child = run(child_args, component=COMPONENT, source_file=Path(PREFIX + source),
                        target='obj/' + PREFIX + target, caller=__file__,
                        overlay_component_headers=True, required_candidate_headers=HEADERS,
                        additional_components=(PORT,))
            child_args.output.write_text(json.dumps(child, indent=2) + '\n')
            report['objects'].extend(dict(tu=name, **item) for item in child['objects'])
            report['objects_count'] += child['objects_count']
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' +
            ('actual compilation failed; inspect retained per-TU logs' if isinstance(error, subprocess.CalledProcessError)
             else str(error)))
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'],
                         first_artifact_behavior_gate_passed=False)))
    raise SystemExit(report['status'] != 'pass')
