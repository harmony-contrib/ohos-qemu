#!/usr/bin/env python3
"""Exact source states required by the existing component apply helper."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "lib"))
from exact_source_states import validate_component

PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (
    ('frameworks/bridge/declarative_frontend/engine/jsi/jsi_bindings.h',
     '40c7cdfcc6a90d1959f110decd3117d08309493d7b00686e8ff00fb8bb8f4246',
     '7b8f993f397669d3b29ad36944ed44bd756b3b9c933d5a4a7bf4704c62eea5f5'),
    ('frameworks/bridge/declarative_frontend/engine/jsi/jsi_bindings.inl',
     '51b744f9bc2584cfdeab53247ea3a6bfd01ee39cc788a0a45e3af0109b7e041a',
     'cda3ba22d913905ada707251a2ffb6184e802f09d99455964f337ece731fc644'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--require-final", action="store_true")
    args = parser.parse_args()
    validate(args.source_root, require_patched=args.require_final)
