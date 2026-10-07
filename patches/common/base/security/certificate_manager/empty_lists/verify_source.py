#!/usr/bin/env python3
"""Require the complete pinned source before/after the empty-list repair."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'base/security/certificate_manager'
REVISION = '57bd41128a07c5289987cf98e04dfc66421029a6'
FILES = (('interfaces/kits/napi/src/cm_napi_common.cpp',
          '1886825f602b6d391fea761abb752490c81289efb9567fc28fb70a9d561ecbfd',
          'ff3c3d31531600f836c64e0817532a24147a44e99e21237d961515fef6bb1c20'),)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('CertificateManager empty-list repair present: ' + str(validate(args.source_root, args.require_patched)))


if __name__ == '__main__':
    main()
