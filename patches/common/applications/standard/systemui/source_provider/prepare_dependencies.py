#!/usr/bin/env python3
"""Prepare the fixed OS profile; production dependencies are local source."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from systemui_provider import prepare
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--cache-root', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.source_root.resolve(), args.cache_root.resolve())
    args.evidence.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
