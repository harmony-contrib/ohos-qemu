"""Parent-owned HTTPS fixture primitives. Nothing here starts a server/process.

The original Owner creates the listener, generated certificates, exact HDC
rport, guest hosts/CA fixture and append-only output files, and tears them down.
No caller/API response is injected into the guest. Only ordinary HTTPS bytes
are served to the real OS AppDomainVerify agent.
"""
import hashlib
from http.server import BaseHTTPRequestHandler
import ssl
from threading import Lock
from time import monotonic_ns

from system_services578_project import require, validate

PHASES = ('match', 'fingerprint-mismatch', 'revoke', 'server-error', 'untrusted-cert', 'wrong-host', 'retry')


def fixture_spec(run_id):
    """Concrete reserved DNS names and exact guest resources for one owned VM."""
    hosts = {'host': 'a-' + run_id[:12] + '.services578.test',
             'other_host': 'b-' + run_id[:12] + '.services578.test'}
    validate('domain', run_id, 'target', hosts)
    return {'hosts': hosts, 'guest_hosts_path': '/system/etc/hosts',
            'hosts_line': '127.0.0.1 ' + ' '.join(hosts.values()) + '\n',
            'guest_ca_directory': '/system/etc/security/certificates',
            'guest_listener': '127.0.0.1:443', 'host_listener': '127.0.0.1',
            'transport': 'owned-hdc-rport', 'rport_arguments': ['rport', 'tcp:443'],
            'verification': {'peer': 1, 'host': 2},
            'asset_path': '/.well-known/applinking.json', 'minimum_tls': 'TLSv1.2'}


class PeerState:
    """Shared HTTP/TLS facts only; the parent retains all resource ownership."""

    def __init__(self, run_id, hosts, append_raw):
        validate('domain', run_id, 'target', hosts)
        require(callable(append_raw), 'parent append-only raw writer required')
        self.run_id, self.hosts, self.append_raw = run_id, dict(hosts), append_raw
        self.lock = Lock()
        self.current = None
        self.contexts = {}
        self.names = {}
        self.serial = 0

    def publish(self, payload):
        require(payload['generation'] in PHASES and payload['host'] == self.hosts['host'] and
                payload['tls_profile'] in ('trusted', 'untrusted-cert', 'wrong-host'), 'fixed peer phase required')
        body = payload['body'].encode()
        require(len(body) <= 20480 and hashlib.sha256(body).hexdigest() == payload['body_sha256'] and
                payload['status'] in (200, 500), 'bounded exact actual HTTPS body/status required')
        with self.lock:
            self.current = dict(payload)

    def snapshot(self):
        with self.lock:
            require(self.current is not None, 'parent must publish before an OS installation starts verification')
            return dict(self.current)

    def register_context(self, profile, certificate_path, private_key_path):
        require(profile in ('trusted', 'untrusted-cert', 'wrong-host'), 'fixed TLS profile required')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certificate_path, private_key_path)

        def sni(connection, name, _context):
            with self.lock:
                self.names[id(connection)] = name
        context.set_servername_callback(sni)
        self.contexts[profile] = context


def wrap_accepted_socket(state, accepted_socket, address):
    """Called by the parent's original HTTPS listener get_request adapter.

    It records native TLS handshakes/alerts before HTTP exists, so an untrusted
    CA/wrong SAN cannot be counted as an application rejection or absent data.
    A failed wrapped socket is closed here because SSL wrapping detaches the
    original descriptor; the parent still owns listener/server lifetime.
    """
    snapshot = state.snapshot()
    profile = snapshot['tls_profile']
    require(profile in state.contexts, 'actual generated certificate context missing')
    with state.lock:
        state.serial += 1
        serial = state.serial
    connection = None
    record = {'run_id': state.run_id, 'generation': snapshot['generation'], 'connection_id': serial,
              'peer_ip': address[0], 'peer_port': address[1], 'tls_profile': profile,
              'host_monotonic_ns': monotonic_ns(), 'sni': None, 'handshake_error': None}
    try:
        connection = state.contexts[profile].wrap_socket(accepted_socket, server_side=True,
                                                       do_handshake_on_connect=False)
        connection.settimeout(20)
        connection.do_handshake()
        record['cipher'] = connection.cipher()
        record['tls_version'] = connection.version()
        return connection
    except (ssl.SSLError, TimeoutError, OSError) as error:
        record['handshake_error'] = {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
            'library': getattr(error, 'library', None), 'reason': getattr(error, 'reason', None), 'message': str(error)}
        if connection is not None:
            connection.close()
        raise
    finally:
        if connection is not None:
            with state.lock:
                record['sni'] = state.names.pop(id(connection), None)
        state.append_raw('connections', record)


def handler_factory(state):
    """Return an HTTP handler class for the parent's already-owned listener."""
    class AssociationHandler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            snapshot = state.snapshot()
            host = self.headers.get('Host', '').lower()
            valid_path = self.path == '/.well-known/applinking.json'
            if host == state.hosts['host']:
                status, body = snapshot['status'], snapshot['body'].encode()
            elif host == state.hosts['other_host']:
                status, body = 200, snapshot['other_host_body'].encode()
            else:
                status, body = 421, b'unknown test authority'
            if not valid_path:
                status, body = 404, b'unknown test path'
            headers = {'Content-Type': 'application/json', 'Content-Length': str(len(body)),
                       'Cache-Control': 'no-store', 'Connection': 'close',
                       'X-Services578-Generation': snapshot['generation']}
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True
            state.append_raw('requests', {'run_id': state.run_id, 'generation': snapshot['generation'],
                'host_monotonic_ns': monotonic_ns(), 'method': 'GET', 'scheme': 'https', 'host': host,
                'path': self.path, 'peer_ip': self.client_address[0], 'peer_port': self.client_address[1],
                'raw_request_line': self.raw_requestline.decode('iso-8859-1'),
                'request_headers': list(self.headers.raw_items()), 'status': status,
                'response_headers': headers, 'response_sha256': hashlib.sha256(body).hexdigest(),
                'cipher': self.connection.cipher(), 'tls_version': self.connection.version()})

        def log_message(self, *_args):
            # The exact request/status/headers/body hash are captured above.
            pass
    return AssociationHandler
