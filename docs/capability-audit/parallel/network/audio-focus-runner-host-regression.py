#!/usr/bin/env python3
"""Light host guard regressions; never Docker, HAP build, HDC, or guest execution."""
import argparse
import copy
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


class FocusHostGuards(unittest.TestCase):
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
