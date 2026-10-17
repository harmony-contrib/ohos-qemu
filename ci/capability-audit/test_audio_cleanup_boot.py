"""Controlled host cleanup counterexamples; no SDK, compiler, HDC or VM runs."""
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from audio_capture_runtime import BOOT_SCRIPT, CaptureRuntime, cleanup_boot_prefix
from audio_focus_runtime import AudioFocusRuntime
from media_capture_contract import BUNDLES
from run_audio_focus_probe import cleanup_owned_applications

BOOT = '12345678-1234-1234-1234-123456789abc'
OTHER = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
AA = 'User ID #100\n  AppRunningRecords:\n'
ABSENT_REPLY = ('error: failed to force stop process.\nError Code:10104002\n'
    'The application corresponding to the specified package name is not installed.')
MISSING_UNINSTALL = ('[Info]App uninstall path: msg:error: failed to uninstall bundle. '
    'code:9568386 error: uninstall missing installed bundle.\nAppMod finish\n')


class OwnedHostProcess:
    pid = 31415
    returncode = None
    def poll(self): return self.returncode
    def wait(self, timeout):
        if self.returncode is None: raise subprocess.TimeoutExpired('controlled owned host process', timeout)
        return self.returncode


class CleanupBootTests(unittest.TestCase):
    def capture(self, output, observer, process=None):
        capture = CaptureRuntime.__new__(CaptureRuntime)
        capture.started = True; capture.finished = False; capture.process = process; capture.producer_log = None
        capture.remote = '/data/local/tmp/qemu-mic-' + 'a' * 32
        capture.boot_id = BOOT; capture.value = {}; capture.output = output; capture.actual_shell = observer
        return capture

    def test_changed_or_unreadable_boot_preserves_remote_and_only_reaps_owned_host(self):
        for unreadable in (False, True):
            with self.subTest(unreadable=unreadable), tempfile.TemporaryDirectory() as directory:
                calls, signals = [], []; process = OwnedHostProcess()
                def observe(script, label):
                    calls.append((script, label)); self.assertEqual(script, BOOT_SCRIPT)
                    if unreadable: raise ValueError('controlled boot query failed')
                    return OTHER
                capture = self.capture(Path(directory), observe, process)
                def reap(pid, sig): signals.append((pid, sig)); process.returncode = -sig
                with patch('audio_capture_runtime.os.killpg', side_effect=reap):
                    with self.assertRaises(ValueError): capture.close()
                self.assertEqual(signals, [(process.pid, signal.SIGTERM)])
                self.assertEqual(len(calls), 1); self.assertTrue(capture.started)
                self.assertFalse(capture.finished); self.assertFalse(capture.value['cleanup_complete'])
                self.assertNotIn('owned_remote_directory_removed', capture.value)
                with self.assertRaises(ValueError): capture.require_cleanup_boot('must-not-requery')
                self.assertEqual(len(calls), 1)

    def test_boot_change_after_stop_prevents_private_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []; boots = iter((BOOT, OTHER))
            def observe(script, label):
                calls.append((script, label)); return next(boots) if script == BOOT_SCRIPT else ''
            capture = self.capture(Path(directory), observe)
            with self.assertRaisesRegex(ValueError, 'different guest kernel'): capture.close()
            scripts = [s for s, _ in calls if s != BOOT_SCRIPT]
            self.assertEqual(len(scripts), 1); self.assertTrue(scripts[0].startswith(cleanup_boot_prefix(BOOT)))
            self.assertNotIn('rm -f', scripts[0]); self.assertTrue(capture.started)

    def test_inband_guard_failure_cannot_become_cleanup_success(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def observe(script, label):
                calls.append((script, label))
                if script == BOOT_SCRIPT: return BOOT
                self.assertTrue(script.startswith(cleanup_boot_prefix(BOOT)))
                raise ValueError('controlled inband boot guard refused mutation')
            capture = self.capture(Path(directory), observe)
            with self.assertRaisesRegex(ValueError, 'inband boot guard'): capture.close()
            self.assertFalse(capture.value['cleanup_complete'])
            self.assertFalse(any('rm -f' in s for s, _ in calls))

    def test_same_boot_checks_both_mutating_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def observe(script, label):
                calls.append((script, label)); return BOOT if script == BOOT_SCRIPT else ''
            capture = self.capture(Path(directory), observe); capture.close()
            mutation = [(s, l) for s, l in calls if s != BOOT_SCRIPT]
            self.assertEqual(len(mutation), 2)
            self.assertTrue(all(s.startswith(cleanup_boot_prefix(BOOT)) for s, _ in mutation))
            self.assertEqual([l for _, l in calls if l.startswith('PCM-cleanup-boot')],
                ['PCM-cleanup-boot-before-stop', 'PCM-cleanup-boot-before-private-removal'])
            self.assertTrue(capture.finished); self.assertFalse(capture.started)
            self.assertTrue(capture.value['owned_remote_directory_removed'])

    def test_focus_changed_boot_skips_actor_reads_and_guest_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def observe(script, label):
                calls.append((script, label)); self.assertEqual(script, BOOT_SCRIPT); return OTHER
            focus = AudioFocusRuntime.__new__(AudioFocusRuntime)
            focus.closed = False; focus.capture = self.capture(Path(directory), observe)
            focus.value = {'actors': {'owner': {}}, 'status': 'captured_NOT_independently_verified', 'failures': []}
            focus.native_rows = lambda *args: self.fail('must not read the changed guest')
            focus.collect_actor = lambda *args, **kwargs: self.fail('must not collect from the changed guest')
            focus.save = lambda: None; focus.close()
            self.assertEqual(len(calls), 1); self.assertTrue(focus.value['cleanup_errors'])
            self.assertEqual(focus.value['status'], 'fail'); self.assertTrue(focus.capture.started)

    def fixture(self, *, wrong_boot_label=None, unreadable_boot_label=None, uninstall_reply='uninstall bundle successfully.\n',
                stop_reply='force stop process successfully.', bms='com.ohos.launcher\n', host_exit=0):
        commands, calls = [], []
        def shell(script, label, **kwargs):
            calls.append(('shell', script, label))
            commands.append({'argv': ['fixture-hdc', '-t', 'fixture-target', 'shell', script], 'exit_code': 0})
            if script == BOOT_SCRIPT:
                if label == unreadable_boot_label: raise ValueError('controlled boot query failed')
                return OTHER if label == wrong_boot_label else BOOT
            if script.endswith(tuple('aa force-stop ' + bundle for bundle in BUNDLES)):
                self.assertTrue(script.startswith(cleanup_boot_prefix(BOOT))); return stop_reply
            if script.startswith('focus_pids='): return 'ABSENT\n'
            if script == 'aa dump -a -u 100': return AA
            if script == 'bm dump -a': return bms
            if script.startswith('test ! -d /data/app/el2/100/base/'): return ''
            raise AssertionError(script)
        def command(argv, label, **kwargs):
            calls.append(('command', argv, label))
            commands.append({'argv': argv, 'exit_code': host_exit, 'timed_out': False}); return uninstall_reply
        return shell, command, commands, calls

    def cleanup(self, fixture, **kwargs):
        shell, command, commands, _ = fixture
        with patch('run_audio_focus_probe.time.sleep'):
            return cleanup_owned_applications(shell, command, 'fixture-hdc', 'fixture-target', BOOT,
                commands=commands, **kwargs)

    def test_two_HAPs_are_really_uninstalled_after_evidence_phase(self):
        fixture = self.fixture(); receipt = self.cleanup(fixture)
        self.assertTrue(receipt['complete']); self.assertEqual(receipt['confirmed_installed'], list(BUNDLES))
        self.assertEqual([r['bundle'] for r in receipt['roles']], list(BUNDLES))
        self.assertEqual([r['argv'] for r in receipt['uninstalls']],
            [['fixture-hdc', '-t', 'fixture-target', 'uninstall', b] for b in BUNDLES])
        self.assertTrue(all(not r['already_absent_after_failed_install'] for r in receipt['uninstalls']))
        self.assertEqual([r['label'] for r in receipt['observations']][-3:],
            ['focus-cleanup-full-BMS-list', 'focus-cleanup-full-AA-list', 'focus-application-cleanup-boot-after'])
        for row in receipt['observations']:
            self.assertEqual(fixture[2][row['command_index']]['argv'][4], row['script'])
        for row in receipt['uninstalls']:
            self.assertEqual(fixture[2][row['command_index']]['argv'], row['argv'])

    def test_focus_boot_change_before_mutation_or_uninstall_is_not_accepted(self):
        for label in ('focus-application-cleanup-boot-before', 'focus-uninstall-boot-before-' + BUNDLES[0],
                      'focus-stop-boot-before-' + BUNDLES[1], 'focus-application-cleanup-boot-after'):
            with self.subTest(label=label):
                fixture = self.fixture(wrong_boot_label=label); receipt = {}
                with self.assertRaisesRegex(ValueError, 'different guest kernel'): self.cleanup(fixture, receipt=receipt)
                self.assertFalse(receipt['complete'])
                expected = 0 if label in ('focus-application-cleanup-boot-before',
                    'focus-uninstall-boot-before-' + BUNDLES[0]) else 1 if label.startswith('focus-stop-') else 2
                self.assertEqual(sum(r[0] == 'command' for r in fixture[3]), expected)
                self.assertEqual(fixture[3][-1][2], label)

    def test_unreadable_boot_is_latched_without_retry_or_second_HAP_mutation(self):
        label = 'focus-uninstall-boot-before-' + BUNDLES[0]
        fixture = self.fixture(unreadable_boot_label=label); receipt = {}
        with self.assertRaisesRegex(ValueError, 'cannot confirm original guest kernel'):
            self.cleanup(fixture, receipt=receipt)
        self.assertFalse(receipt['complete']); self.assertEqual(fixture[3][-1][2], label)
        self.assertFalse(any(r[0] == 'command' for r in fixture[3]))

    def test_local_uninstall_failure_does_not_abandon_second_owned_HAP(self):
        fixture = self.fixture(host_exit=1); receipt = {}
        with self.assertRaisesRegex(ValueError, 'actual owned Focus uninstall command failed'):
            self.cleanup(fixture, receipt=receipt)
        self.assertEqual([r['bundle'] for r in receipt['uninstalls']], list(BUNDLES))
        self.assertEqual([r['label'] for r in receipt['observations']][-3:],
            ['focus-cleanup-full-BMS-list', 'focus-cleanup-full-AA-list', 'focus-application-cleanup-boot-after'])
        self.assertFalse(receipt['complete']); self.assertEqual(len(receipt['errors']), 2)

    def test_prior_runtime_boot_loss_prevents_HAP_cleanup_requery(self):
        fixture = self.fixture(); receipt = {}
        with self.assertRaisesRegex(ValueError, 'prior runtime boot loss'):
            self.cleanup(fixture, receipt=receipt, host_only_reason='prior runtime boot loss')
        self.assertFalse(receipt['complete']); self.assertEqual(fixture[3], [])

    def test_false_uninstall_success_host_failure_and_owned_BMS_residue_fail(self):
        for options in ({'uninstall_reply': 'success'}, {'host_exit': 1}, {'bms': ''},
                        {'bms': 'com.ohos.launcher\n' + BUNDLES[0] + '\n'}):
            with self.subTest(options=options):
                receipt = {}
                with self.assertRaises(ValueError): self.cleanup(self.fixture(**options), receipt=receipt)
                self.assertFalse(receipt['complete'])

    def test_missing_HAP_is_not_a_real_uninstall_for_a_confirmed_install(self):
        fixture = self.fixture(stop_reply=ABSENT_REPLY, uninstall_reply=MISSING_UNINSTALL)
        with self.assertRaisesRegex(ValueError, 'uninstall failed'): self.cleanup(fixture)
        fixture = self.fixture(stop_reply=ABSENT_REPLY, uninstall_reply=MISSING_UNINSTALL)
        receipt = self.cleanup(fixture, bundles=(BUNDLES[0],), confirmed_installed=())
        self.assertTrue(receipt['complete']); self.assertEqual(receipt['confirmed_installed'], [])
        self.assertTrue(receipt['uninstalls'][0]['already_absent_after_failed_install'])

    def test_cannot_cleanup_a_foreign_bundle(self):
        fixture = self.fixture()
        with self.assertRaises(ValueError): self.cleanup(fixture, bundles=('com.example.foreign',))
        self.assertEqual(fixture[3], [])


if __name__ == '__main__': unittest.main()
