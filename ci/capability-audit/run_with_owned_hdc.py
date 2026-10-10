#!/usr/bin/env python3
"""Run the packaged suite with an owned foreground HDC, never restart a shared one.

HDC's POSIX singleton lock is in TMPDIR, not keyed by server port. Isolate both.
The private temp directory is retained as diagnostic evidence on failure/success.
No test command is retried and no guest failure is converted to success.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from hdc_transport import failed


def stop_owned(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run(argv, output, hdc):
    output.mkdir(parents=True, exist_ok=False)
    private_tmp = tempfile.mkdtemp(prefix='oq-hdc-', dir='/tmp')
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    environment = dict(os.environ, TMPDIR=private_tmp, OHOS_HDC_SERVER_PORT=str(port), HDC=str(hdc))
    server_argv = [str(hdc), '-l', '4', '-s', '127.0.0.1:' + str(port), '-m']
    report = dict(status='fail', scope='host_transport_only_NOT_guest_behavior',
        server_argv=server_argv, server_port=port, private_tmp=private_tmp,
        child_argv=list(map(str, argv)), shared_server_restarted=False, commands_retried=False)
    server = None
    try:
        with (output / 'server.log').open('x') as log:
            server = subprocess.Popen(server_argv, env=environment, stdout=log,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            report['owned_server_pid'] = server.pid
            deadline = time.monotonic() + 15
            while True:
                if server.poll() is not None:
                    raise ValueError('owned HDC exited during startup')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ValueError('owned HDC startup deadline exceeded')
                    time.sleep(0.1)
            check = subprocess.run([str(hdc), '-p', 'checkserver'], env=environment,
                capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
            (output / 'checkserver.log').write_text(check.stdout + check.stderr)
            if check.returncode or failed(check.stdout, check.stderr) or not check.stdout.strip():
                raise ValueError('owned HDC handshake failed')
            # In particular, do not take over a port whose reservation was raced.
            locks = list(Path(private_tmp).glob('.*.pid'))
            if not any(p.read_text().strip() == str(server.pid) for p in locks):
                raise ValueError('private HDC singleton lock does not belong to owned process')
            result = subprocess.run(argv, env=environment, stdin=subprocess.DEVNULL)
            report['child_exit_code'] = result.returncode
            if server.poll() is not None:
                raise ValueError('owned HDC exited before validation ended')
            report['status'] = 'pass' if result.returncode == 0 else 'fail'
            return result.returncode
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
        return 1
    finally:
        if server is not None:
            stop_owned(server)
            report['owned_server_exit_code'] = server.returncode
            report['owned_server_closed'] = server.poll() is not None
        report['files_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in output.glob('*.log')}
        (output / 'transport.json').write_text(json.dumps(report, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-output', type=Path, required=True)
    args, _ = parser.parse_known_args()
    hdc = shutil.which(os.environ.get('HDC', 'hdc'))
    if not hdc:
        parser.error('HDC executable is required')
    return run([sys.executable, str(Path(__file__).with_name('run_packaged_qemu_suite.py')),
                *sys.argv[1:]], Path(str(args.evidence_output) + '.hdc'), Path(hdc))


if __name__ == '__main__':
    raise SystemExit(main())
