#!/usr/bin/env python3
"""Compile actual BEGIN/UPDATE TUs with the candidate timer header, all ABIs."""
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
    component = ROOT / 'patches/common/foundation/arkui/ace_engine/spring_loading_lifecycle'
    folder = 'foundation/arkui/ace_engine/frameworks/core/components_ng/manager/drag_drop/drag_drop_spring_loading/'
    results = []
    for state in ('begin', 'update'):
        name = 'drag_drop_spring_loading_state_' + state
        selected = argparse.Namespace(source_root=args.source_root,
            output=args.output.parent / (args.output.stem + '-' + state + '.json'), product=args.product)
        result = run(selected, component=component, source_file=Path(folder + name + '.cpp'),
            target='obj/' + folder + 'ace_core_components_manager_ng_ohos/' + name + '.o',
            caller=__file__, overlay_component_headers=True)
        selected.output.write_text(json.dumps(result, indent=2) + '\n')
        results.append(result)
    args.output.write_text(json.dumps(dict(status='pass', objects_count=sum(
        result['objects_count'] for result in results), first_artifact_behavior_gate_passed=False,
        scope='actual_two_spring_state_TUs_NOT_link_or_guest', results=results), indent=2) + '\n')
