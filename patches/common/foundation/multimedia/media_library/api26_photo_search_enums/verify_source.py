#!/usr/bin/env python3
"""Require the complete known Photo/Fusion stack before adding search enums."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import digest, validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (('frameworks/js/src/media_library_napi.cpp',
          'c45cb3a1a9b65df3dddd37a816660309b82c5c40af4605d63932b5d338335b30',
          'b05869e1ab9a777c2a03b4cb114d161eccc6381ada8992d71984b2516ab43af0'),
         ('frameworks/js/src/photoaccesshelperinf.js',
          '5e5035b8b3913f49bc568798ebf83e737e627bec154331f2177db20dba519b4c',
          '2488397b285f55dd5b78f5aa0393a67f2c4a4a758867c5b0fbb5d315bb1fce5e'))

def validate(root, require_patched=False):
    wrapper = Path(root) / PROJECT / FILES[1][0]
    recent_sha = '7a8dd9dd99d77b5657cb57bc8cb65d60d681254586f4690919e2870650578a9c'
    records_sha = '7843fe2799ab30bb78aae887196b06bcb96471cdc9c6bb0fb5017aab772bcce2'
    files = FILES
    wrapper_sha = digest(wrapper.read_bytes()) if wrapper.is_file() else None
    if wrapper_sha in (recent_sha, records_sha, '2b0cbaa4c727061697794e9ade94cb98c6cabe3d68c7aa5a49956ff33f882f26', '7108e690526019093c562302afb8d2b41cfefe064bffb555a9da4d0180e32682'):
        files = (FILES[0], (FILES[1][0], FILES[1][1], wrapper_sha))
    return validate_component(root, PROJECT, REVISION, files, require_patched)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('Complete photo source/search enum repair: ' + str(validate(args.source_root, args.require_patched)))
