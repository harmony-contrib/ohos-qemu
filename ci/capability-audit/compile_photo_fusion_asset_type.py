#!/usr/bin/env python3
"""Compile the whole real PhotoAccessHelper TU, not a mock or guest result."""
import argparse
import json
from pathlib import Path

from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/fusion_asset_type'
SOURCE = Path('foundation/multimedia/media_library/frameworks/js/src/media_library_napi.cpp')
TARGET = 'obj/foundation/multimedia/media_library/frameworks/js/src/medialibrary_nutils/media_library_napi.o'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--product', choices=tuple(PRODUCTS), action='append')
    args = parser.parse_args()
    report = run(args, COMPONENT, SOURCE, TARGET, Path(__file__))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name: report[name] for name in ('status', 'source_final_sha256', 'objects_count')}))
