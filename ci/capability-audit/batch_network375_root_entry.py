"""Root-admitted command constructors shared by the two different peer cases.

No command runs at import.  This class does not acquire a lease or grant Docker,
VM, HDC or signalling authority.  The calling root owner must supply its live
admission and held-Popen registration/termination functions.  JSON flags cannot
stand in for those functions.  Records are observations, never kill authority.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading
import time

PS_COLUMNS = 'pid=,ppid=,pgid=,uid=,lstart='
PS_ARGV = ['/usr/bin/env', 'LC_ALL=C', '/bin/ps', '-axo', PS_COLUMNS]
STAT_FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid',
               'st_size', 'st_mtime_ns', 'st_ctime_ns')


class AdmissionError(ValueError):
    pass


def require(value, message):
    if not value:
        raise AdmissionError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tool_identity(path, *, executable=True):
    """Read a real regular executable and all credential-bearing metadata."""
    path = Path(path).absolute()
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
            (not executable or before.st_mode & 0o111), 'one regular tool inode required')
    raw = path.read_bytes()
    after = path.lstat()
    fields = lambda item: {name: getattr(item, name) for name in STAT_FIELDS}
    require(fields(before) == fields(after), 'executable changed during observation')
    return dict(descriptor=dict(path=str(path), sha256=digest(raw), bytes=len(raw)),
                stat=fields(after))


def query_tools():
    return {name: tool_identity(path) for name, path in
            (('env', PS_ARGV[0]), ('ps', PS_ARGV[2]))}


def expected_query_uid(tools, effective_uid):
    """Derive one EUID for the exact env -> ps chain, including real setuid."""
    require(type(effective_uid) is int and effective_uid >= 0, 'actual effective UID required')
    require(type(tools) is dict and set(tools) == {'env', 'ps'}, 'exact query tool pair required')
    uid = effective_uid
    for name, literal in (('env', PS_ARGV[0]), ('ps', PS_ARGV[2])):
        value = tools[name]
        require(type(value) is dict and set(value) == {'descriptor', 'stat'}, 'whole tool observation required')
        desc, meta = value['descriptor'], value['stat']
        require(type(desc) is dict and set(desc) == {'path', 'sha256', 'bytes'} and
                desc['path'] == literal and type(desc['sha256']) is str and
                re.fullmatch('[a-f0-9]{64}', desc['sha256']) and
                type(desc['bytes']) is int and desc['bytes'] > 0, 'exact query tool descriptor required')
        require(type(meta) is dict and set(meta) == set(STAT_FIELDS) and
                all(type(v) is int and v >= 0 for v in meta.values()) and
                stat.S_ISREG(meta['st_mode']) and meta['st_nlink'] == 1 and
                meta['st_size'] == desc['bytes'] and meta['st_mode'] & 0o111,
                'complete regular executable credential metadata required')
        if meta['st_mode'] & stat.S_ISUID:
            uid = meta['st_uid']
    return uid


def process_census(stdout, stderr, returncode, *, actor, query, tools_before, tools_after):
    """A complete C-locale census must include its live owner and query child."""
    require(type(actor) is dict and set(actor) == {'pid', 'pgid', 'effective_uid'} and
            all(type(actor[k]) is int and actor[k] > 1 for k in ('pid', 'pgid')) and
            type(actor['effective_uid']) is int and actor['effective_uid'] >= 0 and
            type(query) is dict and set(query) == {'pid', 'uid'} and
            type(query['pid']) is int and query['pid'] > 1 and
            type(query['uid']) is int and query['uid'] >= 0,
            'whole typed actual actor/query identities required')
    require(tools_before == tools_after, 'query executable identity changed')
    uid = expected_query_uid(tools_before, actor['effective_uid'])
    require(expected_query_uid(tools_after, actor['effective_uid']) == uid,
            'post-query executable credential metadata differs')
    require(type(returncode) is int and returncode == 0 and stderr == b'' and
            type(stdout) is bytes and 0 < len(stdout) <= 8 * 1024**2 and
            stdout.endswith(b'\n') and b'\r' not in stdout and b'\0' not in stdout,
            'complete successful bounded process census required')
    rows = []
    for line in stdout.decode('ascii', 'strict').splitlines():
        words = line.split()
        require(len(words) == 9 and all(re.fullmatch('[0-9]+', v) for v in words[:4]),
                'complete typed process row required')
        pid, ppid, pgid, euid = map(int, words[:4])
        require(words[4] in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun') and
                words[5] in ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec') and
                re.fullmatch('[0-9]{1,2}', words[6]) and
                re.fullmatch('[0-9]{2}:[0-9]{2}:[0-9]{2}', words[7]) and
                re.fullmatch('[0-9]{4}', words[8]), 'complete C-locale process birth required')
        stamp = datetime.datetime(int(words[8]),
            ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec').index(words[5]) + 1,
            int(words[6]), *map(int, words[7].split(':')))
        require(stamp.weekday() == ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun').index(words[4]),
                'contradictory process birth weekday')
        rows.append(dict(pid=pid, ppid=ppid, pgid=pgid, uid=euid, birth=' '.join(words[4:])))
    by_pid = {r['pid']: r for r in rows}
    require(len(rows) == len(by_pid), 'duplicate process identity')
    owner = by_pid.get(actor['pid'])
    child = by_pid.get(query['pid'])
    require(owner and owner['pgid'] == actor['pgid'] and owner['uid'] == actor['effective_uid'],
            'census omits or changes live root actor')
    require(child and child['pid'] != actor['pid'] and child['ppid'] == actor['pid'] and
            child['pgid'] == child['pid'] and child['uid'] == uid and query['uid'] == uid,
            'census omits or changes exact direct query child/EUID')
    return rows


class RootExecutor:
    """Actual constructors, usable only inside the calling root's admission.

    admit(stage, payload) must recheck the caller's same live lease, unresolved
    markers, source/tool/environment and stage-specific exact argv. register
    receives the still-held Popen and returns actual pid/pgid/uid observations.
    stop_held receives that same handle on timeout/error; it must quarantine if
    cleanup cannot be proved. Nothing here releases the root lease.
    """
    def __init__(self, output, *, admit, register, stop_held, python, trampoline,
                 environment, popen_factory=subprocess.Popen):
        require(all(callable(fn) for fn in (admit, register, stop_held, popen_factory)),
                'actual root admission/held-handle callbacks required')
        self.admit, self.register, self.stop_held = admit, register, stop_held
        self._popen = popen_factory
        self.environment = dict(environment)
        require(all(type(k) is str and type(v) is str for k, v in self.environment.items()),
                'complete actual string environment required')
        self.python = str(python)
        self.trampoline = copy.deepcopy(trampoline)
        self.actor = dict(pid=os.getpid(), pgid=os.getpgrp(), effective_uid=os.geteuid())
        self.thread = threading.get_ident()
        self.output = Path(output).absolute()
        self.records, self.handles = [], []
        self.quarantined = False
        self.authorize('constructor-output', dict(path=str(self.output)))
        self.output.mkdir(mode=0o700, exist_ok=False)
        self.journal = self.output / 'constructors375.json'
        self._save()

    def authorize(self, stage, payload):
        require(os.getpid() == self.actor['pid'] and threading.get_ident() == self.thread,
                'root executor cannot be transferred to another actor/thread')
        require(not self.quarantined, 'root executor quarantined; retain root lease')
        # A callback must raise on failure. No permissive bool/JSON fallback.
        result = self.admit(stage, copy.deepcopy(payload))
        require(result is None, 'root admission must raise on denial, not return a flag')

    def _save(self):
        value = dict(schema='root-peer-constructors375/v1', actor=self.actor,
                     quarantined=self.quarantined, spawns=self.records,
                     process_group_cleanup_verified=False, resource_cleanup_verified=False)
        raw = (json.dumps(value, indent=2) + '\n').encode()
        temporary = self.output / '.constructors375.next'
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, self.journal)

    def run(self, argv, *, timeout, label, start_new_session=True):
        require(type(argv) is list and argv and all(type(x) is str and '\0' not in x for x in argv),
                'whole literal argv required')
        require(type(timeout) in (int, float) and 0 < timeout <= 1800 and
                type(start_new_session) is bool, 'finite bounded command/session mode required')
        payload = dict(argv=argv, environment=self.environment, timeout=timeout,
                       label=label, start_new_session=start_new_session)
        self.authorize('command-intent', payload)
        before = query_tools() if argv == PS_ARGV else None
        row = dict(sequence=len(self.records) + 1, original_argv=list(argv),
                   state='intent', label=label, pid=None, pgid=None, uid=None,
                   reaped=False, exit_code=None, timed_out=False, error=None,
                   start_new_session=start_new_session, tool_identities_before=before,
                   tool_identities_after=None, started_monotonic_ns=time.monotonic_ns())
        self.records.append(row); self._save()
        process = None
        saved = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            mask = sorted(int(v) for v in saved)
            require(not {2, 15}.intersection(mask), 'caller control signals already blocked')
            require(tool_identity(self.trampoline['path'], executable=False)['descriptor'] == self.trampoline,
                    'actual trampoline source changed')
            spawn = [self.python, '-B', self.trampoline['path'], '--restore-mask', json.dumps(mask), '--', *argv]
            row.update(previous_signal_mask=mask, actual_spawn_argv=spawn,
                       effective_environment=copy.deepcopy(self.environment))
            self._save()
            self.authorize('before-popen', payload)
            process = self._popen(spawn, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=self.environment,
                                  start_new_session=start_new_session)
            self.handles.append(process)
            identity = self.register(process, copy.deepcopy(row))
            require(type(identity) is dict and set(identity) == {'pid', 'pgid', 'uid'} and
                    all(type(v) is int for v in identity.values()) and
                    identity['pid'] == process.pid and identity['pid'] > 1 and
                    identity['pgid'] > 1 and identity['uid'] >= 0,
                    'actual held direct-child identity observation required')
            expected = expected_query_uid(before, self.actor['effective_uid']) if before else self.actor['effective_uid']
            # Registration may observe the pinned Python trampoline before its
            # exec of setuid ps. The final query UID is proved by that query's
            # own complete census, not guessed from this initial observation.
            initial_uids = {self.actor['effective_uid'], expected} if before else {expected}
            require(identity['uid'] in initial_uids and
                    identity['pgid'] == (process.pid if start_new_session else self.actor['pgid']),
                    'actual child session/EUID differs from admitted executable chain')
            row.update(identity, state='started', initial_observed_uid=identity['uid'])
            if before is not None:
                row['uid'] = None
            self._save()
        except BaseException as error:
            row['error'] = type(error).__name__ + ': ' + str(error)
            self.quarantined = True
            self._save()
            if process is not None:
                self.stop_held(process, copy.deepcopy(row))
            self._save()
            raise
        finally:
            try:
                signal.pthread_sigmask(signal.SIG_SETMASK, saved)
            except BaseException as error:
                row['error'] = 'signal restoration: ' + type(error).__name__ + ': ' + str(error)
                self.quarantined = True
                self._save()
                if process is not None and process.returncode is None:
                    self.stop_held(process, copy.deepcopy(row))
                raise
        stdout, stderr = b'', b''
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException as error:
            row.update(error=type(error).__name__ + ': ' + str(error),
                       timed_out=isinstance(error, subprocess.TimeoutExpired))
            if isinstance(error, subprocess.TimeoutExpired):
                stdout, stderr = error.stdout or b'', error.stderr or b''
            self.quarantined = True
            self.stop_held(process, copy.deepcopy(row))
            try:
                stdout, stderr = process.communicate(timeout=10)
            except BaseException:
                pass
            raise
        finally:
            require(type(stdout) is bytes and type(stderr) is bytes, 'raw command streams required')
            for name, raw in (('stdout', stdout), ('stderr', stderr)):
                path = self.output / (str(row['sequence']).zfill(5) + '-' + name + '.bin')
                with path.open('xb') as stream: stream.write(raw)
                row[name] = dict(path=str(path), sha256=digest(raw), bytes=len(raw))
            row.update(exit_code=process.returncode, reaped=process.returncode is not None,
                       finished_monotonic_ns=time.monotonic_ns())
            if before is not None:
                try:
                    row['tool_identities_after'] = query_tools()
                    process_census(stdout, stderr, process.returncode, actor=self.actor,
                        query=dict(pid=process.pid, uid=expected), tools_before=before,
                        tools_after=row['tool_identities_after'])
                    row['uid'] = expected
                    row['uid_observed_in_query'] = True
                except (ValueError, UnicodeError, OSError) as error:
                    self.quarantined = True
                    row['error'] = 'query identity proof: ' + type(error).__name__ + ': ' + str(error)
            self._save()
        require(row['reaped'] and not self.quarantined, 'constructor unsettled; root must retain lease')
        return subprocess.CompletedProcess(argv, row['exit_code'], stdout, stderr)


def require_owner(owner):
    require(isinstance(owner, RootExecutor), 'root-owned Python API with live admission is required')
    return owner
