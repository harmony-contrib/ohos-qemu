#!/usr/bin/env python3
"""Compile the real repaired MMI-to-ArkUI converter for selected product ABIs."""
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
    component = ROOT / 'patches/common/foundation/arkui/ace_engine/mouse_pressed_buttons'
    result = run(args, component=component,
        source_file=Path('foundation/arkui/ace_engine/adapter/ohos/entrance/mmi_event_convertor.cpp'),
        target='obj/foundation/arkui/ace_engine/adapter/ohos/entrance/ace_ohos_standard_entrance_ohos/mmi_event_convertor.o',
        caller=__file__)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
