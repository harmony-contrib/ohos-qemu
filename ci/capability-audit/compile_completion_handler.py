#!/usr/bin/env python3
"""Compile the actual completion module TU; not linking or guest verification."""
import argparse
import json
from pathlib import Path

from compile_contact_sync_mode import run, PRODUCTS, ROOT


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=tuple(PRODUCTS), action='append')
    args = parser.parse_args()
    prefix = 'foundation/ability/ability_runtime/frameworks/js/napi/completion_handler_for_abilitystartcallback/'
    result = run(args,
        component=ROOT / 'patches/common/foundation/ability/ability_runtime/completion_handler',
        source_file=prefix + 'completion_handler_for_abilitystartcallback_module.cpp',
        target='obj/' + prefix + 'completionhandlerforabilitystartcallback/' +
               'completion_handler_for_abilitystartcallback_module.o', caller=__file__)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(status=result['status'], objects_count=result['objects_count'])))
