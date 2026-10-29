#!/usr/bin/env python3
"""Accept only paired fixed AVC wrapper/util states, with the earlier EOS/input stack."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


layout = load('avc_surface_layout_transform', HERE / 'layout.py')
eos = load('avc_surface_layout_eos', HERE.parent / 'avc_eos/verify_source.py')
REVISION = eos.REVISION
MANIFEST = {
    layout.WRAPPER: 'd0ac01afa69a884d986342af5d79965dca8c4eb2e3fcceb8a6cd0059482c82ab',
    layout.UTIL: 'af9284e935e02ea21c64811ebddb36995f0b944e3bfe35aec281593d2bba6bec',
}


def validate(root, require_patched=False):
    root = Path(root).absolute()
    project = root / 'foundation/multimedia/av_codec'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('AVC surface layout requires pinned OpenHarmony 7.0 source')
    originals, actuals = {}, {}
    for name, checksum in MANIFEST.items():
        target = project / name
        if target.is_symlink() or not target.is_file():
            raise ValueError('regular fixed AVC input required: ' + name)
        for parent in target.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError('linked AVC surface layout input rejected')
        original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + name])
        if hashlib.sha256(original).hexdigest() != checksum:
            raise ValueError('AVC layout pinned bytes differ: ' + name)
        originals[name] = original.decode()
        actuals[name] = target.read_text()
    previous = {layout.WRAPPER: eos.repaired_source(originals[layout.WRAPPER]),
                layout.UTIL: originals[layout.UTIL]}
    repaired = {layout.WRAPPER: layout.repair_wrapper(previous[layout.WRAPPER]),
                layout.UTIL: layout.repair_util(previous[layout.UTIL])}
    accepted = (repaired,) if require_patched else (previous, repaired)
    if actuals not in accepted:
        raise ValueError('unknown/incomplete AVC layout changes; no source overwritten')
    return actuals == repaired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('AVC surface layout present: ' + str(validate(args.source_root, args.require_patched)))


if __name__ == '__main__':
    main()
