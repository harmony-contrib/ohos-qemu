#!/usr/bin/env python3
"""Exact complete chooser guard, with one fully proved readonly ancestor view."""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile

_spec = importlib.util.spec_from_file_location('share_choose_apply', Path(__file__).with_name('apply.py'))
_apply = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_apply)

DIALOG = 'foundation/ability/ability_runtime/services/abilitymgr/src/dialog_session/dialog_session_manager.cpp'
CHOOSER_FINAL = '65d04f5cf9dfaf1f0aaa267ff8b0dfa06296a0ea600e25ceac2ac0438a60f11a'
ADDITIONAL_FINAL = 'b3dec3bcc065de6c80814fd3c0cca599f80da43f25f00c5e56406732f57aef63'
ADDITIONAL_HELPER_SHA256 = '148960d9f68f668967e86d1c98b26b7b37e124bc915e2b66a3c5a6871bdc00c0'


def additional_helper():
    path = Path(__file__).resolve().parents[6] / 'scripts/apply_additional579_product.py'
    if path.resolve() != path or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('fixed Additional5 helper path required')
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('fixed regular Additional5 helper required')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ADDITIONAL_HELPER_SHA256:
        raise ValueError('unknown Additional5 helper bytes')
    name = 'share_choose_additional579_source_guard'
    if name in sys.modules:
        raise ValueError('cached Additional5 helper refused')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != path or path.read_bytes() != data:
        raise ValueError('Additional5 helper changed during fixed import')
    return module


def actual_or_preceding_state(root, value):
    root = _apply.source_root(root)
    path = _apply.safe_path(root, DIALOG)
    if not path.is_file() or _apply.digest(path.read_bytes()) != ADDITIONAL_FINAL:
        return _apply.state(root, value)

    # This branch never alters source or the real apply.state contract. Only
    # the exact five-final vector, both asset vectors and all three actual
    # project HEADs authorize the one known dialog predecessor substitution.
    helper = additional_helper()
    if value['files'][DIALOG]['after'] != CHOOSER_FINAL:
        raise ValueError('unknown chooser ancestor contract')
    with helper.preceding_view(root) as before:
        _apply.revisions(root, value)
        names = sorted(set(value['files']) | set(value['dependencies']))
        actual = {name: helper.capture(_apply.safe_path(root, name)) for name in names}
        if _apply.digest(actual[DIALOG]['data']) != ADDITIONAL_FINAL or _apply.digest(before[DIALOG]) != CHOOSER_FINAL:
            raise ValueError('actual/preceding dialog source differs')
        with tempfile.TemporaryDirectory(prefix='share-choose-additional579-') as directory:
            view = Path(directory).resolve(strict=True)
            for name, saved in actual.items():
                target = _apply.safe_path(view, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(before[DIALOG] if name == DIALOG else saved['data'])
                os.chmod(target, saved['mode'])
            result = _apply.state(view, value, check_revisions=False)
        _apply.revisions(root, value)
        for name, saved in actual.items():
            if helper.capture(_apply.safe_path(root, name)) != saved:
                raise ValueError('actual chooser source changed during readonly view: ' + name)
        if result != 'after':
            raise ValueError('complete chooser final required beneath Additional5')
        return result


def validate(root, require_patched=False):
    patched = actual_or_preceding_state(root, _apply.manifest()) == 'after'
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
