#!/usr/bin/env python3
"""Real packaged keyboard routing; does not prove privileged duration APIs."""
import argparse
import json
import re
from pathlib import Path
import socket
import subprocess
import sys
import time

from boot_package import QemuGuest
from guest_ui import GuestUi, LayoutNotReady, select_node
from power_test_policy import power_timeout, verify_restoration
from run_application_home_probe import system_screen
from run_root_probe import digest
from run_wifi_scan_diagnostic import capture_hilog
from settings_navigation_ui import require_painted_title
from verify_settings_navigation_results import settings_identity

ROOT = Path(__file__).resolve().parents[2]
SCOPE = 'fresh_package_real_keyboard_shortcut_NOT_duration_API_or_full_gate'
SHORTCUT = dict(businessId='qemu.settings', preKey=[2076], finalKey=2025,
    trigger='key_down', keyDownDuration=500, statusConfig='',
    ability=dict(bundleName='com.ohos.settings', abilityName='com.ohos.settings.MainAbility'))


def key_request(modifier, hold_ms):
    if modifier not in ('meta_l', 'ctrl') or type(hold_ms) is not int or hold_ms not in (100, 800):
        raise ValueError('only bounded owned diagnostic key sequences allowed')
    return {'keys': [{'type': 'qcode', 'data': modifier}, {'type': 'qcode', 'data': 'i'}],
            'hold-time': hold_ms}


