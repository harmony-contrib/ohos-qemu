"""One root-owned HTTPS content peer for the real QEMU AppDomainVerify path.

The host only serves bytes. It never queries the asset itself or writes an OS
association registry. TLS/DNS/CA/rport setup and all actual OS queries run in the
held guest through its fixed bindings. This is not a host validation stage.
"""
from pathlib import Path
from http.server import HTTPServer
import hashlib
import json
import os
import re
import threading

from capability578_owned_io import reference, require


class OwnedHTTPS:
    def __init__(self, io, spec, state_type, handler_factory, wrap_socket):
        self.io, self.spec = io, dict(spec)
        self.root = io.output / 'https-peer'
        self.root.mkdir(mode=0o700)
        self.server = self.thread = None
        self.closed = False
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.active = set()
        self.thread_errors = []
        self.streams = {key: self.root / (key + '.jsonl') for key in ('requests', 'connections')}
        for path in self.streams.values():
            path.write_bytes(b'')
        self.state = state_type(io.run_id, spec['hosts'], self.append)
        self.handler_factory, self.wrap_socket = handler_factory, wrap_socket
        self.commands = []
        self._snapshots = 0

    def append(self, kind, row):
        require(kind in self.streams, 'fixed peer transcript stream required')
        data = (json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n').encode()
        with self.lock, self.streams[kind].open('ab') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())

    def openssl(self, args, label):
        row = self.io.command(['openssl', *map(str, args)], 'https_' + label, timeout=90)
        self.commands.append(self.io.ref_receipt(row))
        return row['stdout']

    def authority(self, name):
        key, certificate = self.root / (name + '.key'), self.root / (name + '.pem')
        self.openssl(['req', '-new', '-newkey', 'rsa:2048', '-nodes', '-x509', '-sha256', '-days', '2',
            '-subj', '/CN=QEMU-services578-' + name, '-keyout', key, '-out', certificate,
            '-addext', 'basicConstraints=critical,CA:TRUE',
            '-addext', 'keyUsage=critical,keyCertSign,cRLSign'], name + '_ca')
        key.chmod(0o600)
        return key, certificate

    def server_certificate(self, name, ca_key, ca_certificate, names):
        key, request, certificate, extensions = (self.root / (name + suffix)
            for suffix in ('.key', '.csr', '.pem', '.extensions'))
        extensions.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
            'extendedKeyUsage=serverAuth\nsubjectAltName=' + ','.join('DNS:' + n for n in names) + '\n')
        self.openssl(['req', '-new', '-newkey', 'rsa:2048', '-nodes', '-sha256',
            '-subj', '/CN=' + names[0], '-keyout', key, '-out', request], name + '_request')
        key.chmod(0o600)
        self.openssl(['x509', '-req', '-sha256', '-days', '2', '-in', request,
            '-CA', ca_certificate, '-CAkey', ca_key, '-CAcreateserial',
            '-extfile', extensions, '-out', certificate], name + '_certificate')
        self.state.register_context(name, str(certificate), str(key))
        return reference(certificate)

    def start(self):
        require(self.server is None and not self.closed, 'fresh owned listener required')
        ca_key, ca = self.authority('trusted-ca')
        untrusted_key, untrusted_ca = self.authority('untrusted-ca')
        hosts = list(self.spec['hosts'].values())
        certificates = {
            'trusted': self.server_certificate('trusted', ca_key, ca, hosts),
            'untrusted-cert': self.server_certificate('untrusted-cert', untrusted_key, untrusted_ca, hosts),
            'wrong-host': self.server_certificate('wrong-host', ca_key, ca, ['wrong.services578.test'])}
        subject_hash = self.openssl(['x509', '-in', ca, '-noout', '-subject_hash'], 'ca_subject_hash').strip()
        require(re.fullmatch('[a-f0-9]{8}', subject_hash), 'actual OpenSSL CA hash required')
        # Empty association is real initial content, so even the first identity
        # installation cannot accidentally inherit a successful association.
        empty = '{"applinking":{"apps":[]}}'
        self.state.publish({'generation': 'revoke', 'host': self.spec['hosts']['host'],
            'body': empty, 'body_sha256': hashlib.sha256(empty.encode()).hexdigest(),
            'status': 200, 'other_host_body': empty, 'tls_profile': 'trusted'})
        owner = self

        class FixedHTTPSListener(HTTPServer):
            allow_reuse_address = False

            def get_request(self):
                accepted, address = super().get_request()
                accepted.settimeout(20)
                with owner.lock:
                    owner.active.add(accepted)
                try:
                    wrapped = owner.wrap_socket(owner.state, accepted, address)
                    with owner.lock:
                        owner.active.discard(accepted)
                        owner.active.add(wrapped)
                    return wrapped, address
                except BaseException:
                    accepted.close()
                    with owner.lock:
                        owner.active.discard(accepted)
                    raise

            def shutdown_request(self, request):
                try:
                    super().shutdown_request(request)
                finally:
                    with owner.lock:
                        owner.active.discard(request)

        self.server = FixedHTTPSListener(('127.0.0.1', 0), self.handler_factory(self.state))
        self.server.timeout = .2

        def serve():
            try:
                while not self.stop.is_set():
                    self.server.handle_request()
            except Exception as error:
                self.thread_errors.append(type(error).__name__ + ': ' + str(error))

        # handle_request has a finite accept timeout. TLS handshake has its
        # original 20-second socket deadline; active HTTP sockets are retained
        # above and explicitly closed before the bounded join.
        self.thread = threading.Thread(target=serve, name='qemu-services578-https', daemon=False)
        self.thread.start()
        port = self.server.server_address[1]
        require(type(port) is int and port >= 1024 and self.thread.is_alive(), 'actual owned high-port peer failed')
        info = {'host_port': port, 'host_listener': '127.0.0.1', 'transport_peer_ip': '127.0.0.1',
            'ca': reference(ca), 'ca_subject_hash': subject_hash, 'certificates': certificates,
            'commands': self.commands, 'boot_id': self.io.boot_id,
            'scope': 'owned_content_peer_NOT_guest_or_host_acceptance'}
        (self.root / 'fixture.json').write_text(json.dumps(info, indent=2) + '\n')
        return info

    def publish(self, payload):
        require(self.server is not None and not self.closed and self.thread.is_alive(), 'actual peer is not running')
        require(payload['generation'] in ('match', 'fingerprint-mismatch', 'revoke', 'server-error',
                'untrusted-cert', 'wrong-host', 'retry'), 'fixed peer publication generation required')
        path = self.root / ('publication-' + payload['generation'] + '.json')
        require(not path.exists(), 'a publication generation cannot be replayed')
        self.state.publish(payload)
        path.write_text(json.dumps(payload, indent=2) + '\n')
        return {'publication': reference(path), 'boot_id': self.io.boot_id}

    def collect(self):
        self._snapshots += 1
        references = {}
        with self.lock:
            for name, original in self.streams.items():
                snapshot = self.root / (name + '-%05d.jsonl' % self._snapshots)
                snapshot.write_bytes(original.read_bytes())
                references[name] = reference(snapshot)
        return dict(references, transport_peer_ip='127.0.0.1', boot_id=self.io.boot_id)

    def close(self):
        if self.closed:
            return reference(self.root / 'cleanup.json')
        errors = []
        self.stop.set()
        if self.server is not None:
            import socket
            with self.lock:
                active = tuple(self.active)
            for connection in active:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # Peer may already have closed; close the actual retained object.
                finally:
                    try:
                        connection.close()
                    except OSError as error:
                        errors.append('active peer close: ' + str(error))
            if self.thread is not None and self.thread.is_alive():
                self.thread.join(timeout=25)
                if self.thread.is_alive():
                    errors.append('original owned HTTPS thread remains alive')
            try:
                self.server.server_close()
            except OSError as error:
                errors.append('listener close: ' + str(error))
        # Preserve peer failures separately from unsettled resources. A dead
        # thread and closed listener can be safely disposed after a failed
        # business case; they must not cause a false cleanup quarantine.
        if not errors:
            self.closed = True
        path = self.root / 'cleanup.json'
        path.write_text(json.dumps({'boot_id': self.io.boot_id, 'errors': errors,
                                   'runtime_errors': list(self.thread_errors),
                                   'listener_closed': not errors}, indent=2) + '\n')
        require(not errors, 'owned HTTPS peer cleanup incomplete: ' + repr(errors))
        return reference(path)
