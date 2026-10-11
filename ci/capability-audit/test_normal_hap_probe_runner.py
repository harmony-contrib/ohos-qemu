"""Ordinary probe orchestration fixtures, not HAP signing or guest passes."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest

from run_normal_hap_probe import (BUNDLE, PERSONAS, previous_probe_absent, require_normal_identity, result_directory, save_command_output,
                                  reject_terminal_web_failure, run, stop_previous_probe, verifier_arguments)


class NormalHapRunnerTests(unittest.TestCase):
    def test_terminal_web_timeout_fails_even_if_completion_arrives_later(self):
        for marker in ('web.reload.timeout=true', 'web.renderer.recovery.timeout=true'):
            for suffix in ('', '\nweb.execution.complete=true\n'):
                with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'Web terminal failure'):
                    reject_terminal_web_failure('web', marker + suffix)

    def test_web_diagnostic_does_not_decide_pass_or_reject_other_personas(self):
        for text in ('', 'web.renderer.terminate.result=true\n',
                     'web.js.exception.result=Error:QEMU_WEB_EXPECTED_ERROR\n'):
            self.assertIsNone(reject_terminal_web_failure('web', text))
        self.assertIsNone(reject_terminal_web_failure('web-factory', 'web.reload.timeout=true'))
        source = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        self.assertIn("shell('hilog -x -D 0xD001311', 'web-lifecycle-appmgr'", source)

    def test_camera_uses_actual_module_context_private_results_and_photos(self):
        self.assertEqual(result_directory('camera'), '/data/app/el2/100/base/' + BUNDLE + '/haps/entry/files/')
        for persona in PERSONAS:
            if persona != 'camera':
                self.assertEqual(result_directory(persona), '/data/app/el2/100/base/' + BUNDLE + '/files/')
        source = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        self.assertIn('native_remote = app_files +', source)
        self.assertIn('receive_photos(command, args.hdc, args.target, app_files,', source)

    def test_previous_app_requires_actual_kernel_and_AA_absence(self):
        dump = 'User ID #100\n  AppRunningRecords:\n'
        self.assertTrue(previous_probe_absent('ABSENT\n', dump))
        self.assertFalse(previous_probe_absent('456 789\n', dump))
        for own in (BUNDLE, BUNDLE + ':renderer'):
            self.assertFalse(previous_probe_absent('ABSENT', dump + 'process name [' + own + ']\n'))
        self.assertTrue(previous_probe_absent('ABSENT', dump + 'process name [' + BUNDLE + '.unrelated]\n'))
        for pids, abilities in (('', dump), ('error', dump), ('ABSENT', ''),
                                ('ABSENT', dump.replace('#100', '#0'))):
            with self.assertRaises(ValueError): previous_probe_absent(pids, abilities)

    def test_stop_waits_for_two_real_absent_observations_and_is_bounded(self):
        dump = 'User ID #100\n  AppRunningRecords:\n'
        calls, ticks = [], [0.0]
        pids = iter(['123', 'ABSENT', '123', 'ABSENT', 'ABSENT'])
        def shell(script, label, **kwargs):
            calls.append(script)
            if script == 'aa force-stop ' + BUNDLE: return 'force stop process successfully.\n'
            if script == 'aa dump -a -u 100': return dump
            return next(pids)
        def sleep(value): ticks[0] += value
        result = stop_previous_probe(shell, clock=lambda: ticks[0], sleep=sleep)
        self.assertEqual(result['observations'], 5)
        self.assertEqual(result['consecutive_absent_observations'], 2)
        self.assertEqual(calls.count('aa force-stop ' + BUNDLE), 1)
        def persistent(script, label, **kwargs):
            if script == 'aa force-stop ' + BUNDLE: return 'force stop process successfully.'
            if script == 'aa dump -a -u 100': return dump
            return '456'
        with self.assertRaisesRegex(ValueError, 'did not drain'):
            stop_previous_probe(persistent, clock=lambda: ticks[0], sleep=sleep)

    def test_stop_accepts_only_exact_success_or_real_not_installed_error(self):
        dump = 'User ID #100\n  AppRunningRecords:\n'
        def shell(reply):
            def call(script, label, **kwargs):
                if script == 'aa force-stop ' + BUNDLE: return reply
                return dump if script == 'aa dump -a -u 100' else 'ABSENT'
            return call
        absent = ('error: failed to force stop process.\nError Code:10104002\n'
                  'The application corresponding to the specified package name is not installed.')
        self.assertTrue(stop_previous_probe(shell(absent), sleep=lambda _: None)['kernel_process_absent'])
        for reply in ('', '[Fail]', 'error: permission denied', 'success', absent.replace('10104002', '201')):
            with self.assertRaisesRegex(ValueError, 'did not confirm'):
                stop_previous_probe(shell(reply), sleep=lambda _: None)

    def test_requires_real_ordinary_account_identity_and_rejects_system_persona(self):
        identity = {'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010001}}
        self.assertEqual(require_normal_identity(BUNDLE + ':\n' + json.dumps(identity)), 20010001)
        for field, value in (('isSystemApp', True), ('appPrivilegeLevel', 'system_core'), ('uid', 10001), ('uid', '20010001')):
            modified = json.loads(json.dumps(identity))
            modified['applicationInfo'][field] = value
            with self.assertRaises(ValueError):
                require_normal_identity(json.dumps(modified))

    def test_strict_verifier_routes_include_identity_nonce_and_account_boundaries(self):
        for persona in PERSONAS:
            arguments = verifier_arguments(persona, Path('/new.tar.gz'), Path('/fresh.log'),
                Path('/ordinary.json'), 'a' * 32, 'armv7a', Path('/verified.json'))
            self.assertIn('--output', arguments)
            self.assertIn('--arkts-results' if persona == 'camera' else
                          '--log' if persona in ('web', 'userid') else '--results', arguments)
            self.assertEqual('--run-id' in arguments, persona not in ('web', 'vulkan-window'))
            if persona in ('avc-media', 'audio-stream', 'audio-suite-effects', 'camera'):
                self.assertIn('--application-identity', arguments)
            if persona == 'userid':
                self.assertIn('--app-context', arguments)
                self.assertIn('--expected-user-id', arguments)
            if persona == 'web':
                self.assertNotIn('--archive', arguments)

    def test_media_completion_waits_for_actual_summary_not_a_nonexistent_marker(self):
        for persona in ('avc-media', 'audio-suite-effects', 'audio-stream'):
            self.assertEqual(PERSONAS[persona][2], '"summary"')

    def test_real_factories_and_phone_discovery_use_one_normal_runner_and_strict_inputs(self):
        runner = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        builder = Path(__file__).with_name('build_hap_probe.py').read_text()
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        for persona in ('curve', 'binding', 'optional-phone-profile'):
            self.assertEqual(PERSONAS[persona][0], '--' + persona + '-only')
            self.assertEqual(PERSONAS[persona][2], '"summary"')
            argv = verifier_arguments(persona, Path('/archive'), Path('/raw'), Path('/identity'),
                'a' * 32, 'arm64', Path('/result'))
            for flag in ('--archive', '--application-identity', '--arch', '--run-id'): self.assertIn(flag, argv)
        self.assertIn("args.device != 'phone'", runner)
        self.assertIn("'--boot', str(args.boot), '--boot-id', boot_id", runner)
        self.assertIn("if device == 'phone':", suite)
        self.assertIn("personas += ('optional-phone-profile',)", suite)
        self.assertIn("if args.runtime_enum_only or args.curve_only:", builder)
        self.assertIn('or args.binding_only or args.storage_stats_only or args.optional_phone_profile_only or args.photos_recent_only or args.photos_asset_only or args.settings_navigation_only):', builder)
        self.assertNotIn('build_curve_hap_probe.py', runner)
        self.assertNotIn('build_binding_hap_probe.py', runner)

    def test_camera_uses_real_permission_UI_two_live_captures_and_private_photos(self):
        source = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertEqual(PERSONAS['camera'][0], '--camera-only')
        self.assertEqual(PERSONAS['camera'][2], '"arkts_complete"')
        for required in ('allow_camera(ui, labels', 'live_captures(ui, shell', 'receive_photos(command',
                         "'--native-results'", "'--captures'", "'--photo-root'", 'verify_inputs('):
            self.assertIn(required, source)
        self.assertIn("'audio-suite-effects', 'camera', 'settings-navigation', 'photos-recent', 'photos-asset', 'storage-stats')", suite)

    def test_vulkan_builder_does_not_receive_an_unsupported_nonce_flag(self):
        source = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        self.assertIn("if args.persona not in ('web', 'vulkan-window'):", source)
        self.assertEqual(PERSONAS['const-enum'][0], '--const-enum-only')

    def test_vulkan_requires_actual_compositor_captures_and_real_ui_recreation(self):
        source = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        self.assertEqual(PERSONAS['vulkan-window'][3], 'verify_vulkan_window.py')
        capture_source = Path(__file__).with_name('vulkan_frame_capture.py').read_text()
        self.assertIn("identifier='qemu-vulkan-surface'", capture_source)
        self.assertIn("poll_result('vulkan_window.destroyed|')", source)
        self.assertIn("result = poll_result('generation=2')", source)
        self.assertIn('capture_presented_frame(ui, BUNDLE, generation, result,', source)
        self.assertIn("report['presentation_attempts']", source)
        self.assertIn('except PixelMismatch', capture_source)
        self.assertIn('verify_pixels(picture', capture_source)
        self.assertIn("prefix + '-rect'", source)

    def test_missing_actual_archive_records_failure_not_pass_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = argparse.Namespace(output=root / 'attempt', archive=root / 'missing.tar.gz',
                persona='web', target='127.0.0.1:5555', arch='arm64', device='phone')
            result = run(args)
            self.assertEqual(result['status'], 'fail')
            self.assertFalse(result['first_artifact_behavior_gate_passed'])
            self.assertEqual(result['commands'], [])
            self.assertEqual(json.loads((args.output / 'evidence.json').read_text()), result)
            with self.assertRaises(FileExistsError):
                run(args)

    def test_runner_does_not_grant_permissions_replace_dsos_or_use_periodic_keepalive(self):
        source = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        self.assertIn("start_new_session=True", source)
        self.assertIn("os.killpg(process.pid, signal.SIGTERM)", source)
        self.assertIn("--sign-code', '1'", source)
        self.assertIn("--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar'", source)
        for forbidden in ('grantPermission', 'LD_PRELOAD=', 'LD_LIBRARY_PATH=', 'setenforce', 'while true'):
            self.assertNotIn(forbidden, source)

    def test_failure_diagnostics_check_the_original_boot_and_never_clear_guest_logs(self):
        source = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        capture = source.split("if 'boot_id' in report:", 1)[1].split('\n    finally:', 1)[0]
        self.assertLess(capture.index("'failure-capture-boot-id'"), capture.index("'hilog -x'"))
        self.assertIn('diagnostic_bytes=True', capture)
        self.assertIn("!= report['boot_id']", capture)
        self.assertIn("shell('ps -ef'", capture)
        self.assertIn("report['failure_diagnostics_error']", capture)
        for forbidden in ('hilog -r', 'hilog -b', 'status=', 'status =', 'power-shell', 'uninstall', 'setenforce'):
            self.assertNotIn(forbidden, capture)

    def test_binary_diagnostics_preserve_exact_streams_without_changing_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hilog.log'
            stdout, stderr, record = save_command_output(path, b'prefix\xf8\n', b'error\xff\n', True)
            self.assertEqual(Path(record['stdout_raw']).read_bytes(), b'prefix\xf8\n')
            self.assertEqual(Path(record['stderr_raw']).read_bytes(), b'error\xff\n')
            self.assertEqual(path.read_text(), stdout + stderr)
            self.assertIn('\ufffd', stdout)
            self.assertEqual(record['decoded_text_scope'], 'diagnostic_only_NOT_behavior_acceptance')
            stdout, stderr, record = save_command_output(Path(directory) / 'strict.log', 'actual', 'error')
            self.assertEqual((stdout, stderr), ('actual', 'error'))
            self.assertNotIn('decoded_text_scope', record)
            with self.assertRaises(ValueError):
                save_command_output(path, 'not raw', '', True)


if __name__ == '__main__':
    unittest.main()
