"""Primitives for capability stages on the original Owner's one held guest.

This module has no VM, HDC, Docker, compiler or lease constructor. Commands and
long-lived guest transports use that Owner's existing process authority. Raw
stdout/stderr are captured before adapters reshape receipts. No result here is
a capability verdict.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import time

from guest_ui import GuestUi
from hdc_transport import failed as hdc_failed


def require(ok, message):
    if not ok:
        raise ValueError(message)


def reference(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(),
            'actual regular absolute raw artifact required')
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


class OwnedIO:
    def __init__(self, owner, guest, output, *, run_id, package_inputs, prepare_callers, https_factory):
        require(owner.vm is guest and callable(prepare_callers) and callable(https_factory),
                'original held Owner and fixed source callbacks required')
        owner.held_binding(guest)
        require(re.fullmatch('[a-f0-9]{32}', run_id) is not None, 'fresh actual stage run required')
        self.run_id = run_id
        self.owner, self.guest = owner, guest
        self.output = Path(output)
        require(self.output.is_absolute() and self.output.resolve() == self.output and
                self.output.is_relative_to(owner.output) and not self.output.exists(),
                'fresh stage output under the original Owner required')
        self.output.mkdir()
        self.hdc, self.target = owner.hdc, guest.target
        self.boot_id = guest.report['test_environment']['boot_id']
        self.udid = guest.udid
        self.archive_sha256 = guest.report['archive_sha256']
        require(type(package_inputs) is dict, 'actual package input descriptors required')
        self.package_inputs = package_inputs
        self.environment = dict(owner.env)
        self.receipts, self.qmp_receipts, self._cleanup, self._long = [], [], [], {}
        self._prepare, self._https_factory = prepare_callers, https_factory
        self._https = None
        self._closed = False
        self._cleanup_attempt = 0
        self._serial = 0
        self.ui = GuestUi(self._ui_command, self.hdc, self.target, self.output / 'ui')
        self.register_cleanup(self._stop_guest_transports)

    def _next(self, label):
        require(not self._closed and re.fullmatch('[A-Za-z0-9_-]+', label) is not None,
                'fixed source command label required')
        self._serial += 1
        return 'cap578_%05d_%s' % (self._serial, label)

    def _save(self):
        (self.output / 'io.json').write_text(json.dumps({
            'scope': 'actual_original_Owner_IO_only_NOT_acceptance',
            'archive_sha256': self.archive_sha256, 'boot_id': self.boot_id,
            'commands': self.receipts, 'qmp': self.qmp_receipts, 'closed': self._closed,
            'held_transports': {key: {'pid': row['child'].pid, 'argv': row['argv'],
                'stdout': str(row['out']), 'stderr': str(row['err']),
                'exit_code': row['child'].returncode, 'reaped': row['child'].reaped}
                for key, row in self._long.items()}}, ensure_ascii=False, indent=2) + '\n')

    def command(self, argv, label, timeout=60, allow_failure=False, *, cwd=None, env=None):
        """Return actual streams, including real empty stderr, never guessed ones."""
        self.owner.held_binding(self.guest)
        argv = list(map(str, argv))
        if argv and argv[0] == 'java':
            # The original signer uses this fixed literal. Bind it to the
            # already admitted JDK rather than leaving PATH to choose a tool.
            argv[0] = str(Path(self.environment['JAVA_HOME']) / 'bin/java')
        require(argv and all('\x00' not in value for value in argv) and 0 < timeout <= 3600,
                'bounded literal argv required')
        name = self._next(label)
        log = self.output / (name + '.log')
        if argv[0] == self.hdc:
            require(cwd is None and env is None and argv[1:3] == ['-t', self.target] and
                    len(argv) >= 4 and argv[3] in {'shell', 'file', 'install', 'uninstall', 'rport', 'fport', 'target'},
                    'actual one-guest HDC operation required')
            # rport/fport are the fixed fixture's mapping on this same retained
            # foreground HDC, not a new HDC server or endpoint constructor.
            if argv[3] in {'rport', 'fport', 'target'}:
                actual, stdout, stderr = self.owner.direct(argv, label=name, timeout=timeout, log=log)
            else:
                actual, stdout, stderr = self.owner.guest_command(self.guest, argv, label=name,
                                                               timeout=timeout, log=log)
            self.guest.report['commands'].append(dict(actual))
            self.guest.save()
        else:
            tools = {'java', 'openssl', '/usr/bin/nice'}
            tools.update(str(Path(self.environment[k]) / 'bin' / n) for k, n in
                         (('JAVA_HOME', 'java'), ('QEMU_TEST_NODE_HOME', 'node')) if k in self.environment)
            require(argv[0] in tools, 'unknown capability fixture executable')
            require(cwd is None or (Path(cwd).is_absolute() and Path(cwd).resolve() == Path(cwd) and
                    Path(cwd).is_relative_to(self.owner.output)), 'fixture cwd must belong to this Owner')
            # The fixed builder/peer supplies source-defined argv; parameter JSON
            # cannot choose an executable. All descendants retain this group.
            actual, stdout, stderr = self.owner.direct(argv, label=name, timeout=timeout, log=log,
                                                       cwd=cwd, env=env)
        require(actual['argv'] == argv and type(actual['exit_code']) is int and
                log.read_bytes() == (stdout + stderr).encode(), 'original actual command receipt differs')
        out, err = self.output / (name + '.stdout'), self.output / (name + '.stderr')
        out.write_text(stdout); err.write_text(stderr)
        row = {'argv': argv, 'exit_code': actual['exit_code'], 'stdout': stdout, 'stderr': stderr,
               'stdout_ref': reference(out), 'stderr_ref': reference(err), 'log': reference(log),
               'boot_id': self.boot_id, 'timed_out': bool(actual.get('timed_out', False))}
        self.receipts.append(row); self._save()
        if not allow_failure:
            require(not row['timed_out'] and row['exit_code'] == 0 and
                    (argv[0] != self.hdc or not hdc_failed(stdout, stderr)),
                    'actual capability command failed: ' + name)
        return row

    @staticmethod
    def ref_receipt(row):
        receipt = {k: row[k] for k in ('argv', 'exit_code', 'boot_id', 'timed_out')} | {
            'stdout': row['stdout_ref'], 'stderr': row['stderr_ref']}
        if 'transport_exit_code' in row:
            receipt.update(exit_code=row['transport_exit_code'], shell_exit_code=row['shell_exit_code'],
                stdout=row['transport_stdout_ref'], shell_stdout=row['stdout_ref'])
        return receipt

    def shell(self, script, label, timeout=60, allow_failure=False):
        require(type(script) is str and '\x00' not in script, 'literal fixed guest program required')
        marker = '__CAP578_EXIT_' + secrets.token_hex(16) + '__='
        # Isolate explicit exit/exec in existing identity programs from the
        # outer status footer. shlex.join quotes the entire literal program.
        program = shlex.join(['sh', '-c', script]) + '; cap578_rc=$?; printf "\\n' + marker + '%s\\n" "$cap578_rc"'
        row = self.command([self.hdc, '-t', self.target, 'shell', program], label, timeout,
                           allow_failure=True)
        from guest_ui import command_exit
        body, code = command_exit(row['stdout'], marker)
        body_path = self.output / (self._next('guest_body') + '.stdout')
        body_path.write_text(body)
        row.update(shell_stdout=body, shell_stdout_ref=reference(body_path), shell_exit_code=code)
        self._save()
        if not allow_failure:
            require(code == 0 and row['exit_code'] == 0 and not hdc_failed(row['stdout'], row['stderr']),
                    'actual guest program failed: ' + label)
        # The adapter sees the program body/status. The retained receipt still
        # has the actual HDC stdout/status and the nonce-bound footer proving
        # the separate guest status; neither stream is manufactured.
        return dict(row, stdout=body, stdout_ref=reference(body_path), exit_code=code,
            transport_stdout=row['stdout'], transport_stdout_ref=row['stdout_ref'],
            transport_exit_code=row['exit_code'])

    def _ui_command(self, argv, label):
        return self.command(argv, label)['stdout']

    def send(self, local, remote, label):
        reference(local)
        require(type(remote) is str and remote.startswith('/'), 'absolute guest target required')
        return self.command([self.hdc, '-t', self.target, 'file', 'send', str(local), remote], label)

    def receive(self, remote, local, label):
        local = Path(local)
        require(local.is_absolute() and local.is_relative_to(self.output) and not local.exists(),
                'fresh owned receive output required')
        local.parent.mkdir(parents=True, exist_ok=True)
        return self.command([self.hdc, '-t', self.target, 'file', 'recv', remote, str(local)], label)

    def qmp(self, name, args=None):
        self.owner.held_binding(self.guest)
        label = self._next('qmp')
        request_path, response_path = (self.output / (label + suffix)
                                       for suffix in ('.request.jsonl', '.response.jsonl'))
        row = {'execute': name, 'arguments': args or {}, 'boot_id': self.boot_id, 'completed': False}
        self.qmp_receipts.append(row)
        try:
            with request_path.open('xb') as requests, response_path.open('xb') as responses:
                def trace(kind, data):
                    require(kind in ('request', 'response') and type(data) is bytes,
                            'original QMP wire bytes required')
                    stream = requests if kind == 'request' else responses
                    stream.write(data); stream.flush()
                reply = self.guest.qmp(name, args, trace=trace)
            row.update(reply=reply, completed=True)
            return row
        finally:
            row.update(request=reference(request_path), response=reference(response_path))
            self._save()

    def frame(self, label):
        name = self._next(label)
        path = self.output / (name + '.ppm')
        self.qmp('screendump', {'filename': str(path)})
        return reference(path)

    def prepare_callers(self, family, case, run, roles, parameters):
        self.owner.held_binding(self.guest)
        return self._prepare(self, family, case, run, roles, parameters)

    def register_cleanup(self, function):
        require(callable(function), 'fixed source cleanup callable required')
        self._cleanup.append(function)

    def spawn_guest(self, script, label):
        self.owner.held_binding(self.guest)
        name = self._next(label)
        out, err = self.output / (name + '.stdout'), self.output / (name + '.stderr')
        marker = '__CAP578_LONG_EXIT_' + secrets.token_hex(16) + '__='
        program = shlex.join(['sh', '-c', script]) + '; cap578_rc=$?; printf "\\n' + marker + '%s\\n" "$cap578_rc"'
        argv = [self.hdc, '-t', self.target, 'shell', program]
        # Only the original Authority constructs the process and keeps WNOWAIT
        # identity through final group closure. This layer never reaps it.
        with out.open('xb') as stdout, err.open('xb') as stderr:
            child = self.owner.authority.spawn(argv, label=name, stdin=-1,
                stdout=stdout, stderr=stderr, env=self.owner.env,
                start_new_session=True, umask=0o077)
        self._long[name] = {'child': child, 'argv': argv, 'out': out, 'err': err, 'marker': marker}
        self._save()
        return name

    def write_stdin(self, key, data):
        row = self._long[key]; child = row['child']
        child.assert_held()
        require(child.poll() is None and type(data) is bytes and 0 < len(data) <= 65536,
                'live original held transport and bounded wire bytes required')
        child.real.stdin.write(data); child.real.stdin.flush()
        path = self.output / (self._next('stdin') + '.bin')
        path.write_bytes(data)
        return {'key': key, 'pid': child.pid, 'raw': reference(path), 'boot_id': self.boot_id}

    def wait(self, key, timeout=30):
        require(0 < timeout <= 120, 'bounded original held wait required')
        row = self._long[key]; child = row['child']
        code = child.wait(timeout)
        from guest_ui import command_exit
        transport = row['out'].read_text()
        body, guest_code = command_exit(transport, row['marker'])
        body_path = self.output / (key + '.guest.stdout')
        body_path.write_text(body)
        return {'key': key, 'argv': row['argv'], 'exit_code': guest_code, 'shell_exit_code': guest_code,
                'transport_exit_code': code, 'boot_id': self.boot_id, 'stdout': body,
                'stderr': row['err'].read_text(), 'timed_out': False,
                'stdout_ref': reference(body_path), 'stderr_ref': reference(row['err']),
                'transport_stdout': transport, 'transport_stdout_ref': reference(row['out'])}

    def _stop_guest_transports(self):
        errors = []
        for key, row in reversed(tuple(self._long.items())):
            child = row['child']
            try:
                if child.real.stdin and not child.real.stdin.closed:
                    child.real.stdin.close()
                if child.poll() is None:
                    child.signal(signal.SIGTERM)
                    try:
                        child.wait(5)
                    except subprocess.TimeoutExpired:
                        child.signal(signal.SIGKILL); child.wait(5)
                self.wait(key, 5)
            except Exception as error:
                errors.append(key + ': ' + repr(error))
        require(not errors, 'held guest transport cleanup incomplete: ' + repr(errors))

    def https_start(self, spec, state, handler_factory, wrap_socket):
        require(self._https is None, 'one original owned HTTPS fixture only')
        self._https = self._https_factory(self, spec, state, handler_factory, wrap_socket)
        self.register_cleanup(self.https_close)
        return self._https.start()

    def https_publish(self, payload):
        require(self._https is not None, 'actual owned HTTPS peer missing')
        return self._https.publish(payload)

    def https_collect(self):
        require(self._https is not None, 'actual owned HTTPS peer missing')
        return self._https.collect()

    def https_close(self):
        if self._https is not None:
            return self._https.close()

    def close(self):
        require(not self._closed, 'stage cleanup may run only once')
        self._cleanup_attempt += 1
        errors = []
        for function in reversed(self._cleanup):
            try:
                function()
            except Exception as error:
                errors.append(type(error).__name__ + ': ' + str(error))
        self._closed = not errors
        path = self.output / ('cleanup-%05d.json' % self._cleanup_attempt)
        path.write_text(json.dumps({'boot_id': self.boot_id,
            'errors': errors, 'cleanup_complete': not errors}, indent=2) + '\n')
        self._save()
        require(not errors, 'capability stage resources remain unsettled: ' + repr(errors))
        self.owner.held_binding(self.guest)
        return reference(path)
