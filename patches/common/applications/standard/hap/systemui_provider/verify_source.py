#!/usr/bin/env python3
"""Strict actual three-provider whole graph plus exactly seven SystemUI definitions."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from systemui_provider import read, digest, hap_state, normalize_hap_build, LEGACY_HAP_SHA

def validate(root, require_patched=False):
    raw = read(Path(root) / 'applications/standard/hap/BUILD.gn')
    state = hap_state(raw)
    if digest(normalize_hap_build(raw)) != LEGACY_HAP_SHA or (require_patched and not state):
        raise ValueError('unknown/incomplete source SystemUI HAP graph')
    return state
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
