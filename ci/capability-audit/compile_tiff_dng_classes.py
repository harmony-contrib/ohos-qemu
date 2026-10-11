#!/usr/bin/env python3
"""Compile the actual metadata binding with real commands for three ABIs."""
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
    result = run(args,
        component=ROOT / 'patches/common/foundation/multimedia/image_framework/tiff_dng_class_exports',
        source_file=Path('foundation/multimedia/image_framework/frameworks/kits/js/common/metadata_napi.cpp'),
        target='obj/foundation/multimedia/image_framework/frameworks/kits/js/common/image/metadata_napi.o',
        caller=__file__, overlay_component_headers=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: result[name] for name in ('status', 'objects_count')}))
