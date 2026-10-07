"""Synthetic verifier regression only, never guest audio evidence."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from verify_audio_stream_results import BOUNDARIES, CYCLE, verify

RUN = 'c' * 32
UID = 20010036
IDENTITY = json.dumps({'applicationInfo': {'uid': UID, 'appPrivilegeLevel': 'normal', 'isSystemApp': False}})


def rows():
    result = [dict(type='identity', run_id=RUN, uid=UID, euid=UID)]
    for cycle, sequence in ((0, BOUNDARIES), (1, CYCLE), (2, CYCLE)):
        for name, expected in sequence:
            if name.startswith('@'):
                resumed = name == '@resumed'
                result.append(dict(type='progress', run_id=RUN, cycle=cycle, phase=name[1:], result=0,
                                   before_frames=960 if resumed else 0, frames=1920 if resumed else 960,
                                   before_callbacks=5 if resumed else 0, callbacks=10 if resumed else 5,
                                   bytes=7680 if resumed else 3840, invalid_buffers=0,
                                   callback_error=0, passed=True))
            else:
                result.append(dict(type='step', run_id=RUN, cycle=cycle, name=name,
                                   actual=expected, expected=expected, passed=True))
    result.append(dict(type='summary', run_id=RUN, cycles=2, passed=True))
    return result


def render(values):
    return '\n'.join(json.dumps(row) for row in values)


class AudioStreamVerifierTests(unittest.TestCase):
    def test_complete_fixture_and_bm_prefix(self):
        self.assertEqual(len(verify(render(rows()), RUN, IDENTITY)), 71)
        verify(render(rows()), RUN, 'org.harmonycontrib.capabilityaudit:\n' + IDENTITY)

    def test_partial_reordered_duplicate_stale_fail(self):
        complete = rows()
        for broken in (complete[:-1], complete * 2, list(reversed(complete)), complete[:10] + complete[11:]):
            with self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)
        for index in range(len(complete)):
            broken = copy.deepcopy(complete)
            broken[index]['run_id'] = 'd' * 32
            with self.assertRaises(ValueError): verify(render(broken), RUN, IDENTITY)

    def test_false_success_or_frames_without_callbacks_fail(self):
        for index, row in enumerate(rows()):
            changes = [('passed', 1)] if 'passed' in row else [('uid', 0)]
            if row['type'] == 'step': changes += [('actual', 6800104), ('expected', 6800104), ('actual', True)]
            if row['type'] == 'progress':
                changes += [(key, 0) for key in ('frames', 'callbacks', 'bytes')]
                changes += [('invalid_buffers', 1), ('callback_error', 3), ('bytes', 11), ('result', True)]
            for key, value in changes:
                broken = rows()
                broken[index][key] = value
                with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                    verify(render(broken), RUN, IDENTITY)

    def test_privileged_or_mismatched_app_identity_fails(self):
        for key, value in (('appPrivilegeLevel', 'system_basic'), ('isSystemApp', True), ('uid', 0), ('uid', UID + 1)):
            identity = json.loads(IDENTITY)
            identity['applicationInfo'][key] = value
            with self.assertRaises(ValueError): verify(render(rows()), RUN, json.dumps(identity))

    def test_cli_preserves_failed_native_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in (('archive', 'host fixture only'), ('results', render(rows()[:-1])), ('identity', IDENTITY)):
                (root / name).write_text(content)
            result = root / 'result.json'
            completed = subprocess.run([sys.executable, str(Path(__file__).with_name('verify_audio_stream_results.py')),
                                        '--archive', str(root / 'archive'), '--results', str(root / 'results'),
                                        '--application-identity', str(root / 'identity'), '--run-id', RUN,
                                        '--output', str(result)], capture_output=True)
            evidence = json.loads(result.read_text())
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(evidence['status'], 'fail')
            self.assertEqual(len(evidence['observations']), 70)
            self.assertFalse(evidence['first_artifact_behavior_gate_passed'])
            self.assertFalse(evidence['capturer_tested'])
            self.assertFalse(evidence['actual_host_audio_samples_tested'])


if __name__ == '__main__':
    unittest.main()
