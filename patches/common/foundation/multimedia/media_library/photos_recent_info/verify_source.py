#!/usr/bin/env python3
"""Exact Photos API fixes on the complete fixed-release public enum stack."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (
    ('frameworks/js/src/photoaccesshelperinf.js',
     '2488397b285f55dd5b78f5aa0393a67f2c4a4a758867c5b0fbb5d315bb1fce5e',
     '7a8dd9dd99d77b5657cb57bc8cb65d60d681254586f4690919e2870650578a9c'),
    ('frameworks/js/src/media_library_napi.cpp',
     'b05869e1ab9a777c2a03b4cb114d161eccc6381ada8992d71984b2516ab43af0',
     'b05869e1ab9a777c2a03b4cb114d161eccc6381ada8992d71984b2516ab43af0'),
    ('frameworks/js/src/photo_album_napi.cpp',
     'e24265bb5563eddd384c7c11181ca53697b075f7f3df8c4484178daac7a6535c',
     'e24265bb5563eddd384c7c11181ca53697b075f7f3df8c4484178daac7a6535c'),
)

def validate(root, require_patched=False):
    for entry in FILES[1:]:
        validate_component(root, PROJECT, REVISION, (entry,), require_patched=True)
    # The later public-record component preserves this complete implementation.
    # Recognize only its exact final bytes so replaying the shared patch plan is
    # idempotent; unknown edits still fail the original validator below.
    successor = '992b87e1cef32bf50fda7ac9893de60762ebdf6f1ea29da9fee18cf7cafe2ed1'
    try:
        return validate_component(root, PROJECT, REVISION,
                                  ((FILES[0][0], successor, successor),), require_patched=True)
    except ValueError:
        pass
    return validate_component(root, PROJECT, REVISION, FILES[:1], require_patched)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('Recent Photos public contract repair: ' + str(validate(args.source_root, args.require_patched)))
