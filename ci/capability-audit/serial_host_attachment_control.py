#!/usr/bin/env python3
"""Operator-controlled connection to a private, dedicated QEMU Serial backend.

With usb-serial always-plugged=off, connect/disconnect changes the actual QEMU
attachment. Journal entries prove only host socket operations, never guest
enumeration, hardware identity, authorization, or new-package acceptance.
No VM, QMP endpoint, SA, permission, or data transfer is simulated here.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import time

SCOPE = 'real_host_socket_operations_NOT_guest_device_UI_or_package_acceptance'
CONNECT_TIMEOUT_SECONDS = 10


def endpoint_identity(endpoint):
    if endpoint.is_symlink():
        raise ValueError('dedicated backend must not be a symlink')
    parent = endpoint.parent.stat()
    metadata = endpoint.stat()
    if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError('backend directory must be caller-owned and mode 0700')
    if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
        raise ValueError('backend must be a caller-owned private Unix socket')
    return metadata.st_dev, metadata.st_ino


class AttachmentControl:
    def __init__(self, endpoint, run_id, journal):
        self.endpoint = endpoint
        self.run_id = run_id
        self.journal = journal
        self.identity = endpoint_identity(endpoint)
        self.connection = None
        self.sequence = 0

    def record(self, operation, completed, error=None):
        self.sequence += 1
        row = {'kind': 'serial_host_attachment', 'run_id': self.run_id,
               'sequence': self.sequence, 'host_time_ns': time.time_ns(),
               'operation': operation, 'host_operation_completed': completed,
               'host_socket_connected': self.connection is not None,
               'socket_path': str(self.endpoint), 'host_uid': os.geteuid(),
               'scope': SCOPE, 'first_package_gate_passed': False,
               'hardware_UI_acceptance_established': False}
        if error is not None:
            row['error'] = str(error)
        self.journal.write(json.dumps(row) + '\n')
        self.journal.flush()

    def attach(self):
        if self.connection is not None:
            raise ValueError('already connected; detach before a new attachment')
        if endpoint_identity(self.endpoint) != self.identity:
            raise ValueError('backend socket was replaced; start a fresh scoped run')
        connected = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connected.settimeout(CONNECT_TIMEOUT_SECONDS)
            connected.connect(str(self.endpoint))
            if endpoint_identity(self.endpoint) != self.identity:
                raise ValueError('backend changed during connection')
        except (OSError, ValueError):
            connected.close()
            raise
        self.connection = connected
        self.record('attach', True)

    def detach(self, operation='detach'):
        if self.connection is None:
            raise ValueError('not connected; no attachment can be detached')
        connected, self.connection = self.connection, None
        try:
            connected.shutdown(socket.SHUT_RDWR)
        finally:
            connected.close()
        self.record(operation, True)


def operate(control, commands):
    control.record('begin', True)
    try:
        for line in commands:
            command = line.strip()
            if command == 'attach':
                control.attach()
            elif command == 'detach':
                control.detach()
            elif command == 'quit':
                if control.connection is not None:
                    control.detach('quit_detach')
                control.record('quit', True)
                return 0
            else:
                raise ValueError('commands are exactly attach, detach, or quit')
            print(command + ' complete (host socket only; verify actual guest state)', flush=True)
    except (OSError, ValueError) as error:
        control.record('failure', False, error)
        return 1
    finally:
        if control.connection is not None:
            try:
                control.detach('cleanup_detach')
            except OSError as error:
                control.record('cleanup_failure', False, error)
    control.record('unexpected_eof', False, 'explicit quit required for an operator-controlled run')
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{32}', args.run_id):
        parser.error('run-id needs 32 lowercase hex digits from the fresh ordinary HAP inputs')
    endpoint = args.socket.absolute()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as journal:
        control = AttachmentControl(endpoint, args.run_id, journal)
        print('Commands: attach, detach, quit. Retain guest sysfs/stat and actual UI evidence.', flush=True)
        return operate(control, sys.stdin)


if __name__ == '__main__':
    raise SystemExit(main())
