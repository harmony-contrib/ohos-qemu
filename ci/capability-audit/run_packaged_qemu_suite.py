#!/usr/bin/env python3
"""Run local package-bound probes on one privately owned, freshly booted VM.

The full audit closure is mandatory: successful boot/browser/graphics/bindings
samples alone cannot turn all audited C++/ArkTS 1.1 gaps into verified passes.
Only this enclosing suite may bind child results to the archive and boot ID.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile

from boot_package import QemuGuest
from batch_probe_policy import independent_probe
from collect_backend_inventory import collect as collect_backend_inventory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_first_artifact_gate import checksum, verify
from power_test_policy import power_timeout, verify_restoration


def unused_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def test_sdk():
    configured = os.environ.get('QEMU_TEST_SDK_HOME') or os.environ.get('OHOS_SDK_HOME')
    candidates = [Path(configured)] if configured else []
    candidates += [ROOT.parent.parent.parent / 'qemu/validation/first-20261005/provider-sdk-26-full/26.0.0',
                   Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0'),
                   Path('/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony')]
    for candidate in candidates:
        try:
            metadata = json.loads((candidate / 'native/oh-uni-package.json').read_text())
        except (OSError, ValueError):
            continue
        if metadata.get('apiVersion') == '26' and metadata.get('releaseType') == 'Release':
            return candidate.resolve()
    raise ValueError('set QEMU_TEST_SDK_HOME to a real host-compatible API26 Release SDK')


def run(args):
    args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=args.package_archive.name.removesuffix('.tar.gz') + '-runtime-',
                                 dir=args.evidence_output.parent))
    report = {'schema_version': 2, 'status': 'fail', 'scope': 'new_packaged_qemu_behavior',
        'first_artifact_behavior_gate_passed': False, 'checks': {}, 'commands': [],
        'failures': [], 'started_utc': datetime.now(timezone.utc).isoformat(), 'work': str(work)}
    guest = None
    screen_timeout_override = False
    checks_complete = False

    def save():
        args.evidence_output.write_text(json.dumps(report, indent=2) + '\n')

    def command(argv, label, timeout=600, env=None):
        argv = list(map(str, argv))
        log = work / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        record = {'argv': argv, 'exit_code': None, 'log': str(log)}
        report['commands'].append(record)
        with log.open('w') as stream:
            process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, env=env)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                record.update(timed_out=True, sha256=checksum(log))
                raise ValueError('owned suite command timed out: ' + label) from error
        record.update(exit_code=process.returncode, sha256=checksum(log))
        if process.returncode:
            raise ValueError('actual suite command failed: ' + label)
        return record

    def check(name, path, commands):
        document = json.loads(path.read_text())
        if document.get('status') != 'pass':
            raise ValueError('actual child behavior verifier failed: ' + name)
        report['checks'][name] = {'status': 'pass', 'evidence': str(path),
            'sha256': checksum(path), 'commands': commands}
        save()

    def same_guest(label):
        guest.healthy()
        guest.wake_for_interaction(label)
        if 'boot' in report['checks']:
            report['checks']['boot']['sha256'] = checksum(work / 'boot/boot.json')
        if guest.shell('cat /proc/sys/kernel/random/boot_id', label + '-boot-id').strip() != guest.report[
                'test_environment']['boot_id']:
            raise ValueError('suite is no longer using the exact fresh package VM')

    try:
        hdc = shutil.which(os.environ.get('HDC', 'hdc'))
        if hdc is None:
            fallback = Path('/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc')
            hdc = str(fallback) if fallback.is_file() else None
        if hdc is None:
            raise ValueError('an actual HDC executable is required')
        sdk = test_sdk()
        port = int(os.environ.get('QEMU_TEST_HDC_PORT', unused_port()))
        boot_args = argparse.Namespace(archive=args.package_archive, output=work / 'boot', hdc=hdc,
            hdc_port=port, accel=os.environ.get('QEMU_TEST_ACCEL', 'auto'), resolution='1280x800',
            purpose='acceptance', wait_seconds=1800, stable_seconds=60,
            kernel_diagnostic=None, power_diagnostic_wakeup=False, hold=False)
        guest = QemuGuest(boot_args).start()
        environment = guest.report['test_environment']
        report.update(package={'archive': str(args.package_archive.resolve()),
            'sha256': guest.report['archive_sha256'],
            'build_inputs_tree_sha256': guest.report['build_inputs_tree_sha256']},
            test_environment=environment)
        check('boot', work / 'boot/boot.json', [{'argv': guest.report['qemu_launch_argv'], 'exit_code': 0}])
        if args.package_directory and args.package_directory.name != guest.directory.name:
            raise ValueError('matrix directory does not match actual archive extraction')
        backup_record = command([sys.executable, Path(__file__).with_name('run_backup_init_probe.py'),
            '--archive', args.package_archive, '--boot', work / 'boot/boot.json',
            '--output', work / 'backup-init'], 'actual-backup-SA-init-and-exec')
        check('backup-init', work / 'backup-init/evidence.json', [backup_record])
        profile_record = command([sys.executable, Path(__file__).with_name('run_boot_profile_probe.py'),
            '--archive', args.package_archive, '--boot', work / 'boot/boot.json',
            '--output', work / 'boot-profile', '--docker-image',
            os.environ.get('QEMU_TEST_DOCKER_IMAGE', 'ohos-qemu-m144-build-env:7.0-release')],
            'actual-image-and-boot-profile-boundaries', timeout=300)
        check('boot-profile', work / 'boot-profile/evidence.json', [profile_record])
        power_record = command([sys.executable, Path(__file__).with_name('run_power_suspend_probe.py'),
            '--boot', work / 'boot/boot.json', '--output', work / 'power-suspend', '--hdc', hdc],
            'default-policy-real-suspend-wake-compositor', timeout=300)
        check('power-suspend', work / 'power-suspend/evidence.json', [power_record])
        # A real wake leaves the ordinary lock screen active. Let that screen
        # restore its own policy through a real gesture before taking our own
        # finite test override. Never restore another client's override.
        home_record = command([sys.executable, Path(__file__).with_name('run_application_home_probe.py'),
            '--boot', work / 'boot/boot.json', '--output', work / 'application-home', '--hdc', hdc],
            'real-system-home-before-test-policy', timeout=180)
        check('application-home', work / 'application-home/evidence.json', [home_record])
        # Boot's no-input sleep/key-wake check already finished with the real
        # default policy. Application compilation/tests may take hours. Use
        # the existing development test API (not recurring input or a kernel
        # bypass), record it separately and always restore on this owned VM.
        report['application_test_setup'] = {'screen_timeout_ms': 86400000,
            'method': 'existing_power-shell_development_override',
            'after_unassisted_default_policy_boot_validation': True,
            'not_default_power_policy_acceptance': True, 'restored': False, 'policy_states': {}}
        policy = report['application_test_setup']['policy_states']
        policy['before'] = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'app-test-power-before'))
        if policy['before']['override_ms'] is not None:
            raise ValueError('refuse to replace another client\'s existing PowerMgr override')
        screen_timeout_override = True  # Also restore if the setup reply is lost.
        setup = guest.shell('power-shell timeout -o 86400000', 'finite-app-test-screen-timeout-override')
        if setup.strip() != 'Override screen off time to 86400000':
            raise ValueError('real PowerMgr rejected the development-test timeout override')
        policy['setup'] = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'app-test-power-setup'))
        if policy['setup'] != dict(policy['before'], override_ms=86400000):
            raise ValueError('actual PowerMgr did not retain the finite timeout and original backup')
        arch, device, target = guest.arch, guest.device, guest.target
        collect_backend_inventory(guest, work / 'backend-inventory', report['package']['sha256'],
                                  environment['boot_id'])
        inventory_path = work / 'backend-inventory/inventory.json'
        report['backend_inventory'] = {'evidence': str(inventory_path),
            'sha256': checksum(inventory_path), 'not_a_behavior_check': True}
        save()
        from parallel_runtime_suite import (FAMILIES, TIMEOUTS, argv as capability_argv,
            boot_copy, load_plan, representative, verify_family)
        if representative(environment):
            capability_plan = None
            plan_error = None
            try:
                configured = os.environ.get('QEMU_TEST_CAPABILITY_INPUTS')
                capability_plan = load_plan(Path(configured) if configured else None, environment)
                report['capability_inputs'] = {'path': str(Path(configured).resolve()),
                    'sha256': checksum(Path(configured)), 'scope': 'prebuilt_inputs_NOT_behavior_evidence'}
            except (OSError, ValueError, KeyError, TypeError) as error:
                plan_error = str(error)
            for family in FAMILIES:
                output = work / family
                previous_command_count = len(report['commands'])
                def capability_health(label):
                    same_guest(label)
                    if label.startswith('after-') and len(report['commands']) > previous_command_count:
                        if report['commands'][-1].get('timed_out'):
                            raise ValueError('timed-out capability child cleanup is not certified; stop batch')
                        evidence = output / 'evidence.json'
                        if not evidence.is_file():
                            raise ValueError('capability child cleanup evidence missing; stop batch: ' + family)
                        child = json.loads(evidence.read_text())
                        if child.get('cleanup_complete') is not True or child.get('cleanup_errors'):
                            raise ValueError('owned capability cleanup failed; stop batch: ' + family)
                with independent_probe(report, family, capability_health, save):
                    if capability_plan is None:
                        raise ValueError('real capability inputs unavailable: ' + str(plan_error))
                    # Wake records may change the parent's boot.json later.
                    # Keep the actual qemu.log directory and freeze this boot's bytes.
                    guest.save()
                    stable_boot = boot_copy(work / 'boot/boot.json', work / 'boot' / (family + '-boot.json'))
                    save()  # Wallpaper verifies the current owner's finite power override.
                    record = command(capability_argv(family, capability_plan, stable_boot,
                        args.package_archive, hdc, output, args.evidence_output),
                        'actual-' + family + '-complete-boundaries', timeout=TIMEOUTS[family])
                    verify_family(family, output / 'evidence.json', args.package_archive, environment)
                    check(family, output / 'evidence.json', [record])
        native_definitions = guest.directory / 'native-gap-abi-image.json'
        native_abi_probe = work / 'native-gap-abi-build'
        command([sys.executable, Path(__file__).with_name('build_native_gap_abi_probe.py'),
            '--sdk', sdk / 'native', '--definitions', native_definitions, '--arch', arch,
            '--device', device, '--output', native_abi_probe], 'build-actual-whole-Native-ABI-caller')
        native_abi_record = command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
            '--kind', 'native-gap-abi', '--archive', args.package_archive,
            '--probe', native_abi_probe / 'native-gap-abi', '--definitions', native_definitions,
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--boot-evidence', work / 'boot/boot.json',
            '--output', work / 'native-gap-abi'],
            'actual-system-DSO-whole-Native-ABI', timeout=300)
        check('native-gap-abi', work / 'native-gap-abi/result.json', [native_abi_record])
        source_volume = os.environ.get('DOCKER_SOURCE_VOLUME', 'ohos-qemu-7_0-release-source')
        docker_image = os.environ.get('QEMU_TEST_DOCKER_IMAGE', 'ohos-qemu-m144-build-env:7.0-release')
        child_env = dict(os.environ, OHOS_SDK=str(sdk / 'native'), HDC=hdc)
        same_guest('before-HUKS-compatibility')
        huks_record = command([sys.executable, Path(__file__).with_name('run_huks_compatibility_probe.py'),
            '--archive', args.package_archive, '--boot', work / 'boot/boot.json',
            '--output', work / 'huks-compatibility', '--hdc', hdc, '--docker-image', docker_image],
            'actual-HUKS-init-and-owned-legacy-migration', timeout=300, env=child_env)
        check('huks-compatibility', work / 'huks-compatibility/evidence.json', [huks_record])
        same_guest('after-HUKS-compatibility')
        kernel_probes = work / 'kernel-probes'
        command(['bash', Path(__file__).with_name('build_access_token_probe.sh'),
                 '--arch', arch, '--output', kernel_probes],
                'build-real-kernel-ABI-and-BPF-probes', env=child_env)
        for kind, executable in (('bitmap', 'access_token_kernel'),
                                 ('userid', 'access_token_userid'), ('bpf', 'bpf_syscall')):
            same_guest('before-kernel-' + kind)
            command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
                '--kind', kind, '--archive', args.package_archive, '--probe', kernel_probes / executable,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--boot-evidence', work / 'boot/boot.json',
                '--output', work / ('kernel-' + kind)],
                'actual-kernel-' + kind + '-data-and-boundaries', env=child_env)
            same_guest('after-kernel-' + kind)
        binder_probes = work / 'binder-sender-probes'
        binder_probes.mkdir()
        command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
            '--mount', 'type=volume,src=' + source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(binder_probes) + ',dst=/probe',
            docker_image, 'python3', '/work/ci/capability-audit/build_binder_sender_probe.py',
            '--source-root', '/ohos', '--sdk', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/native',
            '--arch', arch, '--output', '/probe/build'],
            'compile-real-fixed-kernel-Binder-sender-probe', env=child_env)
        command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
            '--kind', 'binder-sender', '--archive', args.package_archive,
            '--probe', binder_probes / 'build/binder-async-sender',
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--boot-evidence', work / 'boot/boot.json',
            '--output', work / 'binder-sender'], 'actual-kernel-Binder-trusted-async-identity', env=child_env)
        same_guest('after-Binder-sender-boundaries')
        rs_probes = work / 'rs-object-probes'
        rs_probes.mkdir()
        rs_build = command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
            '--mount', 'type=volume,src=' + source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=volume,src=' + os.environ.get('DOCKER_OUT_VOLUME', 'ohos-qemu-7_0-release-out') +
                       ',dst=/ohos/out,readonly',
            '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(rs_probes) + ',dst=/probe',
            docker_image, 'python3', '/work/ci/capability-audit/build_rs_object_probe.py',
            '--source-root', '/ohos', '--arch', arch, '--output', '/probe/build'],
            'compile-caller-of-real-new-product-RS-IPC-libraries', env=child_env)
        rs_runtime = command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
            '--kind', 'rs-objects', '--archive', args.package_archive,
            '--probe', rs_probes / 'build/rs-object-encoding',
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--boot-evidence', work / 'boot/boot.json',
            '--output', work / 'rs-objects'], 'actual-packaged-RS-object-boundaries', env=child_env)
        check('rs-objects', work / 'rs-objects/result.json', [rs_build, rs_runtime])
        same_guest('after-RS-object-boundaries')
        screen_probes = work / 'screen-mode-probes'
        screen_probes.mkdir()
        screen_build = command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
            '--mount', 'type=volume,src=' + source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=volume,src=' + os.environ.get('DOCKER_OUT_VOLUME', 'ohos-qemu-7_0-release-out') +
                       ',dst=/ohos/out,readonly',
            '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(screen_probes) + ',dst=/probe',
            docker_image, 'python3', '/work/ci/capability-audit/build_screen_modes_probe.py',
            '--source-root', '/ohos', '--arch', arch, '--output', '/probe/build'],
            'compile-readonly-real-display-service-caller', env=child_env)
        screen_runtime = command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
            '--kind', 'screen-modes', '--archive', args.package_archive,
            '--probe', screen_probes / 'build/screen-modes-readback',
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--boot-evidence', work / 'boot/boot.json',
            '--output', work / 'screen-modes'], 'actual-packaged-display-mode-readback', env=child_env)
        check('screen-modes', work / 'screen-modes/result.json', [screen_build, screen_runtime])
        same_guest('after-display-mode-readback')
        quota_probes = work / 'project-quota-probes'
        quota_build = command([sys.executable, Path(__file__).with_name('build_project_quota_probe.py'),
            '--sdk', sdk / 'native', '--arch', arch, '--output', quota_probes],
            'compile-actual-SDK-project-quota-probe', env=child_env)
        quota_runtime = command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
            '--kind', 'project-quota', '--archive', args.package_archive,
            '--probe', quota_probes / 'project-quota-runtime',
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--boot-evidence', work / 'boot/boot.json',
            '--output', work / 'project-quota'], 'actual-packaged-unprivileged-EDQUOT-and-recovery', env=child_env)
        check('project-quota', work / 'project-quota/result.json', [quota_build, quota_runtime])
        same_guest('after-project-quota')
        audio_suite_probes = work / 'audio-suite-probes'
        command(['bash', Path(__file__).with_name('build_audio_suite_probe.sh'), arch, audio_suite_probes],
                'build-actual-public-AudioSuite-PCM-probe', env=child_env)
        command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
            '--kind', 'audio-suite', '--archive', args.package_archive,
            '--probe', audio_suite_probes / 'audio_suite', '--arch', arch, '--device', device,
            '--target', target, '--hdc', hdc, '--boot-id', environment['boot_id'],
            '--boot-evidence', work / 'boot/boot.json',
            '--output', work / 'audio-suite'], 'actual-AudioSuite-PCM-and-state', env=child_env)
        same_guest('after-AudioSuite-PCM')
        same_guest('before-system-exit')
        exit_probes = work / 'library-exit-probes'
        build = command([sys.executable, Path(__file__).with_name('build_library_exit_probes.py'),
            '--sdk', sdk / 'native', '--output', exit_probes, '--arch', arch], 'build-real-link-order-probes', env=child_env)
        runtime = command([sys.executable, Path(__file__).with_name('run_library_exit_probes.py'),
            '--probes', exit_probes, '--arch', arch, '--device', device, '--target', target,
            '--hdc', hdc, '--output', work / 'library-exit'], 'system-DSO-exit-regressions', env=child_env)
        check('issue20-library-exit', work / 'library-exit/result.json', [build, runtime])
        same_guest('after-system-exit')
        certificate_record = command([sys.executable, Path(__file__).with_name('run_certificate_probe.py'),
            '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--output', work / 'certificate-manager',
            '--source-volume', source_volume, '--docker-image', docker_image],
            'certificate-real-empty-import-cleanup-and-ordinary-denial', timeout=4800, env=child_env)
        check('certificate-manager', work / 'certificate-manager/evidence.json', [certificate_record])
        same_guest('after-certificate-both-roles')
        def photo_result_set_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'photo-result-set/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('photo query caller cleanup unproven; stop batch')
        with independent_probe(report, 'photo-result-set', photo_result_set_batch_health, save):
            photo_result_set_record = command([sys.executable, Path(__file__).with_name('run_photo_result_set_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'photo-result-set',
                '--source-volume', source_volume, '--docker-image', docker_image],
                'readonly-photo-query-typed-ResultSet-cursors-boundaries-and-three-roles', timeout=4800, env=child_env)
            check('photo-result-set', work / 'photo-result-set/evidence.json', [photo_result_set_record])
        # Policy mutation requires verified cleanup; failure cannot be treated
        # as independent from later networking probes.
        vpn_record = command([sys.executable, Path(__file__).with_name('run_always_on_vpn_probe.py'),
            '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--output', work / 'vpn-policy',
            '--source-volume', source_volume, '--docker-image', docker_image],
            'vpn-policy-three-roles-and-caller-restart', timeout=6000, env=child_env)
        check('vpn-policy', work / 'vpn-policy/evidence.json', [vpn_record])
        same_guest('after-vpn-policy-cleanup')
        def vpn_store_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'sys-vpn-store/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('system VPN store caller cleanup unproven; stop batch')
        with independent_probe(report, 'sys-vpn-store', vpn_store_batch_health, save):
            vpn_store_record = command([sys.executable, Path(__file__).with_name('run_sys_vpn_store_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'sys-vpn-store',
                '--source-volume', source_volume, '--docker-image', docker_image],
                'system-VPN-three-variant-CRUD-replacement-boundaries-restart-and-denials', timeout=6000, env=child_env)
            check('sys-vpn-store', work / 'sys-vpn-store/evidence.json', [vpn_store_record])
        # Actual global controls can briefly drop TCP HDC. Recovery must happen
        # inside the same permission-checked application, never a root override.
        ethernet_record = command([sys.executable, Path(__file__).with_name('run_ethernet_control_probe.py'),
            '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--output', work / 'ethernet-control',
            '--source-volume', source_volume, '--docker-image', docker_image],
            'Ethernet-three-roles-real-kernel-flags-repeated-control-and-caller-restart', timeout=6000, env=child_env)
        check('ethernet-control', work / 'ethernet-control/evidence.json', [ethernet_record])
        same_guest('after-Ethernet-policy-cleanup')
        def insight_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'insight-contract/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('intent caller/widget cleanup unproven; stop batch')
        with independent_probe(report, 'insight-contract', insight_batch_health, save):
            insight_record = command([sys.executable, Path(__file__).with_name('run_insight_contract_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'insight-contract',
                '--source-volume', source_volume, '--docker-image', docker_image],
                'seven-dynamic-intent-decorators-three-roles-real-dispatch-widgets-and-routes',
                timeout=6000, env=child_env)
            check('insight-contract', work / 'insight-contract/evidence.json', [insight_record])
        def lazy_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'lazy-column/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('lazy caller cleanup unproven; stop batch')
        with independent_probe(report, 'lazy-column', lazy_batch_health, save):
            lazy_record = command([sys.executable, Path(__file__).with_name('run_lazy_column_contract_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'lazy-column',
                '--hvigor-home', os.environ.get('QEMU_TEST_HVIGOR_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/hvigor'),
                '--node-home', os.environ.get('QEMU_TEST_NODE_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/node'),
                '--source-volume', source_volume, '--docker-image', docker_image],
                'typed-LazyColumn-native-scroll-reset-remove-and-recreate-stable-pixels',
                timeout=2400, env=child_env)
            check('lazy-column', work / 'lazy-column/evidence.json', [lazy_record])
        def lazy_layout_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'lazy-layouts/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('lazy layout caller cleanup unproven; stop batch')
        with independent_probe(report, 'lazy-layouts', lazy_layout_batch_health, save):
            lazy_layout_record = command([sys.executable, Path(__file__).with_name('run_lazy_layouts_contract_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'lazy-layouts',
                '--hvigor-home', os.environ.get('QEMU_TEST_HVIGOR_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/hvigor'),
                '--node-home', os.environ.get('QEMU_TEST_NODE_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/node'),
                '--source-volume', source_volume, '--docker-image', docker_image],
                'typed-waterflow-and-lazy-dynamic-real-algorithm-change-scroll-and-recreation',
                timeout=3000, env=child_env)
            check('lazy-layouts', work / 'lazy-layouts/evidence.json', [lazy_layout_record])
        def selection_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'selection/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('selection caller cleanup unproven; stop batch')
        with independent_probe(report, 'selection', selection_batch_health, save):
            selection_record = command([sys.executable, Path(__file__).with_name('run_selection_contract_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'selection',
                '--hvigor-home', os.environ.get('QEMU_TEST_HVIGOR_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/hvigor'),
                '--node-home', os.environ.get('QEMU_TEST_NODE_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/node'),
                '--source-volume', source_volume, '--docker-image', docker_image],
                'typed-selection-three-ordinary-roles-real-user-consent-copy-veto-join-and-recreation',
                timeout=3600, env=child_env)
            check('selection', work / 'selection/evidence.json', [selection_record])
        def env_reader_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'env-reader/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('environment/reader caller cleanup unproven; stop batch')
        with independent_probe(report, 'env-reader', env_reader_batch_health, save):
            env_reader_record = command([sys.executable, Path(__file__).with_name('run_env_reader_contract_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'env-reader',
                '--hvigor-home', os.environ.get('QEMU_TEST_HVIGOR_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/hvigor'),
                '--node-home', os.environ.get('QEMU_TEST_NODE_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/node'),
                '--source-volume', source_volume, '--docker-image', docker_image],
                'typed-WithEnv-inheritance-default-font-and-ContainerReader-native-equality-boundaries',
                timeout=3600, env=child_env)
            check('env-reader', work / 'env-reader/evidence.json', [env_reader_record])
        def settings_all_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'settings-all-navigation/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('complete Settings caller cleanup unproven; stop batch')
        with independent_probe(report, 'settings-all-navigation', settings_all_batch_health, save):
            settings_all_record = command([sys.executable, Path(__file__).with_name('run_settings_all_navigation_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'settings-all-navigation',
                '--hvigor-home', os.environ.get('QEMU_TEST_HVIGOR_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/hvigor'),
                '--node-home', os.environ.get('QEMU_TEST_NODE_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/node'),
                '--source-volume', source_volume, '--docker-image', docker_image],
                'typed-Settings-all-twelve-routes-two-rounds-profile-boundaries-provider-pixels-and-exit',
                timeout=6000, env=child_env)
            check('settings-all-navigation', work / 'settings-all-navigation/evidence.json', [settings_all_record])
        def child_default_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'child-default-profile/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or
                        child.get('caller_cleanup_verified') is not True):
                    raise ValueError('default child profile caller cleanup unproven; stop batch')
        with independent_probe(report, 'child-default-profile', child_default_batch_health, save):
            child_default_record = command([sys.executable, Path(__file__).with_name('run_child_default_profile_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'child-default-profile',
                '--hvigor-home', os.environ.get('QEMU_TEST_HVIGOR_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/hvigor'),
                '--node-home', os.environ.get('QEMU_TEST_NODE_HOME',
                    '/Applications/DevEco-Studio.app/Contents/tools/node'),
                '--source-volume', source_volume, '--docker-image', docker_image],
                'typed-default-child-C-ArkTS-parameters-config-boundaries-no-peer-and-actual-PID-exit',
                timeout=2400, env=child_env)
            check('child-default-profile', work / 'child-default-profile/evidence.json', [child_default_record])
        def blink_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'screen-blink/evidence.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or child.get('cleanup_verified') is not True):
                    raise ValueError('blink caller/window/settings cleanup unproven; stop batch')

        with independent_probe(report, 'screen-blink', blink_batch_health, save):
            blink_record = command([sys.executable, Path(__file__).with_name('run_screen_blink_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'screen-blink',
                '--source-volume', source_volume, '--docker-image', docker_image],
                'screen-blink-three-roles-real-pixels-and-cleanup', timeout=6000, env=child_env)
            check('screen-blink', work / 'screen-blink/evidence.json', [blink_record])
        def luminance_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                path = work / 'luminance-sampler/evidence.json'
                child = json.loads(path.read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or child.get('cleanup_verified') is not True):
                    raise ValueError('luminance caller cleanup unproven; stop batch')

        with independent_probe(report, 'luminance-sampler', luminance_batch_health, save):
            luminance_record = command([sys.executable, Path(__file__).with_name('run_luminance_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--output', work / 'luminance-sampler',
                '--source-volume', source_volume, '--docker-image', docker_image],
                'luminance-real-factory-RS-callbacks-and-unsubscription', timeout=3000, env=child_env)
            check('luminance-sampler', work / 'luminance-sampler/evidence.json', [luminance_record])
        def wifi_batch_health(label):
            same_guest(label)
            if label.startswith('after-'):
                child = json.loads((work / 'wifi-scan/diagnostic.json').read_text())
                if (child.get('archive_sha256') != report['package']['sha256'] or
                        child.get('boot_id') != environment['boot_id'] or child.get('cleanup_verified') is not True or
                        child.get('radio_restored') is not True or child.get('enclosing_guest_preserved') is not True or
                        child.get('power_restoration') != 'unchanged_enclosing_policy'):
                    raise ValueError('Wi-Fi radio/caller/power restoration unproven; stop batch')

        with independent_probe(report, 'wifi-scan', wifi_batch_health, save):
            wifi_record = command([sys.executable, Path(__file__).with_name('run_wifi_scan_diagnostic.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--boot', work / 'boot/boot.json',
                '--output', work / 'wifi-scan', '--hdc', hdc,
                '--source-volume', source_volume, '--docker-image', docker_image],
                'ordinary-WPA-radio-cycles-scans-and-real-bands', timeout=6000, env=child_env)
            check('wifi-scan', work / 'wifi-scan/diagnostic.json', [wifi_record])
        # The FA compatibility API requires a real FA service, not a Stage
        # caller impersonating one. Both models run on this unchanged archive.
        fa_record = command([sys.executable, Path(__file__).with_name('run_fa_particle_probe.py'),
            '--archive', args.package_archive, '--boot', work / 'boot/boot.json',
            '--output', work / 'fa-particle', '--sdk', sdk, '--hdc', hdc,
            '--hvigor-home', os.environ.get('QEMU_TEST_HVIGOR_HOME',
                '/Applications/DevEco-Studio.app/Contents/tools/hvigor'),
            '--node-home', os.environ.get('QEMU_TEST_NODE_HOME',
                '/Applications/DevEco-Studio.app/Contents/tools/node'),
            '--source-volume', source_volume, '--docker-image', docker_image],
            'ordinary-FA-service-constant-and-existing-calls', timeout=2400, env=child_env)
        check('fa-particle', work / 'fa-particle/evidence.json', [fa_record])
        same_guest('after-FA-service')
        # A denied generic audio error alone is ambiguous. Require actual PCM
        # controls on both sides of the real denied-token/UI case, all on this
        # unchanged newly packaged VM and with freshly installed normal callers.
        from verify_audio_capture_results import SCOPE as capture_scope, verify_batch as verify_capture_batch
        from verify_media_recorder_results import SCOPE as recorder_scope, verify_batch as verify_recorder_batch
        for persona, scope, verify_batch in (('audio-capture', capture_scope, verify_capture_batch),
                                              ('media-recorder', recorder_scope, verify_recorder_batch)):
            batch_path = work / (persona + '-batch.json')
            last_microphone_output = None
            def microphone_health(label):
                same_guest(label)
                if label.startswith('after-') and last_microphone_output is not None:
                    if report['commands'][-1].get('timed_out'):
                        raise ValueError('timed-out microphone child cleanup is not certified; stop batch')
                    path = last_microphone_output / 'evidence.json'
                    if path.is_file() and any('cleanup failed' in str(value) for value in json.loads(path.read_text()).get('failures', [])):
                        raise ValueError('owned microphone producer cleanup failed; stop batch')
            with independent_probe(report, persona, microphone_health, save):
                cases, records = [], []
                for index, denied in enumerate((False, True, False)):
                    output = work / (persona + '-' + str(index))
                    last_microphone_output = output
                    argv = [sys.executable, Path(__file__).with_name('run_normal_hap_probe.py'),
                        '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                        '--persona', persona, '--arch', arch, '--device', device, '--target', target,
                        '--hdc', hdc, '--boot-id', environment['boot_id'], '--boot', work / 'boot/boot.json',
                        '--output', output, '--source-volume', source_volume, '--docker-image', docker_image]
                    if denied:
                        argv += ['--' + persona + '-expect-denied']
                    record = command(argv, 'ordinary-' + persona + '-' + str(index), timeout=2400, env=child_env)
                    path = output / 'evidence.json'
                    records.append(record)
                    cases.append({'evidence': str(path), 'sha256': checksum(path)})
                    same_guest('after-ordinary-' + persona + '-' + str(index))
                batch = {'status': 'pass', 'scope': scope + '_grant_deny_grant',
                    'archive_sha256': report['package']['sha256'], 'boot_id': environment['boot_id'],
                    'arch': arch, 'cases': cases, 'first_artifact_behavior_gate_passed': False}
                verify_batch(batch, args.package_archive, environment['boot_id'], arch)
                batch_path.write_text(json.dumps(batch, indent=2) + '\n')
                check(persona, batch_path, records)
        focus_output = work / 'audio-focus'
        def focus_health(label):
            same_guest(label)
            if label.startswith('after-'):
                if report['commands'][-1].get('timed_out'):
                    raise ValueError('timed-out two-UID focus cleanup is not certified; stop batch')
                path = focus_output / 'focus/runtime.json'
                if path.is_file() and json.loads(path.read_text()).get('cleanup_errors') != []:
                    raise ValueError('owned focus producer/app cleanup failed; stop batch')
                path = focus_output / 'result.json'
                if path.is_file() and any('cleanup' in str(v).lower() for v in json.loads(path.read_text()).get('failures', [])):
                    raise ValueError('two-UID focus application cleanup failed; stop batch')
        with independent_probe(report, 'audio-focus', focus_health, save):
            record = command([sys.executable, Path(__file__).with_name('run_audio_focus_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'], '--boot', work / 'boot/boot.json',
                '--output', focus_output, '--source-volume', source_volume, '--docker-image', docker_image],
                'ordinary-two-UID-MIC-VOIP-real-focus-and-background-notifications', timeout=4800, env=child_env)
            check('audio-focus', focus_output / 'result.json', [record])
        normal_results = {}
        personas = ('web', 'web-factory', 'vulkan-window', 'userid', 'i18n', 'matrix4', 'factory-objects', 'curve', 'binding', 'const-enum', 'contact-sync-mode', 'runtime-enum', 'arkts-exports',
                    'worker-legacy', 'worker-thread', 'audio-stream', 'avc-media', 'audio-suite-effects', 'camera', 'settings-navigation', 'photos-recent', 'photos-asset', 'storage-stats')
        personas += ('completion-handler',)
        personas += ('audio-revoke',)
        personas += ('rpc-runtime',)
        personas += ('image-metadata',)
        personas += ('thermal',)
        personas += ('network-accounting',)
        personas += ('router-observer',)
        personas += ('observer-info',)
        personas += ('spring-loading',)
        personas += ('arkui-components',)
        if device == 'phone':
            personas += ('optional-phone-profile',)
        for persona in personas:
            path = work / persona / 'evidence.json'

            def normal_batch_health(label):
                same_guest(label)
                if label.startswith('after-'):
                    if report['commands'][-1].get('timed_out'):
                        raise ValueError('timed-out child cleanup is not certified; stop batch')
                    if path.is_file():
                        child = json.loads(path.read_text())
                        if any('cleanup failed' in str(value) for value in child.get('failures', [])):
                            raise ValueError('owned child cleanup failed; stop batch')

            with independent_probe(report, 'ordinary-' + persona, normal_batch_health, save):
                record = command([sys.executable, Path(__file__).with_name('run_normal_hap_probe.py'),
                    '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                    '--persona', persona, '--arch', arch, '--device', device, '--target', target,
                    '--hdc', hdc, '--boot-id', environment['boot_id'], '--boot', work / 'boot/boot.json', '--output', work / persona,
                    '--source-volume', source_volume, '--docker-image', docker_image],
                    'ordinary-' + persona, timeout=2400, env=child_env)
                document = json.loads(path.read_text())
                if document.get('status') != 'pass' or document.get('boot_id') != environment['boot_id']:
                    raise ValueError('normal-app behavior result is failed or from another boot: ' + persona)
                normal_results[persona] = {'evidence': str(path), 'sha256': checksum(path), 'command': record}
                if persona == 'web':
                    check('arkweb', path, [record])
                if persona == 'photos-asset':
                    check('photos-asset', path, [record])
                if persona == 'settings-navigation':
                    check('settings-navigation', path, [record])
                if persona == 'storage-stats':
                    check('storage-stats', path, [record])
                if persona == 'completion-handler':
                    check('completion-handler', path, [record])
                if persona == 'rpc-runtime':
                    check('rpc-runtime', path, [record])
                if persona == 'avc-media':
                    check('avc-media', path, [record])
                if persona == 'image-metadata':
                    check('image-metadata', path, [record])
                if persona == 'observer-info':
                    check('observer-info', path, [record])
                if persona == 'spring-loading':
                    check('spring-loading', path, [record])
                if persona == 'arkui-components':
                    check('arkui-components', path, [record])
                if persona == 'thermal':
                    check('thermal', path, [record])
                if persona == 'network-accounting':
                    check('network-accounting', path, [record])
        hitrace_record = command([sys.executable, Path(__file__).with_name('run_hitrace_diagnostic.py'),
            '--archive', args.package_archive, '--sdk', sdk, '--hdc', hdc,
            '--boot', work / 'boot/boot.json', '--owned-child', '--output', work / 'hitrace'],
            'ordinary-public-HiTrace-real-kernel-records', timeout=2400, env=child_env)
        check('hitrace', work / 'hitrace/diagnostic.json', [hitrace_record])
        same_guest('after-public-HiTrace-kernel-records')
        graphics_memory_record = command([sys.executable, Path(__file__).with_name('run_graphics_memory_diagnostic.py'),
            '--archive', args.package_archive, '--sdk', sdk, '--hdc', hdc,
            '--boot', work / 'boot/boot.json', '--owned-child', '--output', work / 'graphics-memory'],
            'ordinary-public-graphics-memory-real-buffer-lifecycle', timeout=2400, env=child_env)
        check('graphics-memory', work / 'graphics-memory/diagnostic.json', [graphics_memory_record])
        same_guest('after-public-graphics-memory')
        service_init_record = command([sys.executable,
            Path(__file__).with_name('run_service_init_contract_probe.py'),
            '--archive', args.package_archive, '--boot', work / 'boot/boot.json',
            '--output', work / 'service-init-contracts', '--hdc', hdc,
            '--source-volume', source_volume,
            '--docker-image', docker_image], 'actual-Fusion-accounts-and-I18n-init-paths', timeout=900, env=child_env)
        check('service-init-contracts', work / 'service-init-contracts/evidence.json', [service_init_record])
        same_guest('after-service-init-contracts')
        # Native Vulkan queue/memory, OHOS WSI resize/readback and actual
        # compositor UI are independent tests, not browser/WebGL substitutes.
        graphics = work / 'graphics-probes'
        command(['bash', Path(__file__).with_name('build_graphics_probes.sh'),
                 '--arch', arch, '--output', graphics], 'build-real-native-graphics-probes', env=child_env)
        graphics_results = {}
        for kind, binary in (('vulkan-device', 'vulkan_device_probe'),
                             ('vulkan-headless', 'vulkan_headless_probe'),
                             ('vulkan-ohos-surface', 'vulkan_ohos_surface_probe'),
                             ('gles-llvm', 'mesa_llvm_gles')):
            record = command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
                '--kind', kind, '--archive', args.package_archive, '--probe', graphics / binary,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'],
                '--boot-evidence', work / 'boot/boot.json',
                '--output', work / kind], 'native-' + kind, env=child_env)
            path = work / kind / 'result.json'
            if json.loads(path.read_text()).get('status') != 'pass':
                raise ValueError('native graphics verification failed: ' + kind)
            graphics_results[kind] = {'evidence': str(path), 'sha256': checksum(path), 'command': record}
            same_guest('after-' + kind)
        if 'vulkan-window' in normal_results:
            graphics_results['vulkan-window'] = normal_results['vulkan-window']
        graphics_report = {'schema_version': 1, 'status': 'pass' if 'vulkan-window' in normal_results else 'fail',
            'scope': 'independent_Vulkan_native_WSI_resize_and_compositor_regressions',
            'archive_sha256': report['package']['sha256'], 'boot_id': environment['boot_id'],
            'results': graphics_results}
        graphics_path = work / 'vulkan.json'
        graphics_path.write_text(json.dumps(graphics_report, indent=2) + '\n')
        if graphics_report['status'] == 'pass':
            check('vulkan', graphics_path, [row['command'] for row in graphics_results.values()])
        else:
            report['checks']['vulkan'] = {'status': 'fail', 'evidence': str(graphics_path),
                'sha256': checksum(graphics_path), 'reason': 'ordinary Vulkan window proof failed or missing'}
            report['failures'].append('Vulkan aggregate missing ordinary window proof')
            save()
        permission_probes = work / 'permission-probes'
        permission_probes.mkdir()
        permission_build = command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
            '--mount', 'type=volume,src=' + source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=volume,src=' + os.environ.get('DOCKER_OUT_VOLUME', 'ohos-qemu-7_0-release-out') +
                       ',dst=/ohos/out,readonly',
            '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(permission_probes) + ',dst=/probe',
            docker_image, 'python3', '/work/ci/capability-audit/build_permission_probe.py',
            '--source-root', '/ohos', '--arch', arch, '--output', '/probe'],
            'compile-real-same-product-permission-innerkit', env=child_env)
        permission_runtime = command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
            '--kind', 'permission-registry', '--archive', args.package_archive,
            '--probe', permission_probes / 'permission_registry',
            '--definitions', permission_probes / 'permission-definitions.json',
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--boot-evidence', work / 'boot/boot.json',
            '--output', work / 'permission-registry'],
            'actual-complete-permission-registry-and-boundaries', env=child_env)
        check('permission-registry', work / 'permission-registry/result.json', [permission_build, permission_runtime])
        same_guest('after-permission-registry')
        vibrator_probes = work / 'vibrator-probes'
        vibrator_probes.mkdir()
        command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
            '--mount', 'type=volume,src=' + source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=volume,src=' + os.environ.get('DOCKER_OUT_VOLUME', 'ohos-qemu-7_0-release-out') +
                       ',dst=/ohos/out,readonly',
            '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(vibrator_probes) + ',dst=/probe',
            docker_image, 'python3', '/work/ci/capability-audit/build_vibrator_hdi_probe.py',
            '--source-root', '/ohos', '--arch', arch, '--output', '/probe'],
            'compile-real-same-product-Vibrator-HDI-probe', env=child_env)
        command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
            '--kind', 'vibrator-hdi', '--archive', args.package_archive,
            '--probe', vibrator_probes / 'vibrator_hdi', '--arch', arch, '--device', device,
            '--target', target, '--hdc', hdc, '--boot-id', environment['boot_id'],
            '--boot-evidence', work / 'boot/boot.json',
            '--output', work / 'vibrator-hdi'], 'actual-virtual-Vibrator-HDI-boundaries', env=child_env)
        same_guest('after-vibrator-HDI')
        if device == '2in1':
            serial_record = command([sys.executable, Path(__file__).with_name('run_serial_package_probe.py'),
                '--archive', args.package_archive, '--boot', work / 'boot/boot.json',
                '--sdk', sdk, '--output', work / 'serial', '--hdc', hdc,
                '--source-volume', source_volume, '--docker-image', docker_image],
                'ordinary-Serial-real-USB-authorization-bytes-and-attachment', timeout=5400, env=child_env)
            check('serial', work / 'serial/evidence.json', [serial_record])
            same_guest('after-serial')
        bindings_record = command([sys.executable, Path(__file__).with_name('run_native_bindings_e2e.py'),
            '--source', os.environ.get('OHOS_NATIVE_BINDINGS', str(ROOT.parent / 'ohos-native-bindings')),
            '--sdk', sdk, '--archive', args.package_archive, '--output', work / 'native-bindings',
            '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
            '--boot-id', environment['boot_id'], '--udid', guest.udid,
            '--source-volume', source_volume, '--docker-image', docker_image],
            'all-current-native-bindings-E2E', timeout=14400, env=child_env)
        check('native-bindings-e2e', work / 'native-bindings/evidence.json', [bindings_record])
        same_guest('after-bindings')
        # Preserve all successful narrow results while requiring a separate
        # complete ledger closure. Missing registered behavior is a failure,
        # never silently converted into success by this orchestration layer.
        closure_record = command([sys.executable, Path(__file__).with_name('verify_gap_closure.py'),
            '--archive', args.package_archive, '--boot', work / 'boot/boot.json',
            '--runtime-root', work, '--device', device,
            '--output', work / 'cxx-arkts11-gaps.json'], 'complete-Cxx-ArkTS11-gap-closure', env=child_env)
        check('cxx-arkts11-gaps', work / 'cxx-arkts11-gaps.json', [closure_record])
        same_guest('final')
        checks_complete = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report.update(status='fail', first_artifact_behavior_gate_passed=False)
        report['failures'].append(str(error))
    finally:
        if guest is not None:
            if screen_timeout_override:
                try:
                    guest.wake_for_interaction('restore-app-test-timeout')
                    restored = guest.shell('power-shell timeout -r', 'restore-app-test-screen-timeout')
                    policy = report['application_test_setup']['policy_states']
                    policy['restored'] = power_timeout(guest.shell('hidumper -s 3301 -a "-a"',
                                                                'app-test-power-restored'))
                    report['application_test_setup']['restoration_method'] = verify_restoration(
                        restored, policy['before'], policy['setup'], policy['restored'])
                    report['application_test_setup']['restored'] = True
                except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
                    report.update(status='fail', first_artifact_behavior_gate_passed=False)
                    report['failures'].append('owned test setup restoration failed: ' + str(error))
            guest.close()
            if 'boot' in report['checks']:
                report['checks']['boot']['sha256'] = checksum(work / 'boot/boot.json')
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    if checks_complete and not report['failures']:
        report.update(status='pass', first_artifact_behavior_gate_passed=True)
        save()
        try:
            verify(args.package_archive, args.evidence_output, ROOT, environment['product'], device)
        except (OSError, ValueError, KeyError, TypeError) as error:
            report.update(status='fail', first_artifact_behavior_gate_passed=False)
            report['failures'].append('final independent evidence verification failed: ' + str(error))
            save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-archive', type=Path, required=True)
    parser.add_argument('--package-directory', type=Path)
    parser.add_argument('--evidence-output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    print(json.dumps({key: report[key] for key in ('status', 'first_artifact_behavior_gate_passed', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
