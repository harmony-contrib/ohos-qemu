"""Actual host socket helper fixtures, never QEMU/HDI/public API acceptance."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

from serial_host_echo import expected_frame, receive_exact, FRAME_SIZES

RUN = '98623ef520f448c3b573047d1752f864'


class SerialHostEchoFixtureTest(unittest.TestCase):
    def test_real_private_unix_transport_fixture_not_guest(self):
        with tempfile.TemporaryDirectory(prefix='serial-host-fixture-') as temporary:
            directory = Path(temporary)
            endpoint = directory / 'data.sock'
            transcript = directory / 'host.jsonl'
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(endpoint))
                os.chmod(endpoint, 0o600)
                server.listen(1)
                server.settimeout(10)
                process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('serial_host_echo.py')),
                                            '--socket', str(endpoint), '--run-id', RUN,
                                            '--output', str(transcript), '--hold-seconds', '0'],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    with server.accept()[0] as connected:
                        connected.settimeout(10)
                        for phase in FRAME_SIZES:
                            expected = expected_frame(RUN, phase)
                            # Exercise receive_exact with deliberately split stream writes.
                            connected.sendall(expected[:5])
                            connected.sendall(expected[5:])
                            self.assertEqual(receive_exact(connected, len(expected)), expected)
                    stdout, stderr = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertIn('no guest/package acceptance', stdout)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.communicate(timeout=10)
            rows = [json.loads(line) for line in transcript.read_text().splitlines()]
            self.assertEqual([row['phase'] for row in rows], list(FRAME_SIZES))
            self.assertTrue(all(row['echo_completed'] and row['echo_bytes'] == row['frame_size'] for row in rows))

    def test_eof_is_not_successful_zero_byte_frame(self):
        # A closed peer gives a genuine EOF, not a mock.
        pair = socket.socketpair()
        try:
            pair[1].close()
            with self.assertRaises(EOFError):
                receive_exact(pair[0], 1)
        finally:
            pair[0].close()


if __name__ == '__main__':
    unittest.main()
