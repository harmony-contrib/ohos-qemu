#!/usr/bin/env python3
"""Full fixed MediaLibrary TU objects, never query/provider or guest proof."""
import argparse
import json
from pathlib import Path

from compile_contact_sync_mode import ROOT, PRODUCTS, run

BASE = ROOT / 'patches/common/foundation/multimedia/media_library'
FILES = {
    'resultset': ('result_set_boundaries', 'result_set_napi.cpp'),
    'error': ('business_error', 'napi_error.cpp'),
    'utils': ('business_error', 'medialibrary_napi_utils.cpp'),
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    parser.add_argument('--tu', choices=FILES, required=True)
    args = parser.parse_args()
    component, name = FILES[args.tu]
    source = Path('foundation/multimedia/media_library/frameworks/js/src') / name
    target = 'obj/foundation/multimedia/media_library/frameworks/js/src/medialibrary_nutils/' + name[:-4] + '.o'
    result = run(args, component=BASE / component, source_file=source, target=target, caller=__file__)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
