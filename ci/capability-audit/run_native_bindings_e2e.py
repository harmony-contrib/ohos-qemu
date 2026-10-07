#!/usr/bin/env python3
"""Build and run every current bindings test in an owned source snapshot.

No test source, generated List, library, signer cache or build directory in the
user checkout is modified. This runner requires the enclosing suite's actual
fresh kernel boot ID; it cannot establish the archive-to-VM relationship alone.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

from run_root_probe import validate_archive, validate_elf, validate_identity
from snapshot_native_bindings import files, sha, snapshot

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MODULES = frozenset(('ability_access_control', 'ark_web', 'arkui', 'arkui_input',
    'ashmem', 'asset', 'bundle', 'camera', 'display', 'display_soloist', 'drawing',
    'fileshare', 'fileuri', 'hilog', 'huks', 'image', 'image_native', 'ime', 'init',
    'jsvm', 'native_buffer', 'native_window', 'net_connection', 'net_stack',
    'pasteboard', 'qos', 'raw', 'sensor', 'udmf', 'vibrator', 'vsync', 'xcomponent'))
ARCH_NAMES = {'arm64': ('arm64', 'arm64-v8a'), 'armv7a': ('arm', 'armeabi-v7a'),
              'x86_64': ('x64', 'x86_64')}


def adapt_owned_device_profiles(project, device):
    """Only add the actual test device to the owned HAP install declarations.

    The original checkout, permissions, abilities and test assertions stay
    unchanged. Both main/test HAPs originally declare phone only; pretending
    their installation on 2in1 succeeded would omit half of the matrix.
    """
    if device not in ('phone', '2in1'):
        raise ValueError('unsupported test device profile')
    changes = {}
    pattern = re.compile(r'''(?m)^(\s*(?:deviceTypes|"deviceTypes"|'deviceTypes')\s*:\s*)\[([^\]\n]*)\]''')
    for relative in ('entry/src/main/module.json5', 'entry/src/ohosTest/module.json5'):
        path = project / relative
        source = path.read_text()
        matches = list(pattern.finditer(source))
        if len(matches) != 1:
            raise ValueError('require one literal actual test device declaration: ' + relative)
        match = matches[0]
        values = match.group(2)
        if not re.fullmatch(r'''\s*['"](?:phone|2in1)['"](?:\s*,\s*['"](?:phone|2in1)['"])*\s*,?\s*''', values):
            raise ValueError('unknown/nonliteral test device declaration: ' + relative)
        devices = re.findall(r'''['"](phone|2in1)['"]''', values)
        if len(devices) != len(set(devices)):
            raise ValueError('duplicate test device declaration: ' + relative)
        before = sha(path)
        if device not in devices:
            quote = '"' if '"' in values else "'"
            devices.append(device)
            replacement = ', '.join(quote + value + quote for value in devices)
            path.write_text(source[:match.start(2)] + replacement + source[match.end(2):])
        changes[relative] = {'before_sha256': before, 'after_sha256': sha(path),
                             'device_types': devices, 'changed': before != sha(path)}
    return {'scope': 'owned_HAP_deviceTypes_only_no_permission_or_test_source_changes',
            'device': device, 'files': changes}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def adapt_owned_hypium_verifier(project, source_record):
    """Correct grouped Hypium summaries in the owned snapshot, not test assertions."""
    relative = 'examples-ui/scripts/verify-ohostest-results.py'
    expected = '2b92192557f40452287bf09b23238c294da3c10f8accc1db5b4da8f54a828fe5'
    candidate_hash = '324b4bd832eef303222fcaaf963fad0d5d97285ac84c024e0e41a725d69d5f29'
    target = project / 'scripts/verify-ohostest-results.py'
    candidate = Path(__file__).with_name('verify_ohostest_results.py')
    if (source_record['files_sha256'].get(relative) != expected or sha(target) != expected or
            sha(candidate) != candidate_hash):
        raise ValueError('unknown Hypium verifier preimage or correction; preserve all assertions')
    shutil.copy2(candidate, target)
    if sha(target) != candidate_hash:
        raise ValueError('owned Hypium verifier correction did not match the audited bytes')
    return {'scope': 'owned_Hypium_result_tool_only_no_test_assertion_or_user_checkout_change',
            'relative': relative, 'before_sha256': expected, 'after_sha256': candidate_hash,
            'reason': 'sum all describe-group summaries before comparing complete case names'}


def declared_modules(driver):
    match = re.search(r'^declare -a MODULES=\(\n(.*?)^\)', driver, re.M | re.S)
    if match is None:
        raise ValueError('cannot identify the actual complete test driver module list')
    rows = []
    for line in match[1].splitlines():
        row = re.fullmatch(r'\s*([a-z][a-z0-9_]*):([A-Za-z][A-Za-z0-9]*)\s*', line)
        if not row:
            raise ValueError('unknown or nonliteral module selection in test driver')
        rows.append(row.groups())
    names = [name for name, _ in rows]
    if len(names) != len(set(names)) or not EXPECTED_MODULES.issubset(names):
        raise ValueError('current complete 32-module suite is missing or duplicated')
    return rows


def verify_modules(project, diagnostics, modules):
    verifier = load_module(project / 'scripts/verify-ohostest-results.py', 'actual_hypium_verifier')
    records = {}
    for name, stem in modules:
        source = project / 'entry/src/ohosTest/ets/test/modules' / (stem + '.test.ets')
        log = diagnostics / ('ohostest-' + name + '.log')
        result = diagnostics / ('ohostest-' + name + '-result.json')
        actual = verifier.verify(log.read_text().replace('\r', ''), verifier.expected_names(source.read_text()))
        if json.loads(result.read_text()) != actual:
            raise ValueError('recorded result does not match independent completeness verification: ' + name)
        records[name] = {'status': 'pass', 'source_sha256': sha(source),
            'log': str(log), 'log_sha256': sha(log), 'evidence': str(result), 'sha256': sha(result),
            'case_count': actual['pass'], 'cases': actual['cases']}
    return records


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'status': 'fail',
        'scope': 'all_current_native_bindings_modules_on_enclosing_fresh_VM',
        'archive': str(args.archive.resolve()), 'arch': args.arch, 'device': args.device,
        'target': args.target, 'boot_id': args.boot_id, 'commands': [], 'failures': [],
        'boot_binding': 'requires_enclosing_fresh_VM_suite', 'first_artifact_behavior_gate_passed': False}
    owned_source = None

    def command(argv, label, timeout=60, cwd=None, env=None):
        argv = list(map(str, argv))
        log = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        record = {'argv': argv, 'exit_code': None, 'log': str(log)}
        report['commands'].append(record)
        with log.open('w') as stream:
            process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, cwd=cwd, env=env)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                record.update(timed_out=True, sha256=sha(log))
                raise ValueError('owned command timed out: ' + label) from error
        record.update(exit_code=process.returncode, sha256=sha(log))
        text = log.read_text()
        if process.returncode or (argv[0] == str(args.hdc) and
                re.search(r'\[Fail\]|Device not found or connected', text)):
            raise ValueError('actual command did not succeed: ' + label)
        return text.replace('\r', '')

    def identity(label):
        validate_identity(command([args.hdc, '-t', args.target, 'shell',
            'id -u; param get const.product.devicetype; uname -m'], label + '-identity'), args.arch, args.device)
        if command([args.hdc, '-t', args.target, 'shell',
                'cat /proc/sys/kernel/random/boot_id'], label + '-boot-id').strip() != args.boot_id:
            raise ValueError('bindings test is no longer connected to the enclosing fresh VM')

    try:
        if re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', args.boot_id) is None:
            raise ValueError('actual enclosing kernel boot ID required')
        report['archive_sha256'] = sha(args.archive)
        validate_archive(args.archive, args.arch, args.device)
        identity('before')
        before = files(args.source.resolve())
        source_record = snapshot(args.source, args.output / 'workspace')
        owned_source = Path(source_record['snapshot'])
        report['source_snapshot'] = str(args.output / 'workspace/source-snapshot.json')
        report['source_snapshot_sha256'] = sha(Path(report['source_snapshot']))
        project = owned_source / 'examples-ui'
        report['test_device_profile_adaptation'] = adapt_owned_device_profiles(project, args.device)
        report['hypium_verifier_tool_adaptation'] = adapt_owned_hypium_verifier(project, source_record)
        modules = declared_modules((project / 'scripts/run-ohostest.sh').read_text())
        report['expected_modules'] = [name for name, _ in modules]
        package_manager = json.loads((owned_source / 'package.json').read_text())['packageManager']
        if re.fullmatch(r'pnpm@[0-9]+\.[0-9]+\.[0-9]+', package_manager) is None:
            raise ValueError('test workspace must pin an exact pnpm version')
        manager = ['npm', 'exec', '--yes', '--package=' + package_manager, '--', 'pnpm']
        report['test_sdk_components'] = {}
        for name in ('native', 'ets'):
            metadata_path = args.sdk / name / 'oh-uni-package.json'
            metadata = json.loads(metadata_path.read_text())
            if (metadata.get('apiVersion') != '26' or metadata.get('releaseType') != 'Release' or
                    metadata.get('platformVersion') != '26.0.0'):
                raise ValueError('a real host-compatible API26 Release test SDK is required')
            report['test_sdk_components'][name] = {'metadata': metadata, 'sha256': sha(metadata_path)}
        report['test_compiler_sha256'] = sha(args.sdk / 'native/llvm/bin/clang')
        environment = dict(os.environ, OHOS_SDK_HOME=str(args.sdk.resolve()),
            OHOS_NDK_HOME=str(args.sdk.resolve()), CARGO_TARGET_DIR=str(args.output / 'rust-target'),
            CARGO_BUILD_JOBS='4', HDC_TARGET=args.target, HAP_SIGN_DEVICE_ID=args.udid,
            HAP_SIGN=str(ROOT / 'scripts/sign_qemu_test_hap.py'),
            E2E_DIAGNOSTICS_DIR=str(args.output / 'diagnostics'),
            QEMU_TEST_SOURCE_VOLUME=args.source_volume, QEMU_TEST_DOCKER_IMAGE=args.docker_image,
            PATH=str(Path(args.hdc).resolve().parent) + os.pathsep + os.environ.get('PATH', ''),
            LC_ALL='en_US.UTF-8' if sys.platform == 'darwin' else 'C.UTF-8',
            LC_CTYPE='en_US.UTF-8' if sys.platform == 'darwin' else 'C.UTF-8',
            LANG='en_US.UTF-8' if sys.platform == 'darwin' else 'C.UTF-8')
        report['rustc_identity'] = command(['rustc', '-Vv'], 'actual-rustc-version', env=environment)
        report['cargo_identity'] = command(['cargo', '-V'], 'actual-cargo-version', env=environment)
        command(manager + ['install', '--frozen-lockfile', '--lockfile=true', '--ignore-scripts'],
                'pinned-workspace-dependencies', timeout=600, cwd=owned_source, env=environment)
        bindings_arch, abi = ARCH_NAMES[args.arch]
        command(['bash', project / 'scripts/sync-rust.sh', '--arch', bindings_arch, '--fail-fast'],
                'fresh-same-ABI-bindings', timeout=3600, cwd=project, env=environment)
        report['native_libraries'] = {}
        for name, _ in modules:
            library = project / 'entry/libs' / abi / ('lib' + name + '_test.so')
            validate_elf(library, args.arch)
            report['native_libraries'][name] = {'path': str(library), 'sha256': sha(library)}
        command(manager + ['-C', 'examples-ui', 'run', 'test', '--', '--arch', bindings_arch],
                'all-current-ohostest-modules', timeout=7200, cwd=owned_source, env=environment)
        report['modules'] = verify_modules(project, args.output / 'diagnostics', modules)
        for name in ('Cargo.lock', 'pnpm-lock.yaml'):
            if sha(owned_source / name) != source_record['files_sha256'][name]:
                raise ValueError('test dependency lock changed during the fresh run: ' + name)
        if files(args.source.resolve()) != before:
            raise ValueError('original user test sources changed during run; snapshot is no longer current')
        identity('after')
        report.update(status='pass', module_count=len(modules),
            case_count=sum(row['case_count'] for row in report['modules'].values()),
            original_checkout_unchanged=True, dependency_locks_unchanged=True)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT.parent / 'ohos-native-bindings')
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arch', choices=tuple(ARCH_NAMES), required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--udid', required=True)
    parser.add_argument('--hdc', required=True)
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({key: result.get(key) for key in ('status', 'module_count', 'case_count', 'failures')}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
