#!/usr/bin/env python3
"""Compile radio/SIM/SMS and both VPN TUs for all three product ABIs.

Radio/SIM/SMS preserve their complete real product flags. For VPN, explicitly
activate the intended SUPPORT_SYSVPN branch if an older cached GN command
omits it; preserve and report both original/executed commands. This is a
candidate branch check, not validation of fresh product GN feature selection.
Read-only source/output inputs and private objects only, never guest evidence.
"""
import argparse
import json
from pathlib import Path

from compile_ethernet_enum import ROOT, digest, run

PLAN = (
    ('radio', 'base/telephony/core_service', 'api26_enums',
     'frameworks/js/network_search/src/napi_radio.cpp',
     'frameworks/js/network_search/src/radio/napi_radio.o'),
    ('sim', 'base/telephony/core_service', 'api26_enums',
     'frameworks/js/sim/src/napi_sim.cpp', 'frameworks/js/sim/src/sim/napi_sim.o'),
    ('sms', 'base/telephony/sms_mms', 'api26_enums',
     'frameworks/js/napi/src/napi_sms.cpp', 'frameworks/js/napi/src/sms/napi_sms.o'),
    ('vpn', 'foundation/communication/netmanager_ext', 'api26_features',
     'frameworks/js/napi/vpn/src/vpn_module.cpp', 'frameworks/js/napi/vpn/src/vpn/vpn_module.o'),
    ('vpn-extension', 'foundation/communication/netmanager_ext', 'api26_features',
     'frameworks/js/napi/vpnext/src/vpn_module_ext.cpp',
     'frameworks/js/napi/vpnext/src/vpnextension/vpn_module_ext.o'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    report = {'status': 'fail', 'scope': '15_three_ABI_enum_objects_VPN_candidate_feature_NOT_fresh_GN_link_or_guest',
              'first_artifact_behavior_gate_passed': False, 'objects': [], 'failures': []}
    try:
        for label, project, component, source, target in PLAN:
            child_args = argparse.Namespace(source_root=args.source_root, output=args.output / label)
            value = run(child_args, component=ROOT / 'patches/common' / project / component,
                        project_path=project, source_path=Path(project) / source,
                        target='obj/' + project + '/' + target, caller=Path(__file__),
                        scope='three_' + label + '_TU_objects_NOT_fresh_GN_link_or_guest',
                        extra_defines=('SUPPORT_SYSVPN',) if label.startswith('vpn') else ())
            evidence = child_args.output / 'evidence.json'
            report['objects'].append({'component': label, 'evidence': str(evidence),
                'sha256': digest(evidence), 'count': len(value['objects'])})
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'objects': sum(row['count'] for row in report['objects']),
                      'scope': report['scope']}))


if __name__ == '__main__':
    main()
