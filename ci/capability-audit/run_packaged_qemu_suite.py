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
        normal_results = {}
        personas = ('web', 'web-factory', 'vulkan-window', 'userid', 'i18n', 'matrix4', 'factory-objects', 'curve', 'binding', 'const-enum', 'contact-sync-mode', 'runtime-enum', 'arkts-exports',
                    'worker-legacy', 'worker-thread', 'audio-stream', 'avc-media', 'audio-suite-effects', 'camera', 'settings-navigation', 'photos-recent', 'photos-asset', 'storage-stats')
        if device == 'phone':
            personas += ('optional-phone-profile',)
        for persona in personas:
            record = command([sys.executable, Path(__file__).with_name('run_normal_hap_probe.py'),
                '--archive', args.package_archive, '--sdk', sdk, '--udid', guest.udid,
                '--persona', persona, '--arch', arch, '--device', device, '--target', target,
                '--hdc', hdc, '--boot-id', environment['boot_id'], '--boot', work / 'boot/boot.json', '--output', work / persona,
                '--source-volume', source_volume, '--docker-image', docker_image],
                'ordinary-' + persona, timeout=2400, env=child_env)
            path = work / persona / 'evidence.json'
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
            same_guest('after-' + persona)
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
                             ('vulkan-ohos-surface', 'vulkan_ohos_surface_probe')):
            record = command([sys.executable, Path(__file__).with_name('run_root_probe.py'),
                '--kind', kind, '--archive', args.package_archive, '--probe', graphics / binary,
                '--arch', arch, '--device', device, '--target', target, '--hdc', hdc,
                '--boot-id', environment['boot_id'],
                '--boot-evidence', work / 'boot/boot.json',
                '--output', work / kind], 'native-' + kind, env=child_env)
            path = work / kind / 'result.json'
            if json.loads(path.read_text()).get('status') != 'pass':
                raise ValueError('native Vulkan verification failed: ' + kind)
            graphics_results[kind] = {'evidence': str(path), 'sha256': checksum(path), 'command': record}
            same_guest('after-' + kind)
        graphics_results['vulkan-window'] = normal_results['vulkan-window']
        graphics_report = {'schema_version': 1, 'status': 'pass',
            'scope': 'independent_Vulkan_native_WSI_resize_and_compositor_regressions',
            'archive_sha256': report['package']['sha256'], 'boot_id': environment['boot_id'],
            'results': graphics_results}
        graphics_path = work / 'vulkan.json'
        graphics_path.write_text(json.dumps(graphics_report, indent=2) + '\n')
        check('vulkan', graphics_path, [row['command'] for row in graphics_results.values()])
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
