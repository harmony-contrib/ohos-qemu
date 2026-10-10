"""Synthetic ownership/transport negatives; never live acceptance evidence."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from enclosing_acceptance_guest import EnclosingAcceptanceGuest, validate_binding


def fixture():
    return dict(status='pass', purpose='acceptance', scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
        archive_sha256='a' * 64, test_environment=dict(external_keepalive=False, guest_arch='arm64',
        device_type='phone', qemu_pid=123, qemu_command='qemu -qmp unix:/tmp/test.sock',
        qmp_socket='/tmp/test.sock', target='127.0.0.1:4321',
        boot_id='11111111-2222-3333-4444-555555555555', udid='b' * 64))


class EnclosingGuestTests(unittest.TestCase):
    def test_only_actual_acceptance_binding(self):
        self.assertEqual(validate_binding(fixture(), 'a' * 64)['qemu_pid'], 123)
        for key, value in (('status', 'fail'), ('purpose', 'diagnostic'),
                           ('archive_sha256', 'c' * 64), ('candidate_kernel', 'candidate'),
                           ('diagnostic_power_button', True)):
            item = fixture()
            item[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_binding(item, 'a' * 64)
        for key, value in (('external_keepalive', True), ('qemu_pid', True), ('qemu_pid', 1),
                           ('qmp_socket', 'relative'), ('target', 'remote:4321'),
                           ('boot_id', 'stale'), ('guest_arch', 'unknown'), ('device_type', 'watch')):
            item = fixture()
            item['test_environment'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_binding(item, 'a' * 64)

    def test_real_command_and_guest_exit_required(self):
        with tempfile.TemporaryDirectory() as directory:
            guest = object.__new__(EnclosingAcceptanceGuest)
            guest.target, guest.hdc = '127.0.0.1:4321', '/test/hdc'
            guest.output, guest.report = Path(directory), dict(commands=[])
            token = 'd' * 32
            marker = '__QEMU_CHILD_EXIT_' + token + '__='
            with patch.object(guest, 'healthy'), patch('enclosing_acceptance_guest.secrets.token_hex', return_value=token):
                for stdout, returncode, valid in (('value\n\n' + marker + '0\n', 0, True),
                        ('value\n\n' + marker + '1\n', 0, False), ('value', 0, False),
                        ('[Fail]\n' + marker + '0\n', 0, False),
                        ('value\n\n' + marker + '0\n', 1, False)):
                    result = subprocess.CompletedProcess([], returncode, stdout, '')
                    with patch('enclosing_acceptance_guest.subprocess.run', return_value=result):
                        if valid:
                            self.assertEqual(guest.shell('echo value', 'test'), 'value\n')
                        else:
                            with self.assertRaises(ValueError): guest.shell('echo value', 'test')

    def test_never_owns_process_lifecycle(self):
        source = Path(__file__).with_name('enclosing_acceptance_guest.py').read_text()
        self.assertNotIn('os.kill', source)
        self.assertNotIn('Popen(', source)
        self.assertNotIn('power-shell', source)
        self.assertIn('actual != self.env[\'qemu_command\']', source)
        self.assertIn('digest(self.boot) != self.boot_sha', source)
