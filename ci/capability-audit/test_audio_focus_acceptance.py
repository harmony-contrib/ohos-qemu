"""Synthetic evidence mutations only; no fixture is an audio/guest acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import batch_media_audio_capture_challenge as P
import audio_focus_runtime as R
import verify_audio_focus_results as V

RUN, UID = 'a' * 32, 20010001


def file(root, name, data):
    path = root / name;path.write_bytes(data)
    return {'path': str(path), 'sha256': V.sha(path), 'bytes': len(data)}


class FreshFocusEvidence(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source';P.generate(source, RUN)
        _, reference = P.load_reference(source / 'challenge.json', source / 'challenge.pcm', RUN)
        data = (source / 'challenge.pcm').read_bytes()
        nonce = 'b' * 32
        value = {'type': 'event_fresh_reply', 'run_id': RUN, 'action': 'focus_begin', 'ready_nonce': nonce,
            'request_nonce': nonce, 'uid': UID, 'euid': UID, 'phase': 1, 'persisted': True,
            'request_seen_ns': 1490000000, 'requested_offset': 96000, 'request_frames': 24000,
            'request_position': 24000, 'request_timestamp_ns': 1490000000, 'request_query_before_ns': 1491000000,
            'request_query_after_ns': 1492000000, 'state_result': 0, 'state': 2, 'frames_result': 0, 'frames': 48000,
            'timestamp_result': 0, 'position': 48000, 'timestamp_ns': 2000000000, 'source_result': 0, 'source_type': 0,
            'rate_result': 0, 'rate': 48000, 'channels_result': 0, 'channels': 2, 'format_result': 0, 'format': 1,
            'query_before_ns': 2001000000, 'query_after_ns': 2002000000, 'copy_before_ns': 2000000000,
            'copy_after_ns': 2000500000, 'first_callback_ns': 1500000000, 'last_callback_ns': 1990000000,
            'callback_count': 50, 'offset': 96000, 'bytes': 96000, 'end_offset': 192000,
            'pcm_basename': 'audio-event-' + RUN + '-focus_begin-snapshot-' + nonce + '.pcm', 'reply_prepared_ns': 2004000000}
        chunks = [{'type': 'event_chunk', 'run_id': RUN, 'phase': 1, 'offset': i * 1920, 'bytes': 1920,
                   'monotonic_ns': 1000000000 + i * 10000000} for i in range(100)]
        files = {'request': file(root, 'request', (nonce + '\n').encode()),
                 'reply': file(root, 'reply.json', json.dumps(value).encode()),
                 'fresh': file(root, value['pcm_basename'], data[96000:]),
                 'audio-event-' + RUN + '-mode1.pcm': file(root, 'full.pcm', data)}
        results = root / 'native.log'
        results.write_text(''.join(json.dumps(r) + '\n' for r in [*chunks, value]))
        completion = file(root, 'completion.log', results.read_bytes())
        actor = {'mode': 1, 'uid': UID, 'files': files, 'native_results_path': str(results),
                 'native_results_sha256': V.sha(results), 'fresh_snapshots': [{'action': 'focus_begin', 'nonce': nonce,
                    'request_file': 'request', 'reply_file': 'reply', 'pcm_file': 'fresh', 'observation': value,
                    'request_clock_interval': [1480000000, 1495000000], 'correlation': P.phase_content(data[96000:], reference),
                    'native_completion': value, 'completion_log': completion}]}
        native = {'signals': [{'action': 'focus_begin', 'nonce': nonce, 'monotonic_ns': 1400000000}]}
        return actor, native, reference, chunks

    def test_request_requires_real_new_PCM_ranges_clock_configuration_and_matching_native_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            actor, native, reference, chunks = self.fixture(Path(directory))
            self.assertEqual(V.verify_fresh_snapshot(actor, native, reference, RUN)['bytes'], 96000)
            changes = ({'state': 3}, {'source_type': 7}, {'rate': 44100}, {'channels': 1}, {'format': 3},
                       {'state_result': 2}, {'first_callback_ns': 1480000000}, {'callback_count': 49},
                       {'request_nonce': 'c' * 32}, {'requested_offset': 192000}, {'frames': 24000},
                       {'request_seen_ns': 1400000000}, {'query_after_ns': 2500000000})
            for change in changes:
                broken = copy.deepcopy(actor);point = broken['fresh_snapshots'][0];point['observation'].update(change)
                reply = Path(broken['files']['reply']['path']);reply.write_text(json.dumps(point['observation']))
                broken['files']['reply']['sha256'] = V.sha(reply)
                log = Path(broken['native_results_path']);log.write_text(''.join(json.dumps(r) + '\n' for r in [*chunks, point['observation']]))
                broken['native_results_sha256'] = V.sha(log)
                point['native_completion'] = point['observation']
                completion = Path(point['completion_log']['path']);completion.write_bytes(log.read_bytes())
                point['completion_log']['sha256'] = V.sha(completion)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    V.verify_fresh_snapshot(broken, native, reference, RUN)

    def test_silence_or_another_PCM_snapshot_never_satisfies_fresh_content(self):
        with tempfile.TemporaryDirectory() as directory:
            actor, native, reference, _ = self.fixture(Path(directory))
            fresh = Path(actor['files']['fresh']['path']);fresh.write_bytes(bytes(96000));actor['files']['fresh']['sha256'] = V.sha(fresh)
            with self.assertRaises(ValueError): V.verify_fresh_snapshot(actor, native, reference, RUN)

    def test_runtime_waits_for_native_completion_before_reading_new_reply_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            actor, _, reference, _ = self.fixture(Path(directory))
            runtime = object.__new__(R.AudioFocusRuntime)
            runtime.run, runtime.reference, runtime.constants = RUN, reference, {'MIC': 0, 'S16LE': 1}
            runtime.token = Mock(side_effect=[{'after_ns': 1480000000}, {'before_ns': 1495000000}])
            runtime.write_nonce = Mock(return_value=actor['files']['request'])
            runtime.collect_file = Mock(side_effect=[actor['files']['reply'], actor['files']['fresh']])
            runtime.note = Mock()
            point = actor['fresh_snapshots'].pop()
            actor.update(app_files='/owned/', latest_native_log=point['completion_log'])
            order = []
            def wait_native(who, label, callback):
                runtime.collect_file.assert_not_called()
                self.assertIsNone(callback([]))
                with self.assertRaises(ValueError): callback([point['observation']] * 2)
                result = callback([point['observation']])
                order.append('completed')
                return result
            runtime.wait_native = Mock(side_effect=wait_native)
            ready = dict(run_id=RUN, action='focus_begin', nonce='b' * 32, uid=UID,
                         monotonic_ns=1400000000, state_result=0, state=2, frames_result=0, frames=20000, copied_bytes=80000)
            self.assertEqual(runtime.fresh_snapshot(actor, ready), point['observation'])
            self.assertEqual(order, ['completed'])
            self.assertEqual(actor['fresh_snapshots'][0]['native_completion'], point['observation'])

    def test_independent_completion_replay_requires_unique_matching_marker_and_preserved_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = dict(type='event_ready', run_id=RUN, action='focus_begin', nonce='b' * 32, monotonic_ns=100)
            row = {'native_completion': expected, 'completion_log': file(root, 'live.log', (json.dumps(expected) + '\n{').encode())}
            V.completed_native(row, 'event_ready', expected)
            for raw in ('{\n' + json.dumps(expected), json.dumps(expected) + '\n' + json.dumps(expected),
                        json.dumps(dict(expected, nonce='c' * 32)), ''):
                path = Path(row['completion_log']['path']);path.write_text(raw)
                row['completion_log']['sha256'] = V.sha(path)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    V.completed_native(row, 'event_ready', expected)


if __name__ == '__main__': unittest.main()
