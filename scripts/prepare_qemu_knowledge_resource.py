#!/usr/bin/env python3
"""Package an optional real trusted ICS resource, keeping its actual provenance.

With no asset, publish only the fixed resource contract/directory. Never invent
calendar dates. An existing complete managed resource is retained on reapply.
The service's bounded actual parser remains responsible for ICS validation.
"""
import argparse
import hashlib
import json
from pathlib import Path

import prepare_qemu_sensor_runtime as shared

DIRECTORY = 'vendor/ohemu/virt/etc/'
CONTRACT = DIRECTORY + 'knowledge_resource.json'
ASSET = DIRECTORY + 'qemu_holidays.ics'
MARKER = '.ohos-qemu-knowledge-calendar.json'
ANCHOR = b'group("product_etc_conf") {\n  deps = [\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def contract(asset):
    return (json.dumps({'schema_version': 1, 'path': '/system/etc/knowledge-content/holidays.ics',
        'format': 'bounded_all_day_ICS_subset', 'optional': True,
        'asset_sha256': sha(asset) if asset is not None else None}, indent=2) + '\n').encode()


def apply(root, asset=None):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError('materialized source root required')
    # Validate the shared source state without generating or interpreting dates.
    build = shared.checked(root, shared.BUILD)
    current = build.read_bytes()
    normalized = current.replace(shared.BLOCK.encode(), b'').replace(shared.DEPENDENCY.encode(), b'')
    present = []
    for block, dependency in shared.KNOWLEDGE_GN:
        count = current.count(block.encode())
        if count not in (0, 1) or count != current.count(dependency.encode()):
            raise ValueError('partial KnowledgeContent product declarations')
        present.append(bool(count))
        normalized = normalized.replace(block.encode(), b'').replace(dependency.encode(), b'')
    if (sha(normalized) != shared.BUILD_SHA or current.count(shared.BLOCK.encode()) != 1 or
            current.count(shared.DEPENDENCY.encode()) != 1 or
            any(shared.optional(shared.checked(root, n)) != data.encode() for n, data in shared.FILES.items())):
        raise ValueError('complete parent sensor/runtime configuration must precede calendar resource preparation')
    names = (CONTRACT, ASSET, MARKER, shared.BUILD)
    snapshots = {name: shared.optional(shared.checked(root, name)) for name in names}
    previous = None
    if snapshots[MARKER] is None:
        if any(snapshots[name] is not None for name in (CONTRACT, ASSET)) or any(present):
            raise ValueError('unmanaged or partial calendar resource; preserving source')
    else:
        previous = json.loads(snapshots[MARKER])
        if (set(previous) != {'schema_version', 'asset_sha256', 'source'} or type(previous['schema_version']) is not int or previous['schema_version'] != 1 or
                previous['asset_sha256'] != (sha(snapshots[ASSET]) if snapshots[ASSET] is not None else None) or
                snapshots[CONTRACT] != contract(snapshots[ASSET]) or present != [True, snapshots[ASSET] is not None] or
                (snapshots[ASSET] is not None and not isinstance(previous['source'], str))):
            raise ValueError('unknown or partial calendar resource bytes; preserving source')
    data = snapshots[ASSET]
    origin = previous['source'] if previous else None
    if asset is not None:
        asset = Path(asset).absolute()
        if asset.is_symlink() or not asset.is_file() or not 0 < asset.stat().st_size <= 1048576:
            raise ValueError('real regular ICS source of at most 1MiB required')
        data = asset.read_bytes()
        data.decode('utf-8')
        origin = str(asset)
    final_build = normalized.replace(ANCHOR, shared.KNOWLEDGE_BLOCK.encode() + ANCHOR + shared.KNOWLEDGE_DEPENDENCY.encode())
    if data is not None:
        final_build = final_build.replace(ANCHOR, shared.KNOWLEDGE_ASSET_BLOCK.encode() + ANCHOR + shared.KNOWLEDGE_ASSET_DEPENDENCY.encode())
    final_build = final_build.replace(ANCHOR, shared.BLOCK.encode() + ANCHOR + shared.DEPENDENCY.encode())
    marker = {'schema_version': 1, 'asset_sha256': sha(data) if data is not None else None, 'source': origin}
    planned = {CONTRACT: contract(data), ASSET: data, MARKER: (json.dumps(marker, indent=2) + '\n').encode(),
               shared.BUILD: final_build}
    written = []
    try:
        for name, value in planned.items():
            path = shared.checked(root, name)
            if shared.optional(path) != snapshots[name]:
                raise ValueError('calendar resource changed after preflight')
            if value != snapshots[name]:
                if value is None:
                    path.unlink()
                else:
                    shared.replace(path, value)
                written.append(name)
    except BaseException:
        for name in reversed(written):
            path = shared.checked(root, name)
            if snapshots[name] is None:
                path.unlink(missing_ok=True)
            else:
                shared.replace(path, snapshots[name])
        raise
    return {'status': 'source_asset_binding_ONLY_NOT_calendar_runtime_or_package', 'asset': marker,
        'files_sha256': {name: sha(value) if value is not None else None for name, value in planned.items()},
        'first_artifact_behavior_gate_passed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--asset', type=Path, help='actual legitimate external all-day ICS input; no synthetic default')
    args = parser.parse_args()
    print(json.dumps(apply(args.source_root, args.asset), indent=2))
