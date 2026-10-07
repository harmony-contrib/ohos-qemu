#!/usr/bin/env python3
"""Require the fixed full MediaLibrary source before adding the missing enum."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (('frameworks/js/src/media_library_napi.cpp',
          'd8a1c5d24e24b8029dc1e5e59cfff529b7edc15ce8a8dfe3105c6b48031bd363',
          '4be781efd4c1ab2be368facd0dce7eb66ce1243dcec2f1a5e43f7672fc4c312e'),
         ('frameworks/js/src/photoaccesshelperinf.js',
          '804aea4300b31167be5a2fed86f0870c95f605ac689ea906f128ecc03dc37127',
          'b283d47255e633b5ed1b0f0ae27ef98ddc835d69ab60cdd2137e50da55ef1439'))


def validate(root, require_patched=False):
    # Recognize only the pristine source, the exact 0001 prefix already used
    # by prior builds, or the complete native + public-wrapper stack. No marker
    # file, reverse hunk or unrelated source edit can authorize a transition.
    states = tuple(validate_component(root, PROJECT, REVISION, (entry,)) for entry in FILES)
    if states not in ((False, False), (True, False), (True, True)):
        raise ValueError('noncontiguous FusionAssetType component state; preserving source')
    complete = states == (True, True)
    if require_patched and not complete:
        raise ValueError('complete native and public-wrapper enum repair required')
    return complete


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('FusionAssetType repair present: ' + str(validate(args.source_root, args.require_patched)))
