#!/usr/bin/env python3
"""Compile the actual drag controller TU for all three product ABIs."""
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
    component = ROOT / 'patches/common/foundation/arkui/ace_engine/spring_loading_context'
    result = run(args, component=component,
        source_file=Path('foundation/arkui/ace_engine/interfaces/napi/kits/drag_controller/js_drag_controller.cpp'),
        target='obj/foundation/arkui/ace_engine/interfaces/napi/kits/drag_controller/dragcontroller_static_ohos/js_drag_controller.o',
        caller=__file__, overlay_component_headers=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
