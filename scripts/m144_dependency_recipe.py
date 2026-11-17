#!/usr/bin/env python3
"""Version default dependency caches by the actual fixed-release recipe.

No artifacts are deleted or overwritten. Unrelated OS/test edits do not force a
Chromium rebuild; changing source locks, engine patches or dependency builders
selects a fresh cache. Explicit artifact directories still fail closed if stale.
"""
import argparse
import hashlib
import json
from pathlib import Path

REQUIRED = ('scripts/m144_release_source_lock.json', 'scripts/openharmony_7_0_release_source_lock.json',
            'scripts/run_m144_release_build_docker.sh', 'scripts/docker/m144-build-env.Dockerfile',
            'scripts/snapshot_build_inputs.py', 'scripts/verify_alsa_config_image.py',
            'scripts/verify_runtime_elf_contract.py', 'patches/lib/apply_patch.sh',
            'patches/lib/apply_component_dir.sh', 'patches/lib/avc_artifacts.py')
REQUIRED += ('patches/lib/apply_component_stack.py',)
REQUIRED += ('scripts/m144_hap_tools/release-tools-lock.json',)
PATTERNS = ('build_m144*', 'prepare_m144*', 'run_m144*', 'package_m144*', 'record_m144*',
            'verify_m144*', 'm144_*', 'verify_arkweb_core_image.py', 'ext_image_entries.py')
COMPONENTS = ('patches/common/web/arkweb', 'patches/common/arkcompiler/jsvm')


def recipe(repository):
    repository = Path(repository).resolve()
    paths = {repository / name for name in REQUIRED}
    for pattern in PATTERNS:
        paths.update((repository / 'scripts').glob(pattern))
    for relative in COMPONENTS:
        paths.update((repository / relative).rglob('*'))
    result = {}
    for path in sorted(paths):
        if path.suffix in ('.md', '.pyc') or '__pycache__' in path.parts or path.name == '.DS_Store':
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(repository):
            raise ValueError('dependency recipe input must be an owned regular file: ' + str(path))
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('fixed dependency recipe input missing: ' + str(path))
        result[str(path.relative_to(repository))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if any(name not in result for name in REQUIRED):
        raise ValueError('incomplete fixed dependency recipe')
    return {'schema_version': 1, 'files_sha256': result,
            'recipe_sha256': hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    result = recipe(args.repository)
    print(json.dumps(result, indent=2) if args.json else result['recipe_sha256'])


if __name__ == '__main__':
    main()
