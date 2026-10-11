#!/usr/bin/env python3
"""Build/sign exact test roles and exercise pixels in an owned packaged guest.

Does not boot a VM or launch a build matrix. Failure (including cleanup) is fatal
to this probe; a passing result is not the complete first-artifact gate.
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

from build_screen_blink_probe import BUNDLE, ROLES, module
from guest_ui import GuestUi
from run_normal_hap_probe import APP_FILES, ROOT
from run_root_probe import digest
from screen_blink_runtime import exercise
from sign_screen_blink_probe import configure_profile
from verify_screen_blink_results import identity, verify_inputs


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='fail', archive=str(args.archive), archive_sha256=digest(args.archive),
                  arch=args.arch, device=args.device, boot_id=args.boot_id, target=args.target,
                  udid=args.udid, roles={}, commands=[], failures=[],
                  scope='three_roles_actual_screen_pixels_NOT_complete_lifecycle_or_full_gate',
                  first_artifact_behavior_gate_passed=False)

    def command(argv, label, timeout=90, allow_failure=False):
        argv = list(map(str, argv))
        log = args.output / f'{len(report["commands"]):04d}-{label}.log'
        record = dict(argv=argv, log=str(log), exit_code=None)
        report['commands'].append(record)
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
            record.update(timed_out=True, sha256=digest(log))
            raise ValueError('screen blink command timed out: ' + label)
        log.write_text(stdout + stderr)
        record.update(exit_code=child.returncode, sha256=digest(log))
        if not allow_failure and (child.returncode or (argv[0] == str(args.hdc) and
                re.search(r'\[Fail\]|Device not found or connected', stdout))):
            raise ValueError('screen blink command failed: ' + label)
        return stdout.replace('\r', '')

    def shell(script, label, allow_failure=False):
        return command([args.hdc, '-t', args.target, 'shell', script], label, allow_failure=allow_failure)

    def same_guest(label):
        if shell('cat /proc/sys/kernel/random/boot_id', label).strip() != args.boot_id:
            raise ValueError('screen blink probe escaped its packaged guest')

    try:
        cpu = {'arm64': 'aarch64', 'armv7a': 'armv7l', 'x86_64': 'x86_64'}[args.arch]
        if shell('id -u; param get const.product.devicetype; uname -m', 'identity').split() != ['0', args.device, cpu]:
            raise ValueError('wrong packaged guest architecture/profile')
        same_guest('boot-before')
        for role in ROLES:
            output = args.output / role
            output.mkdir()
            nonce = secrets.token_hex(16)
            project = output / 'project'
            command([sys.executable, Path(__file__).with_name('build_screen_blink_probe.py'),
                '--role', role, '--arch', args.arch, '--sdk', args.sdk, '--run-id', nonce, '--output', project],
                role + '-build', timeout=1800)
            unsigned = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
            signed = output / 'screen-blink-signed.hap'
            command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly',
                '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
                '--mount', 'type=bind,src=' + str(args.output.resolve()) + ',dst=/probe',
                args.docker_image, 'python3', '/work/ci/capability-audit/sign_screen_blink_probe.py',
                '--signer-dist', '/ohos/developtools/hapsigner/dist',
                '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
                '--unsigned', '/probe/' + str(unsigned.relative_to(args.output)),
                '--output', '/probe/' + str(signed.relative_to(args.output)), '--role', role, '--udid', args.udid],
                role + '-sign', timeout=300)
            receipt = signed.with_suffix('.signing.json')
            document = json.loads(receipt.read_text())
            profile = document['verified_profile']
            with zipfile.ZipFile(signed) as archive:
                compiled = json.loads(archive.read('module.json'))
            if (document.get('status') != 'pass' or document.get('role') != role or
                    document.get('signed_sha256') != digest(signed) or
                    document.get('unsigned_sha256') != digest(unsigned) or
                    compiled['module']['requestPermissions'] != module(role)['module']['requestPermissions'] or
                    configure_profile(json.loads(json.dumps(profile)), role, args.udid, compiled) != profile):
                raise ValueError('signed blink role or permission scope differs')
            inputs = project / 'screen-blink-probe-inputs.json'
            verify_inputs(json.loads(inputs.read_text()), nonce, args.arch, role)
            same_guest(role + '-boot')
            command([args.hdc, '-t', args.target, 'uninstall', BUNDLE], role + '-uninstall-own', allow_failure=True)
            installed = command([args.hdc, '-t', args.target, 'install', signed], role + '-install')
            if not re.search('success', installed, re.I) or re.search('failed to install', installed, re.I):
                raise ValueError('blink test installation failed')
            identity_path = output / 'application-identity.json'
            identity_path.write_text(shell('bm dump -n ' + BUNDLE, role + '-identity'))
            uid = identity(identity_path.read_text(), role)
            record = dict(run_id=nonce, uid=uid, status='running')
            for field, path in dict(inputs=inputs, signed_hap=signed, unsigned_hap=unsigned,
                                    signing_receipt=receipt, application_identity=identity_path).items():
                record.update({field: str(path), field + '_sha256': digest(path)})
            report['roles'][role] = record
            remote = APP_FILES + 'screen-blink-' + nonce + '-results.log'
            if shell('if test -e ' + shlex.quote(remote) + '; then echo STALE; else echo ABSENT; fi',
                     role + '-absence').strip() != 'ABSENT':
                raise ValueError('stale blink observations')
            shell('power-shell wakeup', role + '-wake')
            ui = GuestUi(command, args.hdc, args.target, output / 'ui')
            background = None
            if role == 'system':
                time.sleep(2)
                baseline = ui.screenshot(label='before-owned-caller')
                background = dict(path=str(baseline), sha256=digest(baseline))
            if 'start ability successfully' not in shell('aa start -a EntryAbility -b ' + BUNDLE,
                    role + '-launch').lower():
                raise ValueError('blink caller did not launch')
            deadline = time.monotonic() + args.wait_seconds
            while time.monotonic() < deadline:
                if shell('test -s ' + shlex.quote(remote) + ' && echo READY', role + '-wait', True).strip() == 'READY':
                    break
                time.sleep(.2)
            else:
                raise ValueError('blink caller did not produce observations')
            result = exercise(ui, shell, remote, output / 'runtime', nonce, role,
                              identity_path.read_text(), args.wait_seconds, background=background)
            evidence = output / 'runtime/evidence.json'
            record.update(status=result['status'], runtime=str(evidence), runtime_sha256=digest(evidence))
            if result['status'] != 'pass' or not result['cleanup_verified']:
                raise ValueError('blink role failed or cleanup is unproven: ' + role)
            shell('aa force-stop ' + BUNDLE, role + '-stop-owned-caller')
        same_guest('boot-after')
        if digest(args.archive) != report['archive_sha256']:
            raise ValueError('archive changed during blink regression')
        report['status'] = 'pass'
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
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
