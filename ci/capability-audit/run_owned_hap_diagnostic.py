#!/usr/bin/env python3
"""Run bounded HAP/root diagnostics on one explicitly diagnostic, owned VM.

Never boots, replaces a library/kernel, restarts HDC, or grants package
acceptance. One physical key is permitted only after observed kernel sleep.
The normal development screen-timeout override is restored even on failure.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from boot_package import FATAL, QemuGuest, kernel_sleeping
from run_root_probe import digest, validate_identity
from run_normal_hap_probe import PERSONAS
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from power_test_policy import power_timeout, verify_policy_states


def validate_boot(boot):
    env = boot.get('test_environment', {})
    if (boot.get('status') != 'pass' or boot.get('purpose') != 'diagnostic' or
            env.get('external_keepalive') is not False or
            type(env.get('qemu_pid')) is not int or env['qemu_pid'] <= 1 or
            not env.get('qemu_command') or not env.get('boot_id') or
            not Path(env.get('qmp_socket', '')).is_absolute()):
        raise ValueError('requires an explicitly diagnostic, owned, unassisted live VM')
    return env


def validate_policy_mode(personas, root_probes, preserve):
    if preserve and (personas or len(root_probes) != 1):
        raise ValueError('unchanged-power diagnostic mode requires exactly one root probe and no HAP')


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'status': 'fail',
        'scope': 'owned_existing_image_HAP_or_root_DIAGNOSTIC_NOT_new_package_acceptance',
        'first_artifact_behavior_gate_passed': False, 'commands': [],
        'results': {}, 'failures': [], 'periodic_external_input': False,
        'screen_timeout_restore_attempted': False, 'screen_timeout_restored': False}
    restore = False
    env = None

    def command(argv, label, timeout=30):
        argv = list(map(str, argv))
        log = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        row = {'argv': argv, 'log': str(log), 'exit_code': None}
        report['commands'].append(row)
        with log.open('w') as stream:
            process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                row['timed_out'] = True
        row.update(exit_code=process.returncode, sha256=digest(log))
        value = log.read_text().replace('\r', '')
        if process.returncode or row.get('timed_out') or '[Fail]' in value or 'Device not found or connected' in value:
            raise ValueError('diagnostic operation failed: ' + label)
        return value

    def owned(label):
        current = command(['ps', '-p', env['qemu_pid'], '-o', 'command='], label + '-owned-process').strip()
        if current != env['qemu_command'] or env['qmp_socket'] not in current:
            raise ValueError('diagnostic socket no longer belongs to the original VM')
        if FATAL.search((args.boot.parent / 'qemu.log').read_text(errors='replace')):
            raise ValueError('diagnostic guest has a fatal service/kernel failure')

    def shell(script, label):
        return command([args.hdc, '-t', env['target'], 'shell', script], label)

    def same_boot(label):
        owned(label)
        validate_identity(shell('id -u; param get const.product.devicetype; uname -m', label + '-identity'),
                          env['guest_arch'], env['device_type'])
        if shell('cat /proc/sys/kernel/random/boot_id', label + '-boot-id').strip() != env['boot_id']:
            raise ValueError('diagnostic guest kernel boot identity changed')

    try:
        preserve_policy = getattr(args, 'preserve_power_policy', False)
        validate_policy_mode(getattr(args, 'persona', []), getattr(args, 'root_probe', []), preserve_policy)
        boot = json.loads(args.boot.read_text())
        env = validate_boot(boot)
        archive = Path(boot['archive'])
        if digest(archive) != boot['archive_sha256']:
            raise ValueError('diagnostic archive identity changed')
        report.update(boot_evidence=str(args.boot.resolve()), boot_evidence_sha256=digest(args.boot),
            archive=str(archive), archive_sha256=boot['archive_sha256'], boot_id=env['boot_id'])
        owned('initial')
        serial = args.boot.parent / 'qemu.log'
        if kernel_sleeping(serial.read_text(errors='replace')):
            control = QemuGuest(argparse.Namespace(archive=archive, purpose='diagnostic',
                                                   hdc_port=env['hdc_host_port']))
            control.qmp_path = Path(env['qmp_socket'])
            report['one_observed_sleep_key'] = {'serial_sha256_before': digest(serial),
                'execute': 'system_powerdown', 'reply': control.qmp('system_powerdown')}
            deadline = time.monotonic() + 30
            while kernel_sleeping(serial.read_text(errors='replace')):
                if time.monotonic() >= deadline:
                    raise ValueError('one physical diagnostic wake did not resume the kernel')
                time.sleep(0.25)
        command([args.hdc, 'tconn', env['target']], 'connect-original-owned-forward')
        same_boot('before')
        report['power_states'] = {'before': power_timeout(shell('hidumper -s 3301 -a "-a"', 'power-before'))}
        report['preserve_power_policy'] = preserve_policy
        if not preserve_policy:
            if report['power_states']['before']['override_ms'] is not None:
                raise ValueError('refuse to replace another client\'s existing PowerMgr override')
            restore = True  # Restore even if the reply is lost or malformed.
            if shell('power-shell timeout -o 86400000', 'finite-app-test-timeout').strip() != 'Override screen off time to 86400000':
                raise ValueError('PowerMgr rejected the finite diagnostic test timeout')
            report['power_states']['setup'] = power_timeout(shell('hidumper -s 3301 -a "-a"', 'power-setup'))
            if report['power_states']['setup'] != dict(report['power_states']['before'], override_ms=86400000):
                raise ValueError('actual PowerMgr did not retain the diagnostic timeout/backup policy')
        for persona in args.persona:
            command([sys.executable, Path(__file__).with_name('run_normal_hap_probe.py'),
                '--archive', archive, '--output', args.output / persona, '--sdk', args.sdk,
                '--udid', env['udid'], '--persona', persona, '--arch', env['guest_arch'],
                '--device', env['device_type'], '--target', env['target'], '--boot-id', env['boot_id'],
                '--hdc', args.hdc], 'actual-ordinary-' + persona, timeout=2400)
            evidence = args.output / persona / 'evidence.json'
            child = json.loads(evidence.read_text())
            if (child.get('status') != 'pass' or child.get('boot_id') != env['boot_id'] or
                    child.get('archive_sha256') != boot['archive_sha256']):
                raise ValueError('diagnostic child is not bound to the actual original VM/archive')
            report['results'][persona] = {'evidence': str(evidence), 'sha256': digest(evidence)}
            report['power_states']['after-' + persona] = power_timeout(
                shell('hidumper -s 3301 -a "-a"', 'power-after-' + persona))
        for kind, probe in getattr(args, 'root_probe', []):
            if kind not in ('binder-sender', 'bitmap', 'userid', 'bpf', 'audio-suite', 'vibrator-hdi'):
                raise ValueError('unsupported owned root diagnostic')
            label = 'root-' + kind
            if label in report['results']:
                raise ValueError('duplicate owned root diagnostic result')
            command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
                '--archive', archive, '--output', args.output / label, '--kind', kind,
                '--probe', Path(probe), '--arch', env['guest_arch'], '--device', env['device_type'],
                '--target', env['target'], '--boot-id', env['boot_id'], '--hdc', args.hdc,
                '--boot-evidence', args.boot], 'actual-' + label, timeout=300)
            evidence = args.output / label / 'result.json'
            child = json.loads(evidence.read_text())
            if (child.get('status') != 'pass' or child.get('boot_id') != env['boot_id'] or
                    child.get('archive_sha256') != boot['archive_sha256']):
                raise ValueError('root diagnostic is not bound to the actual original VM/archive')
            report['results'][label] = {'evidence': str(evidence), 'sha256': digest(evidence)}
            report['power_states']['after-' + label] = power_timeout(
                shell('hidumper -s 3301 -a "-a"', 'power-after-' + label))
            if preserve_policy:
                if report['power_states']['after-' + label] != report['power_states']['before']:
                    raise ValueError('root diagnostic did not preserve the original PowerMgr policy')
                report['screen_timeout_policy_unchanged'] = True
        same_boot('after')
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        if restore:
            report['screen_timeout_restore_attempted'] = True
            try:
                same_boot('restore')
                reply = shell('power-shell timeout -r', 'restore-test-timeout').strip()
                report['power_states']['restored'] = power_timeout(
                    shell('hidumper -s 3301 -a "-a"', 'power-restored'))
                if reply != 'Restore screen off time':
                    raise ValueError('PowerMgr rejected diagnostic timeout restoration')
                verify_policy_states(report['power_states']['before'], report['power_states']['setup'],
                                     report['power_states']['restored'])
                report['screen_timeout_restored'] = True
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
                report['status'] = 'fail'
                report['failures'].append('diagnostic test setup restoration failed: ' + str(error))
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--hdc', default='hdc')
    parser.add_argument('--persona', choices=tuple(PERSONAS), action='append', default=[])
    parser.add_argument('--root-probe', nargs=2, action='append', default=[], metavar=('KIND', 'PROBE'))
    parser.add_argument('--preserve-power-policy', action='store_true',
                        help='one short root diagnostic only: do not alter any PowerMgr timeout/override')
    args = parser.parse_args()
    if len(args.persona) != len(set(args.persona)):
        parser.error('duplicate diagnostic persona')
    if not args.persona and not args.root_probe:
        parser.error('at least one ordinary HAP or owned root probe is required')
    result = run(args)
    print(json.dumps({key: result[key] for key in ('status', 'scope', 'failures')}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
