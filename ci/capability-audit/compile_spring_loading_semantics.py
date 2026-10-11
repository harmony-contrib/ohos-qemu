#!/usr/bin/env python3
"""Compile the actual context methods for both dynamic frontends, all ABIs."""
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
    component = ROOT / 'patches/common/foundation/arkui/ace_engine/spring_loading_semantics'
    folder = 'foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/engine/functions/'
    results = []
    for frontend in ('ark', 'ng_ark'):
        selected = argparse.Namespace(source_root=args.source_root,
            output=args.output.parent / (args.output.stem + '-' + frontend + '.json'), product=args.product)
        result = run(selected, component=component, source_file=Path(folder + 'js_drag_function.cpp'),
            target='obj/' + folder + 'declarative_js_engine_' + frontend + '_ohos/js_drag_function.o',
            caller=__file__, overlay_component_headers=True)
        selected.output.write_text(json.dumps(result, indent=2) + '\n')
        results.append(result)
    args.output.write_text(json.dumps(dict(status='pass', objects_count=sum(
        result['objects_count'] for result in results), first_artifact_behavior_gate_passed=False,
        scope='actual_both_dynamic_frontend_context_TUs_NOT_link_or_guest', results=results), indent=2) + '\n')
