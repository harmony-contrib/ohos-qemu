#!/usr/bin/env python3
"""Challenge-check bytes from a dedicated QEMU USB-serial Unix socket backend.

This is the real host data endpoint, not a guest SA/HDI mock. Its transcript is
only transport evidence; guest/public API and package boot gates are separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import time

FRAME_HEADER_SIZE = 21
FRAME_SIZES = {1: 64, 2: 4096, 3: 64, 4: 64}


def expected_frame(run_id, phase):
    size = FRAME_SIZES[phase]
    header = bytes([0x53, 0x37, phase, size & 0xff, size >> 8]) + bytes.fromhex(run_id)
    return header + bytes((index + phase) & 0xff for index in range(FRAME_HEADER_SIZE, size))


def receive_exact(connection, size):
    result = bytearray()
    while len(result) < size:
        chunk = connection.recv(size - len(result))
        if not chunk:
            raise EOFError('QEMU disconnected before the full challenge frame')
        result.extend(chunk)
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hold-seconds', type=int, default=60)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{32}', args.run_id) or not 0 <= args.hold_seconds <= 300:
        parser.error('run-id needs 32 lowercase hex digits; hold-seconds must be [0,300]')
    endpoint = args.socket.resolve()
    parent = endpoint.parent.stat()
    if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError('socket must be inside a caller-owned private mode-0700 directory')
    metadata = endpoint.stat()
    if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
        raise ValueError('backend must be a caller-owned private Unix socket')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as journal, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(120)
        connection.connect(str(endpoint))
        for phase in FRAME_SIZES:
            expected = expected_frame(args.run_id, phase)
            received = receive_exact(connection, len(expected))
            matches = received == expected
            row = {'kind': 'serial_host_frame', 'run_id': args.run_id, 'phase': phase,
                   'frame_size': len(received), 'frame_sha256': hashlib.sha256(received).hexdigest(),
                   'expected_sha256': hashlib.sha256(expected).hexdigest(), 'challenge_matched': matches,
                   'echo_bytes': 0, 'echo_completed': False,
                   'scope': 'real_host_transport_only_not_guest_acceptance'}
            if matches:
                try:
                    connection.sendall(received)
                    row.update(echo_bytes=len(received), echo_completed=True)
                except OSError as error:
                    row['send_error'] = str(error)
            journal.write(json.dumps(row) + '\n')
            journal.flush()
            if not matches:
                raise ValueError('unexpected/challenge-mismatching bytes on dedicated backend')
            if not row['echo_completed']:
                raise OSError('actual host echo send failed; no successful transfer is recorded')
        # Keep the hardware attached while guest control/close tests finish.
        connection.settimeout(0.5)
        deadline = time.monotonic() + args.hold_seconds
        while time.monotonic() < deadline:
            try:
                extra = connection.recv(1)
                if extra:
                    journal.write(json.dumps({'kind': 'serial_host_error', 'run_id': args.run_id,
                                              'error': 'unexpected bytes after the four valid API frames',
                                              'extra_sha256': hashlib.sha256(extra).hexdigest()}) + '\n')
                    journal.flush()
                    raise ValueError('unexpected bytes after the four valid API frames')
                break
            except socket.timeout:
                continue
    print('Host transport challenge transcript complete; no guest/package acceptance implied')


if __name__ == '__main__':
    main()
