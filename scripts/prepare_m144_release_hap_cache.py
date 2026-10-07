#!/usr/bin/env python3
"""Prepare the exact Release HAP tools in an owned, verified host cache.

Only download/extraction run on the host; original tool code is unchanged.
All actual HAP compilation runs in local Docker with this cache read-only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

LOCK = 'scripts/m144_hap_tools/release-tools-lock.json'


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def recipe(repository):
    repository = Path(repository)
    lock = json.loads((repository / LOCK).read_text())
    if (lock.get('schema_version') != 1 or lock.get('hvigor_version') != '6.0.0-release-patch-rc.2'
            or lock.get('sdkmanager_version') != '2.26.2'
            or lock.get('archive_sha256') != '83e45209c65662bbeab81d36d691807bf8db56d94d7d15c959600dcc348814c3'
            or lock.get('archive_url') != 'https://repo.huaweicloud.com/harmonyos/compiler/hvigor/6.0.0-release-patch-rc.2/command-line-tools.tar'
            or lock.get('build_revision') != '5c0623072ed9c2ee93ab909a7a01f428fee95082'
            or lock.get('node_version') != 'v18.20.1' or lock.get('npm_version') != '10.5.0'
            or lock.get('project_model_version') != '6.0.0'):
        raise ValueError('fixed Release HAP tool selection differs')
    names = [LOCK]
    inputs = {}
    for name in names:
        path = repository / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('owned fixed HAP recipe input required: ' + name)
        inputs[name] = sha(path)
    return {'lock': lock, 'inputs_sha256': inputs, 'recipe_sha256': hashlib.sha256(
        json.dumps(inputs, sort_keys=True).encode()).hexdigest()}


def tree_digest(cache):
    root = Path(cache) / 'hvigor'
    if root.is_symlink() or not root.is_dir():
        raise ValueError('owned complete HAP tool tree required')
    entries = {}
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in (*dirs, *names):
            path = Path(current) / name
            key = str(path.relative_to(root))
            if path.is_symlink():
                if not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError('HAP tool link escapes owned tree')
                entries[key] = {'link': str(path.readlink())}
            elif path.is_file():
                entries[key] = {'sha256': sha(path), 'executable': bool(path.stat().st_mode & 0o111)}
    if not entries:
        raise ValueError('empty HAP tools')
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def verify(cache, expected):
    cache = Path(cache)
    if cache.is_symlink():
        raise ValueError('owned HAP tool cache required')
    record = json.loads((cache / 'cache-evidence.json').read_text())
    if record.get('status') != 'pass' or any(record.get(key) != value for key, value in expected.items()):
        raise ValueError('HAP tool cache recipe differs')
    if tree_digest(cache) != record.get('installed_tree_sha256'):
        raise ValueError('HAP tool cache content changed')
    roles = {'hvigor': expected['lock']['hvigor_version'],
             'hvigor-ohos-plugin': expected['lock']['hvigor_version'],
             'hvigor-ohos-plugin/node_modules/@ohos/sdkmanager-common': expected['lock']['sdkmanager_version']}
    for role, version in roles.items():
        if json.loads((cache / 'hvigor' / role / 'package.json').read_text()).get('version') != version:
            raise ValueError('HAP tool package version differs: ' + role)
    return record


def prepare(repository, cache_root, archive=None):
    expected = recipe(repository)
    cache_root = Path(cache_root)
    if cache_root.is_symlink():
        raise ValueError('owned HAP cache root required')
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / expected['recipe_sha256']
    if target.exists() or target.is_symlink():
        verify(target, expected)
        return target
    staging = Path(tempfile.mkdtemp(prefix='release-hap-tools-', dir=cache_root))
    if archive is None:
        archive = staging / 'command-line-tools.tar'
        subprocess.run(['curl', '-fL', '--retry', '2', '--output', str(archive),
                        expected['lock']['archive_url']], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE)
    archive = Path(archive)
    if archive.is_symlink() or sha(archive) != expected['lock']['archive_sha256']:
        raise ValueError('fixed Release HAP archive checksum differs')
    with tarfile.open(archive) as source:
        members, seen = [], set()
        for member in source.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or '\\' in member.name:
                raise ValueError('unsafe HAP tool archive path')
            if not name.parts or name.parts[0] != 'hvigor':
                continue
            if member.name in seen:
                raise ValueError('duplicate HAP tool archive entry')
            seen.add(member.name)
            members.append(member)
        if not members:
            raise ValueError('missing HAP tool archive subtree')
        source.extractall(staging, members=members, filter='data')
    record = {'status': 'pass', **expected, 'installed_tree_sha256': tree_digest(staging),
              'scope': 'fixed_release_paired_HAP_host_tools_NOT_HAP_or_guest_acceptance',
              'dependency_scripts_executed': False, 'sdk_metadata_modified': False,
              'official_tool_code_modified': False,
              'first_artifact_behavior_gate_passed': False}
    (staging / 'cache-evidence.json').write_text(json.dumps(record, indent=2) + '\n')
    verify(staging, expected)
    staging.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    print(prepare(args.repository, args.cache_root, args.archive))


if __name__ == '__main__':
    main()
