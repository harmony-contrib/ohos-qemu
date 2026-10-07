#!/usr/bin/env python3
"""Check candidate patch application and compile the actual token helper.

These are isolated host/source checks, never a service, HDI, HAP, or guest pass.
The provided release source and upstream git cache are read-only inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

COMPONENTS = [
    'base/busmanager/serial_manager',
    'base/usb/usb_manager/serial_dialog',
    'base/startup/init/serial_devices',
    'device/qemu/serial_usb_endpoint',
    'base/security/selinux_adapter/serial_metadata',
]


def run(command, expected=0):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=120)
    if (result.returncode == 0) != (expected == 0):
        raise AssertionError('unexpected status: ' + str(command) + '\n' + result.stdout)
    return result.stdout


def manifest_fixture(source, destination):
    destination.mkdir()
    (destination / '.repo').symlink_to(source / '.repo', target_is_directory=True)


def copy_patch_inputs(source, fixture, patch):
    for relative in re.findall(r'^\+\+\+ b/(.+)$', patch.read_text(), re.MULTILINE):
        target = fixture / relative
        original = source / relative
        if original.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--source-repo', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--cxx', default='c++')
    parser.add_argument('--node', type=Path)
    parser.add_argument('--typescript', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = args.source_root.resolve()
    repo = args.repo_root.resolve()
    checks = []
    hashes = {}
    with tempfile.TemporaryDirectory(prefix='serial-candidate-check-') as temporary:
        scratch = Path(temporary)
        fixture = scratch / 'source'
        manifest_fixture(source, fixture)
        for component in COMPONENTS:
            directory = repo / 'patches/2in1' / component
            patches = sorted(directory.glob('[0-9][0-9][0-9][0-9]-*.patch'))
            if not patches:
                raise AssertionError('component has no numbered patches: ' + component)
            for patch in patches:
                copy_patch_inputs(source, fixture, patch)
                hashes[str(patch.relative_to(repo))] = hashlib.sha256(patch.read_bytes()).hexdigest()
            command = ['bash', str(directory / 'apply.sh'), '--source-root', str(fixture)]
            if component == 'base/security/selinux_adapter/serial_metadata':
                metadata = fixture / 'base/security/selinux_adapter/.git'
                metadata.symlink_to((source / 'base/security/selinux_adapter/.git').resolve(), target_is_directory=True)
            if component == COMPONENTS[0]:
                command.extend(['--source-repo', str(args.source_repo.resolve())])
            run(command)
            run(command)
            # Overlapping diffs are a stack: unwind it in reverse order only
            # inside a separate disposable copy, without applied markers.
            reversed_fixture = scratch / ('reverse-' + str(len(checks)))
            shutil.copytree(fixture, reversed_fixture, symlinks=True,
                            ignore=shutil.ignore_patterns('.ohos-qemu-patches', '.ohos-qemu-stack.lock'))
            for patch in reversed(patches):
                reverse = ['git', '-C', str(reversed_fixture), 'apply', '--check', '--reverse', str(patch)]
                checked = subprocess.run(reverse, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                if checked.returncode != 0:
                    # Match the shared applicator's explicit CRLF tolerance;
                    # production USB ability TS contains CRLF input lines.
                    run(reverse[:-1] + ['--ignore-space-change', reverse[-1]])
                run(['git', '-C', str(reversed_fixture), 'apply', '--reverse', '--ignore-space-change', str(patch)])
            run([str(reversed_fixture) if argument == str(fixture) else argument for argument in command])
            checks.append(component + ': apply, idempotence, reverse-check pass')
        gn = source / 'prebuilts/build-tools/linux-x86/bin/gn'
        if gn.is_file():
            run([str(gn), 'format', '--dry-run',
                 str(fixture / 'base/busmanager/serial_manager/test/unittest/serial_service/BUILD.gn')])
            checks.append('changed upstream test BUILD.gn release GN formatting pass')
        importer = repo / 'patches/2in1/base/busmanager/serial_manager/import_source.py'
        foreign = scratch / 'foreign'
        manifest_fixture(source, foreign)
        sentinel = foreign / 'base/busmanager/serial_manager/user-content.txt'
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text('preserve foreign user content\n')
        run(['python3', str(importer), '--source-root', str(foreign),
             '--source-repo', str(args.source_repo.resolve())], expected=1)
        if sentinel.read_text() != 'preserve foreign user content\n':
            raise AssertionError('importer changed the foreign tree')
        checks.append('foreign Serial tree refused and preserved')
        provenance = fixture / 'base/busmanager/serial_manager/.ohos-qemu-upstream.json'
        linked = scratch / 'linked-source'
        manifest_fixture(source, linked)
        target = linked / 'base/busmanager/serial_manager'
        target.parent.mkdir(parents=True)
        target.symlink_to(provenance.parent, target_is_directory=True)
        original_provenance = provenance.read_bytes()
        run(['python3', str(importer), '--source-root', str(linked),
             '--source-repo', str(args.source_repo.resolve())], expected=1)
        if provenance.read_bytes() != original_provenance:
            raise AssertionError('importer changed the out-of-root linked candidate')
        checks.append('out-of-root linked Serial tree refused despite matching provenance')
        marker = json.loads(provenance.read_text())
        marker['revision'] = 'mismatched-revision-test-only'
        provenance.write_text(json.dumps(marker))
        run(['python3', str(importer), '--source-root', str(fixture),
             '--source-repo', str(args.source_repo.resolve())], expected=1)
        checks.append('mismatched imported provenance refused')
        binary = scratch / 'serial-token-test'
        run([args.cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror',
             '-I' + str(fixture / 'base/busmanager/serial_manager/services/native/include'),
             str(repo / 'ci/capability-audit/serial_token_test.cpp'), '-o', str(binary)])
        parser_output = run([str(binary)]).strip()
        checks.append(parser_output)
        request_binary = scratch / 'serial-request-test'
        run([args.cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror',
             '-I' + str(fixture / 'base/busmanager/serial_manager/services/native/include'),
             str(repo / 'ci/capability-audit/serial_authorization_request_test.cpp'),
             '-Wl,--wrap=getrandom', '-o', str(request_binary)])
        checks.append(run([str(request_binary)]).strip())
        identity_binary = scratch / 'serial-identity-test'
        run([args.cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror',
             '-I' + str(fixture / 'base/busmanager/serial_manager/services/native/include'),
             str(repo / 'ci/capability-audit/serial_device_identity_test.cpp'),
             '-Wl,--wrap=stat', '-o', str(identity_binary)])
        checks.append(run([str(identity_binary)]).strip())
        node = args.node or source / 'prebuilts/build-tools/common/nodejs/node-v18.20.1-linux-x64/bin/node'
        typescript = args.typescript or source / 'prebuilts/ohos-sdk/linux/26.0.0/ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'
        if not node.is_file() or not typescript.is_file():
            raise AssertionError('actual UI helper frontend fixture needs the fixed SDK TypeScript compiler and Node')
        helper = fixture / 'base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog/src/main/ets/util/SerialDialogRequest.ts'
        ui_fixture = json.loads(run([str(node), str(repo / 'ci/capability-audit/check_serial_dialog_request.cjs'),
                                     str(helper), str(typescript)]))
        if ui_fixture.get('first_package_gate_passed') is not False:
            raise AssertionError('frontend fixtures must never claim runtime/package acceptance')
        checks.append('actual UI helper and ability frontend lifecycle fixtures pass (not runtime authorization)')
    result = {'scope': 'fixed_source_patch_and_host_helper_only_not_runtime_acceptance',
              'checks': checks, 'patch_sha256': hashes, 'first_package_gate_passed': False,
              'guest_test_passed': False, 'ui_frontend_logic_fixture': ui_fixture}
    formatted = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted)
    print(formatted, end='')


if __name__ == '__main__':
    main()
