"""Real private Unix socket fixtures; not QEMU/HDI/UI/guest acceptance."""
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest

from serial_host_attachment_control import AttachmentControl, endpoint_identity, operate

RUN = '98623ef520f448c3b573047d1752f864'


class SerialHostAttachmentControlFixtureTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='serial-host-attachment-fixture-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.endpoint = self.directory / 'data.sock'
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(self.server.close)
        self.server.bind(str(self.endpoint))
        os.chmod(self.endpoint, 0o600)
        self.server.listen(4)
        self.server.settimeout(2)
        self.journal = io.StringIO()
        self.control = AttachmentControl(self.endpoint, RUN, self.journal)
        self.addCleanup(self.close_connection)

    def close_connection(self):
        if self.control.connection is not None:
            self.control.connection.close()

    def rows(self):
        return [json.loads(line) for line in self.journal.getvalue().splitlines()]

    def test_real_connect_detach_and_reconnect(self):
        for sequence in range(2):
            self.control.attach()
            with self.server.accept()[0] as peer:
                peer.settimeout(2)
                self.control.detach()
                self.assertEqual(peer.recv(1), b'')
        rows = self.rows()
        self.assertEqual([row['operation'] for row in rows], ['attach', 'detach'] * 2)
        self.assertEqual([row['sequence'] for row in rows], [1, 2, 3, 4])
        self.assertTrue(all(row['host_operation_completed'] for row in rows))
        self.assertTrue(all(row['first_package_gate_passed'] is False for row in rows))

    def test_duplicate_attach_and_empty_detach_fail(self):
        with self.assertRaises(ValueError):
            self.control.detach()
        self.control.attach()
        with self.assertRaises(ValueError):
            self.control.attach()
        self.assertEqual(len(self.rows()), 1)

    def test_broad_directory_or_socket_access_rejected(self):
        os.chmod(self.directory, 0o755)
        with self.assertRaises(ValueError):
            endpoint_identity(self.endpoint)
        os.chmod(self.directory, 0o700)
        os.chmod(self.endpoint, 0o660)
        with self.assertRaises(ValueError):
            endpoint_identity(self.endpoint)

    def test_symlink_and_replaced_backend_rejected(self):
        linked = self.directory / 'linked.sock'
        linked.symlink_to(self.endpoint)
        with self.assertRaises(ValueError):
            endpoint_identity(linked)
        # Move only this fixture's endpoint; no user/QEMU socket is touched.
        self.endpoint.rename(self.directory / 'original.sock')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as replacement:
            replacement.bind(str(self.endpoint))
            os.chmod(self.endpoint, 0o600)
            replacement.listen(1)
            with self.assertRaises(ValueError):
                self.control.attach()

    def test_operator_sequence_and_explicit_quit(self):
        self.assertEqual(operate(self.control, ['attach\n', 'detach\n', 'attach\n', 'quit\n']), 0)
        self.assertEqual([row['operation'] for row in self.rows()],
                         ['begin', 'attach', 'detach', 'attach', 'quit_detach', 'quit'])
        self.assertIsNone(self.control.connection)

    def test_eof_and_unknown_command_are_not_success(self):
        self.assertEqual(operate(self.control, ['attach\n']), 1)
        self.assertEqual(self.rows()[-1]['operation'], 'unexpected_eof')
        self.assertFalse(self.rows()[-1]['host_operation_completed'])
        self.journal = io.StringIO()
        self.control.journal = self.journal
        self.assertEqual(operate(self.control, ['arbitrary_qmp_command\n']), 1)
        self.assertEqual(self.rows()[-1]['operation'], 'failure')


if __name__ == '__main__':
    unittest.main()
