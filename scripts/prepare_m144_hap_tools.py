#!/usr/bin/env python3
"""Select paired Release Hvigor tools from the verified, read-only cache.

The full release Node/npm is separate from Chromium's npm-free Node 24.
No source/SDK binaries, HOME, permissions or bundled wrapper code are replaced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from prepare_m144_release_hap_cache import recipe, sha, verify

BUILD_REVISION = '5c0623072ed9c2ee93ab909a7a01f428fee95082'
NODE_RELATIVE = 'prebuilts/build-tools/common/nodejs/node-v18.20.1-linux-x64'
VERSION_CASES = [('25', True), ('26', False), ('26.0.0', True), ('26.1.2', True),
                 ('0', False), ('26..0', False), ('26.1', False), ('master', False),
                 ('-26', False), (None, False), (26, False)]


def sdk_version_check(cache, node):
    module = Path(cache) / 'hvigor/hvigor-ohos-plugin/node_modules/@ohos/sdkmanager-common'
    script = '''const {ApiVersion}=require(process.argv[1]);
const cases=JSON.parse(process.argv[2]);
const rows=cases.map(([value, expected])=>{let accepted=false;
try {new ApiVersion(value); accepted=true;} catch (_) {}
return {value,expected,accepted};});
process.stdout.write(JSON.stringify(rows));
process.exitCode=rows.every(row=>row.expected===row.accepted)?0:1;'''
    result = subprocess.run([str(node), '-e', script, str(module), json.dumps(VERSION_CASES)],
                            capture_output=True, timeout=30)
    expected = [{'value': value, 'expected': wanted, 'accepted': wanted} for value, wanted in VERSION_CASES]
    try:
        rows = json.loads(result.stdout)
    except (ValueError, TypeError):
        rows = None
    return {'status': 'pass' if result.returncode == 0 and rows == expected else 'fail',
            'exit_code': result.returncode, 'rows': rows,
            'stderr': result.stderr.decode(errors='replace')}


def release_node(ohos):
    ohos = Path(ohos).resolve()
    if not os.statvfs(ohos).f_flag & os.ST_RDONLY:
        raise ValueError('fixed release host tools must be read-only')
    build = ohos / 'build'
    revision = subprocess.check_output(['git', '-C', str(build), 'rev-parse', 'HEAD'], text=True).strip()
    config = build / 'prebuilts_config.json'
    if revision != BUILD_REVISION or config.read_bytes() != subprocess.check_output(
            ['git', '-C', str(build), 'show', 'HEAD:prebuilts_config.json']):
        raise ValueError('fixed release Node selection changed')
    document = json.loads(config.read_text())
    selected = next(row for row in document['tool_list'] if row['name'] == 'node')
    wanted = '/nodejs/v18.20.1/node-v18.20.1-linux-x64.tar.gz'
    if sum(row.get('remote_url') == wanted for row in selected['config']['linux']['x86_64']) != 1:
        raise ValueError('release full Node is not selected by the fixed config')
    lock = recipe(Path(__file__).resolve().parents[1])['lock']
    hvigor = next(row for row in document['tool_list'] if row['name'] == 'hvigor')
    wanted = lock['archive_url'].removeprefix('https://repo.huaweicloud.com')
    if sum(row.get('remote_url') == wanted for row in hvigor['config']['linux']['x86_64']) != 1:
        raise ValueError('paired Hvigor is not selected by the fixed release config')
    node_root = ohos / NODE_RELATIVE
    node, npm = node_root / 'bin/node', node_root / 'bin/npm'
    if not npm.is_file() or not os.access(npm, os.X_OK) or not npm.resolve().is_relative_to(node_root):
        raise ValueError('full release npm is missing or aliased outside its tool tree')
    if subprocess.check_output([str(node), '--version'], text=True).strip() != 'v18.20.1':
        raise ValueError('full release Node version differs')
    if json.loads((node_root / 'lib/node_modules/npm/package.json').read_text())['version'] != '10.5.0':
        raise ValueError('full release npm version differs')
    return node_root, {'build_revision': revision, 'config_sha256': sha(config),
                       'node_sha256': sha(node), 'npm_cli_sha256': sha(npm.resolve()),
                       'node_version': 'v18.20.1', 'npm_version': '10.5.0'}


def seed(cache, repository, project, home=None):
    cache, project = Path(cache).resolve(), Path(project).resolve()
    if not os.statvfs(cache).f_flag & os.ST_RDONLY:
        raise ValueError('locked HAP host cache must be mounted read-only')
    record = verify(cache, recipe(repository))
    if not project.is_dir():
        raise ValueError('actual HAP project is absent')
    home = Path.home() if home is None else Path(home)
    if not home.is_absolute() or not home.is_dir():
        raise ValueError('preserve the real existing HOME')
    key = hashlib.md5(str(project).encode()).hexdigest()  # exact fixed wrapper cache key, not integrity
    target = home / '.hvigor/project_caches' / key / 'workspace'
    destinations = {'workspace': target}
    for role, target in destinations.items():
        if target.exists() or target.is_symlink():
            raise ValueError('refusing to overwrite an existing Hvigor cache: ' + role)
        for parent in target.parents:
            if parent == home:
                break
            if parent.is_symlink():
                raise ValueError('Hvigor cache ancestor must not redirect outside HOME')
    modules = target / 'node_modules/@ohos'
    modules.mkdir(parents=True)
    for role in ('hvigor', 'hvigor-ohos-plugin'):
        (modules / role).symlink_to(cache / 'hvigor' / role, target_is_directory=True)
    return {'recipe_sha256': record['recipe_sha256'],
            'installed_tree_sha256': record['installed_tree_sha256'],
            'project_cache_key': key, 'cache': str(cache),
            'official_wrapper_unchanged': True, 'dependency_network_required': False,
            'lock': record['lock'], 'sdk_metadata_modified': False,
            'official_tool_code_modified': record['official_tool_code_modified']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--ohos-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    if args.evidence.exists() or args.evidence.is_symlink():
        raise ValueError('fresh HAP host tool evidence path required')
    if not os.statvfs(args.cache_root).f_flag & os.ST_RDONLY:
        raise ValueError('paired HAP tool cache must be mounted read-only')
    verify(args.cache_root, recipe(args.repository))
    node_root, node_evidence = release_node(args.ohos_root)
    source = args.source_root.resolve()
    link = source / 'ohos_sdk/nodejs'
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() != node_root:
            raise ValueError('unknown existing HAP Node alias')
    elif link.exists():
        raise ValueError('refusing to replace an existing HAP Node tree')
    else:
        link.symlink_to(node_root, target_is_directory=True)
    hvigor = source / 'ohos_sdk/hvigor'
    cache_tools = args.cache_root.resolve() / 'hvigor'
    if hvigor.is_symlink():
        if hvigor.resolve() != cache_tools:
            raise ValueError('unknown existing HAP tool alias')
    elif hvigor.exists():
        raise ValueError('refusing to replace existing HAP tools')
    else:
        hvigor.symlink_to(cache_tools, target_is_directory=True)
    result = seed(args.cache_root, args.repository, source / 'third_party/ohos_nweb_hap')
    result.update(scope='fixed_release_paired_Hvigor_host_tools_NOT_HAP_or_guest_acceptance',
                  release_node=node_evidence, first_artifact_behavior_gate_passed=False)
    if args.preflight:
        project = source / 'third_party/ohos_nweb_hap'
        env = dict(os.environ, NODE_HOME=str(node_root),
                   PATH=str(node_root / 'bin') + ':' + os.environ.get('PATH', ''),
                   OHOS_BASE_SDK_HOME=str(source / 'ohos_sdk'),
                   npm_config_offline='true', NPM_CONFIG_OFFLINE='true')
        argv = [str(cache_tools / 'bin/hvigorw'), '--version']
        process = subprocess.run(argv, cwd=project, env=env, capture_output=True, timeout=90)
        result['preflight'] = {'argv': argv, 'exit_code': process.returncode,
                               'stdout': process.stdout.decode(errors='replace'),
                               'stderr': process.stderr.decode(errors='replace')}
        result['sdk_version_boundary'] = sdk_version_check(args.cache_root, node_root / 'bin/node')
        result['status'] = 'pass' if (process.returncode == 0 and
            process.stdout.strip().decode() == result['lock']['hvigor_version'] and
            result['sdk_version_boundary']['status'] == 'pass') else 'fail'
    args.evidence.write_text(json.dumps(result, indent=2) + '\n')
    if args.preflight and result['status'] != 'pass':
        raise ValueError('official Hvigor offline preflight failed; preserved both streams in evidence')
    print(json.dumps({'scope': result['scope'], 'recipe_sha256': result['recipe_sha256']}))


if __name__ == '__main__':
    main()
