#!/usr/bin/env python3
"""Exact complete three-project vector, never a build or runtime acceptance."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

HERE = Path(__file__).resolve().parent
MIGRATED_CPP = 'foundation/ability/ability_runtime/frameworks/native/ability/native/js_service_extension_context.cpp'
LEGACY_CPP_SHA256 = 'a6e17567ddbef26dbbbf2c4c156ebdc9b08078c5d904b82b7f7121de1dcca78d'


def manifest():
    value = json.loads((HERE / 'source_states.json').read_text())
    if value.get('schema') != 'settings579-conditional-idle-stop-source-vector/v3' or len(value['files']) != 18:
        raise ValueError('Fixed complete 18-file manifest required')
    if (set(value.get('legacy_final', {})) != set(value['files']) or
            set(value.get('previous_napi_final', {})) != set(value['files'])):
        raise ValueError('Complete exact legacy final vector required')
    for name, hashes in value['files'].items():
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or str(path) != name or len(hashes) != 2 or
                hashes[0] == hashes[1] or any(re.fullmatch('[a-f0-9]{64}', h) is None for h in hashes)):
            raise ValueError('Finite exact source path/vector required: ' + name)
        if not any(name.startswith(project + '/') for project in value['projects']):
            raise ValueError('Source outside the three actual projects: ' + name)
        if re.fullmatch('[a-f0-9]{64}', value['legacy_final'][name]) is None:
            raise ValueError('Fixed whole-file legacy source hash required: ' + name)
    service = 'applications/standard/settings/product/phone/src/main/ets/Setting/Accessibility/service/IgnoreRepeatClickService.ets'
    previous = value['previous_napi_final']
    if (value['legacy_final'].get(MIGRATED_CPP) != LEGACY_CPP_SHA256 or
            previous[MIGRATED_CPP] != '0d7dcd29b5fde218ba473b74def468778bb63b62c1c1679fbde3b03fd9448cd6' or
            previous[service] != value['legacy_final'][service] or
            {name for name in previous if previous[name] != value['legacy_final'][name]} != {MIGRATED_CPP} or
            {name for name, pair in value['files'].items() if previous[name] != pair[1]} != {service} or
            {name for name, pair in value['files'].items() if value['legacy_final'][name] != pair[1]} != {MIGRATED_CPP, service}):
        raise ValueError('Only exact whole72/NAPI18 -> direct native SDK26 service may migrate')
    return value


def target(root, name):
    path = root / name
    for parent in path.relative_to(root).parents:
        if (root / parent).is_symlink():
            raise ValueError('Source parent symlink rejected: ' + name)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Complete regular source missing: ' + name)
    return path


def heads(root, value):
    for project, expected in value['projects'].items():
        path = root / project
        if path.is_symlink() or not path.is_dir():
            raise ValueError('Actual regular project missing: ' + project)
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != expected:
            raise ValueError('Actual fixed project HEAD required: ' + project)


def hashes_for_state(value, observed_state):
    if observed_state in ('legacy_final', 'previous_napi_final'):
        return value[observed_state]
    if observed_state not in ('before', 'final'):
        raise ValueError('Unknown complete source state')
    index = 0 if observed_state == 'before' else 1
    return {name: pair[index] for name, pair in value['files'].items()}


def vector(root, value):
    observed = {}
    for name, pair in value['files'].items():
        digest = hashlib.sha256(target(root, name).read_bytes()).hexdigest()
        if digest not in (*pair, value['legacy_final'][name], value['previous_napi_final'][name]):
            raise ValueError('Unknown actual source bytes: ' + name)
        observed[name] = digest
    for observed_state in ('before', 'legacy_final', 'previous_napi_final', 'final'):
        if observed == hashes_for_state(value, observed_state):
            return observed_state
    raise ValueError('Mixed conditional-stop source vector rejected')


def state(root):
    value = manifest()
    heads(root, value)
    return vector(root, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    observed = state(args.source_root.resolve())
    if args.require_final and observed != 'final':
        raise ValueError('Complete final conditional-stop source vector required')
    print(json.dumps({'state': observed, 'scope': 'source_only_NOT_runtime_acceptance'}))


if __name__ == '__main__':
    main()
