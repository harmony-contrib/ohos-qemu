#!/usr/bin/env python3
"""Require the complete known Photo/Fusion stack before adding search enums."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (('frameworks/js/src/media_library_napi.cpp',
          'c45cb3a1a9b65df3dddd37a816660309b82c5c40af4605d63932b5d338335b30',
          'b05869e1ab9a777c2a03b4cb114d161eccc6381ada8992d71984b2516ab43af0'),
         ('frameworks/js/src/photoaccesshelperinf.js',
          '5e5035b8b3913f49bc568798ebf83e737e627bec154331f2177db20dba519b4c',
          '2488397b285f55dd5b78f5aa0393a67f2c4a4a758867c5b0fbb5d315bb1fce5e'))

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('Complete photo source/search enum repair: ' + str(validate(args.source_root, args.require_patched)))
