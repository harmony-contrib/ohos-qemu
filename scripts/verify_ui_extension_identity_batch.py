#!/usr/bin/env python3
"""Require both native diagnostic carriers to share a complete source state."""
import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    guard = Path(__file__).resolve().parents[1] / 'patches/common/foundation/arkui/ace_engine/ui_extension_identity_diagnostics/verify_source.py'
    if guard.is_symlink() or not guard.is_file():
        raise ValueError('actual paired native identity source guard required')
    spec = importlib.util.spec_from_file_location('native_identity_batch_guard', guard)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patched = module.validate_batch(args.source_root, require_patched=args.require_patched)
    print(json.dumps({'scope':'paired native source state ONLY; no build or runtime proof',
        'state':'final' if patched else 'original','first_artifact_behavior_gate_passed':False}))


if __name__ == '__main__': main()
