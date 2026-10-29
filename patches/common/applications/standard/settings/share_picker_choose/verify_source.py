#!/usr/bin/env python3
"""Exact complete chooser guard, with one fully proved readonly ancestor view."""
from contextlib import ExitStack
import hashlib
import importlib.util
import os
import subprocess
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
ADDITIONAL_HELPER_SHA256 = '95a43375a75894531689af6e3dcdd868dd0749e771998e258dcd83fcd00de924'


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


def actual_or_idle_preceding_state(root, value):
    """Project only AMS2 after a complete current Idle18 and original chooser proof."""
    root = _apply.source_root(root)
    ams_final = {
        'foundation/ability/ability_runtime/services/abilitymgr/src/ability_manager_service.cpp':
            '5c79649860dabce5b1ef3a6902a38f9aea4b5370b71aa8e06ccfdc9049c4eeb0',
        'foundation/ability/ability_runtime/services/abilitymgr/include/ability_manager_service.h':
            '3bd8401bc3d7192cb0e8ae7ae8aba03db0d68799698a3027ebec21e4e626287c',
    }
    if not any((path := _apply.safe_path(root, name)).is_file() and
               _apply.digest(path.read_bytes()) == expected for name, expected in ams_final.items()):
        return actual_or_preceding_state(root, value)

    # Marker presence only schedules a full proof. It never accepts a file or
    # bypasses either the complete Idle18 or the complete chooser vector.
    helper = additional_helper()
    component = Path(__file__).resolve().parents[4] / 'foundation/ability/ability_runtime/service_idle_startid'
    pinned_assets = {
        'verify_source.py': '378ba36a4037107510e307bdb1381d16da082f537aaea8d779df4aa66ccb2810',
        'source_states.json': '69ad372ea53eafb45c8223e45631baddaf06e53420275297dfc31115ef18a48a',
        '0001-stop-only-the-current-service-request.patch':
            'aca1ab5f8cb09b9f0608ace253e0847b615f0c0ddfe4aeca959cea47525b858c',
    }
    assets = {name: helper.capture(helper.target(component, name)) for name in pinned_assets}
    if any(_apply.digest(assets[name]['data']) != expected for name, expected in pinned_assets.items()):
        raise ValueError('fixed complete Idle18 guard/manifest/patch required')
    module_name = 'share_choose_idle579_complete_source_guard'
    if module_name in sys.modules:
        raise ValueError('cached Idle18 guard refused')
    spec = importlib.util.spec_from_file_location(module_name, component / 'verify_source.py')
    idle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(idle)
    if Path(idle.__file__).resolve() != component / 'verify_source.py':
        raise ValueError('fixed Idle18 source guard path required')
    for name, saved in assets.items():
        if helper.capture(helper.target(component, name)) != saved:
            raise ValueError('Idle18 asset changed during fixed import: ' + name)
    contract = idle.manifest()
    if (set(value['files']) & set(contract['files']) != set(ams_final) or
            set(value['dependencies']) & set(contract['files']) or
            any(contract['files'][name][0] != value['files'][name]['after'] or
                contract['files'][name][1] != expected for name, expected in ams_final.items())):
        raise ValueError('only the exact two chooser/Idle18 AMS successors may project')

    with ExitStack() as stack:
        dialog = _apply.safe_path(root, DIALOG)
        before = (stack.enter_context(helper.preceding_view(root))
                  if dialog.is_file() and _apply.digest(dialog.read_bytes()) == ADDITIONAL_FINAL else {})
        if before and value['files'][DIALOG]['after'] != CHOOSER_FINAL:
            raise ValueError('unknown chooser Additional5 ancestor contract')
        _apply.revisions(root, value)
        idle.heads(root, contract)
        actual_idle = {name: helper.capture(_apply.safe_path(root, name)) for name in contract['files']}
        if {name: _apply.digest(saved['data']) for name, saved in actual_idle.items()} != idle.hashes_for_state(contract, 'final'):
            raise ValueError('complete current Idle18 final required; mixed/legacy/unknown preserved')
        names = sorted(set(value['files']) | set(value['dependencies']))
        actual = {name: helper.capture(_apply.safe_path(root, name)) for name in names}
        if any(actual[name] != actual_idle[name] for name in ams_final):
            raise ValueError('actual AMS changed between complete snapshots')
        try:
            # Reverse only the pinned current patch in a finite temporary copy.
            # Every one of the eighteen ancestor hashes and the entire path set
            # must match before either AMS predecessor byte string is exposed.
            with tempfile.TemporaryDirectory(prefix='share-choose-idle18-') as directory:
                ancestor = Path(directory).resolve(strict=True)
                for name, saved in actual_idle.items():
                    target = _apply.safe_path(ancestor, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(saved['data'])
                    os.chmod(target, saved['mode'])
                subprocess.run(['patch', '--binary', '--batch', '--reverse', '--fuzz=0', '-p1', '-i',
                    str(component / '0001-stop-only-the-current-service-request.patch')], cwd=ancestor, check=True)
                if idle.vector(ancestor, contract) != 'before' or {
                        path.relative_to(ancestor).as_posix() for path in ancestor.rglob('*') if path.is_file()
                } != set(contract['files']):
                    raise ValueError('complete exact Idle18 ancestor and no patch side files required')
                replacements = {name: helper.capture(_apply.safe_path(ancestor, name))['data'] for name in ams_final}
                if before:
                    if (_apply.digest(actual[DIALOG]['data']) != ADDITIONAL_FINAL or
                            _apply.digest(before[DIALOG]) != CHOOSER_FINAL):
                        raise ValueError('actual/preceding Additional5 dialog differs')
                    replacements[DIALOG] = before[DIALOG]
                with tempfile.TemporaryDirectory(prefix='share-choose-idle-view-') as view_directory:
                    view = Path(view_directory).resolve(strict=True)
                    for name, saved in actual.items():
                        target = _apply.safe_path(view, name)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(replacements.get(name, saved['data']))
                        os.chmod(target, saved['mode'])
                    result = _apply.state(view, value, check_revisions=False)
        finally:
            _apply.revisions(root, value)
            idle.heads(root, contract)
            for name, saved in actual_idle.items():
                if helper.capture(_apply.safe_path(root, name)) != saved:
                    raise ValueError('actual Idle18 source changed during readonly view: ' + name)
            for name, saved in actual.items():
                if helper.capture(_apply.safe_path(root, name)) != saved:
                    raise ValueError('actual chooser source changed during readonly view: ' + name)
            for name, saved in assets.items():
                if helper.capture(helper.target(component, name)) != saved:
                    raise ValueError('fixed Idle18 asset changed during readonly view: ' + name)
        if result != 'after':
            raise ValueError('complete chooser final required beneath current Idle18')
        return result


def validate(root, require_patched=False):
    patched = actual_or_idle_preceding_state(root, _apply.manifest()) == 'after'
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
