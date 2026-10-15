#!/usr/bin/env python3
"""Install the pinned system widget declaration into an isolated API26 SDK.

No types are invented. The loader copy only adapts its two relative Want imports.
This prepares test compilation, not a guest or artifact capability proof.
"""
import argparse
import json
from pathlib import Path
from build_insight_form_host_probe import COMPONENT_DECLARATION, COMPONENT_SHA256, LOADER_DECLARATION
from run_root_probe import digest

PROJECT_HEAD = '43e34facc58b9c0f15c58571554ddd7eaa004455'
SOURCE_PATH = 'interface/sdk-js/api/@internal/component/ets/form_component.d.ts'


def prepare(sdk, declaration):
    sdk, declaration = Path(sdk), Path(declaration)
    if declaration.is_symlink() or not declaration.is_file() or digest(declaration) != COMPONENT_SHA256:
        raise ValueError('complete pinned system declaration required')
    for part in ('ets', 'native'):
        metadata = json.loads((sdk / part / 'oh-uni-package.json').read_text())
        if any(metadata.get(key) != value for key, value in (
                ('apiVersion', '26'), ('releaseType', 'Release'), ('platformVersion', '26.0.0'))):
            raise ValueError('isolated API26 Release SDK required')
    source = declaration.read_bytes()
    if source.count(b"import('../api/") != 2:
        raise ValueError('pinned loader import adaptation differs')
    inputs = {COMPONENT_DECLARATION: source,
              LOADER_DECLARATION: source.replace(b"import('../api/", b"import('../../../api/")}
    # Validate both destinations before changing either. Unknown SDK files remain intact.
    for name, data in inputs.items():
        path = sdk / name
        if any(parent.is_symlink() for parent in (path, *path.parents)
               if parent == sdk or parent.is_relative_to(sdk)):
            raise ValueError('SDK declaration destination must not traverse a symlink')
        if path.exists() and (not path.is_file() or path.read_bytes() != data):
            raise ValueError('unknown existing SDK declaration: ' + name)
    for name, data in inputs.items():
        path = sdk / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(data)
    return dict(status='pass_sdk_preparation_only', first_artifact_behavior_gate_passed=False,
        source_project_head=PROJECT_HEAD, source_path=SOURCE_PATH,
        source_sha256=COMPONENT_SHA256,
        sdk_declarations={name: digest(sdk / name) for name in inputs},
        adaptation='exactly two relative Want imports; all type declarations unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'declaration', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.sdk, args.declaration)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
