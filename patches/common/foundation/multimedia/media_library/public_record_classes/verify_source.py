#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/media_library'
REVISION = '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380'
FILES = [('frameworks/js/src/photoaccesshelperinf.js',
          '7a8dd9dd99d77b5657cb57bc8cb65d60d681254586f4690919e2870650578a9c',
          '7843fe2799ab30bb78aae887196b06bcb96471cdc9c6bb0fb5017aab772bcce2')]


def validate(root, require_patched=False):
    try:
        return validate_component(root, PROJECT, REVISION,
            ((FILES[0][0], '2b0cbaa4c727061697794e9ade94cb98c6cabe3d68c7aa5a49956ff33f882f26', '2b0cbaa4c727061697794e9ade94cb98c6cabe3d68c7aa5a49956ff33f882f26'),), require_patched=True)
    except ValueError:
        pass
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
