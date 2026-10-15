#!/usr/bin/env python3
"""Compile both actual current-read/error-delivery TUs and the modified header."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT = ROOT/'patches/common/foundation/distributeddatamgr/pasteboard/read_business_errors'
PREFIX = 'foundation/distributeddatamgr/pasteboard/interfaces/kits/napi/'
TARGET = 'obj/foundation/distributeddatamgr/pasteboard/interfaces/kits/napi/src/pasteboard_napi/'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('fresh actual BusinessError TU evidence required')
    records = []
    for stem in ('napi_systempasteboard', 'async_call'):
        per_tu = SimpleNamespace(source_root=args.source_root, product=args.product,
            output=args.output.with_name(args.output.stem+'-'+stem+'.json'))
        result = run(per_tu, component=COMPONENT, source_file=Path(PREFIX+'src/'+stem+'.cpp'),
            target=TARGET+stem+'.o', caller=__file__, overlay_component_headers=True,
            prepare_component_idl=True)
        per_tu.output.write_text(json.dumps(result, indent=2)+'\n')
        records.append(result)
    report = dict(status='pass', scope='actual_current_Pasteboard_read_and_error_delivery_TUs_NOT_package_runtime',
        first_artifact_behavior_gate_passed=False, records=records,
        objects_count=sum(row['objects_count'] for row in records),
        all_three_products_checked=all(row['all_three_products_checked'] for row in records))
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'])))
