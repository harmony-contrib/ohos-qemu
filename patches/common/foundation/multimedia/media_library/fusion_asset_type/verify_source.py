#!/usr/bin/env python3
"""Require the fixed full MediaLibrary source before adding the missing enum."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import digest, validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = (('frameworks/js/src/media_library_napi.cpp',
          'd8a1c5d24e24b8029dc1e5e59cfff529b7edc15ce8a8dfe3105c6b48031bd363',
          '4be781efd4c1ab2be368facd0dce7eb66ce1243dcec2f1a5e43f7672fc4c312e'),
         ('frameworks/js/src/photoaccesshelperinf.js',
          '804aea4300b31167be5a2fed86f0870c95f605ac689ea906f128ecc03dc37127',
          'b283d47255e633b5ed1b0f0ae27ef98ddc835d69ab60cdd2137e50da55ef1439'))
COMPOSED_NATIVE_SHA = 'c45cb3a1a9b65df3dddd37a816660309b82c5c40af4605d63932b5d338335b30'
COMPOSED_WRAPPER_SHA = '5e5035b8b3913f49bc568798ebf83e737e627bec154331f2177db20dba519b4c'
SEARCH_NATIVE_SHA = 'b05869e1ab9a777c2a03b4cb114d161eccc6381ada8992d71984b2516ab43af0'
SEARCH_WRAPPER_SHA = '2488397b285f55dd5b78f5aa0393a67f2c4a4a758867c5b0fbb5d315bb1fce5e'
RECENT_WRAPPER_SHA = '7a8dd9dd99d77b5657cb57bc8cb65d60d681254586f4690919e2870650578a9c'
RECORD_WRAPPER_SHA = '992b87e1cef32bf50fda7ac9893de60762ebdf6f1ea29da9fee18cf7cafe2ed1'
COMPOSED_COVER_FILE = ('frameworks/js/src/photo_album_napi.cpp',
    'ff44f5e8a2cfb8d22c8f3291233e37dcf01a3739111f98360991eed04ba501f2',
    'e24265bb5563eddd384c7c11181ca53697b075f7f3df8c4484178daac7a6535c')


def validate(root, require_patched=False):
    # Recognize only the pristine source, the exact 0001 prefix already used
    # by prior builds, or the complete native + public-wrapper stack. No marker
    # file, reverse hunk or unrelated source edit can authorize a transition.
    root = Path(root).resolve()
    native = root / PROJECT / FILES[0][0]
    cursor = native
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('component input contains a symlink: ' + FILES[0][0])
        cursor = cursor.parent
    native_sha = digest(native.read_bytes())
    search_composed = native_sha == SEARCH_NATIVE_SHA
    composed = search_composed or native_sha == COMPOSED_NATIVE_SHA
    files = ((FILES[0][0], FILES[0][1], native_sha), FILES[1]) if composed else FILES
    if composed:
        wrapper = root / PROJECT / FILES[1][0]
        cursor = wrapper
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError('component input contains a symlink: ' + FILES[1][0])
            cursor = cursor.parent
        wrapper_sha = digest(wrapper.read_bytes())
        if search_composed and wrapper_sha not in (SEARCH_WRAPPER_SHA, RECENT_WRAPPER_SHA, RECORD_WRAPPER_SHA):
            raise ValueError('incomplete source/search Photo composition; preserving source')
        expected_wrapper = wrapper_sha if search_composed else COMPOSED_WRAPPER_SHA
        if wrapper_sha == expected_wrapper:
            files = (files[0], (FILES[1][0], FILES[1][1], expected_wrapper))
    states = tuple(validate_component(root, PROJECT, REVISION, (entry,)) for entry in files)
    if composed:
        # Recognize only the exact FULL Fusion+Photo native source together
        # with its actual cover getter and complete public Fusion wrapper.
        # Unknown sibling edits and partial compositions remain fatal.
        validate_component(root, PROJECT, REVISION, (COMPOSED_COVER_FILE,), require_patched=True)
        if states != (True, True):
            raise ValueError('incomplete composed Photo/Fusion stack; preserving source')
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
