"""Host-only constructor/identity/failure doubles; no external resources."""
import copy
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import batch_network375_root_entry as E
import batch_network375_peer_protocol as P
from batch_network375_peer_fixture import Frame267, synthetic_query_tools


class ProcessDouble:
    pid = 62341
    returncode = None

    def communicate(self, timeout):
        self.returncode = 0
        return b'original stdout\xff', b'original stderr'


class RootEntryTests(unittest.TestCase):
    def owner(self, root, *, factory=None, register=None, stop=None, admit=None):
        script = root / 'trampoline.py'
        script.write_text('# explicit host-only unexecuted trampoline double\n')
        desc = E.tool_identity(script, executable=False)['descriptor']
        return E.RootExecutor(root / 'owned-command-records',
            admit=admit or Mock(return_value=None),
            register=register or (lambda process, row: dict(pid=process.pid,
                pgid=process.pid if row['start_new_session'] else os.getpgrp(), uid=os.geteuid())),
            stop_held=stop or Mock(), python=sys.executable, trampoline=desc,
            environment={'PATH': '/unit-only/bin:/usr/bin:/bin'},
            popen_factory=factory or Mock(return_value=ProcessDouble()))

    def test_missing_live_root_callbacks_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(E.AdmissionError):
                E.RootExecutor(Path(temporary) / 'out', admit=True, register=lambda *a: None,
                    stop_held=lambda *a: None, python=sys.executable, trampoline={}, environment={})
        with self.assertRaises(E.AdmissionError):
            E.require_owner({'lease_held': True})

    def test_admission_boolean_is_never_an_authorization_receipt(self):
        for flag in (False, True):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.assertRaises(E.AdmissionError):
                    self.owner(root, admit=lambda *args: flag)
                self.assertFalse((root / 'owned-command-records').exists())

    def test_intent_and_admission_precede_constructor_and_raw_streams_survive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seen = []
            def popen(argv, **kwargs):
                saved = json.loads((root / 'owned-command-records/constructors375.json').read_text())
                self.assertEqual(saved['spawns'][0]['state'], 'intent')
                self.assertEqual(seen[-1], 'before-popen')
                self.assertTrue(kwargs['start_new_session'])
                self.assertEqual(argv[-2:], ['unit-command', '--exact'])
                return ProcessDouble()
            owner = self.owner(root, factory=popen, admit=lambda stage, payload: seen.append(stage))
            result = owner.run(['unit-command', '--exact'], timeout=1, label='unit')
            self.assertEqual(result.stdout, b'original stdout\xff')
            self.assertEqual(Path(owner.records[0]['stdout']['path']).read_bytes(), result.stdout)
            self.assertTrue(owner.records[0]['reaped'])
            self.assertFalse(json.loads(owner.journal.read_text())['resource_cleanup_verified'])

    def test_registration_exception_retains_held_handle_and_restores_signal_mask(self):
        with tempfile.TemporaryDirectory() as temporary:
            stop = Mock()
            factory = Mock(return_value=ProcessDouble())
            def broken(*args): raise ValueError('register fault')
            owner = self.owner(Path(temporary), factory=factory, register=broken, stop=stop)
            before = signal.pthread_sigmask(signal.SIG_BLOCK, set())
            with self.assertRaisesRegex(ValueError, 'register fault'):
                owner.run(['unit-command'], timeout=1, label='fault')
            self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, set()), before)
            self.assertIs(stop.call_args.args[0], factory.return_value)
            self.assertTrue(json.loads(owner.journal.read_text())['quarantined'])
            with self.assertRaisesRegex(E.AdmissionError, 'quarantined'):
                owner.run(['another-command'], timeout=1, label='forbidden')

    def test_popen_error_has_no_invented_pid_or_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            owner = self.owner(Path(temporary), factory=Mock(side_effect=OSError('constructor failed')))
            with self.assertRaises(OSError): owner.run(['unit-command'], timeout=1, label='fault')
            row = owner.records[0]
            self.assertIsNone(row['pid'])
            self.assertFalse(row['reaped'])
            self.assertTrue(owner.quarantined)

    def test_pending_interruption_at_mask_restore_still_owns_and_stops_held_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            stop = Mock()
            owner = self.owner(Path(temporary), stop=stop)
            def mask(how, values):
                if how == signal.SIG_SETMASK:
                    raise KeyboardInterrupt('pending root cancellation')
                return set()
            with patch.object(E.signal, 'pthread_sigmask', side_effect=mask):
                with self.assertRaises(KeyboardInterrupt):
                    owner.run(['unit-command'], timeout=1, label='pending-cancel')
            self.assertIs(stop.call_args.args[0], owner.handles[0])
            self.assertTrue(owner.quarantined)

    def test_timeout_preserves_full_reaped_bytes_and_original_failure(self):
        class TimeoutDouble(ProcessDouble):
            calls = 0
            def communicate(self, timeout):
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired(['unit-command'], timeout, output=b'partial', stderr=b'error')
                self.returncode = -15
                return b'partial plus actual tail', b'error'
        with tempfile.TemporaryDirectory() as temporary:
            process = TimeoutDouble(); stop = Mock()
            owner = self.owner(Path(temporary), factory=Mock(return_value=process), stop=stop)
            with self.assertRaises(subprocess.TimeoutExpired):
                owner.run(['unit-command'], timeout=1, label='timeout')
            self.assertTrue(owner.records[0]['timed_out'])
            self.assertEqual(Path(owner.records[0]['stdout']['path']).read_bytes(), b'partial plus actual tail')
            self.assertIs(stop.call_args.args[0], process)
            self.assertTrue(owner.quarantined)

    def test_wrong_non_query_uid_never_gets_ps_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            wrong = lambda process, row: dict(pid=process.pid, pgid=process.pid, uid=os.geteuid() + 1)
            owner = self.owner(Path(temporary), register=wrong)
            with self.assertRaisesRegex(E.AdmissionError, 'EUID'):
                owner.run(['unit-command'], timeout=1, label='wrong-uid')

    def test_query_initial_trampoline_uid_is_not_confused_with_final_ps_uid(self):
        for final_uid, success in ((777, True), (778, False)):
            with tempfile.TemporaryDirectory() as temporary:
                tools = synthetic_query_tools()
                tools['ps']['stat']['st_mode'] |= stat.S_ISUID
                tools['ps']['stat']['st_uid'] = 777
                owner = self.owner(Path(temporary))
                class QueryDouble(ProcessDouble):
                    def communicate(self, timeout):
                        self.returncode = 0
                        actor = owner.actor
                        body = (str(actor['pid'])+' 1 '+str(actor['pgid'])+' '+str(actor['effective_uid'])+
                            ' Fri Oct 16 00:00:00 2026\n'+str(self.pid)+' '+str(actor['pid'])+' '+
                            str(self.pid)+' '+str(final_uid)+' Fri Oct 16 00:00:00 2026\n')
                        return body.encode(), b''
                owner._popen = Mock(return_value=QueryDouble())
                with patch.object(E, 'query_tools', return_value=tools):
                    if success:
                        owner.run(E.PS_ARGV, timeout=1, label='query')
                    else:
                        with self.assertRaises(E.AdmissionError):
                            owner.run(E.PS_ARGV, timeout=1, label='query')
                self.assertEqual(owner.records[0]['initial_observed_uid'], os.geteuid())
                self.assertEqual(owner.records[0]['uid'], 777 if success else None)
                self.assertEqual(owner.quarantined, not success)

    def test_exact_setuid_metadata_derives_one_uid_and_rejects_alias_or_bool(self):
        tools = synthetic_query_tools()
        self.assertEqual(E.expected_query_uid(tools, 501), 501)
        tools['ps']['stat']['st_mode'] |= stat.S_ISUID
        self.assertEqual(E.expected_query_uid(tools, 501), 0)
        tools['ps']['descriptor']['path'] = '/foreign/ps'
        with self.assertRaises(E.AdmissionError): E.expected_query_uid(tools, 501)
        tools = synthetic_query_tools(); tools['ps']['stat']['st_uid'] = True
        with self.assertRaises(E.AdmissionError): E.expected_query_uid(tools, 501)


