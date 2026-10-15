#!/usr/bin/env python3
"""Compile the complete real RS registration stub with each product command."""
import argparse
import json
from pathlib import Path
from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT = ROOT / 'patches/common/foundation/graphic/graphic_2d/application_agent_identity'
SOURCE = Path('foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/rs_client_to_render_connection_stub.cpp')
TARGET = 'obj/foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/librender_service/rs_client_to_render_connection_stub.o'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    args = parser.parse_args()
    report = run(args, component=COMPONENT, source_file=SOURCE, target=TARGET, caller=__file__,
                 overlay_component_headers=True, prepare_component_idl=True,
                 prepare_component_hdi=True, prepare_component_display_common=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'],
                         first_artifact_behavior_gate_passed=False)))
