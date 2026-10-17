"""Owned cleanup controls; synthetic commands never attest a real guest."""
import unittest

from run_normal_hap_probe import BUNDLE, cleanup_microphone_application


class MicrophoneApplicationCleanupTests(unittest.TestCase):
    def fixture(self, listing='com.ohos.launcher\ncom.ohos.sceneboard\n',
                reply='uninstall bundle successfully.\n', changed=None):
        calls = []

        def shell(script, label, **kwargs):
            calls.append(('shell', script, label))
            if script == 'cat /proc/sys/kernel/random/boot_id':
                return ('other' if label == changed else 'owned-boot') + '\n'
            if script == 'aa force-stop ' + BUNDLE:
                return 'force stop process successfully.\n'
            if script.startswith('task_probe_pids='):
                return 'ABSENT\n'
            if script == 'aa dump -a -u 100':
                return 'User ID #100\n  AppRunningRecords:\n'
            if script == 'bm dump -a':
                return listing
            raise AssertionError(script)

        def command(argv, label):
            self.assertEqual(argv, ['owned-hdc', '-t', 'owned-target', 'uninstall', BUNDLE])
            calls.append(('command', argv, label))
            return reply

        return shell, command, calls

    def test_reserved_bundle_is_stopped_drained_uninstalled_and_checked(self):
        shell, command, calls = self.fixture()
        result = cleanup_microphone_application(shell, command, 'owned-hdc', 'owned-target', 'owned-boot')
        self.assertTrue(result['installed_bundle_absent'])
        self.assertEqual(result['lifecycle']['consecutive_absent_observations'], 2)
        self.assertEqual(sum(c[0] == 'shell' and c[1] == 'aa dump -a -u 100' for c in calls), 2)
        self.assertLess(next(i for i, c in enumerate(calls) if c[0] == 'command'),
                        next(i for i, c in enumerate(calls) if c[1] == 'bm dump -a'))

    def test_other_kernel_is_never_mutated(self):
        shell, command, calls = self.fixture(changed='MIC-cleanup-boot-before')
        with self.assertRaisesRegex(ValueError, 'different guest kernel'):
            cleanup_microphone_application(shell, command, 'owned-hdc', 'owned-target', 'owned-boot')
        self.assertEqual(len(calls), 1)

    def test_lost_kernel_identity_cannot_be_requeried_and_reauthorized(self):
        shell, command, calls = self.fixture()
        with self.assertRaisesRegex(ValueError, 'retains lost guest kernel identity'):
            cleanup_microphone_application(shell, command, 'owned-hdc', 'owned-target', 'owned-boot',
                                           boot_failure='prior actual boot query failed')
        self.assertEqual(calls, [])

    def test_diagnostic_preservation_failure_prevents_uninstall(self):
        shell, command, calls = self.fixture()
        def preserve(): raise ValueError('controlled partial transfer failed')
        with self.assertRaisesRegex(ValueError, 'partial transfer failed'):
            cleanup_microphone_application(shell, command, 'owned-hdc', 'owned-target', 'owned-boot', preserve=preserve)
        self.assertFalse(any(c[0] == 'command' for c in calls))

    def test_false_uninstall_success_and_incomplete_or_owned_BMS_listing_fail(self):
        for reply in ('', '[Fail] uninstall failed', 'permission denied', 'success'):
            shell, command, _ = self.fixture(reply=reply)
            with self.subTest(reply=reply), self.assertRaisesRegex(ValueError, 'uninstall failed'):
                cleanup_microphone_application(shell, command, 'owned-hdc', 'owned-target', 'owned-boot')
        for listing in ('', 'error: dump failed', 'com.ohos.launcher\n' + BUNDLE + '\n'):
            shell, command, _ = self.fixture(listing=listing)
            with self.subTest(listing=listing), self.assertRaisesRegex(ValueError, 'BMS listing'):
                cleanup_microphone_application(shell, command, 'owned-hdc', 'owned-target', 'owned-boot')

    def test_changed_final_boot_fails_and_similar_bundle_is_not_removed(self):
        shell, command, _ = self.fixture(changed='MIC-cleanup-boot-after')
        with self.assertRaisesRegex(ValueError, 'changed during'):
            cleanup_microphone_application(shell, command, 'owned-hdc', 'owned-target', 'owned-boot')
        shell, command, calls = self.fixture(listing='com.ohos.launcher\n' + BUNDLE + '.unrelated\n')
        self.assertTrue(cleanup_microphone_application(
            shell, command, 'owned-hdc', 'owned-target', 'owned-boot')['installed_bundle_absent'])
        self.assertEqual([c[1][-1] for c in calls if c[0] == 'command'], [BUNDLE])


if __name__ == '__main__':
    unittest.main()