class QueryProtocolTests(unittest.TestCase):
    def complete(self):
        frame = Frame267(); frame.runtime(); return frame

    def query_row(self, frame, op):
        ref = op['constructor']; return frame.ledgers[ref['ledger_path']]['spawns'][ref['index']]

    def test_actual_shaped_setuid_query_chain_accepted_without_nonquery_uid_relaxation(self):
        frame = Frame267()
        frame.binding['query_tools']['ps']['stat']['st_mode'] |= stat.S_ISUID
        frame.runtime()
        for op in frame.operations:
            if op['origin'] == 'process-cut':
                row = self.query_row(frame, op); row['uid'] = 0
                body = frame.results[op['id']]['stdout'].decode().replace(
                    str(row['pid']) + ' 501 ', str(row['pid']) + ' 0 ')
                frame.replace_result(op['id'], stdout=body.encode())
        self.assertTrue(frame.prove()['closed'], frame.prove())
        op = next(x for x in frame.operations if x['origin'] == 'controller')
        self.query_row(frame, op)['uid'] = 0
        self.assertFalse(frame.prove()['closed'])

    def test_tool_metadata_drift_rejects_whole_settlement(self):
        frame = self.complete()
        op = next(x for x in frame.operations if x['origin'] == 'process-cut')
        self.query_row(frame, op)['query_tools_after']['ps']['stat']['st_ino'] += 1
        self.assertFalse(frame.prove()['closed'])

    def test_census_must_include_live_owner_and_its_query(self):
        for omission in ('20000 ', '1 '):
            frame = self.complete()
            op = next(x for x in frame.operations if x['origin'] == 'process-cut')
            row = self.query_row(frame, op)
            target = '20000 ' if omission == '20000 ' else str(row['pid']) + ' '
            body = b''.join(line for line in frame.results[op['id']]['stdout'].splitlines(True)
                            if not line.startswith(target.encode()))
            frame.replace_result(op['id'], stdout=body)
            self.assertFalse(frame.prove()['closed'])

    def test_ps_argv_cannot_be_truncated_or_redirected(self):
        frame = self.complete(); op = next(x for x in frame.operations if x['origin'] == 'process-cut')
        op['argv'] = ['ps', '-p', '1']
        self.assertFalse(frame.prove()['closed'])


if __name__ == '__main__':
    unittest.main()
