#!/usr/bin/env python3
"""Finite real suspend/key-wake/compositor regression on the suite-owned VM.

No sleep-policy override, recurring input, kernel substitution or service
restart. Diagnostic kernels are explicitly labelled and cannot satisfy the
new-package acceptance contract.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from boot_package import FATAL, QemuGuest, kernel_sleeping
from guest_ui import GuestUi, bounds
from run_root_probe import digest, validate_identity


def visible_nodes(layout):
    pending = list(layout) if isinstance(layout, list) else [layout]
    count = 0
    visible = []
    while pending:
        node = pending.pop()
        count += 1
        if count > 100000 or not isinstance(node, dict):
            raise ValueError('malformed compositor accessibility hierarchy')
        attributes = node.get('attributes', {})
        children = node.get('children', [])
        if not isinstance(attributes, dict) or not isinstance(children, list):
            raise ValueError('malformed compositor node')
        if attributes.get('visible') == 'true' and attributes.get('bundleName'):
            try:
                rectangle = bounds(attributes.get('bounds'))
            except ValueError:
                pass  # Non-rendering roots may have empty bounds.
            else:
                visible.append({'bundle': attributes['bundleName'], 'rect': rectangle})
        pending.extend(children)
    if not visible:
        raise ValueError('no actual visible application/system window after resume')
    return visible


def screen_metrics(path):
    from PIL import Image
    with Image.open(path) as picture:
        rgb = picture.convert('RGB')
        sample = rgb.resize((128, 80))
        colors = len(set(sample.get_flattened_data()))
        low, high = sample.convert('L').getextrema()
        if min(picture.size) < 100 or colors < 64 or high - low < 16:
            raise ValueError('actual compositor returned an empty/uniform display after resume')
        return {'width': picture.width, 'height': picture.height,
                'sample_color_count': colors, 'luminance_range': high - low}


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    boot = json.loads(args.boot.read_text())
    environment = boot['test_environment']
    diagnostic = boot.get('purpose') != 'acceptance' or bool(boot.get('candidate_kernel'))
    report = {'schema_version': 1, 'status': 'fail',
        'scope': ('finite_suspend_compositor_DIAGNOSTIC_NOT_package_acceptance' if diagnostic
                  else 'fresh_packaged_finite_suspend_key_wake_real_compositor'),
        'archive_sha256': boot['archive_sha256'], 'boot_id': environment['boot_id'],
        'boot_evidence': str(args.boot.resolve()), 'boot_evidence_sha256': digest(args.boot),
        'target': environment['target'], 'arch': environment['guest_arch'],
        'device': environment['device_type'], 'commands': [], 'cycles': [], 'failures': [],
        'sleep_policy_changed': False, 'periodic_external_input': False,
        'first_artifact_behavior_gate_passed': False}

    def command(argv, label, timeout=30):
        argv = list(map(str, argv))
        log = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        row = {'argv': argv, 'log': str(log), 'exit_code': None}
        report['commands'].append(row)
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            log.write_bytes((error.stdout or b'') + (error.stderr or b''))
            row.update(timed_out=True, sha256=digest(log))
            raise ValueError('actual suspend/compositor command timed out: ' + label) from error
        log.write_text(result.stdout + result.stderr)
        row.update(exit_code=result.returncode, sha256=digest(log))
        if result.returncode or '[Fail]' in result.stdout or 'Device not found or connected' in result.stdout:
            raise ValueError('actual suspend/compositor command failed: ' + label)
        return result.stdout.replace('\r', '')

    control = QemuGuest(argparse.Namespace(archive=Path(boot['archive']), purpose=boot['purpose'],
                                          hdc_port=environment['hdc_host_port']))
    control.qmp_path = Path(environment['qmp_socket'])
    serial = args.boot.parent / 'qemu.log'
    ui = GuestUi(command, args.hdc, environment['target'], args.output / 'ui')

    def healthy():
        current = command(['ps', '-p', str(environment['qemu_pid']), '-o', 'command='],
                          'verify-suite-owned-QEMU').strip()
        if current != environment['qemu_command'] or str(control.qmp_path) not in current:
            raise ValueError('suite-owned QEMU process/socket identity changed')
        if FATAL.search(serial.read_text(errors='replace')):
            raise ValueError('actual guest has a fatal kernel/service failure')

    try:
        if boot.get('status') != 'pass' or diagnostic and not args.allow_diagnostic:
            raise ValueError('actual fresh acceptance boot required; diagnostic results stay diagnostic')
        if digest(Path(boot['archive'])) != boot['archive_sha256']:
            raise ValueError('actual archive identity changed')
        prior = next((row for row in boot['commands'] if row['log'].endswith(
            'render-service-after-stability.log')), None)
        if prior is None or digest(Path(prior['log'])) != prior.get('sha256'):
            raise ValueError('boot RenderService process evidence is missing/changed')
        expected_rs = Path(prior['log']).read_text().strip()
        if not expected_rs.isdecimal():
            raise ValueError('boot has no unambiguous RenderService process')
        foundation = None
        for cycle in range(2):
            healthy()
            # Only read an owned host serial file until real kernel sleep.
            # HDC/UI polling is deliberately absent from this quiet period.
            deadline = time.monotonic() + 60
            while not kernel_sleeping(serial.read_text(errors='replace')):
                if FATAL.search(serial.read_text(errors='replace')):
                    raise ValueError('guest service failed before real suspend')
                if time.monotonic() >= deadline:
                    raise ValueError('default policy did not enter actual s2idle within the finite test')
                time.sleep(0.5)
            row = {'sequence': cycle + 1, 'execute': 'system_powerdown',
                   'observed_actual_s2idle_before_key': True, 'reply': control.qmp('system_powerdown')}
            report['cycles'].append(row)
            deadline = time.monotonic() + 30
            while kernel_sleeping(serial.read_text(errors='replace')):
                if FATAL.search(serial.read_text(errors='replace')) or time.monotonic() >= deadline:
                    raise ValueError('actual key did not resume a healthy kernel')
                time.sleep(0.25)
            time.sleep(2)
            command([args.hdc, 'tconn', environment['target']], 'resume-connect')
            validate_identity(ui.shell('id -u; param get const.product.devicetype; uname -m', 'resume-identity'),
                              environment['guest_arch'], environment['device_type'])
            if ui.shell('cat /proc/sys/kernel/random/boot_id', 'resume-boot-id').strip() != environment['boot_id']:
                raise ValueError('guest kernel rebooted during suspend/resume')
            if ui.shell('pidof render_service', 'resume-render-service').strip() != expected_rs:
                raise ValueError('RenderService restarted during suspend/resume')
            actual_foundation = ui.shell('pidof foundation', 'resume-foundation').strip()
            if not actual_foundation.isdecimal() or foundation is not None and actual_foundation != foundation:
                raise ValueError('Foundation restarted during repeated suspend/resume')
            foundation = actual_foundation
            layout, layout_path = ui.layout(label='resumed-' + str(cycle + 1))
            nodes = visible_nodes(layout)
            screenshot = ui.screenshot(label='resumed-' + str(cycle + 1))
            row.update(render_service_pid=int(expected_rs), foundation_pid=int(foundation),
                actual_visible_windows=nodes, layout=str(layout_path), layout_sha256=digest(layout_path),
                screenshot=str(screenshot), screenshot_sha256=digest(screenshot),
                screen_metrics=screen_metrics(screenshot))
            snapshot = args.output / ('cycle-' + str(cycle + 1) + '-serial.log')
            snapshot.write_text(serial.read_text(errors='replace'))
            row.update(serial_evidence=str(snapshot), serial_sha256=digest(snapshot))
            healthy()
        report.update(status='pass', independent_real_sleep_wake_compositor_cycles=2)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hdc', required=True)
    parser.add_argument('--allow-diagnostic', action='store_true')
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'scope': result['scope'], 'failures': result['failures']}))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
