#!/usr/bin/env python3
"""Run bounded system-success and ordinary-denial certificate probes on one VM.

Does not boot a VM, change permissions or attest the whole first-artifact gate.
The enclosing package suite supplies the actual fresh VM boot ID.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import subprocess
import sys
import time

from run_normal_hap_probe import APP_FILES, ROOT
from run_root_probe import digest
from sign_certificate_probe import BUNDLE, configure_profile
from verify_certificate_results import identity


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'status': 'fail', 'scope': 'two_real_certificate_HAP_roles_NOT_full_gate',
        'archive_sha256': digest(args.archive), 'boot_id': args.boot_id, 'arch': args.arch,
        'target': args.target, 'udid': args.udid, 'roles': {}, 'commands': [], 'failures': [],
        'first_artifact_behavior_gate_passed': False}

    def command(argv, label, timeout=60, accepted_failure=False):
        argv = list(map(str, argv))
        log = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        record = {'argv': argv, 'exit_code': None, 'log': str(log)}; report['commands'].append(record)
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); stdout, stderr = process.communicate()
            log.write_text(stdout + stderr); record.update(timed_out=True, sha256=digest(log))
            raise ValueError('certificate command timed out: ' + label)
        log.write_text(stdout + stderr); record.update(exit_code=process.returncode, sha256=digest(log))
        if (not accepted_failure and (process.returncode or (argv[0] == str(args.hdc) and
                re.search(r'\[Fail\]|Device not found or connected', stdout)))):
            raise ValueError('certificate command did not actually succeed: ' + label)
        return stdout.replace('\r', '')

    def shell(value, label, accepted_failure=False):
        return command([args.hdc, '-t', args.target, 'shell', value], label, accepted_failure=accepted_failure)

    def same_guest(label):
        if shell('cat /proc/sys/kernel/random/boot_id', label).strip() != args.boot_id:
            raise ValueError('certificate regression is not on the enclosing fresh VM')

    try:
        expected_cpu = {'arm64': 'aarch64', 'armv7a': 'armv7l', 'x86_64': 'x86_64'}[args.arch]
        if shell('id -u; param get const.product.devicetype; uname -m', 'guest-identity').split() != [
                '0', args.device, expected_cpu]:
            raise ValueError('wrong certificate test guest identity/architecture/profile')
        same_guest('boot-before')
        for role in ('system', 'normal'):
            output = args.output / role; output.mkdir()
            challenge = secrets.token_hex(16)
            project = output / 'project'
            command([sys.executable, Path(__file__).with_name('build_certificate_probe.py'), '--role', role,
                '--arch', args.arch, '--sdk', args.sdk, '--run-id', challenge, '--output', project],
                role + '-build-actual-SDK-HAP', timeout=1800)
            unsigned = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
            signed = output / 'certificate-signed.hap'
            command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly',
                '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
                '--mount', 'type=bind,src=' + str(args.output.resolve()) + ',dst=/probe',
                args.docker_image, 'python3', '/work/ci/capability-audit/sign_certificate_probe.py',
                '--signer-dist', '/ohos/developtools/hapsigner/dist',
                '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
                '--unsigned', '/probe/' + unsigned.relative_to(args.output).as_posix(),
                '--output', '/probe/' + signed.relative_to(args.output).as_posix(),
                '--role', role, '--udid', args.udid], role + '-sign-verify-exact-profile', timeout=300)
            receipt = signed.with_suffix('.signing.json')
            document = json.loads(receipt.read_text())
            expected_module = {'app': {'bundleName': BUNDLE}, 'module': {'requestPermissions':
                [{'name': name} for name in ('ohos.permission.ACCESS_CERT_MANAGER',
                    'ohos.permission.ACCESS_CERT_MANAGER_INTERNAL')] if role == 'system' else []}}
            actual_profile = document['verified_profile']
            if (document.get('status') != 'pass' or document.get('role') != role or
                    document.get('signed_sha256') != digest(signed) or
                    document.get('unsigned_sha256') != digest(unsigned) or
                    configure_profile(json.loads(json.dumps(actual_profile)), role, args.udid,
                        expected_module) != actual_profile):
                raise ValueError('actual signed certificate profile receipt does not match the exact role')
            command([args.hdc, '-t', args.target, 'uninstall', BUNDLE],
                role + '-remove-own-prior-audit-bundle', accepted_failure=True)
            installed = command([args.hdc, '-t', args.target, 'install', signed], role + '-install')
            if not re.search(r'success', installed, re.I) or re.search('failed to install', installed, re.I):
                raise ValueError('actual certificate HAP installation did not succeed')
            identity_path = output / 'application-identity.json'
            identity_path.write_text(shell('bm dump -n ' + BUNDLE, role + '-actual-BMS-identity'))
            actual_uid = identity(identity_path.read_text(), role)
            remote = APP_FILES + 'certificate-' + challenge + '-results.log'
            if shell('if test -e ' + shlex.quote(remote) + '; then echo STALE; else echo ABSENT; fi',
                    role + '-result-absent-before-launch').strip() != 'ABSENT':
                raise ValueError('stale certificate result exists before fresh launch')
            same_guest(role + '-boot-before-launch')
            shell('power-shell wakeup', role + '-single-test-wakeup')
            if 'start ability successfully' not in shell('aa start -a EntryAbility -b ' + BUNDLE,
                    role + '-launch').lower():
                raise ValueError('actual certificate ability did not start')
            deadline = time.monotonic() + args.wait_seconds
            raw = ''
            while time.monotonic() < deadline:
                raw = shell('cat ' + shlex.quote(remote) + ' 2>/dev/null',
                    role + '-poll-own-results', accepted_failure=True)
                if '"summary"' in raw and raw.endswith('\n'):
                    break
                time.sleep(2)
            else:
                raise ValueError('certificate application did not actually complete')
            raw_path, result, inputs = output / 'results.log', output / 'verified-result.json', project / 'certificate-probe-inputs.json'
            raw_path.write_text(raw)
            command([sys.executable, Path(__file__).with_name('verify_certificate_results.py'),
                '--archive', args.archive, '--results', raw_path, '--inputs', inputs,
                '--application-identity', identity_path, '--arch', args.arch, '--role', role,
                '--run-id', challenge, '--output', result], role + '-strict-actual-results')
            if json.loads(result.read_text()).get('status') != 'pass':
                raise ValueError('strict certificate role verifier did not pass')
            same_guest(role + '-boot-after')
            report['roles'][role] = {'status': 'pass', 'run_id': challenge, 'actual_uid': actual_uid,
                'raw_results': str(raw_path), 'raw_results_sha256': digest(raw_path),
                'result': str(result), 'result_sha256': digest(result), 'inputs': str(inputs),
                'inputs_sha256': digest(inputs), 'application_identity': str(identity_path),
                'application_identity_sha256': digest(identity_path), 'signed_hap': str(signed),
                'signed_hap_sha256': digest(signed), 'signing_receipt': str(receipt), 'signing_receipt_sha256': digest(receipt)}
        same_guest('boot-final')
        if digest(args.archive) != report['archive_sha256']:
            raise ValueError('archive changed during certificate validation')
        report['status'] = 'pass'
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    for name in ('udid', 'target', 'boot-id'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--hdc', default='hdc')
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    parser.add_argument('--wait-seconds', type=int, choices=range(60, 1801), default=300)
    args = parser.parse_args()
    if re.fullmatch('[0-9a-fA-F]{64}', args.udid) is None or re.fullmatch(
            '[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', args.boot_id) is None:
        parser.error('actual guest UDID and fresh kernel boot ID required')
    report = run(args)
    print(json.dumps({'status': report['status'], 'scope': report['scope'], 'failures': report['failures']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
