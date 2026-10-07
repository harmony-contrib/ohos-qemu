#!/usr/bin/env python3
"""Build/sign/run one fresh ordinary-app regression on an already booted guest.

Never boots a guest, substitutes libraries, grants permissions or attests the
whole first-artifact gate. The enclosing boot suite must bind this to its VM.
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

from guest_ui import GuestUi, select_node
from vulkan_frame_capture import capture_presented_frame

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_first_artifact_gate import checksum

BUNDLE = 'org.harmonycontrib.capabilityaudit'
APP_BASE = '/data/app/el2/100/base/' + BUNDLE + '/'
APP_FILES = APP_BASE + 'files/'
PERSONAS = {
    'web': ('--web-only', 'capability-results.log', 'web.execution.complete=true', 'verify_web_results.py'),
    'userid': ('--userid-only', 'userid-results.log', '"native_result"', 'verify_userid_results.py'),
    'i18n': ('--i18n-only', 'i18n-data-{run}-results.log', '"parameter.missing"', 'verify_i18n_data.py'),
    'matrix4': ('--matrix4-only', 'matrix4-{run}-results.log', '"summary"', 'verify_matrix4_results.py'),
    'factory-objects': ('--factory-objects-only', 'factory-objects-{run}-results.log', '"summary"',
                        'verify_factory_objects_results.py'),
    'const-enum': ('--const-enum-only', 'const-enum-{run}-results.log', '"summary"', 'verify_const_enum_results.py'),
    'contact-sync-mode': ('--contact-sync-mode-only', 'contact-sync-mode-{run}-results.log', '"native"',
                          'verify_contact_sync_mode_results.py'),
    'arkts-exports': ('--arkts-exports-only', 'arkts-exports-{run}-results.log',
                      '"export_collection_complete":true', 'verify_arkts_exports_results.py'),
    'audio-stream': ('--audio-stream-only', 'audio-stream-{run}-results.log', '"summary"', 'verify_audio_stream_results.py'),
    'avc-media': ('--avc-media-only', 'avc-media-{run}-results.log', '"summary"', 'verify_avc_media_results.py'),
    'audio-suite-effects': ('--audio-suite-effects-only', 'audio-suite-effects-{run}-results.log', '"summary"',
                            'verify_audio_suite_effects_results.py'),
    'vulkan-window': ('--vulkan-window-only', 'vulkan-window-results.log', 'generation=1', 'verify_vulkan_window.py'),
    'worker-legacy': ('--worker-legacy-only', 'worker-legacy-{run}-results.log', '"summary"', 'verify_worker_results.py'),
    'worker-thread': ('--worker-thread-only', 'worker-thread-{run}-results.log', '"summary"', 'verify_worker_results.py'),
    'camera': ('--camera-only', 'camera-arkts-{run}-results.log', '"arkts_complete"', 'verify_camera_results.py'),
}


def require_normal_identity(text, bundle=BUNDLE):
    prefix = bundle + ':\n'
    if text.startswith(prefix):
        text = text[len(prefix):]
    info = json.loads(text)['applicationInfo']
    if (info.get('appPrivilegeLevel') != 'normal' or info.get('isSystemApp') is not False or
            type(info.get('uid')) is not int or info['uid'] // 200000 != 100 or info['uid'] % 200000 < 10000):
        raise ValueError('probe must be an ordinary non-system app in account 100')
    return info['uid']


def previous_probe_absent(pids, abilities):
    """Check the real kernel and AA records, not a successful stop reply alone."""
    if pids.strip() != 'ABSENT':
        if re.fullmatch(r'[1-9][0-9]*(?:\s+[1-9][0-9]*)*', pids.strip()) is None:
            raise ValueError('invalid actual audit process observation')
        return False
    if not re.search(r'^User ID #100\s*$', abilities, re.M) or 'AppRunningRecords:' not in abilities:
        raise ValueError('actual account-100 ability/process dump missing')
    # Include native subprocesses and pending ability records belonging only
    # to our bundle. A similarly prefixed, unrelated bundle is not ours.
    return re.search(r'(?<![A-Za-z0-9_.])' + re.escape(BUNDLE) +
                     r'(?=$|[^A-Za-z0-9_.])', abilities) is None


def result_directory(persona):
    # Camera uses a UIAbility (module) context; the other probes explicitly
    # use the application context. Do not confuse these two private sandboxes.
    return APP_BASE + 'haps/entry/files/' if persona == 'camera' else APP_FILES


def stop_previous_probe(shell, *, clock=time.monotonic, sleep=time.sleep):
    """Drain our previous test application before replacing its HAP."""
    reply = shell('aa force-stop ' + BUNDLE, 'stop-own-previous-audit-app', accepted_failure=True).strip()
    stopped = reply == 'force stop process successfully.'
    not_installed = ('error: failed to force stop process.' in reply and
                     'Error Code:10104002' in reply and
                     'The application corresponding to the specified package name is not installed.' in reply)
    if not stopped and not not_installed:
        raise ValueError('AA did not confirm stopping our previous audit app')
    deadline = clock() + 30
    observations = 0
    consecutive = 0
    while clock() < deadline:
        pids = shell('task_probe_pids=$(pidof ' + BUNDLE + '); '
                     'if test -n "$task_probe_pids"; then printf "%s\\n" "$task_probe_pids"; '
                     'else echo ABSENT; fi', 'previous-own-kernel-processes')
        abilities = shell('aa dump -a -u 100', 'previous-own-ability-and-process-records')
        observations += 1
        consecutive = consecutive + 1 if previous_probe_absent(pids, abilities) else 0
        if consecutive >= 2:
            return {'scope': 'bounded_own_test_bundle_lifecycle_setup_NOT_capability_pass',
                    'bundle': BUNDLE, 'stop_reply': reply, 'observations': observations,
                    'consecutive_absent_observations': consecutive,
                    'kernel_process_absent': True, 'ability_process_records_absent': True}
        sleep(0.25)
    raise ValueError('previous audit app lifecycle did not drain before replacement')


def verifier_arguments(persona, archive, results, identity, run_id, arch, output):
    arguments = ['--archive', str(archive), '--output', str(output)] if persona != 'web' else ['--output', str(output)]
    arguments += ['--arkts-results' if persona == 'camera' else
                  '--log' if persona in ('web', 'userid') else '--results', str(results)]
    if persona not in ('web', 'vulkan-window'):
        arguments += ['--run-id', run_id]
    if persona == 'userid':
        arguments += ['--arch', arch, '--mode', 'unprivileged', '--expected-user-id', '100',
                      '--app-context', '--probe-exit-code', '0']
    if persona in ('const-enum', 'arkts-exports', 'matrix4', 'factory-objects', 'camera', 'contact-sync-mode'):
        arguments += ['--arch', arch]
    if persona in ('audio-stream', 'avc-media', 'audio-suite-effects', 'worker-legacy', 'worker-thread', 'matrix4', 'factory-objects', 'camera', 'contact-sync-mode'):
        arguments += ['--application-identity', str(identity)]
    if persona in ('worker-legacy', 'worker-thread'):
        arguments += ['--mode', persona.removeprefix('worker-')]
    return arguments


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    challenge = secrets.token_hex(16)
    report = {'schema_version': 1, 'status': 'fail', 'scope': 'one_fresh_ordinary_HAP_regression_NOT_full_gate',
        'persona': args.persona, 'run_id': challenge, 'archive': str(args.archive.resolve()),
        'target': args.target, 'arch': args.arch, 'commands': [], 'failures': [],
        'boot_binding': 'requires_enclosing_fresh_VM_suite', 'first_artifact_behavior_gate_passed': False}

    def command(argv, label, timeout=60, accepted_failure=False):
        argv = list(map(str, argv))
        path = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        record = {'argv': argv, 'log': str(path), 'exit_code': None}
        report['commands'].append(record)
        try:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout, stderr = process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate()
                path.write_text(stdout + stderr)
                record.update(timed_out=True, sha256=checksum(path))
                raise ValueError('command timed out: ' + label)
            record['exit_code'] = process.returncode
            path.write_text(stdout + stderr)
            record['sha256'] = checksum(path)
            if process.returncode and not accepted_failure:
                raise ValueError('command failed: ' + label)
            if argv[0] == str(args.hdc) and not accepted_failure and re.search(
                    r'\[Fail\]|Device not found or connected', stdout):
                raise ValueError('HDC did not execute the requested operation: ' + label)
            return stdout.replace('\r', '')
        except OSError as error:
            record['launch_error'] = str(error)
            raise

    def shell(script, label, accepted_failure=False):
        return command([args.hdc, '-t', args.target, 'shell', script], label, accepted_failure=accepted_failure)

    try:
        report['archive_sha256'] = checksum(args.archive)
        report['test_sdk_components'] = {}
        for name in ('native', 'ets'):
            metadata_path = args.sdk / name / 'oh-uni-package.json'
            metadata = json.loads(metadata_path.read_text())
            # Test SDK patch releases need not equal the OS build number. Keep
            # the actual API26 Release identity, not a hard-coded tool version.
            if (metadata.get('apiVersion') != '26' or metadata.get('platformVersion') != '26.0.0'
                    or metadata.get('releaseType') != 'Release'
                    or re.fullmatch(r'26\.0\.0\.[0-9]+', metadata.get('version', '')) is None):
                raise ValueError('ordinary regression requires a real API26 Release test SDK: ' + name)
            report['test_sdk_components'][name] = {'metadata': metadata, 'metadata_sha256': checksum(metadata_path)}
        identity = shell('id -u; param get const.product.devicetype; uname -m', 'guest-identity')
        expected_cpu = {'arm64': 'aarch64', 'armv7a': 'armv7l', 'x86_64': 'x86_64'}[args.arch]
        if identity.split() != ['0', args.device, expected_cpu]:
            raise ValueError('wrong connected guest role/profile/architecture')
        report['guest_identity'] = identity
        boot_id = shell('cat /proc/sys/kernel/random/boot_id', 'actual-boot-id-before').strip()
        if re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot_id) is None:
            raise ValueError('actual guest kernel boot ID missing')
        if getattr(args, 'boot_id', None) is not None and args.boot_id != boot_id:
            raise ValueError('ordinary probe is not connected to the enclosing fresh VM')
        report['boot_id'] = boot_id
        flag, filename, completion, verifier = PERSONAS[args.persona]
        project = args.output / 'project'
        build = [sys.executable, str(Path(__file__).with_name('build_hap_probe.py')), flag,
                 '--arch', args.arch, '--sdk', args.sdk, '--udid', args.udid, '--output', project]
        if args.persona not in ('web', 'vulkan-window'):
            build += ['--probe-run-id', challenge]
        command(build, 'build-fresh-hap', timeout=1800)
        unsigned = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
        signed = args.output / 'ordinary-probe-signed.hap'
        relative_unsigned = unsigned.relative_to(args.output).as_posix()
        sign = ['docker', 'run', '--rm', '--platform', 'linux/amd64',
            '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(args.output.resolve()) + ',dst=/probe',
            args.docker_image, 'python3', '/work/ci/capability-audit/sign_web_probe.py',
            '--signer-dist', '/ohos/developtools/hapsigner/dist',
            '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
            '--unsigned', '/probe/' + relative_unsigned, '--output', '/probe/' + signed.name,
            '--bundle-name', BUNDLE, '--udid', args.udid, '--sign-code', '1']
        command(sign, 'docker-sign-and-verify', timeout=300)
        report['hap_sha256'] = checksum(signed)
        # Only our dedicated audit bundle is stopped/replaced. A successful
        # uninstall alone can leave asynchronous old-session teardown queued
        # against the next app with the same bundle name.
        report['previous_app_cleanup'] = stop_previous_probe(shell)
        if shell('cat /proc/sys/kernel/random/boot_id', 'boot-id-after-own-app-cleanup').strip() != boot_id:
            raise ValueError('guest kernel changed during own-app cleanup')
        # Uninstall so no old app file or renderer can satisfy the fresh run.
        command([args.hdc, '-t', args.target, 'uninstall', BUNDLE], 'remove-own-previous-audit-app', accepted_failure=True)
        installed = command([args.hdc, '-t', args.target, 'install', signed], 'install-ordinary-hap')
        if re.search(r'\[Fail\]|failed to install', installed, re.I) or not re.search(r'success', installed, re.I):
            raise ValueError('HDC did not report actual HAP installation success')
        identity_text = shell('bm dump -n ' + BUNDLE, 'ordinary-application-identity')
        report['ordinary_uid'] = require_normal_identity(identity_text)
        application_identity = args.output / 'application-identity.json'
        application_identity.write_text(identity_text)
        app_files = result_directory(args.persona)
        report['ordinary_result_directory'] = app_files
        remote = app_files + filename.format(run=challenge)
        stale = shell('if test -e ' + shlex.quote(remote) + '; then echo STALE; else echo ABSENT; fi', 'result-absent-before-launch')
        if stale.strip() != 'ABSENT':
            raise ValueError('pre-existing result is not a fresh app execution')
        # A single requested wake is ordinary test setup, never a periodic
        # external QMP keepalive and never proof of unattended boot.
        shell('power-shell wakeup', 'single-test-wakeup')
        launched = shell('aa start -a EntryAbility -b ' + BUNDLE, 'launch-ordinary-app')
        if not re.search(r'start ability successfully', launched, re.I):
            raise ValueError('ordinary ability did not launch successfully')
        def poll_result(marker):
            deadline = time.monotonic() + args.wait_seconds
            while time.monotonic() < deadline:
                value = shell('cat ' + shlex.quote(remote) + ' 2>/dev/null', 'poll-own-result', accepted_failure=True)
                if marker in value and value.endswith('\n'):
                    return value
                time.sleep(2)
            raise ValueError('actual application regression did not complete before timeout')

        ui_arguments = []
        if args.persona == 'camera':
            from camera_package_capture import allow_camera, live_captures, receive_photos
            from camera_probe_contract import verify_inputs
            labels_text = command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly',
                '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
                args.docker_image, 'python3', '/work/ci/capability-audit/camera_probe_contract.py',
                '--source-root', '/ohos'], 'actual-trusted-camera-dialog-labels', timeout=120)
            labels = json.loads(labels_text)
            labels_file = args.output / 'permission-labels.json'
            labels_file.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + '\n')
            ui = GuestUi(command, args.hdc, args.target, args.output / 'ui')
            action = allow_camera(ui, labels, min(args.wait_seconds, 120))
            action['layout_sha256'] = checksum(Path(action['layout']))
            report['camera_permission_action'] = action
            report.update(camera_permission_labels=str(labels_file), camera_permission_labels_sha256=checksum(labels_file))
            captures = live_captures(ui, shell, remote, BUNDLE, challenge, args.wait_seconds)
            for capture in captures:
                capture['layout_sha256'] = checksum(Path(capture['layout']))
                capture['screenshot_sha256'] = checksum(Path(capture['screenshot']))
            capture_file = args.output / 'camera-captures.json'
            capture_file.write_text(json.dumps(captures, indent=2) + '\n')
            report.update(camera_captures=str(capture_file), camera_captures_sha256=checksum(capture_file))
            inputs = project / 'camera-probe-inputs.json'
            verify_inputs(json.loads(inputs.read_text()), project, challenge, args.arch)
            report.update(compiled_contract_inputs=str(inputs), compiled_contract_inputs_sha256=checksum(inputs))
            native_results = args.output / 'native-results.log'
            native_remote = app_files + 'camera-native-' + challenge + '-results.log'
            native_results.write_text(shell('cat ' + shlex.quote(native_remote), 'actual-native-camera-result'))
            report['camera_native_results_sha256'] = checksum(native_results)
            # Photos only exist after the complete ArkTS sequence, below.
            ui_arguments += ['--native-results', str(native_results), '--captures', str(capture_file)]
        result = poll_result(completion)
        if args.persona == 'camera':
            photo_root = receive_photos(command, args.hdc, args.target, app_files, args.output, challenge)
            ui_arguments += ['--photo-root', str(photo_root)]
        if args.persona == 'vulkan-window':
            ui = GuestUi(command, args.hdc, args.target, args.output / 'ui')
            captures = []
            report['presentation_attempts'] = []
            for generation in (1, 2):
                if generation == 2:
                    report['surface_destroy_action'] = ui.click(BUNDLE, identifier='qemu-vulkan-lifecycle',
                                                               label='destroy-surface')
                    poll_result('vulkan_window.destroyed|')
                    report['surface_recreate_action'] = ui.click(BUNDLE, identifier='qemu-vulkan-lifecycle',
                                                                label='recreate-surface')
                    result = poll_result('generation=2')
                capture = capture_presented_frame(ui, BUNDLE, generation, result,
                    report['presentation_attempts'], checksum)
                captures.append(capture)
                prefix = '--initial' if generation == 1 else '--recreated'
                ui_arguments += [prefix + '-screenshot', capture['screenshot'],
                                 prefix + '-rect', ','.join(map(str, capture['selected_node']['rect']))]
            report['actual_surface_captures'] = captures
        results = args.output / 'results.log'
        results.write_text(result)
        verification = args.output / 'verified-result.json'
        if args.persona in ('const-enum', 'arkts-exports', 'worker-legacy', 'worker-thread', 'matrix4', 'factory-objects', 'contact-sync-mode'):
            inputs = project / (args.persona + '-probe-inputs.json')
            report.update(compiled_contract_inputs=str(inputs), compiled_contract_inputs_sha256=checksum(inputs))
            ui_arguments += ['--inputs', str(inputs)]
            if args.persona in ('worker-legacy', 'worker-thread'):
                ui_arguments += ['--arch', args.arch]
        command([sys.executable, str(Path(__file__).with_name(verifier)),
                 *verifier_arguments(args.persona, args.archive, results, application_identity,
                     challenge, args.arch, verification), *ui_arguments], 'strict-behavior-verification')
        if json.loads(verification.read_text()).get('status') != 'pass':
            raise ValueError('strict ordinary-app verifier did not pass')
        if shell('cat /proc/sys/kernel/random/boot_id', 'actual-boot-id-after').strip() != boot_id:
            raise ValueError('guest rebooted or changed while the ordinary probe was running')
        report.update(status='pass', result=str(verification), result_sha256=checksum(verification),
                      raw_results_sha256=checksum(results), ordinary_identity_sha256=checksum(application_identity))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
        # Preserve the cause before the enclosing suite closes its private VM.
        # Never clear shared buffers, modify policy or turn diagnostics into a
        # behavior pass. A disconnected/different guest is not queried further.
        if 'boot_id' in report:
            try:
                if shell('cat /proc/sys/kernel/random/boot_id', 'failure-capture-boot-id').strip() != report['boot_id']:
                    raise ValueError('failure diagnostics refused a changed guest kernel')
                shell('hilog -x', 'failure-actual-hilog')
                shell('ps -ef', 'failure-actual-processes')
                report['same_boot_failure_diagnostics_captured'] = True
            except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as capture_error:
                report['failure_diagnostics_error'] = str(capture_error)
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--udid', required=True)
    parser.add_argument('--persona', choices=tuple(PERSONAS), required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--boot-id', help='actual boot ID supplied by the enclosing owned-VM suite')
    parser.add_argument('--hdc', default='hdc')
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    parser.add_argument('--wait-seconds', type=int, choices=range(60, 1801), default=300)
    args = parser.parse_args()
    if re.fullmatch('[0-9A-Fa-f]{64}', args.udid) is None:
        parser.error('actual guest UDID must be 64 hex digits')
    report = run(args)
    print(json.dumps({'persona': report['persona'], 'status': report['status'], 'failures': report['failures']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