def title_node(layout):
    # ArkUI exposes the same label on the TitleBar container and its Text child.
    # Select the actual painted title by its unique observed navigation ID,
    # rather than treating those two different nodes as duplicate titles.
    node = select_node(layout, 'com.ohos.settings', identifier='__NavigationField__Text__MainTitle__')
    if node['attributes'].get('type') != 'Text' or node['attributes'].get('text') not in ('设置', 'Settings'):
        raise ValueError('actual preinstalled Settings navigation title Text required')
    return node


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='fail', scope=SCOPE, archive=str(args.archive.resolve()),
        archive_sha256=digest(args.archive), runner_sha256=digest(Path(__file__)),
        commands=[], keys=[], cycles=[], failures=[], closed=[], first_artifact_behavior_gate_passed=False)
    guest = None
    override = False

    def command(argv, label, timeout=2400):
        argv = list(map(str, argv))
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        path = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        path.write_text(result.stdout + result.stderr)
        report['commands'].append(dict(argv=argv, log=str(path), sha256=digest(path), exit_code=result.returncode))
        if result.returncode or (argv[0] == str(args.hdc) and '[Fail]' in result.stdout):
            raise ValueError('real keyboard diagnostic command failed: ' + label)
        return result.stdout.replace('\r', '')

    try:
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        guest = QemuGuest(argparse.Namespace(archive=args.archive, output=args.output / 'boot',
            hdc=args.hdc, hdc_port=port, accel='auto', resolution='1280x800', purpose='acceptance',
            wait_seconds=1800, stable_seconds=60, kernel_diagnostic=None,
            power_diagnostic_wakeup=False, hold=False)).start()
        env = guest.report['test_environment']
        report['test_environment'] = env
        command([sys.executable, ROOT / 'ci/capability-audit/run_application_home_probe.py',
            '--boot', args.output / 'boot/boot.json', '--output', args.output / 'home', '--hdc', args.hdc], 'home')
        before = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'shortcut-power-before'))
        if before['override_ms'] is not None:
            raise ValueError('preexisting power override is not owned')
        override = True
        if guest.shell('power-shell timeout -o 86400000', 'shortcut-power-setup').strip() != 'Override screen off time to 86400000':
            raise ValueError('finite test setup failed')
        setup = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'shortcut-power-confirm'))
        if setup != dict(before, override_ms=86400000):
            raise ValueError('unexpected power policy change')
        ui = GuestUi(command, args.hdc, guest.target, args.output / 'ui')
        config = json.loads(ui.shell('cat /system/etc/multimodalinput/ability_launch_config.json', 'packaged-shortcuts'))
        if config.get('Shortkeys') != [SHORTCUT]:
            raise ValueError('new package does not contain the real expected shortcut')
        report['settings_uid'] = settings_identity(ui.shell('bm dump -n com.ohos.settings', 'settings-identity'))
        registered = ui.shell('hidumper -s 3101 -a "-k"', 'registered-input-shortcuts')
        if re.findall(r'ShortcutKey: count = (\d+)', registered) != ['1']:
            raise ValueError('MMI did not register the packaged system shortcut')
        ui.shell('hidumper -s 3101 -a "-l"', 'registered-input-devices')
        schema = guest.qmp('query-qmp-schema')
        schema_path = args.output / 'qmp-schema.json'
        schema_path.write_text(json.dumps(schema, indent=2) + '\n')
        if not any(row.get('name') == 'send-key' and row.get('meta-type') == 'command' for row in schema):
            raise ValueError('actual owned QEMU does not support keyboard injection')
        report.update(qmp_schema=str(schema_path), qmp_schema_sha256=digest(schema_path))

        def press(modifier, duration):
            guest.healthy()
            arguments = key_request(modifier, duration)
            report['keys'].append(dict(execute='send-key', arguments=arguments,
                reply=guest.qmp('send-key', arguments)))
            time.sleep((duration + 300) / 1000)
            diagnostic = args.output / ('key-diagnostic-' + str(len(report['keys'])))
            diagnostic.mkdir()
            report['keys'][-1]['hilog'] = capture_hilog(args.hdc, guest.target, diagnostic, 'failure-hilog')

        def home(label):
            layout, path = ui.layout(label=label)
            if system_screen(layout)[0] != 'home':
                raise ValueError('shortcut boundary left the real home screen')
            return dict(layout=str(path), sha256=digest(path))

        report['initial_home'] = home('shortcut-initial-home')
        for cycle in range(2):
            row = dict(cycle=cycle)
            press('meta_l', 100)
            time.sleep(1)
            row['early_release_home'] = home('early-release-' + str(cycle))
            press('ctrl', 800)
            row['wrong_modifier_home'] = home('wrong-modifier-' + str(cycle))
            press('meta_l', 800)
            deadline = time.monotonic() + 30
            last = ''
            while time.monotonic() < deadline:
                try:
                    layout, path = ui.layout(label='shortcut-settings-' + str(cycle))
                    node = title_node(layout)
                    screenshot = ui.screenshot(label='shortcut-settings-painted-' + str(cycle))
                    require_painted_title(screenshot, node)
                    row['settings'] = dict(layout=str(path), sha256=digest(path), node=node,
                        screenshot=str(screenshot), screenshot_sha256=digest(screenshot))
                    break
                except (ValueError, LayoutNotReady) as error:
                    last = str(error)
                    time.sleep(0.5)
            else:
                raise ValueError('real shortcut did not show painted Settings: ' + last)
            ui.shell('uitest uiInput keyEvent Back', 'ordinary-return-' + str(cycle))
            time.sleep(1)
            row['returned_home'] = home('returned-home-' + str(cycle))
            report['cycles'].append(row)
        if guest.shell('cat /proc/sys/kernel/random/boot_id', 'shortcut-boot-after').strip() != env['boot_id']:
            raise ValueError('shortcut testing changed the guest boot')
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
        if guest is not None:
            try:
                report['failure_hilog'] = capture_hilog(args.hdc, guest.target, args.output, 'failure-hilog')
                command([args.hdc, '-t', guest.target, 'shell',
                    'hidumper -s 3101 -a "-h"'], 'failure-input-help', timeout=30)
                command([args.hdc, '-t', guest.target, 'shell',
                    'cat /proc/bus/input/devices'], 'failure-input-devices', timeout=30)
            except Exception as diagnostic_error:
                report['failures'].append('failure diagnostics: ' + str(diagnostic_error))
    finally:
        if guest is not None:
            if override:
                try:
                    reply = guest.shell('power-shell timeout -r', 'shortcut-power-restore')
                    restored = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'shortcut-power-restored'))
                    report['power_restoration'] = verify_restoration(reply, before, setup, restored)
                except Exception as error:
                    report['failures'].append('power restoration: ' + str(error))
            guest.close()
            report['disposable_guest_closed'] = guest.process is None or guest.process.poll() is not None
        if report['failures']:
            report['status'] = 'fail'
        (args.output / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hdc', required=True)
    result = run(parser.parse_args())
    print(json.dumps(dict(status=result['status'], scope=SCOPE, failures=result['failures'])))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
