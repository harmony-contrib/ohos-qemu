"""Active-revoke evidence mutation tests, never live microphone acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from verify_audio_revoke_results import verify_revocation
from verify_audio_capture_results import sha


class LiveRevokeBoundary(unittest.TestCase):
    def test_only_same_token_same_process_committed_inside_live_nonce_is_accepted(self):
        run, uid, token_id = 'c' * 32, 20010001, 123
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / 'NOT-guest-unit-PCM'
            checkpoint.write_bytes(b'unit-structure-only')
            file = {'path': str(checkpoint), 'sha256': sha(checkpoint)}
            ready = {'run_id': run, 'action': 'revoke', 'uid': uid, 'nonce': 'a' * 32, 'monotonic_ns': 10,
                     'state_result': 0, 'state': 2, 'frames_result': 0, 'frames': 48000, 'copied_bytes': 192000}
            observation = {'run_id': run, 'uid': uid, 'bundle': 'org.harmonycontrib.capabilityaudit', 'user_id': 100,
                'token_id': token_id, 'permission': 'ohos.permission.MICROPHONE', 'operation': 'revoke',
                'result': 0, 'before': 0, 'after': -1, 'before_ns': 20, 'after_ns': 30}
            process = {'pid': 1234, 'starttime': 125, 'uid': uid}
            value = {'ready': ready, 'token': observation, 'process_before': process, 'process_after': dict(process),
                     'checkpoint': file, 'ack_nonce': ready['nonce']}
            runtime = {'tokens': [{'observation': {'token_id': token_id}}],
                       'files': {'audio-event-' + run + '-mode0-baseline.pcm': file}}
            result = {'signals': [{'nonce': ready['nonce'], 'monotonic_ns': 10}], 'acks': [{'monotonic_ns': 40}]}
            self.assertEqual(verify_revocation(value, runtime, result, uid, run)['token_id'], token_id)
            for mutation in ('grant', 'root', 'dead', 'PID_reuse', 'too_early', 'too_late', 'stopped', 'stale', 'wrong_token'):
                broken = copy.deepcopy(value)
                if mutation == 'grant': broken['token']['operation'] = 'grant'
                elif mutation == 'root': broken['process_before']['uid'] = broken['process_after']['uid'] = 0
                elif mutation == 'dead': broken['process_after']['pid'] += 1
                elif mutation == 'PID_reuse': broken['process_after']['starttime'] += 1
                elif mutation == 'too_early': broken['token']['before_ns'] = 9
                elif mutation == 'too_late': broken['token']['after_ns'] = 41
                elif mutation == 'stopped': broken['ready']['state'] = 3
                elif mutation == 'stale': broken['ack_nonce'] = 'b' * 32
                else: broken['token']['token_id'] += 1
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    verify_revocation(broken, runtime, result, uid, run)


if __name__ == '__main__': unittest.main()
