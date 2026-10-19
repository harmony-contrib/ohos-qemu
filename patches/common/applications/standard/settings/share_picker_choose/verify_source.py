#!/usr/bin/env python3
"""Exact complete Settings/native chooser source guard; no runtime claim."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location('share_choose_apply', Path(__file__).with_name('apply.py'))
_apply = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_apply)


def validate(root, require_patched=False):
    patched = _apply.state(root, _apply.manifest()) == 'after'
    if require_patched and not patched:
        raise ValueError('complete native and Settings chooser candidate required')
    return patched


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('patched' if validate(args.source_root, args.require_patched) else 'predecessor')
