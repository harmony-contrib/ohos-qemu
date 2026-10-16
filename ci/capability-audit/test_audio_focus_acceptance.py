"""Synthetic evidence mutations only; no fixture is an audio/guest acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import batch_media_audio_capture_challenge as P
import verify_audio_focus_results as V

RUN, UID = 'a' * 32, 20010001


def file(root, name, data):
    path = root / name;path.write_bytes(data)
    return {'path': str(path), 'sha256': V.sha(path)}


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
        actor = {'mode': 1, 'uid': UID, 'files': files, 'native_results_path': str(results),
                 'native_results_sha256': V.sha(results), 'fresh_snapshots': [{'action': 'focus_begin', 'nonce': nonce,
                    'request_file': 'request', 'reply_file': 'reply', 'pcm_file': 'fresh', 'observation': value,
                    'request_clock_interval': [1480000000, 1495000000], 'correlation': P.phase_content(data[96000:], reference)}]}
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
                with self.subTest(change=change), self.assertRaises(ValueError):
                    V.verify_fresh_snapshot(broken, native, reference, RUN)

    def test_silence_or_another_PCM_snapshot_never_satisfies_fresh_content(self):
        with tempfile.TemporaryDirectory() as directory:
            actor, native, reference, _ = self.fixture(Path(directory))
            fresh = Path(actor['files']['fresh']['path']);fresh.write_bytes(bytes(96000));actor['files']['fresh']['sha256'] = V.sha(fresh)
            with self.assertRaises(ValueError): V.verify_fresh_snapshot(actor, native, reference, RUN)


if __name__ == '__main__': unittest.main()
