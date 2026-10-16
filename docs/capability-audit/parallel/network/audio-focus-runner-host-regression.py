#!/usr/bin/env python3
"""Light host guard regressions; never Docker, HAP build, HDC, or guest execution."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dependency-root', type=Path, required=True,
                    help='parent checkout with the current shared capture/observation modules')
options = parser.parse_args()
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(options.dependency_root.resolve() / 'ci/capability-audit'))
for name in ('audio_focus_runtime', 'run_audio_focus_probe'):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'ci/capability-audit' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
runtime = sys.modules['audio_focus_runtime']
runner = sys.modules['run_audio_focus_probe']


def ready():
    return dict(run_id='a' * 32, action='focus_begin', nonce='b' * 32, uid=20010001,
                monotonic_ns=1000000000, state_result=0, state=2, frames_result=0,
                frames=40000, copied_bytes=160000)


def fresh():
    return dict(type='event_fresh_reply', run_id='a' * 32, action='focus_begin',
        ready_nonce='b' * 32, request_nonce='b' * 32, uid=20010001, euid=20010001,
        phase=1, state_result=0, state=2, frames_result=0, timestamp_result=0, source_result=0,
        source_type=0, rate_result=0, rate=48000, channels_result=0, channels=2,
        format_result=0, format=1, bytes=96000, persisted=True,
        request_seen_ns=1150000000, requested_offset=160000, request_frames=40000,
        request_position=40000, request_timestamp_ns=1140000000,
        request_query_before_ns=1151000000, request_query_after_ns=1152000000,
        frames=100000, position=100000, timestamp_ns=1640000000,
        query_before_ns=1661000000, query_after_ns=1662000000,
        copy_before_ns=1660000000, copy_after_ns=1660500000,
        first_callback_ns=1160000000, last_callback_ns=1650000000,
        callback_count=20, offset=160000, end_offset=256000,
        reply_prepared_ns=1670000000,
        pcm_basename='audio-event-' + 'a' * 32 + '-focus_begin-snapshot-' + 'b' * 32 + '.pcm')


def journal_fixture(directory, bodies, *, count=1, stats=None):
    """Model HDC bytes/stat only; exercise the real runtime collection methods."""
    value = object.__new__(runtime.AudioFocusRuntime)
    value.run, value.serial = 'a' * 32, 0
    value.args = SimpleNamespace(output=Path(directory), hdc='host-double', target='host-double')
    value.capture = SimpleNamespace(process=None)
    value.save = Mock()
    for name in ('private', 'live'):
        (value.args.output / 'owner' / name).mkdir(parents=True)
    actor = dict(uid=20010001, mode=1, app_files='/owned/', files={}, background_journal=[])
    paths = ['/owned/audio-event-' + value.run + '-mode1-background-' + str(i).zfill(3) + '.json'
             for i in range(count)]
    def metadata(body, remote=paths[0], uid=20010001):
        return str(uid) + ' 644 ' + str(len(body)) + ' 100 200 200\n' + hashlib.sha256(body).hexdigest() + '  ' + remote
    observations = stats or [metadata(body) for body in bodies for _ in range(2)]
    stat_values, received = iter(observations), iter(bodies)
    def actual(script, label):
        if label in ('focus-background-journal-list', 'focus-all-own-private-evidence'):
            return '\n'.join(paths)
        if label != 'focus-background-journal-stat':
            raise AssertionError('unexpected host fixture command: ' + label)
        return next(stat_values, observations[-1])
    def transfer(argv, label):
        if label != 'focus-background-journal-receive':
            raise AssertionError('unexpected host fixture transfer: ' + label)
        Path(argv[-1]).write_bytes(next(received, bodies[-1]))
    value.actual, value.command = Mock(side_effect=actual), Mock(side_effect=transfer)
    return value, actor, paths, metadata


class FocusHostGuards(unittest.TestCase):
    def test_ready_waits_for_completed_log_before_collecting_private_json(self):
        with tempfile.TemporaryDirectory() as directory:
            value, actor, _, _ = journal_fixture(directory, [b''])
            actor['ready_json'] = []
            marker = {key: ready()[key] for key in ('run_id', 'action', 'nonce', 'monotonic_ns')}
            marker['type'] = 'event_ready'
            text = json.dumps(marker)
            value.actual = Mock(side_effect=['', text[:-5], text])
            path = value.args.output / 'ready.json'
            path.write_bytes(b'{')  # Existence precedes native fsync/close.
            def transfer_ready(owner, remote):
                self.assertEqual(value.actual.call_count, 3)
                path.write_text(json.dumps(ready()) + '\n')
                return dict(path=str(path), sha256=runtime.sha(path))
            value.collect_file = Mock(side_effect=transfer_ready)
            value.bracket = lambda owner, label, operation: (operation(), [1100000000, 1200000000])
            value.present = Mock(side_effect=AssertionError('file existence cannot establish readiness'))
            with patch.object(runtime.time, 'sleep'):
                self.assertEqual(value.ready(actor, 'focus_begin'), ready())
            self.assertEqual(actor['ready_json'][0]['native_completion'], marker)
            log = actor['ready_json'][0]['completion_log']
            self.assertEqual(runtime.sha(Path(log['path'])), log['sha256'])
            self.assertIn(text, Path(log['path']).read_text())
            value.collect_file.assert_called_once()
            value.present.assert_not_called()

    def test_ready_rejects_completed_log_file_mismatch_and_duplicate_markers(self):
        for mutation in ({'nonce': 'c' * 32}, {'monotonic_ns': 1000000001}, {'duplicate': True}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                value, actor, _, _ = journal_fixture(directory, [b''])
                actor['ready_json'] = []
                marker = {key: ready()[key] for key in ('run_id', 'action', 'nonce', 'monotonic_ns')}
                marker.update(type='event_ready', **{key: item for key, item in mutation.items() if key != 'duplicate'})
                line = json.dumps(marker)
                value.actual = Mock(return_value=line + ('\n' + line if mutation.get('duplicate') else ''))
                path = value.args.output / 'ready.json'
                path.write_text(json.dumps(ready()) + '\n')
                value.collect_file = Mock(return_value=dict(path=str(path), sha256=runtime.sha(path)))
                value.bracket = lambda owner, label, operation: (operation(), [1100000000, 1200000000])
                with self.assertRaises(ValueError):
                    value.ready(actor, 'focus_begin')
                self.assertEqual(actor['ready_json'], [])
                if mutation.get('duplicate'):
                    value.collect_file.assert_not_called()

    def test_journal_tail_retries_empty_short_and_unterminated_json_preserving_raw(self):
        body = (json.dumps(dict(run_id='a' * 32, mode=1, event='notification_initial')) + '\n').encode()
        for partial in (b'', b'{"run_id":', body[:-1]):
            with self.subTest(partial=partial), tempfile.TemporaryDirectory() as directory:
                value, actor, paths, _ = journal_fixture(directory, [partial, body])
                def pending_sleep(seconds):
                    self.assertEqual(actor['files'], {})
                    self.assertEqual(list((value.args.output / 'owner/private').iterdir()), [])
                with patch.object(runtime.time, 'sleep', side_effect=pending_sleep):
                    self.assertEqual(value.journal(actor), [json.loads(body)])
                reads = actor['journal_reads']
                self.assertEqual(len(reads), 2)
                self.assertEqual(Path(reads[0]['path']).read_bytes(), partial)
                self.assertEqual(reads[0]['sha256'], hashlib.sha256(partial).hexdigest())
                self.assertFalse(reads[0]['complete'])
                self.assertTrue(reads[1]['complete'])
                self.assertEqual(Path(actor['files'][Path(paths[0]).name]['path']).read_bytes(), body)

    def test_journal_tail_retries_changed_stat_or_content_without_freezing_partial(self):
        body = (json.dumps(dict(run_id='a' * 32, mode=1, event='background_started')) + '\n').encode()
        with tempfile.TemporaryDirectory() as directory:
            value, actor, _, metadata = journal_fixture(directory, [body, body])
            original = value.actual.side_effect
            stats = iter([metadata(body).replace(' 100 200 200\n', ' 100 199 200\n'),
                          metadata(body), metadata(body), metadata(body)])
            value.actual.side_effect = lambda script, label: (next(stats) if label == 'focus-background-journal-stat'
                                                               else original(script, label))
            with patch.object(runtime.time, 'sleep'):
                self.assertEqual(value.journal(actor), [json.loads(body)])
            self.assertEqual(actor['journal_reads'][0]['pending_reason'], 'stat-or-content-changed')
            self.assertEqual(len(actor['files']), 1)

    def test_pending_tail_becoming_middle_requires_immediate_strict_complete_read(self):
        body = (json.dumps(dict(run_id='a' * 32, mode=1, event='notification_initial')) + '\n').encode()
        for last in (b'{', body):
            with self.subTest(last=last), tempfile.TemporaryDirectory() as directory:
                value, actor, paths, _ = journal_fixture(directory, [b'{', last], count=2)
                original = value.actual.side_effect
                listed = iter([paths[0], '\n'.join(paths)])
                value.actual.side_effect = lambda script, label: (next(listed) if label == 'focus-background-journal-list'
                                                                   else original(script, label))
                with patch.object(runtime.time, 'sleep') as sleep:
                    if last == b'{':
                        with self.assertRaisesRegex(ValueError, 'incomplete'):
                            value.journal(actor)
                        self.assertEqual(actor['files'], {})
                    else:
                        self.assertEqual(value.journal(actor), [json.loads(body)])
                    sleep.assert_not_called()
                self.assertEqual(len(actor['journal_reads']), 2)

    def test_journal_stable_partial_tail_has_fixed_deadline_and_retains_all_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            value, actor, _, _ = journal_fixture(directory, [b'{'])
            with patch.object(runtime.time, 'monotonic', side_effect=[10.0, 10.1, 12.1]), \
                    patch.object(runtime.time, 'sleep'), self.assertRaisesRegex(ValueError, 'timed out'):
                value.journal(actor)
            self.assertEqual(len(actor['journal_reads']), 2)
            self.assertEqual(actor['files'], {})
            for read in actor['journal_reads']:
                self.assertEqual(Path(read['path']).read_bytes(), b'{')

    def test_journal_never_retries_middle_damage_or_complete_malformed_tail(self):
        for body, count in [(b'{', 2), (b'{"run_id":\n', 1), (b'{"uid":1,"uid":2}\n', 1),
                            (b'\xff\n', 1), (b'[]\n', 1)]:
            with self.subTest(body=body, count=count), tempfile.TemporaryDirectory() as directory:
                value, actor, _, _ = journal_fixture(directory, [body], count=count)
                with patch.object(runtime.time, 'sleep') as sleep, self.assertRaises((ValueError, UnicodeError)):
                    value.journal(actor)
                sleep.assert_not_called()
                self.assertEqual(len(actor['journal_reads']), 1)
                self.assertEqual(actor['files'], {})

    def test_journal_owner_and_session_failure_stay_fatal(self):
        for uid, row in [(0, dict(run_id='a' * 32, mode=1)),
                         (20010001, dict(run_id='b' * 32, mode=1)),
                         (20010001, dict(run_id='a' * 32, mode=True)),
                         (20010001, dict(run_id='a' * 32, mode=1, event='startup_failed'))]:
            with self.subTest(uid=uid, row=row), tempfile.TemporaryDirectory() as directory:
                body = (json.dumps(row) + '\n').encode()
                value, actor, _, metadata = journal_fixture(directory, [body])
                if uid == 0:
                    value.actual.side_effect = iter(['/owned/audio-event-' + 'a' * 32 + '-mode1-background-000.json',
                                                     metadata(body, uid=uid)])
                with self.assertRaises(ValueError):
                    value.journal(actor)
                if uid == 0:
                    value.command.assert_not_called()

    def test_final_collect_refuses_unfinished_tail_and_rechecks_immutable_remote(self):
        body = (json.dumps(dict(run_id='a' * 32, mode=1, event='background_stopped')) + '\n').encode()
        with tempfile.TemporaryDirectory() as directory:
            value, actor, _, _ = journal_fixture(directory, [body[:-1]])
            with patch.object(runtime.time, 'sleep') as sleep, self.assertRaisesRegex(ValueError, 'incomplete'):
                value.collect_actor(actor)
            sleep.assert_not_called()
            self.assertEqual(actor['files'], {})
        with tempfile.TemporaryDirectory() as directory:
            value, actor, paths, _ = journal_fixture(directory, [body])
            self.assertEqual(value.journal(actor), [json.loads(body)])
            original = value.actual.side_effect
            def altered_remote(script, label):
                if label == 'focus-private-stat-and-content':
                    return '20010001 644 ' + str(len(body)) + '\n' + 'f' * 64 + '  ' + paths[0]
                return original(script, label)
            value.actual.side_effect = altered_remote
            with self.assertRaisesRegex(ValueError, 'immutable focus evidence changed'):
                value.collect_actor(actor)
            self.assertEqual(Path(actor['files'][Path(paths[0]).name]['path']).read_bytes(), body)

    def test_ready_rejects_foreign_uid_nonce_and_nonrunning(self):
        good = ready()
        self.assertEqual(runtime.validate_ready(good, 'a' * 32, 'focus_begin', 20010001, True), good)
        for key, value in [('uid', 20010002), ('nonce', 'bad'), ('state', 4), ('frames', 0), ('state_result', False)]:
            bad = dict(good, **{key: value})
            with self.assertRaises(ValueError):
                runtime.validate_ready(bad, 'a' * 32, 'focus_begin', 20010001, True)

    def test_fresh_reply_rejects_replay_identity_stale_callbacks_and_bool_results(self):
        good = fresh()
        args = (ready(), 20010001, [1100000000, 1200000000], dict(MIC=0, S16LE=1))
        self.assertEqual(runtime.validate_fresh(good, *args), good)
        mutations = [('request_nonce', 'c' * 32), ('uid', 20010002), ('euid', 0),
            ('state_result', False), ('first_callback_ns', 1140000000),
            ('frames', 40000), ('bytes', 95996), ('offset', 159996),
            ('callback_count', 0), ('reply_prepared_ns', 17000000000),
            ('pcm_basename', 'old-sample.pcm')]
        for key, value in mutations:
            with self.subTest(key=key), self.assertRaises(ValueError):
                runtime.validate_fresh(dict(good, **{key: value}), *args)

    def test_forced_stop_requires_actual_force_hint_and_start_causality(self):
        snapshot = dict(type='event_snapshot', state_result=0, state=4, invalid=0,
            before_ns=2000000000, last_callback=dict(kind=1, code=0, hint=3, monotonic_ns=2000000000))
        interval = dict(before_ns=1990000000, after_ns=2010000000)
        self.assertTrue(runtime.forced_stop(snapshot, interval, 4))
        for key, value in [('kind', 2), ('code', 1), ('hint', 2), ('monotonic_ns', 1980000000),
                           ('monotonic_ns', 2600000000)]:
            bad = copy.deepcopy(snapshot);bad['last_callback'][key] = value
            self.assertFalse(runtime.forced_stop(bad, interval, 4))
        self.assertFalse(runtime.forced_stop(dict(snapshot, state=2), interval, 4))

    def test_expired_ack_refuses_before_any_control_write(self):
        value = object.__new__(runtime.AudioFocusRuntime)
        value.run = 'a' * 32
        value.token = Mock(return_value=dict(after_ns=16000000000))
        value.write_nonce = Mock()
        with self.assertRaises(ValueError):
            value.ack(dict(app_files='/owned/'), ready())
        value.write_nonce.assert_not_called()

    def test_expired_fresh_request_refuses_before_any_control_write(self):
        value = object.__new__(runtime.AudioFocusRuntime)
        value.run = 'a' * 32
        value.token = Mock(return_value=dict(after_ns=16000000000))
        value.write_nonce = Mock()
        with self.assertRaises(ValueError):
            value.fresh_snapshot(dict(app_files='/owned/'), ready())
        value.write_nonce.assert_not_called()

    def test_native_private_mode_rejects_before_file_transfer(self):
        value = object.__new__(runtime.AudioFocusRuntime)
        value.run = 'a' * 32
        value.actual = Mock(return_value='20010001 644 96000\n' + 'f' * 64 + '  /owned/audio-event-' + 'a' * 32 + '-focus_begin.pcm')
        value.command = Mock()
        actor = dict(uid=20010001, app_files='/owned/')
        with self.assertRaises(ValueError):
            value.collect_file(actor, '/owned/audio-event-' + 'a' * 32 + '-focus_begin.pcm')
        value.command.assert_not_called()

    def test_identity_rejects_shared_system_and_other_account(self):
        info = dict(appPrivilegeLevel='normal', isSystemApp=False, uid=20010001)
        text = json.dumps(dict(applicationInfo=info))
        self.assertEqual(runner.normal_uid(text, runtime.BUNDLES[0]), 20010001)
        for key, value in [('isSystemApp', True), ('appPrivilegeLevel', 'system_basic'), ('uid', 10001)]:
            with self.assertRaises(ValueError):
                runner.normal_uid(json.dumps(dict(applicationInfo=dict(info, **{key: value}))), runtime.BUNDLES[0])

    def test_duplicate_json_evidence_rejected(self):
        with self.assertRaises(ValueError):
            runtime.strict_json('{"uid":20010001,"uid":20010002}')

    def test_missing_preflight_never_launches_commands_or_stops_bundles(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = SimpleNamespace(output=Path(temporary) / 'run', archive=Path(temporary) / 'missing.tar.gz',
                target='owned-target', arch='arm64', device='phone', boot_id='a' * 36)
            with patch.object(runner.subprocess, 'Popen') as launch:
                value = runner.run(args)
            self.assertEqual(value['status'], 'fail')
            self.assertTrue(value['failures'])
            self.assertEqual(value['commands'], [])
            launch.assert_not_called()
            self.assertFalse(value['first_artifact_behavior_gate_passed'])


if __name__ == '__main__':
    unittest.main(argv=[__file__], verbosity=2)
