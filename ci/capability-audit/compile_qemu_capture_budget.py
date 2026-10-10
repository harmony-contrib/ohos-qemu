#!/usr/bin/env python3
"""Compile the full DMS candidate TU; not linking, GN selection or guest proof."""
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
    prefix = 'foundation/window/window_manager/window_scene/screen_session_manager/src/'
    result = run(args,
        component=ROOT / 'patches/common/foundation/window/window_manager/capture_budget',
        source_file=prefix + 'screen_session_manager.cpp',
        target='obj/' + prefix + 'screen_session_manager/screen_session_manager.o',
        caller=__file__, candidate_defines=('WM_QEMU_SOFTWARE_CAPTURE',),
        prepare_component_idl=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(status=result['status'], objects_count=result['objects_count'])))
