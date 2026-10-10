#!/usr/bin/env python3
"""Validate one fresh archive's real WPA scan path; no association/AP/P2P claim."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time

from boot_package import QemuGuest
from power_test_policy import power_timeout, verify_restoration
from run_root_probe import digest, validate_elf

ROOT = Path(__file__).resolve().parents[2]


def active_state(text):
    values = re.findall(r'^WiFi active state: (inactive|activated)$', text, re.M)
    if len(values) != 1:
        raise ValueError('unambiguous actual WifiDevice state required')
    return values[0] == 'activated'


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='fail', scope='fresh_archive_WPA_scan_and_bands_NOT_association_AP_P2P_or_PNO',
        archive=str(args.archive.resolve()), archive_sha256=digest(args.archive),
        runner_sha256=digest(Path(__file__)), commands=[], observations=[], failures=[],
        first_artifact_behavior_gate_passed=False, closed=[])
    guest = None
    override = False
    radio_owned = False

    def command(argv, label):
        argv = list(map(str, argv))
        log = args.output / (label + '.log')
        with log.open('x') as stream:
            result = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, timeout=2400)
        report['commands'].append(dict(argv=argv, exit_code=result.returncode,
                                      log=str(log), sha256=digest(log)))
        if result.returncode:
            raise ValueError('actual Wi-Fi diagnostic command failed: ' + label)

    def capture(label, script):
        value = guest.shell(script, label)
        path = args.output / (label + '.log')
        path.write_text(value)
        report['observations'].append(dict(shell=script, log=str(path), sha256=digest(path)))
        return value

    def wait_state(expected, label):
        for attempt in range(30):
            if active_state(capture(label + '-' + str(attempt), 'hidumper -s 1120')) == expected:
                return
            time.sleep(1)
        raise ValueError('actual Wi-Fi state did not reach requested state')

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
        before = power_timeout(capture('power-before', 'hidumper -s 3301 -a "-a"'))
        if before['override_ms'] is not None:
            raise ValueError('preexisting power override is not owned by this diagnostic')
        override = True
        if capture('power-setup', 'power-shell timeout -o 86400000').strip() != 'Override screen off time to 86400000':
            raise ValueError('finite application-test power setup failed')
        setup = power_timeout(capture('power-confirm', 'hidumper -s 3301 -a "-a"'))
        if setup != dict(before, override_ms=86400000):
            raise ValueError('unexpected power policy change')
        if active_state(capture('wifi-before', 'hidumper -s 1120')):
            raise ValueError('requires a fresh default-disabled Wi-Fi image; preserve existing state')
        # Read the very same pinned assets as the build recipe, from the guest.
        spec = importlib.util.spec_from_file_location('qemu_regdb_assets',
            ROOT / 'patches/common/device/qemu/wlan_regulatory/verify_assets.py')
        assets = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(assets)
        for name in ('regulatory.db', 'regulatory.db.p7s'):
            value = capture('packaged-' + name, 'sha256sum /system/lib/firmware/' + name).split()
            expected = assets.ASSETS['device/soc/unisoc/p7885/hardware/wcn/' + name]
            if value != [expected, '/system/lib/firmware/' + name]:
                raise ValueError('packaged signed regulatory asset differs from the pinned input')
        if capture('firmware-search-path', 'cat /sys/module/firmware_class/parameters/path').strip() != '/system/lib/firmware':
            raise ValueError('actual firmware loader did not receive the preinstalled search path')
        serial = (args.output / 'boot/qemu.log').read_text(errors='replace')
        if re.search(r'(?:failed|invalid|malformed).*regulatory\.db|regulatory\.db.*(?:failed|invalid|malformed)',
                     serial, re.I):
            raise ValueError('actual kernel reported regulatory database rejection/load failure')
        command([sys.executable, ROOT / 'ci/capability-audit/build_wpa_frequency_readback.py',
            '--sdk', args.sdk, '--output', args.output / 'readonly-caller'], 'build-readonly-caller')
        probe = args.output / 'readonly-caller' / ('wpa-frequency-readback-' + env['guest_arch'])
        validate_elf(probe, env['guest_arch'])
        remote = '/data/local/tmp/oq-wpa-readonly-' + secrets.token_hex(16)
        command([args.hdc, '-t', env['target'], 'file', 'send', probe, remote], 'send-readonly-caller')
        if capture('readonly-caller-hash', 'sha256sum ' + remote).split() != [digest(probe), remote]:
            raise ValueError('uploaded diagnostic executable differs from the real SDK build')
        capture('readonly-caller-mode', 'chmod 700 ' + remote)
        for cycle in range(2):
            radio_owned = True
            capture('enable-' + str(cycle), 'svc wifi enable')
            wait_state(True, 'enabled-' + str(cycle))
            # SA activation alone is not accepted: the ordinary HAP must get
            # real supported bands and complete two fresh scan generations.
            command([sys.executable, ROOT / 'ci/capability-audit/run_normal_hap_probe.py',
                '--archive', args.archive, '--sdk', args.sdk, '--udid', guest.udid,
                '--persona', 'wifi-scan', '--arch', env['guest_arch'], '--device', env['device_type'],
                '--target', env['target'], '--hdc', args.hdc, '--boot-id', env['boot_id'],
                '--boot', args.output / 'boot/boot.json', '--output', args.output / ('scan-' + str(cycle)),
                '--source-volume', args.source_volume, '--docker-image', args.docker_image], 'ordinary-scan-' + str(cycle))
            document = capture('real-frequency-table-' + str(cycle), remote)
            if not document.startswith('Mode[') or not document.endswith('\n\n') or len(document.encode()) >= 2047:
                raise ValueError('actual WPA capability document missing or outside validated HDI buffer')
            capture('disable-' + str(cycle), 'svc wifi disable')
            wait_state(False, 'disabled-' + str(cycle))
            radio_owned = False
        capture('wifi-hilog', 'hilog -x')
        if capture('final-boot-id', 'cat /proc/sys/kernel/random/boot_id').strip() != env['boot_id']:
            raise ValueError('guest rebooted during the scan diagnostic')
        guest.healthy()
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
        if guest is not None:
            try:
                capture('failure-hilog', 'hilog -x')
            except Exception as capture_error:
                report['capture_error'] = str(capture_error)
    finally:
        if guest is not None:
            if radio_owned:
                try:
                    capture('restore-wifi-disabled', 'svc wifi disable')
                    wait_state(False, 'restored-wifi-disabled')
                except Exception as error:
                    report['failures'].append('radio restoration: ' + str(error))
            if override:
                try:
                    reply = capture('power-restore', 'power-shell timeout -r')
                    restored = power_timeout(capture('power-restored', 'hidumper -s 3301 -a "-a"'))
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
    for name in ('archive', 'sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hdc', required=True)
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    result = run(parser.parse_args())
    print(json.dumps(dict(status=result['status'], scope=result['scope'], failures=result['failures'])))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
