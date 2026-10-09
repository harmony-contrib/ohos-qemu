#!/usr/bin/env python3
"""Boot one new archive and exercise real Settings refresh modes through UI.

The native caller is read-only; only the preinstalled Settings UI changes modes.
No library replacement, permission grant, fake rate or full-package attestation.
"""
import argparse
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_package import QemuGuest
from guest_ui import GuestUi
from power_test_policy import power_timeout, verify_restoration
from run_root_probe import digest, validate_elf
from settings_navigation_ui import require_painted_title, wait_node
from settings_refresh_ui import controls, verify_caller
from verify_screen_modes import verify as verify_modes
from verify_settings_navigation_results import verify_evidence as verify_navigation


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'fail', 'scope': 'new_package_Settings_refresh_diagnostic_NOT_full_gate',
              'archive': str(args.archive), 'archive_sha256': digest(args.archive),
              'probe': str(args.screen_probe), 'probe_sha256': digest(args.screen_probe),
              'commands': [], 'failures': [], 'first_artifact_behavior_gate_passed': False}
    guest = None
    override = False

    def command(argv, label, timeout=2400, accepted_failure=False):
        argv = list(map(str, argv))
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        path = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        path.write_text(result.stdout + result.stderr)
        report['commands'].append({'argv': argv, 'exit_code': result.returncode,
                                  'log': str(path), 'sha256': digest(path)})
        if result.returncode and not accepted_failure:
            raise ValueError('actual diagnostic command failed: ' + label)
        return result.stdout.replace('\r', '')

    try:
        with socket.socket() as connection:
            connection.bind(('127.0.0.1', 0))
            port = connection.getsockname()[1]
        guest = QemuGuest(argparse.Namespace(archive=args.archive, output=args.output / 'boot',
            hdc=args.hdc, hdc_port=port, accel='auto', resolution=args.resolution, purpose='acceptance',
            wait_seconds=1800, stable_seconds=60, kernel_diagnostic=None,
            power_diagnostic_wakeup=False, hold=False)).start()
        env = guest.report['test_environment']
        report['test_environment'] = env
        validate_elf(args.screen_probe, env['guest_arch'])
        command([sys.executable, ROOT / 'ci/capability-audit/run_application_home_probe.py',
            '--boot', args.output / 'boot/boot.json', '--output', args.output / 'home', '--hdc', args.hdc], 'home')
        before = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'refresh-power-before'))
        if before['override_ms'] is not None:
            raise ValueError('preexisting power override')
        override = True
        if guest.shell('power-shell timeout -o 86400000', 'refresh-power-setup').strip() != 'Override screen off time to 86400000':
            raise ValueError('finite power override failed')
        setup = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'refresh-power-confirm'))
        if setup != dict(before, override_ms=86400000):
            raise ValueError('power policy changed unexpectedly')
        ui = GuestUi(command, args.hdc, guest.target, args.output / 'ui')
        remote = '/data/local/tmp/qemu-screen-readonly-' + secrets.token_hex(16)
        command([args.hdc, '-t', guest.target, 'file', 'send', args.screen_probe, remote], 'send-readonly-caller')
        ui.shell('chmod 700 ' + remote, 'readonly-caller-mode')

        def read_modes():
            return verify_modes(ui.shell('unset LD_LIBRARY_PATH LD_PRELOAD; ' + remote, 'actual-screen-modes'))

        original = read_modes()
        report['original_modes'] = original
        command([sys.executable, ROOT / 'ci/capability-audit/run_normal_hap_probe.py',
            '--archive', args.archive, '--sdk', args.sdk, '--udid', guest.udid,
            '--persona', 'settings-navigation', '--arch', env['guest_arch'], '--device', env['device_type'],
            '--target', guest.target, '--hdc', args.hdc, '--boot-id', env['boot_id'],
            '--boot', args.output / 'boot/boot.json', '--output', args.output / 'settings-navigation',
            '--source-volume', args.source_volume, '--docker-image', args.docker_image], 'ordinary-Settings-caller')
        ordinary = json.loads((args.output / 'settings-navigation/evidence.json').read_text())
        report['navigation'] = verify_navigation(ordinary, report['archive_sha256'], env['boot_id'], env['guest_arch'])
        report['request'] = ui.click('org.harmonycontrib.capabilityaudit', identifier='settings-probe-refresh',
                                     label='request-public-refresh-page')

        def ready(expected):
            deadline = time.monotonic() + 60
            last_error = ''
            while time.monotonic() < deadline:
                try:
                    actual = read_modes()
                    if (actual['main_screen']['id'] != original['main_screen']['id'] or
                            actual['refresh_choices'] != original['refresh_choices'] or
                            actual['main_screen']['activeModeIndex'] != expected):
                        raise ValueError('actual display mode did not match requested choice')
                    layout, path = ui.layout(label='refresh-page')
                    matched = controls(layout, actual)
                    screen = ui.screenshot(label='refresh-painted')
                    for row in matched.values():
                        require_painted_title(screen, row['label'])
                    return {'readback': actual, 'layout': str(path), 'layout_sha256': digest(path),
                            'screenshot': str(screen), 'screenshot_sha256': digest(screen), 'controls': matched}
                except ValueError as error:
                    last_error = str(error)
                    time.sleep(0.5)
            raise ValueError('actual Settings refresh page did not become ready: ' + last_error)

        active = original['main_screen']['activeModeIndex']
        report['initial_page'] = ready(active)
        alternatives = [mode for mode in original['refresh_choices'] if mode['id'] != active]
        if args.require_mode_change and not alternatives:
            raise ValueError('this real display offers no alternate rate; mode-change coverage unavailable')
        if alternatives:
            selected = alternatives[0]['id']
            def click_radio(row, label):
                x, y, width, height = row['radio']['rect']
                ui.shell('uitest uiInput click ' + str(x + width // 2) + ' ' + str(y + height // 2), label)
            click_radio(report['initial_page']['controls'][selected], 'select-actual-alternate-mode')
            report['changed_page'] = ready(selected)
            click_radio(report['changed_page']['controls'][active], 'restore-original-mode')
            report['restored_page'] = ready(active)
        else:
            report['mode_change'] = 'not_claimed_no_real_alternate_rate'
        ui.shell('uitest uiInput keyEvent Back', 'return-from-refresh')
        report['returned'] = wait_node(ui, identifier='settings-probe-refresh', label='original-caller-returned')
        ui.click('org.harmonycontrib.capabilityaudit', identifier='settings-probe-screen-denial', label='ordinary-screen-denial')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            raw = ui.shell('cat /data/app/el2/100/base/org.harmonycontrib.capabilityaudit/files/settings-navigation-' +
                           ordinary['run_id'] + '-results.log', 'ordinary-screen-denial-result')
            rows = [json.loads(line) for line in raw.splitlines()]
            denial = [row for row in rows if row.get('name') == 'screen.ordinary-denial']
            if denial:
                report['ordinary_caller_observations'] = verify_caller(raw, ordinary['run_id'])
                break
            time.sleep(0.5)
        else:
            raise ValueError('ordinary screen denial observation missing')
        guest.healthy()
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
        if guest is not None:
            try:
                guest.shell('hilog -x', 'refresh-failure-hilog')
                guest.shell('aa dump -a -u 100', 'refresh-failure-abilities')
            except Exception as capture_error:
                report['failure_capture_error'] = str(capture_error)
    finally:
        if guest is not None:
            if override:
                try:
                    reply = guest.shell('power-shell timeout -r', 'refresh-power-restore')
                    restored = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'refresh-power-restored'))
                    report['power_restoration'] = verify_restoration(reply, before, setup, restored)
                except Exception as error:
                    report['failures'].append('power restoration: ' + str(error))
            guest.close()
            report['disposable_guest_closed'] = True
        if report['failures']:
            report['status'] = 'fail'
        (args.output / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'output', 'sdk', 'screen-probe'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hdc', default='hdc')
    parser.add_argument('--resolution', default='1280x800')
    parser.add_argument('--require-mode-change', action='store_true')
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    raise SystemExit(run(parser.parse_args()))
