"""Owned loopback-only HTTP peer for nonce-bearing ordinary QEMU traffic."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading


def payload(run_id, generation):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or type(generation) is not int or generation not in (0, 1, 2):
        raise ValueError('exact traffic challenge/generation required')
    return run_id.encode('ascii') * (1 if generation == 0 else generation * 4096)


class Endpoint:
    def __init__(self, run_id):
        payload(run_id, 0)
        self.run_id, self.requests, self.errors = run_id, [], []
        self.lock = threading.Lock()
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                self.connection.settimeout(5)
                try:
                    match = re.fullmatch('/' + owner.run_id + '/([012])', self.path)
                    lengths = self.headers.get_all('Content-Length', [])
                    if (not match or len(lengths) != 1 or not lengths[0].isdigit() or
                            self.headers.get('Transfer-Encoding') is not None):
                        raise ValueError('unexpected traffic request path or framing')
                    generation = int(match[1])
                    expected = payload(owner.run_id, generation)
                    if int(lengths[0]) != len(expected):
                        raise ValueError('unexpected traffic payload length')
                    actual = self.rfile.read(len(expected))
                    if actual != expected:
                        raise ValueError('traffic challenge bytes differ')
                    with owner.lock:
                        if generation != len(owner.requests):
                            raise ValueError('duplicate/reordered traffic generation')
                        owner.requests.append(dict(generation=generation, length=len(actual),
                            sha256=hashlib.sha256(actual).hexdigest()))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(len(actual)))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(actual)
                    self.wfile.flush()
                except Exception as error:
                    with owner.lock:
                        owner.errors.append(type(error).__name__ + ': ' + str(error))
                    self.close_connection = True
                    try:
                        self.send_error(400, 'invalid owned traffic request')
                    except OSError:
                        pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = False
        self.server.block_on_close = True
        self.port = self.server.server_address[1]
        self.endpoint = 'http://10.0.2.2:' + str(self.port) + '/' + run_id
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def finish(self, output):
        if not self.closed:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            self.closed = True
        if self.thread.is_alive():
            raise ValueError('owned HTTP listener did not stop')
        report = dict(scope='owned_loopback_HTTP_peer_NOT_guest_or_statistics_acceptance',
            run_id=self.run_id, bind_address='127.0.0.1', endpoint=self.endpoint,
            requests=self.requests, errors=self.errors, listener_closed=True,
            implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        Path(output).write_text(json.dumps(report, indent=2) + '\n')
        return report
