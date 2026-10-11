#!/usr/bin/env python3
"""Run three-variant CRUD/permission/caller-restart tests on an already booted new package.

No image changes, permission-table edits, library injection or VPN traffic claim.
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
import zipfile

from build_sys_vpn_store_probe import BUNDLE, module
from run_normal_hap_probe import APP_FILES, ROOT, stop_previous_probe
from run_root_probe import digest
from sign_always_on_vpn_probe import configure_profile
from verify_sys_vpn_store_results import identity, verify, verify_inputs, verify_restart, EVIDENCE_SCOPE


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='fail', scope=EVIDENCE_SCOPE,
        archive=str(args.archive), archive_sha256=digest(args.archive), arch=args.arch, device=args.device,
        boot_id=args.boot_id, target=args.target, udid=args.udid, roles={}, commands=[], failures=[],
        first_artifact_behavior_gate_passed=False)

    def command(argv, label, timeout=90, allow_failure=False):
        argv = list(map(str, argv))
        log = args.output / f'{len(report["commands"]):03d}-{label}.log'
        row = dict(argv=argv, log=str(log), exit_code=None)
        report['commands'].append(row)
        child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                stdout, stderr = child.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                stdout, stderr = child.communicate()
            log.write_text(stdout + stderr)
            row.update(timed_out=True, sha256=digest(log))
            raise ValueError('VPN probe command timed out: ' + label)
        log.write_text(stdout + stderr)
        row.update(exit_code=child.returncode, sha256=digest(log))
        if not allow_failure and (child.returncode or (argv[0] == str(args.hdc) and
                re.search(r'\[Fail\]|Device not found or connected', stdout))):
            raise ValueError('VPN probe command failed: ' + label)
        return stdout.replace('\r', '')

    def shell(value, label, allow_failure=False):
        return command([args.hdc, '-t', args.target, 'shell', value], label, allow_failure=allow_failure)

    def same_guest(label):
        if shell('cat /proc/sys/kernel/random/boot_id', label).strip() != args.boot_id:
            raise ValueError('VPN regression escaped its packaged guest')

    try:
        cpu = {'arm64': 'aarch64', 'armv7a': 'armv7l', 'x86_64': 'x86_64'}[args.arch]
        if shell('id -u; param get const.product.devicetype; uname -m', 'guest-identity').split() != ['0', args.device, cpu]:
            raise ValueError('wrong guest architecture/profile')
        same_guest('boot-before')
        # Denial roles run before the one bounded configuration writer.
        for role in ('normal', 'system-denied', 'system'):
            output = args.output / role
            output.mkdir()
            nonce = secrets.token_hex(16)
            project = output / 'project'
            command([sys.executable, Path(__file__).with_name('build_sys_vpn_store_probe.py'),
                '--role', role, '--arch', args.arch, '--sdk', args.sdk, '--run-id', nonce, '--output', project],
                role + '-build', timeout=1800)
            unsigned = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
            signed = output / 'sys-vpn-store-signed.hap'
            command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly',
                '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
                '--mount', 'type=bind,src=' + str(args.output.resolve()) + ',dst=/probe',
                args.docker_image, 'python3', '/work/ci/capability-audit/sign_always_on_vpn_probe.py',
                '--signer-dist', '/ohos/developtools/hapsigner/dist',
                '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
                '--unsigned', '/probe/' + str(unsigned.relative_to(args.output)),
                '--output', '/probe/' + str(signed.relative_to(args.output)), '--role', role, '--udid', args.udid],
                role + '-sign-exact-role', timeout=300)
            receipt = signed.with_suffix('.signing.json')
            document = json.loads(receipt.read_text())
            profile = document['verified_profile']
            with zipfile.ZipFile(signed) as archive:
                compiled = json.loads(archive.read('module.json'))
            if (document.get('status') != 'pass' or document.get('role') != role or
                    document.get('signed_sha256') != digest(signed) or document.get('unsigned_sha256') != digest(unsigned) or
                    compiled['module']['requestPermissions'] != module(role)['module']['requestPermissions'] or
                    configure_profile(json.loads(json.dumps(profile)), role, args.udid, compiled) != profile):
                raise ValueError('signed VPN role/permissions differ')
            command([args.hdc, '-t', args.target, 'uninstall', BUNDLE], role + '-uninstall-own-old', allow_failure=True)
            installed = command([args.hdc, '-t', args.target, 'install', signed], role + '-install')
            if not re.search('success', installed, re.I) or re.search('failed to install', installed, re.I):
                raise ValueError('VPN HAP installation did not succeed')
            identity_path = output / 'application-identity.json'
            identity_path.write_text(shell('bm dump -n ' + BUNDLE, role + '-identity'))
            uid = identity(identity_path.read_text(), role)
            inputs = project / 'sys-vpn-store-probe-inputs.json'
            verify_inputs(json.loads(inputs.read_text()), nonce, args.arch, role)
            paths = dict(inputs=inputs, application_identity=identity_path, signed_hap=signed, signing_receipt=receipt)
            record = dict(run_id=nonce, actual_uid=uid, phases={}, status='running')
            for field, path in paths.items():
                record.update({field: str(path), field + '_sha256': digest(path)})
            report['roles'][role] = record
            remote = APP_FILES + 'sys-vpn-store-' + nonce + '-results.log'
            if shell('if test -e ' + shlex.quote(remote) + '; then echo STALE; else echo ABSENT; fi',
                     role + '-absence').strip() != 'ABSENT':
                raise ValueError('stale VPN result')
            for phase in (('seed', 'restart') if role == 'system' else ('denial',)):
                same_guest(role + '-' + phase + '-boot-before')
                if phase == 'restart':
                    # Terminate only this owned test application. The service and
                    # SettingsData remain running; a different PID is mandatory.
                    shell('aa force-stop ' + BUNDLE, 'system-force-stop-own-caller')
                    shell('rm ' + shlex.quote(remote), 'system-remove-only-previous-own-result')
                shell('power-shell wakeup', role + '-' + phase + '-wakeup')
                if 'start ability successfully' not in shell('aa start -a EntryAbility -b ' + BUNDLE,
                        role + '-' + phase + '-launch').lower():
                    raise ValueError('VPN caller did not launch')
                deadline = time.monotonic() + args.wait_seconds
                while time.monotonic() < deadline:
                    raw = shell('cat ' + shlex.quote(remote) + ' 2>/dev/null', role + '-' + phase + '-poll', True)
                    if '"summary"' in raw and raw.endswith('\n'):
                        break
                    time.sleep(2)
                else:
                    raise ValueError('VPN caller did not complete')
                raw_path = output / (phase + '-results.log')
                raw_path.write_text(raw)
                rows = verify(raw, nonce, role, phase, identity_path.read_text())
                record['phases'][phase] = dict(results=rows, raw_results=str(raw_path), raw_results_sha256=digest(raw_path))
                same_guest(role + '-' + phase + '-boot-after')
            if role == 'system':
                verify_restart(record['phases']['seed']['results'], record['phases']['restart']['results'])
            record['status'] = 'pass'
        same_guest('boot-final')
        if digest(args.archive) != report['archive_sha256']:
            raise ValueError('archive changed')
        report['status'] = 'pass'
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        report['caller_cleanup_verified'] = False
        try:
            report['caller_cleanup'] = stop_previous_probe(
                lambda script, label, accepted_failure=False: shell(script, label, accepted_failure))
            report['caller_cleanup_verified'] = True
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
            report['status'] = 'fail'
            report['failures'].append('owned VPN store caller cleanup failed: ' + str(error))
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
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
    parser.add_argument('--wait-seconds', type=int, choices=range(60, 601), default=180)
    args = parser.parse_args()
    if re.fullmatch('[0-9a-fA-F]{64}', args.udid) is None or re.fullmatch(
            '[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', args.boot_id) is None:
        parser.error('actual guest UDID and boot ID required')
    result = run(args)
    print(json.dumps({'status': result['status'], 'failures': result['failures']}))
    raise SystemExit(result['status'] != 'pass')
