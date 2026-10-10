#!/usr/bin/env python3
"""Actual AppMgr full translation unit checks; not linking or guest validation."""
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
    result = run(args,
        component=ROOT / 'patches/common/foundation/ability/ability_runtime/render_attach_registration',
        source_file='foundation/ability/ability_runtime/services/appmgr/src/app_mgr_service_inner.cpp',
        target='obj/foundation/ability/ability_runtime/services/appmgr/src/libappms/app_mgr_service_inner.o',
        caller=__file__, overlay_component_headers=True, prepare_component_idl=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'objects_count')}))
