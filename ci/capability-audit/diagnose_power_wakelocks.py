#!/usr/bin/env python3
"""Finite private-kernel suspend/key-wakeup and real sysfs lock diagnosis.

Never package acceptance. Does not change sleep policy, grant capabilities,
restart HDC or keep a guest awake periodically. Every key follows observed
kernel sleep; owned test locks have bounded kernel timeouts and are released.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shlex
import signal
import subprocess
import time

from boot_package import FATAL, QemuGuest, kernel_sleeping
from run_root_probe import digest, parse_exit, validate_identity


def sleeping(log):
    return kernel_sleeping(log)


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    boot = json.loads(args.boot.read_text())
    env = boot['test_environment']
    nonce = secrets.token_hex(16)
    names = ['qemu_power_' + nonce + '_' + suffix for suffix in ('a', 'b', 'timer', 'invalid')]
    report = {'schema_version': 1, 'status': 'fail',
        'scope': 'private_candidate_power_kernel_DIAGNOSTIC_NOT_new_package_acceptance',
        'boot_evidence': str(args.boot.resolve()), 'boot_evidence_sha256': digest(args.boot),
        'candidate_kernel_sha256': boot.get('candidate_kernel', {}).get('image_sha256'),
        'boot_id': env['boot_id'], 'target': env['target'], 'commands': [],
        'key_events': [], 'run_id': nonce, 'lock_names': names, 'failures': [],
        'first_artifact_behavior_gate_passed': False}

    def command(argv, label, timeout=30):
        argv = list(map(str, argv))
        log = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        record = {'argv': argv, 'exit_code': None, 'log': str(log)}
        report['commands'].append(record)
        with log.open('w') as stream:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stream,
                stderr=subprocess.STDOUT, start_new_session=True)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                record.update(timed_out=True, sha256=digest(log))
                raise ValueError('owned diagnostic operation timed out: ' + label) from error
        record.update(exit_code=process.returncode, sha256=digest(log))
        if process.returncode:
            raise ValueError('actual diagnostic command failed: ' + label)
        return log.read_text().replace('\r', '')

    def shell(script, label, timeout=30):
        challenge = secrets.token_hex(16)
        wrapper = ('sh -c ' + shlex.quote(script) + '; task_power_status=$?; '
                   "printf '__OHOS_PROBE_EXIT_" + challenge + "=%s\\n' \"$task_power_status\"")
        value = command([args.hdc, '-t', env['target'], 'shell', wrapper], label, timeout)
        rows = value.splitlines(keepends=True)
        if not rows or parse_exit(rows[-1], challenge) != 0:
            raise ValueError('actual guest diagnostic script failed: ' + label)
        return ''.join(rows[:-1])

    guest = QemuGuest(argparse.Namespace(archive=Path(boot['archive']), purpose='diagnostic',
                                        hdc_port=env['hdc_host_port']))
    guest.qmp_path = Path(env['qmp_socket'])
    serial = args.boot.parent / 'qemu.log'

    def wake(label):
        current = command(['ps', '-p', str(env['qemu_pid']), '-o', 'command='], label + '-owned-process').strip()
        if current != env['qemu_command'] or str(guest.qmp_path) not in current:
            raise ValueError('original private VM no longer owns this diagnostic socket')
        actual_log = serial.read_text(errors='replace')
        if FATAL.search(actual_log):
            raise ValueError('private guest already has a fatal service/kernel failure')
        if not sleeping(actual_log):
            raise ValueError('kernel is not actually asleep; do not press an ambiguous power button')
        report['key_events'].append({'label': label, 'execute': 'system_powerdown',
                                     'reply': guest.qmp('system_powerdown')})
        time.sleep(2)
        command([args.hdc, 'tconn', env['target']], label + '-reconnect')
        identity = shell('id -u; param get const.product.devicetype; uname -m', label + '-identity')
        validate_identity(identity, env['guest_arch'], env['device_type'])
        if shell('cat /proc/sys/kernel/random/boot_id', label + '-boot-id').strip() != env['boot_id']:
            raise ValueError('wake changed the actual kernel boot identity')
        if sleeping(serial.read_text(errors='replace')):
            raise ValueError('power key did not finish actual machine_suspend')
        return shell('pidof render_service', label + '-render-service').strip()

    try:
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'diagnostic' or
                not boot.get('candidate_kernel') or env['guest_arch'] != 'arm64'):
            raise ValueError('an actual booted private ARM64 power candidate is required')
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not sleeping(serial.read_text(errors='replace')):
            if FATAL.search(serial.read_text(errors='replace')):
                raise ValueError('guest service failed before the first real sleep')
            time.sleep(1)
        rs_pid = wake('first-real-key')
        prior = next((row for row in boot['commands']
                      if row['log'].endswith('render-service-after-stability.log')), None)
        if (not rs_pid.isdecimal() or prior is None or
                digest(Path(prior['log'])) != prior.get('sha256') or
                Path(prior['log']).read_text().strip() != rs_pid):
            raise ValueError('actual RenderService identity is missing')
        before = shell('cat /sys/power/wake_lock; cat /sys/power/wake_unlock', 'initial-real-locks')
        if any(name in before.split() for name in names):
            raise ValueError('fresh diagnostic lock already exists')
        # Keep only two bounded test wakeup sources while checking the third
        # source's real timer and invalid-write boundaries. This is a test of
        # lock semantics, not an unattended boot or a production sleep-policy
        # override. Every lock expires within 15 seconds if transport fails.
        script = ('set -e; '
            'printf ' + shlex.quote(names[0] + ' 15000000000') + ' > /sys/power/wake_lock; '
            'printf ' + shlex.quote(names[1] + ' 15000000000') + ' > /sys/power/wake_lock; '
            'printf "__HELD_AB__\\n"; cat /sys/power/wake_lock; '
            'printf ' + shlex.quote(names[2] + ' 1000000000') + ' > /sys/power/wake_lock; '
            'printf "__HELD_TIMER__\\n"; cat /sys/power/wake_lock; sleep 2; '
            'printf "__TIMER_EXPIRED__\\n"; cat /sys/power/wake_lock; '
            'if printf ' + shlex.quote(names[3] + ' -1') + ' > /sys/power/wake_lock; then exit 91; fi; '
            'if printf ' + shlex.quote(names[3] + ' 12x') + ' > /sys/power/wake_lock; then exit 92; fi; '
            'printf "__INVALID_REJECTED__\\n"; cat /sys/power/wake_lock; '
            'printf ' + shlex.quote(names[0]) + ' > /sys/power/wake_unlock; '
            'printf "__ONLY_B__\\n"; cat /sys/power/wake_lock; '
            'printf ' + shlex.quote(names[1]) + ' > /sys/power/wake_unlock; '
            'printf "__RELEASED__\\n"; cat /sys/power/wake_lock')
        actual = shell(script, 'real-lock-timer-and-boundaries')
        stages = {}
        selected = None
        for line in actual.splitlines():
            if line.startswith('__') and line.endswith('__'):
                selected = line
                if selected in stages:
                    raise ValueError('duplicated diagnostic lock phase')
                stages[selected] = []
            elif selected is not None:
                stages[selected].extend(line.split())
        expected = {'__HELD_AB__': set(names[:2]), '__HELD_TIMER__': set(names[:3]),
            '__TIMER_EXPIRED__': set(names[:2]), '__INVALID_REJECTED__': set(names[:2]),
            '__ONLY_B__': {names[1]}, '__RELEASED__': set()}
        if set(stages) != set(expected) or any(set(stages[key]) & set(names) != value for key, value in expected.items()):
            raise ValueError('real lock acquisition, timeout, invalid input, isolation or release failed')
        report['verified_lock_stages'] = {key: sorted(set(value) & set(names)) for key, value in stages.items()}
        # No host input or HDC polling during this quiet interval. After the
        # real system sleeps again, prove that the 100ms GPIO pulse released
        # and a subsequent independent press wakes the same kernel.
        deadline = time.monotonic() + 60
        time.sleep(30)
        while time.monotonic() < deadline and not sleeping(serial.read_text(errors='replace')):
            if FATAL.search(serial.read_text(errors='replace')):
                raise ValueError('guest service failed after releasing real wake locks')
            time.sleep(1)
        if wake('second-real-key') != rs_pid:
            raise ValueError('RenderService restarted during repeated real sleep/wake')
        report.update(status='pass', verified_real_lock_phases=6, independent_key_wakeups=2)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        # Exact owned names only; no release of framework/application locks.
        try:
            shell('for task_power_name in ' + shlex.join(names[:3]) +
                '; do printf "%s" "$task_power_name" > /sys/power/wake_unlock 2>/dev/null || :; done',
                'release-only-owned-bounded-test-locks', timeout=3)
        except (OSError, ValueError, subprocess.SubprocessError):
            report['cleanup_note'] = 'transport unavailable; owned kernel locks expire within 15s'
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hdc', required=True)
    result = run(parser.parse_args())
    print(json.dumps({key: result.get(key) for key in ('status', 'verified_real_lock_phases', 'independent_key_wakeups', 'failures')}))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
