#!/usr/bin/env python3
"""Check the entire real Audio NAPI enum TU, not a mock or guest result."""
import argparse
import json
from pathlib import Path

from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT = ROOT / 'patches/common/foundation/multimedia/audio_framework/device_block_status'
SOURCE = Path('foundation/multimedia/audio_framework/frameworks/js/napi/common/napi_audio_enum.cpp')
TARGET = 'obj/foundation/multimedia/audio_framework/frameworks/js/napi/common/audio/napi_audio_enum.o'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--product', choices=tuple(PRODUCTS), action='append')
    args = parser.parse_args()
    report = run(args, COMPONENT, SOURCE, TARGET, Path(__file__))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name: report[name] for name in ('status', 'source_final_sha256', 'objects_count')}))
