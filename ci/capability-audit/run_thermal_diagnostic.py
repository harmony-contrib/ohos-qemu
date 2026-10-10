#!/usr/bin/env python3
"""One owned archive boot: real cool sensor readback and ordinary API callbacks.

No temperature writes, engineering injection, guest library replacement, or
whole-package acceptance claim. All source/archive identities stay explicit.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import boot_package
from boot_package import QemuGuest
from power_test_policy import power_timeout, verify_restoration
from run_root_probe import digest
from thermal_contract import verify_inputs
from verify_thermal_backend import COMMANDS, verify as verify_backend
from verify_thermal_results import verify as verify_callbacks
from verify_thermal_results import verify_evidence

KERNEL_COMMAND = COMMANDS['kernel']


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'fail', 'scope': 'one_archive_real_cool_thermal_path_NOT_hot_transitions_or_full_gate',
        'archive': str(args.archive.resolve()), 'archive_sha256': digest(args.archive),
        'runner_sha256': digest(Path(__file__)), 'source_root': str(ROOT),
        'boot_helper': boot_package.__file__, 'boot_helper_sha256': digest(Path(boot_package.__file__)),
        'failures': [],
        'commands': [], 'observations': [], 'first_artifact_behavior_gate_passed': False}
    guest = None
    override = False

    def command(argv, label):
        log = args.output / (label + '.log')
        with log.open('x') as stream:
            child = subprocess.run(list(map(str, argv)), stdout=stream, stderr=subprocess.STDOUT,
                timeout=2400, env=dict(os.environ, LC_ALL='en_US.UTF-8', LC_CTYPE='en_US.UTF-8'))
        report['commands'].append({'argv': list(map(str, argv)), 'exit_code': child.returncode,
                                   'log': str(log), 'sha256': digest(log)})
        if child.returncode:
            raise ValueError('actual diagnostic command failed: ' + label)

    def capture(label, script):
        text = guest.shell(script, label)
        path = args.output / (label + '.log')
        path.write_text(text)
        report['observations'].append({'shell': script, 'log': str(path), 'sha256': digest(path)})
        return text

    try:
        with socket.socket() as connection:
            connection.bind(('127.0.0.1', 0))
            port = connection.getsockname()[1]
        guest = QemuGuest(argparse.Namespace(archive=args.archive, output=args.output / 'boot',
            hdc=args.hdc, hdc_port=port, accel='auto', resolution='1280x800', purpose='acceptance',
            wait_seconds=1800, stable_seconds=60, kernel_diagnostic=None,
            power_diagnostic_wakeup=False, hold=False)).start()
        env = guest.report['test_environment']
        report['test_environment'] = env
        command([sys.executable, ROOT / 'ci/capability-audit/run_application_home_probe.py',
            '--boot', args.output / 'boot/boot.json', '--output', args.output / 'home',
            '--hdc', args.hdc], 'home')
        before = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'thermal-power-before'))
        if before['override_ms'] is not None:
            raise ValueError('existing power override is not owned by this diagnostic')
        override = True
        if guest.shell('power-shell timeout -o 86400000', 'thermal-power-setup').strip() != 'Override screen off time to 86400000':
            raise ValueError('finite test power setup failed')
        setup = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'thermal-power-confirm'))
        if setup != dict(before, override_ms=86400000):
            raise ValueError('unexpected power policy change')
        hdi = capture('hdi-config', 'cat /vendor/etc/thermal_config/thermal_hdi_config.xml')
        policy = capture('service-config', 'cat /system/etc/thermal_config/thermal_service_config.xml')
        kernel = capture('kernel-before', KERNEL_COMMAND)
        service = capture('service-before', 'hidumper -s 3303 -a "-t"')
        report['backend_before'] = verify_backend(hdi, policy, kernel, service)
        command([sys.executable, ROOT / 'ci/capability-audit/run_normal_hap_probe.py',
            '--archive', args.archive, '--sdk', args.sdk, '--udid', guest.udid,
            '--persona', 'thermal', '--arch', env['guest_arch'], '--device', env['device_type'],
            '--target', guest.target, '--hdc', args.hdc, '--boot-id', env['boot_id'],
            '--boot', args.output / 'boot/boot.json', '--output', args.output / 'thermal',
            '--source-volume', args.source_volume, '--docker-image', args.docker_image], 'ordinary-thermal')
        evidence = args.output / 'thermal/evidence.json'
        app = json.loads(evidence.read_text())
        if (app['status'] != 'pass' or app['archive_sha256'] != report['archive_sha256'] or
                app['boot_id'] != env['boot_id'] or app['arch'] != env['guest_arch']):
            raise ValueError('ordinary thermal evidence is not from this package and boot')
        verify_inputs(json.loads((args.output / 'thermal/project/thermal-probe-inputs.json').read_text()),
                      app['run_id'], env['guest_arch'])
        report['callbacks'] = verify_callbacks((args.output / 'thermal/results.log').read_text(),
            app['run_id'], (args.output / 'thermal/application-identity.json').read_text())
        report['strict_inner_verification'] = verify_evidence(app, report['archive_sha256'],
                                                            env['boot_id'], env['guest_arch'])
        report.update(ordinary_evidence=str(evidence), ordinary_evidence_sha256=digest(evidence))
        kernel = capture('kernel-after', KERNEL_COMMAND)
        service = capture('service-after', 'hidumper -s 3303 -a "-t"')
        report['backend_after'] = verify_backend(hdi, policy, kernel, service)
        if guest.shell('cat /proc/sys/kernel/random/boot_id', 'thermal-final-boot-id').strip() != env['boot_id']:
            raise ValueError('guest boot changed during thermal test')
        guest.healthy()
        if digest(args.archive) != report['archive_sha256']:
            raise ValueError('archive changed during thermal test')
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if guest is not None:
            if override:
                try:
                    reply = guest.shell('power-shell timeout -r', 'thermal-power-restore')
                    restored = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'thermal-power-restored'))
                    report['power_restoration'] = verify_restoration(reply, before, setup, restored)
                except Exception as error:
                    report['status'] = 'fail'
                    report['failures'].append('power restoration: ' + str(error))
            guest.close()
            report['disposable_guest_closed'] = True
        (args.output / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'output', 'sdk'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hdc', default='hdc')
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    raise SystemExit(run(parser.parse_args()))
