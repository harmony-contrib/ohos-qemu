#!/usr/bin/env python3
"""Real ordinary Serial API, trusted UI, USB bytes and attachment regressions.

Uses only the enclosing suite's private QEMU USB socket. No SA/HDI substitute,
token allocation, authorization IPC shortcut or raw-node permission change.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import time

from guest_ui import GuestUi, select_node
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest, validate_identity
from serial_host_attachment_control import AttachmentControl, endpoint_identity
from verify_serial_results import verify as verify_basic
from verify_serial_attachment_results import verify as verify_attachment
from run_usb_manager_cases import run_cases as run_usb_manager_cases

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = 'org.harmonycontrib.serialaudit'
TRUSTED = 'com.usb.right'
PORT = 'ttyUSB0'


def rows(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    boot = json.loads(args.boot.read_text())
    environment = boot['test_environment']
    report = {'schema_version': 1, 'status': 'fail',
        'scope': 'fresh_packaged_2in1_ordinary_Serial_USB_UI_data_attachment_regressions',
        'archive_sha256': digest(args.archive), 'boot_id': environment['boot_id'],
        'target': environment['target'], 'arch': environment['guest_arch'], 'device': '2in1',
        'commands': [], 'ui_actions': [], 'device_snapshots': [], 'scenarios': {}, 'failures': [],
        'first_artifact_behavior_gate_passed': False}
    echo = None
    echo_log = None
    control = None
    journal = None

    def command(argv, label, timeout=60, allowed_failure=False):
        argv = list(map(str, argv))
        path = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        record = {'argv': argv, 'log': str(path), 'exit_code': None}
        report['commands'].append(record)
        with path.open('w') as stream:
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
                record.update(timed_out=True, sha256=digest(path))
                raise ValueError('owned Serial command timed out: ' + label) from error
        record.update(exit_code=process.returncode, sha256=digest(path))
        text = path.read_text().replace('\r', '')
        if not allowed_failure and (process.returncode or '[Fail]' in text or 'Device not found or connected' in text):
            raise ValueError('actual Serial command failed: ' + label)
        return text

    ui = GuestUi(command, args.hdc, environment['target'], args.output / 'ui')

    def same_boot(label):
        validate_identity(ui.shell('id -u; param get const.product.devicetype; uname -m', label + '-identity'),
                          environment['guest_arch'], '2in1')
        if ui.shell('cat /proc/sys/kernel/random/boot_id', label + '-boot-id').strip() != environment['boot_id']:
            raise ValueError('Serial probe guest rebooted/changed')

    def device(present, label):
        deadline = time.monotonic() + 20
        expected = 'PRESENT' if present else 'ABSENT'
        while time.monotonic() < deadline:
            observed = ui.shell('if test -c /dev/' + PORT + '; then echo PRESENT; else echo ABSENT; fi', label)
            if observed == expected:
                break
            time.sleep(0.25)
        else:
            raise ValueError('real USB devnode did not reach expected attachment state: ' + label)
        if present:
            text = ui.shell('set -e; stat -c "%a %u %g %t:%T" /dev/' + PORT + '; '
                'readlink -f /sys/class/tty/' + PORT + '/device; '
                'task_usb_path=$(readlink -f /sys/class/tty/' + PORT + '/device); '
                'while test "$task_usb_path" != /sys && ! test -f "$task_usb_path/idVendor"; do '
                'task_usb_path=${task_usb_path%/*}; done; '
                'test -f "$task_usb_path/idVendor"; cat "$task_usb_path/idVendor" '
                '"$task_usb_path/idProduct" "$task_usb_path/serial"', label + '-actual-sysfs-and-ACL')
            lines = text.splitlines()
            if (len(lines) != 5 or lines[0].split()[:3] != ['660', '1025', '1025'] or
                    not lines[1].startswith('/sys/devices/') or lines[2:] != ['0403', '6001', 'QEMUAPI26']):
                raise ValueError('dedicated real FTDI attachment/serial UID ACL mismatch')
        else:
            text = observed
        report['device_snapshots'].append({'label': label, 'present': present, 'actual': text})

    def result(filename, case, label, wait=30, bundle=BUNDLE):
        remote = '/data/app/el2/100/base/' + bundle + '/files/' + filename
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            text = ui.shell('if test -f ' + remote + '; then cat ' + remote + '; fi', label)
            actual = rows(text)
            if any(row.get('passed') is False for row in actual):
                raise ValueError('actual ordinary Serial case failed: ' + label)
            if any(row.get('case') == case for row in actual):
                return text
            time.sleep(0.25)
        raise ValueError('actual ordinary Serial case did not complete: ' + case)

    def dialog(action, label, click=True):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            layout, layout_path = ui.layout(label=label)
            matches = []
            for text in labels[action]:
                try:
                    matches.append(select_node(layout, TRUSTED, text=text, clickable=True))
                except ValueError:
                    continue
            if len(matches) > 1:
                raise ValueError('ambiguous actual trusted authorization controls')
            if matches:
                node = matches[0]
                action_record = {'label': label, 'trusted_bundle': TRUSTED, 'decision': action,
                    'layout': str(layout_path), 'layout_sha256': digest(layout_path), 'selected_node': node}
                if click:
                    left, top, width, height = node['rect']
                    ui.shell('uitest uiInput click ' + str(left + width // 2) + ' ' + str(top + height // 2), label + '-click')
                action_record['clicked'] = click
                report['ui_actions'].append(action_record)
                return
            time.sleep(0.5)
        raise ValueError('actual trusted Serial authorization UI missing: ' + label)

    def build_install(scenario, nonce, bundle=BUNDLE, scenario_key=None, usb_actor="owner"):
        key = scenario_key or scenario
        directory = args.output / key
        directory.mkdir()
        project = directory / 'project'
        command([sys.executable, Path(__file__).with_name('build_serial_hap_probe.py'),
            '--sdk', args.sdk, '--arch', environment['guest_arch'], '--output', project,
            '--run-id', nonce, '--port-name', PORT, '--bundle-name', bundle, '--scenario', scenario, '--usb-actor', usb_actor],
            'build-fresh-ordinary-' + scenario, timeout=1800)
        unsigned = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
        signed = directory / 'signed.hap'
        command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
            '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(directory.resolve()) + ',dst=/probe', args.docker_image,
            'python3', '/work/ci/capability-audit/sign_web_probe.py',
            '--signer-dist', '/ohos/developtools/hapsigner/dist',
            '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
            '--unsigned', '/probe/' + unsigned.relative_to(directory).as_posix(),
            '--output', '/probe/signed.hap', '--bundle-name', bundle, '--udid', environment['udid'], '--sign-code', '1'],
            'normal-no-ACL-sign-and-verify-' + scenario, timeout=300)
        command([args.hdc, '-t', environment['target'], 'uninstall', bundle], 'remove-only-own-Serial-app', allowed_failure=True)
        installed = command([args.hdc, '-t', environment['target'], 'install', signed], 'install-normal-' + scenario)
        if not re.search(r'success', installed, re.I):
            raise ValueError('real ordinary Serial HAP did not install')
        identity = ui.shell('bm dump -n ' + bundle, 'normal-Serial-identity')
        identity_command = dict(report['commands'][-1])
        uid = require_normal_identity(identity, bundle)
        inputs = project / 'serial-probe-inputs.json'
        data = json.loads(inputs.read_text())
        if data['request_permissions'] != [] or data['run_id'] != nonce:
            raise ValueError('ordinary Serial test must remain permission-free and nonce-bound')
        if data.get('bundle_name') != bundle or (scenario == 'usb-manager' and data.get('usb_actor') != usb_actor):
            raise ValueError('actual USB/Serial SDK caller bundle/actor inputs changed')
        report['scenarios'][key] = {'run_id': nonce, 'ordinary_uid': uid, 'identity_command': identity_command, 'hap_sha256': digest(signed),
            'build_inputs': str(inputs), 'build_inputs_sha256': digest(inputs)}

    def launch(bundle=BUNDLE):
        text = ui.shell('aa start -a EntryAbility -b ' + bundle, 'launch-own-normal-Serial-app')
        if 'start ability successfully' not in text.lower():
            raise ValueError('real ordinary Serial ability did not launch')

    try:
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or boot.get('candidate_kernel') or
                environment.get('device_type') != '2in1' or report['archive_sha256'] != boot.get('archive_sha256') or
                environment.get('usb_serial_hardware', {}).get('always_plugged') is not False):
            raise ValueError('exact newly packaged 2in1 VM with a real attachment-controlled USB endpoint required')
        endpoint = Path(environment['usb_serial_socket'])
        endpoint_identity(endpoint)
        same_boot('before')
        source = '/ohos/base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog/src/main/resources'
        query = ('import json; from pathlib import Path; '
            'values={"allowButton":set(),"notAllowButton":set()}; '
            '[values[row["name"]].add(row["value"]) for p in Path(' + repr(source) + ').rglob("string.json") '
            'for row in json.loads(p.read_text())["string"] if row.get("name") in values]; '
            'print(json.dumps({k:sorted(v) for k,v in values.items()}))')
        labels_raw = command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
            '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly', args.docker_image,
            'python3', '-c', query], 'actual-pinned-trusted-dialog-resource-labels')
        labels = json.loads(labels_raw)
        if not all(isinstance(labels.get(key), list) and labels[key] for key in ('allowButton', 'notAllowButton')):
            raise ValueError('trusted dialog resource declarations are missing')
        trusted = ui.shell('bm dump -n ' + TRUSTED, 'preinstalled-trusted-dialog-identity')
        info = json.loads(trusted.removeprefix(TRUSTED + ':\n'))['applicationInfo']
        if info.get('isSystemApp') is not True or info.get('appPrivilegeLevel') not in ('system_basic', 'system_core'):
            raise ValueError('actual Serial dialog is not the preinstalled trusted system application')
        device(False, 'initial-unconnected-endpoint')
        basic_nonce = secrets.token_hex(16)
        build_install('basic', basic_nonce)
        echo_path = args.output / 'basic/host-frames.jsonl'
        echo_log_path = args.output / 'basic/echo-process.log'
        echo_log = echo_log_path.open('w')
        echo_argv = [sys.executable, str(Path(__file__).with_name('serial_host_echo.py')),
            '--socket', str(endpoint), '--run-id', basic_nonce, '--output', str(echo_path), '--hold-seconds', '10']
        echo_record = {'argv': echo_argv, 'exit_code': None, 'log': str(echo_log_path)}
        report['commands'].append(echo_record)
        echo = subprocess.Popen(echo_argv, stdout=echo_log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        device(True, 'basic-real-USB-attach')
        launch()
        result('serial-results.log', 'begin', 'basic-ready')
        report['ui_actions'].append(ui.click(BUNDLE, identifier='serial-enumerate', label='basic-enumerate'))
        result('serial-results.log', 'ordinary_authorization_denied', 'basic-ordinary-raw-and-service-denial')
        report['ui_actions'].append(ui.click(BUNDLE, identifier='serial-deny', label='basic-request-denial'))
        dialog('notAllowButton', 'basic-trusted-deny')
        result('serial-results.log', 'deny_open', 'basic-denial-completed')
        report['ui_actions'].append(ui.click(BUNDLE, identifier='serial-allow', label='basic-request-approval'))
        dialog('allowButton', 'basic-trusted-allow')
        basic = result('serial-results.log', 'completed', 'basic-completed', wait=60)
        echo.wait(timeout=60)
        echo_log.close()
        echo_record.update(exit_code=echo.returncode, sha256=digest(echo_log_path))
        if echo.returncode:
            raise ValueError('actual host byte challenge/echo process failed')
        errors = verify_basic(rows(basic), rows(echo_path.read_text()), basic_nonce, BUNDLE, PORT)
        if errors:
            raise ValueError('real ordinary Serial data/auth boundaries failed: ' + '; '.join(errors))
        basic_path = args.output / 'basic/guest-results.jsonl'
        basic_path.write_text(basic)
        report['scenarios']['basic'].update(guest_results=str(basic_path), guest_sha256=digest(basic_path),
            host_results=str(echo_path), host_sha256=digest(echo_path), case_count=19, status='pass')
        device(False, 'basic-host-disconnect-actual-USB-detach')
        nonce = secrets.token_hex(16)
        build_install('attachment', nonce)
        journal_path = args.output / 'attachment/host-attachment.jsonl'
        journal = journal_path.open('x')
        control = AttachmentControl(endpoint, nonce, journal)
        control.record('begin', True)
        control.attach()
        device(True, 'attachment-original')
        launch()
        result('serial-attachment-results.log', 'begin', 'attachment-ready')
        report['ui_actions'].append(ui.click(BUNDLE, identifier='serial-attachment-next', label='open-pending-unplug'))
        dialog('allowButton', 'original-trusted-request-before-unplug', click=False)
        control.detach()
        device(False, 'unplug-while-real-authorization-pending')
        result('serial-attachment-results.log', 'unplug_pending_open', 'pending-request-device-gone')
        control.attach()
        device(True, 'replacement-identical-public-USB-tuple')
        report['ui_actions'].append(ui.click(BUNDLE, identifier='serial-attachment-next', label='deny-replacement'))
        dialog('notAllowButton', 'replacement-new-trusted-deny')
        result('serial-attachment-results.log', 'deny_replacement', 'replacement-not-silently-authorized')
        report['ui_actions'].append(ui.click(BUNDLE, identifier='serial-attachment-next', label='allow-replacement'))
        dialog('allowButton', 'replacement-new-trusted-allow')
        result('serial-attachment-results.log', 'raw_node_denied_after_grant', 'replacement-live-ordinary-port')
        control.detach()
        device(False, 'detach-live-open-port')
        result('serial-attachment-results.log', 'write_stale_object', 'disconnect-callback-and-stale-write')
        control.attach()
        device(True, 'replug-same-physical-public-tuple')
        report['ui_actions'].append(ui.click(BUNDLE, identifier='serial-attachment-next', label='deny-after-replug'))
        dialog('notAllowButton', 'replug-new-trusted-deny')
        result('serial-attachment-results.log', 'deny_replug', 'prior-grant-not-inherited')
        report['ui_actions'].append(ui.click(BUNDLE, identifier='serial-attachment-next', label='allow-after-replug'))
        dialog('allowButton', 'replug-new-trusted-allow')
        attachment = result('serial-attachment-results.log', 'completed', 'attachment-completed')
        errors = verify_attachment(rows(attachment), nonce, BUNDLE, PORT)
        if errors:
            raise ValueError('real ordinary Serial attachment boundaries failed: ' + '; '.join(errors))
        attachment_path = args.output / 'attachment/guest-results.jsonl'
        attachment_path.write_text(attachment)
        control.detach()
        control.record('quit', True)
        journal.close()
        report['scenarios']['attachment'].update(guest_results=str(attachment_path),
            guest_sha256=digest(attachment_path), host_results=str(journal_path),
            host_sha256=digest(journal_path), case_count=15, status='pass')
        device(False, 'final-own-endpoint-detached')
        run_usb_manager_cases(args, environment, report, endpoint, ui, command, dialog, device,
                              same_boot, build_install, launch, result)
        same_boot('after')
        report.update(status='pass', kernel_boot_id_unchanged=True,
                      no_raw_node_permission_changes=True, no_authorization_IPC_shortcut=True)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        if control is not None and control.connection is not None:
            try:
                control.detach('cleanup_detach')
            except OSError as error:
                report['failures'].append('owned attachment cleanup failed: ' + str(error))
                report['status'] = 'fail'
        if journal is not None and not journal.closed:
            journal.close()
        if echo is not None and echo.poll() is None:
            os.killpg(echo.pid, signal.SIGTERM)
            try:
                echo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(echo.pid, signal.SIGKILL)
                echo.wait()
        if echo_log is not None and not echo_log.closed:
            echo_log.close()
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--hdc', required=True)
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'failures': result['failures']}))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
