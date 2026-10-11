#!/usr/bin/env python3
"""Compile the actual three observer TUs and candidate header for all ABIs."""
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
    component = ROOT / 'patches/common/foundation/arkui/ace_engine/observer_info_classes'
    results = []
    for name in ('js_ui_observer', 'ui_observer', 'ui_observer_listener'):
        selected = argparse.Namespace(source_root=args.source_root,
            output=args.output.parent / (args.output.stem + '-' + name + '.json'), product=args.product)
        result = run(selected, component=component,
            source_file=Path('foundation/arkui/ace_engine/interfaces/napi/kits/observer/' + name + '.cpp'),
            target='obj/foundation/arkui/ace_engine/interfaces/napi/kits/observer/observer_static_ohos/' + name + '.o',
            caller=__file__, overlay_component_headers=True)
        selected.output.write_text(json.dumps(result, indent=2) + '\n')
        results.append(result)
    args.output.write_text(json.dumps(dict(status='pass', objects_count=sum(
        result['objects_count'] for result in results), first_artifact_behavior_gate_passed=False,
        scope='actual_three_observer_TUs_NOT_link_or_guest', results=results), indent=2) + '\n')
