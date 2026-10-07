"""Fresh-boot orchestration safety fixtures; never QEMU boot evidence."""
import argparse
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

from boot_package import QemuGuest, check_guest_version, kernel_sleeping, members_checked, port_available, verify_extracted_files
from verify_first_artifact_gate import checksum


class FreshPackageBootTests(unittest.TestCase):
    def members(self):
        return [tarfile.TarInfo('package/' + name) for name in ('manifest.json', 'build-inputs.json')]

    def test_safe_regular_members_only_and_no_duplicates_or_escape(self):
        members_checked(self.members(), 'package')
        for name in ('/package/escape', 'package/../escape', 'other/file', 'package/back\\slash'):
            with self.assertRaises(ValueError):
                members_checked(self.members() + [tarfile.TarInfo(name)], 'package')
        with self.assertRaises(ValueError):
            members_checked(self.members() * 2, 'package')
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
            member = tarfile.TarInfo('package/alias')
            member.type = kind
            with self.assertRaises(ValueError):
                members_checked(self.members() + [member], 'package')

    def test_missing_frozen_identity_or_oversized_member_rejected(self):
        with self.assertRaises(ValueError):
            members_checked(self.members()[:1], 'package')
        member = tarfile.TarInfo('package/huge')
        member.size = 8 * 1024**3 + 1
        with self.assertRaises(ValueError):
            members_checked(self.members() + [member], 'package')

    def fixture(self, root):
        names = ('manifest.json', 'build-inputs.json', 'launch/linux.sh', 'launch/macos.command', 'images/system.img')
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic checksum fixture: ' + name)
        sums = '\n'.join(checksum(root / name) + '  ./' + name for name in names) + '\n'
        (root / 'SHA256SUMS').write_text(sums)
        return sums

    def test_complete_initial_payload_hashes_then_missing_or_changed_image_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sums = self.fixture(root)
            self.assertEqual(len(verify_extracted_files(root)), 5)
            (root / 'images/system.img').write_text('tampered')
            with self.assertRaises(ValueError):
                verify_extracted_files(root)
            (root / 'SHA256SUMS').write_text('\n'.join(sums.splitlines()[:-1]) + '\n')
            with self.assertRaises(ValueError):
                verify_extracted_files(root)

    def test_checksum_alias_duplicate_and_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sums = self.fixture(root)
            for extra in (sums.splitlines()[0], 'a' * 64 + '  ../outside', 'a' * 64 + '  /absolute'):
                (root / 'SHA256SUMS').write_text(sums + extra + '\n')
                with self.assertRaises(ValueError):
                    verify_extracted_files(root)
            (root / 'SHA256SUMS').write_text(sums)
            (root / 'images/system.img').unlink()
            (root / 'images/system.img').symlink_to(root / 'manifest.json')
            with self.assertRaises(ValueError):
                verify_extracted_files(root)

    def test_exact_actual_api26_boot_completion_udid_contract(self):
        text = '26 \nOpenHarmony-7.0.0.39 \ntrue \nudid of current device is :\n' + 'A' * 64 + '\n'
        self.assertEqual(check_guest_version(text), 'A' * 64)
        for invalid in (text.replace('26 ', '23 '), text.replace('true', 'false'), text + 'A' * 64,
                        text.replace('OpenHarmony-7.0', 'OpenHarmony-6.1')):
            with self.assertRaises(ValueError):
                check_guest_version(invalid)

    def test_cleanup_uses_only_the_owned_popen_handle_not_pid_files_or_shared_server(self):
        args = argparse.Namespace(archive=Path('/synthetic.tar.gz'), purpose='diagnostic', hdc_port=5555)
        guest = QemuGuest(args)
        guest.process = Mock()
        guest.process.poll.return_value = None
        guest.process.wait.side_effect = [subprocess.TimeoutExpired('owned', 10), 0]
        guest.process.pid = 12345
        with patch('boot_package.os.killpg') as kill:
            guest.close()
            self.assertEqual([call.args[0] for call in kill.call_args_list], [12345, 12345])
        guest.process.terminate.assert_not_called()
        guest.process.kill.assert_not_called()
        guest.process.poll.return_value = 0
        guest.process.reset_mock()
        with patch('boot_package.os.killpg') as kill:
            guest.close()
            kill.assert_not_called()
        guest.process.terminate.assert_not_called()
        guest.process.kill.assert_not_called()

    def test_boot_scope_does_not_attest_apis_and_never_uses_periodic_input(self):
        args = argparse.Namespace(archive=Path('/synthetic.tar.gz'), purpose='acceptance', hdc_port=5555)
        guest = QemuGuest(args)
        self.assertFalse(guest.report['first_artifact_behavior_gate_passed'])
        self.assertFalse(guest.report['test_environment']['external_keepalive'])
        source = Path(__file__).with_name('boot_package.py').read_text()
        for forbidden in ('input-send-event', 'system_wakeup', 'LD_PRELOAD=', 'setenforce', "'kill'"):
            self.assertNotIn(forbidden, source)
        self.assertIn("inputs.get('files_sha256') != files", source)

    def test_failed_enter_cleans_owned_processes_and_reraises_interrupt_or_error(self):
        for error in (KeyboardInterrupt(), SystemExit(7), ValueError('boot failure'),
                      RuntimeError('unexpected boot failure')):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                args = argparse.Namespace(archive=Path('/synthetic.tar.gz'), purpose='diagnostic',
                                          hdc_port=5555, output=Path(directory) / 'boot')
                guest = QemuGuest(args)
                with patch('boot_package.port_available'), patch('boot_package.checksum', side_effect=error), \
                        patch.object(guest, 'close') as close, patch.object(guest, 'save') as save:
                    with self.assertRaises(type(error)) as raised:
                        guest.__enter__()
                    self.assertIs(raised.exception, error)
                    save.assert_called_once_with()
                    close.assert_called_once_with()
                self.assertEqual(guest.report['status'], 'fail')
                self.assertEqual(guest.report['failures'], [str(error) or type(error).__name__])

    def test_failure_evidence_error_does_not_skip_owned_process_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(archive=Path('/synthetic.tar.gz'), purpose='diagnostic',
                                      hdc_port=5555, output=Path(directory) / 'boot')
            guest = QemuGuest(args)
            with patch('boot_package.port_available'), \
                    patch('boot_package.checksum', side_effect=KeyboardInterrupt()), \
                    patch.object(guest, 'save', side_effect=OSError('evidence storage unavailable')), \
                    patch.object(guest, 'close') as close:
                with self.assertRaises(OSError):
                    guest.start()
                close.assert_called_once_with()
            self.assertEqual(guest.report['failures'], ['KeyboardInterrupt'])

    def test_private_port_range(self):
        for value in (True, 80, 65536, '5555'):
            with self.assertRaises(ValueError):
                port_available(value)

    def test_power_key_requires_actual_unmatched_s2idle(self):
        self.assertFalse(kernel_sleeping(''))
        self.assertFalse(kernel_sleeping('QEMU paused; CPUs halted'))
        entry, exit_ = 'PM: suspend entry (s2idle)', 'PM: suspend exit'
        self.assertTrue(kernel_sleeping(entry))
        self.assertFalse(kernel_sleeping(entry + '\n' + exit_))
        self.assertTrue(kernel_sleeping(entry + '\n' + exit_ + '\n' + entry))
        self.assertFalse(kernel_sleeping('PM: suspend entry (deep)'))


if __name__ == '__main__':
    unittest.main()
