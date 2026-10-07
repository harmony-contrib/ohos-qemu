#!/usr/bin/env python3
"""Run the fixed HAP wrapper in owned staging, retaining both diagnostic streams.

This is a host dependency bootstrap check, not a HAP build or guest gate.
Use an ephemeral container with read-only source and a fresh evidence directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ohos-root', type=Path, help='use the full Node pinned by the release build project')
    parser.add_argument('--inherit-host-env', action='store_true', help='retain host proxy configuration for dependency tools')
    parser.add_argument('--public-ohos-registry', action='store_true', help='use the public source for the fixed @ohos packages')
    parser.add_argument('--explicit-proxy-config', action='store_true', help='pass configured proxies to pnpm through npmrc')
    parser.add_argument('--repository', type=Path)
    parser.add_argument('--assemble-hap', action='store_true', help='diagnose actual entry target compilation in an owned project copy')
    parser.add_argument('--release-hvigor', action='store_true', help='use the paired fixed release Hvigor CLI and plugin, not the obsolete project downloader')
    parser.add_argument('--release-tool-cache', type=Path, help='verified unmodified paired Release tool archive')
    parser.add_argument('--dot-api26', action='store_true', help='use the native Release API26 project version and SDK layout without modifying SDK metadata')
    args = parser.parse_args()
    source = args.source_root.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('actual fixed source must be mounted read-only')
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('fresh bootstrap evidence directory required')
    args.output.mkdir(parents=True)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != 'a8168622b056f25c2e68d5f12fe2759bad2d9a44':
        raise ValueError('bootstrap requires the fixed Chromium release')
    node = source / 'third_party/node/linux/node-linux-x64/bin/node'
    expected_version = 'v24.11.1'
    if args.ohos_root:
        ohos = args.ohos_root.resolve()
        if not os.statvfs(ohos).f_flag & os.ST_RDONLY:
            raise ValueError('release build tools must be mounted read-only')
        build_revision = subprocess.check_output(['git', '-C', str(ohos / 'build'), 'rev-parse', 'HEAD'], text=True).strip()
        if build_revision != '5c0623072ed9c2ee93ab909a7a01f428fee95082':
            raise ValueError('release build project differs')
        node = ohos / 'prebuilts/build-tools/common/nodejs/node-v18.20.1-linux-x64/bin/node'
        expected_version = 'v18.20.1'
    version = subprocess.check_output([str(node), '--version'], text=True).strip()
    if version != expected_version:
        raise ValueError('bootstrap requires the actual pinned Node')
    project = source / 'third_party/ohos_nweb_hap'
    files = ('hvigorw', 'hvigor/hvigor-wrapper.js', 'hvigor/hvigor-config.json5',
             'hvigorfile.js', 'oh-package.json5')
    inputs = {str(project / name): digest(project / name) for name in files}
    inputs[str(node)] = digest(node)
    npm = node.parent / 'npm'
    npm_present = npm.is_file() and os.access(npm, os.X_OK)
    if npm_present:
        inputs[str(npm.resolve())] = digest(npm.resolve())
    npmrc = Path.home() / '.npmrc'
    if npmrc.exists() or npmrc.is_symlink():
        raise ValueError('bootstrap requires a private fresh container npm configuration')
    # Match HapProject._ensure_npmrc exactly; preserve the real HOME.
    config = ('no-proxy=.huawei.com\nstrict-ssl=false\n'
                     'registry=https://repo.huaweicloud.com/repository/npm/\n'
                     'disturl=https://repo.huaweicloud.com/nodejs/\n'
                     + ('@ohos:registry=https://repo.harmonyos.com/npm/\n'
                        if args.public_ohos_registry else ''))
    if args.explicit_proxy_config:
        for key, candidates in (('proxy', ('HTTP_PROXY', 'http_proxy')),
                                ('https-proxy', ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'))):
            variable = next((name for name in candidates if os.environ.get(name)), None)
            if variable:
                config += key + '=${' + variable + '}\n'
    npmrc.write_text(config)
    env = dict(os.environ) if args.inherit_host_env else {}
    env.update({'HOME': os.environ['HOME'], 'OHOS_BASE_SDK_HOME': str(source / 'ohos_sdk'),
           'NODE_HOME': str(node.parent.parent),
           'PATH': str(node.parent) + ':' + os.environ.get('PATH', '')})
    with tempfile.TemporaryDirectory(prefix='m144-real-hvigor-bootstrap-') as directory:
        staging = Path(directory) / 'project'
        staging.mkdir()
        sdk_evidence = None
        if args.assemble_hap:
            if not args.ohos_root:
                raise ValueError('actual release SDK required for entry target diagnosis')
            # Hvigor must be allowed to create its own SDK bookkeeping, as in
            # the production private API26 SDK. Never make the source writable.
            sdk_source = args.ohos_root / 'prebuilts/ohos-sdk/linux/26.0.0'
            sdk_home = Path(directory) / 'sdk-home'
            sdk = sdk_home / 'openharmony'
            sdk.mkdir(parents=True)
            sdk_evidence = {}
            for component in ('native', 'ets', 'js', 'toolchains', 'previewer'):
                original = sdk_source / component
                subprocess.run(['cp', '--archive', '--reflink=auto', str(original), str(sdk / component)], check=True)
                metadata = original / 'oh-uni-package.json'
                if digest(metadata) != digest(sdk / component / metadata.name):
                    raise ValueError('diagnostic private SDK metadata differs')
                sdk_evidence[component] = {'source': str(original), 'metadata_sha256': digest(metadata)}
            (sdk_home / '26').symlink_to(sdk, target_is_directory=True)
            if args.dot_api26:
                (sdk_home / '26.0.0').symlink_to(sdk, target_is_directory=True)
            env['OHOS_BASE_SDK_HOME'] = str(sdk_home)
            shutil.copytree(project, staging, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('.git', '.hvigor', 'build', 'node_modules',
                                                         'oh_modules', 'local.properties', '.idea'))
            if args.dot_api26 and not args.release_tool_cache:
                profile = staging / 'build-profile.json5'
                original = profile.read_text()
                if original.count('"compileSdkVersion": 26,') != 1:
                    raise ValueError('unexpected diagnostic project SDK declaration')
                profile.write_text(original.replace('"compileSdkVersion": 26,', '"compileSdkVersion": "26.0.0",'))
        for name in files:
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project / name, target)
        cache_evidence = None
        release_hvigor_evidence = None
        executable = [str(staging / 'hvigorw')]
        if args.release_hvigor:
            if not args.ohos_root:
                raise ValueError('paired release Hvigor requires release tools')
            tools = args.ohos_root / 'prebuilts/tool/command-line-tools/6.x/hvigor'
            verified_tools = None
            if args.release_tool_cache:
                if not args.repository or not os.statvfs(args.release_tool_cache).f_flag & os.ST_RDONLY:
                    raise ValueError('paired cache requires repository verification and a read-only mount')
                sys.path.insert(0, str(args.repository / 'scripts'))
                from prepare_m144_release_hap_cache import recipe, verify
                verified_tools = verify(args.release_tool_cache, recipe(args.repository))
                tools = args.release_tool_cache / 'hvigor'
            expected = '6.0.0-release-patch-rc.2'
            roles = {'hvigor': tools / 'hvigor', 'hvigor-ohos-plugin': tools / 'hvigor-ohos-plugin'}
            for role, target in roles.items():
                if json.loads((target / 'package.json').read_text())['version'] != expected:
                    raise ValueError('paired release Hvigor version differs: ' + role)
            # Match the official CLI's per-project dependency directory without
            # letting an older project wrapper download unrelated versions.
            key = hashlib.md5(str(staging.resolve()).encode()).hexdigest()
            if args.release_tool_cache:
                from prepare_m144_hap_tools import seed, release_node
                actual_node, release_node_evidence = release_node(args.ohos_root)
                if actual_node / 'bin/node' != node:
                    raise ValueError('production Node selection differs')
                cache_evidence = seed(args.release_tool_cache, args.repository, staging)
                cache_evidence['release_node'] = release_node_evidence
                template_patch = args.repository / 'patches/common/web/arkweb/m144_core_build/0009-select-release-hvigor-in-the-public-project-source-template.patch'
                # Match official prepare: patch the authoritative source input
                # and copy it into the disposable project's generated config.
                applied = subprocess.run(['git', '-C', str(staging), 'apply', '--check', '-p4',
                                          str(template_patch)], capture_output=True)
                if applied.returncode == 0:
                    subprocess.run(['git', '-C', str(staging), 'apply', '-p4', str(template_patch)], check=True)
                else:
                    subprocess.run(['git', '-C', str(staging), 'apply', '--reverse', '--check', '-p4',
                                    str(template_patch)], check=True)
                shutil.copy2(staging / 'dependencies/rk/hvigor/hvigor-config.json5',
                             staging / 'hvigor/hvigor-config.json5')
                patch = args.repository / 'patches/common/web/arkweb/m144_core_package/0007-use-fixed-release-hvigor-without-project-downloaders.patch'
                checked = subprocess.run(['git', '-C', str(staging), 'apply', '--check', '-p4', str(patch)], capture_output=True)
                if checked.returncode == 0:
                    subprocess.run(['git', '-C', str(staging), 'apply', '-p4', str(patch)], check=True)
                else:
                    subprocess.run(['git', '-C', str(staging), 'apply', '--reverse', '--check', '-p4', str(patch)], check=True)
                if args.dot_api26:
                    patch = args.repository / 'patches/common/web/arkweb/m144_core_package/0008-use-native-release-dot-api26-project-version.patch'
                    checked = subprocess.run(['git', '-C', str(staging), 'apply', '--check', '-p4', str(patch)], capture_output=True)
                    if checked.returncode == 0:
                        subprocess.run(['git', '-C', str(staging), 'apply', '-p4', str(patch)], check=True)
                    else:
                        subprocess.run(['git', '-C', str(staging), 'apply', '--reverse', '--check', '-p4', str(patch)], check=True)
                (Path(env['OHOS_BASE_SDK_HOME']) / 'hvigor').symlink_to(tools, target_is_directory=True)
                env['npm_config_offline'] = 'true'
                env['NPM_CONFIG_OFFLINE'] = 'true'
            else:
                modules = Path.home() / '.hvigor/project_caches' / key / 'workspace/node_modules/@ohos'
                modules.mkdir(parents=True, exist_ok=False)
                for role, target in roles.items():
                    (modules / role).symlink_to(target, target_is_directory=True)
                (staging / 'hvigor/hvigor-config.json5').write_text(json.dumps({
                    'modelVersion': '6.0.0' if args.dot_api26 else '5.0.0', 'dependencies': {},
                    'properties': {'hvigor.dependency.useNpm': True}}) + '\n')
                if args.dot_api26:
                    package = staging / 'oh-package.json5'
                    original = package.read_text()
                    if original.count('"modelVersion": "5.0.0"') != 1:
                        raise ValueError('unexpected original project model version')
                    package.write_text(original.replace('"modelVersion": "5.0.0"', '"modelVersion": "6.0.0"'))
            cli = tools / 'hvigor/bin/hvigor.js'
            inputs[str(cli)] = digest(cli)
            executable = [str(staging / 'hvigorw') if args.release_tool_cache else str(tools / 'bin/hvigorw')]
            release_hvigor_evidence = {'version': expected, 'cli_sha256': digest(cli),
                                       'project_cache_key': key, 'source_tools_readonly': True,
                                       'verified_cache': verified_tools}
        argv = executable + ['--version']
        if args.assemble_hap:
            argv = executable + ['--mode=module', '-p', 'module=entry@default',
                    '-p', 'product=default', 'clean', '-p', 'debuggable=false',
                    'assembleHap', '--no-daemon', '--stacktrace']
        with (args.output / 'stdout.log').open('x') as stdout, (args.output / 'stderr.log').open('x') as stderr:
            result = subprocess.run(argv, cwd=staging, env=env, stdout=stdout,
                                    stderr=stderr, timeout=600 if args.assemble_hap else 240)
        hap_evidence = None
        if args.assemble_hap:
            produced = staging / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
            hap_evidence = {'unsigned_hap_created': produced.is_file(), 'diagnostic_copy_only': True}
            if produced.is_file():
                shutil.copy2(produced, args.output / 'diagnostic-entry-unsigned.hap')
                hap_evidence['sha256'] = digest(args.output / 'diagnostic-entry-unsigned.hap')
    failures = []
    if result.returncode:
        failures.append('fixed real Hvigor wrapper bootstrap failed; see preserved streams')
    if args.assemble_hap and not hap_evidence['unsigned_hap_created']:
        failures.append('actual explicitly selected entry target did not produce the required HAP')
    if any(digest(Path(name)) != value for name, value in inputs.items()):
        failures.append('read-only source input changed')
    report = {'scope': ('actual_pinned_Hvigor_owned_entry_HAP_compilation_NOT_official_core_provenance_or_guest'
                       if args.assemble_hap else 'actual_pinned_Hvigor_host_dependency_bootstrap_NOT_HAP_or_guest'),
              'status': 'fail' if failures else 'pass', 'source_revision': revision,
              'node_version': version, 'inputs_sha256': inputs, 'argv': argv,
              'npm_present': npm_present,
              'inherited_host_environment': args.inherit_host_env,
              'public_ohos_registry': args.public_ohos_registry,
              'explicit_proxy_config': args.explicit_proxy_config,
              'offline_cache_evidence': cache_evidence,
              'paired_release_hvigor': release_hvigor_evidence,
              'diagnostic_hap': hap_evidence,
              'diagnostic_private_sdk': sdk_evidence,
              'exit_code': result.returncode, 'failures': failures,
              'streams_sha256': {name: digest(args.output / name) for name in ('stdout.log', 'stderr.log')},
              'first_artifact_behavior_gate_passed': False}
    (args.output / 'bootstrap-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name: report[name] for name in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
