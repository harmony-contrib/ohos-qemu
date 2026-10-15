#!/usr/bin/env python3
"""Three actual BaseContext product commands; not linking or guest proof."""
import argparse
import json
from pathlib import Path
from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_base/caller_api_version'
SOURCE = Path('foundation/communication/netmanager_base/utils/napi_utils/src/base_context.cpp')
TARGET = 'obj/foundation/communication/netmanager_base/utils/napi_utils/src/napi_utils/base_context.o'

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    args = parser.parse_args()
    report = run(args, component=COMPONENT, source_file=SOURCE, target=TARGET, caller=__file__)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'],
                         first_artifact_behavior_gate_passed=False)))
