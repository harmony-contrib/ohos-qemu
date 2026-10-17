"""Active-revoke evidence mutation tests, never live microphone acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from verify_audio_revoke_results import verify_revocation, verify_revocation_order
from verify_audio_capture_results import sha
import test_microphone_token_bindings as fixtures
from audio_revoke_runtime import PROCESS_IDENTITY_SCRIPT


class LiveRevokeBoundary(unittest.TestCase):
    def test_only_same_token_same_process_committed_inside_live_nonce_is_accepted(self):
        run, uid, token_id = fixtures.RUN, fixtures.UID, fixtures.TOKEN
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime, binding = fixtures.MicrophoneTokenBindings().fixture(root, operation='revoke')
            process = {'pid': 1234, 'starttime': 125, 'uid': uid}
            def process_frame(index):
                marker = '__MIC_EXIT_' + str(index + 5) * 32 + '__='
                raw = '1234 125 ' + str(uid) + '\n\n' + marker + '0\n'
                path = root / ('process-' + str(index) + '.log'); path.write_text(raw)
                wrapped = PROCESS_IDENTITY_SCRIPT + '; task_mic_rc=$?; printf "\\n' + marker + '%s\\n" "$task_mic_rc"'
                return (dict(argv=['approved-hdc', '-t', 'owned-target', 'shell', wrapped], log=str(path),
                             sha256=sha(path), exit_code=0),
                        dict(script=PROCESS_IDENTITY_SCRIPT, command_index=index,
                             exit_marker=marker, raw=raw, guest_exit_code=0))
            before, after = process_frame(0), process_frame(4)
            for shell in runtime['guest_shell_observations']: shell['command_index'] += 1
            runtime['orchestration_commands'] = [before[0], *runtime['orchestration_commands'], after[0]]
            runtime['guest_shell_observations'] = [before[1], *runtime['guest_shell_observations'], after[1]]
            for key in ('bms_before_observation', 'token_observation', 'bms_after_observation'): binding[key] += 1
            checkpoint = Path(directory) / 'NOT-guest-unit-PCM'
            checkpoint.write_bytes(b'unit-structure-only')
            file = {'path': str(checkpoint), 'sha256': sha(checkpoint)}
            ready = {'run_id': run, 'action': 'revoke', 'uid': uid, 'nonce': 'a' * 32, 'monotonic_ns': 10,
                     'state_result': 0, 'state': 2, 'frames_result': 0, 'frames': 48000, 'copied_bytes': 192000}
            observation = binding['observation']
            value = {'ready': ready, 'token': observation, 'process_before': process, 'process_after': dict(process),
                     'process_before_observation': 0, 'process_after_observation': 4, 'token_binding': binding,
                     'checkpoint': file, 'ack_nonce': ready['nonce'], 'ack_files': ['audio-event-' + run + '-revoke-ack', 'audio-event-' + run + '-revoke-ack.publish-' + 'd' * 32]}
            runtime.update(tokens=[{'observation': {'token_id': token_id}}],
                           files={'audio-event-' + run + '-mode0-baseline.pcm': file})
            for name in value['ack_files']:
                control = Path(directory) / name; control.write_text(ready['nonce'] + '\n')
                runtime['files'][name] = {'path': str(control), 'sha256': sha(control), 'uid': uid, 'mode': 600, 'bytes': 33}
            result = {'signals': [{'nonce': ready['nonce'], 'monotonic_ns': 10}], 'acks': [{'monotonic_ns': 200}]}
            self.assertEqual(verify_revocation(value, runtime, result, uid, run)['token_id'], token_id)
            for mutation in ('grant', 'root', 'dead', 'PID_reuse', 'too_early', 'too_late', 'stopped', 'stale',
                             'wrong_token', 'process_order', 'process_missing'):
                broken = copy.deepcopy(value)
                if mutation == 'grant': broken['token']['operation'] = 'grant'
                elif mutation == 'root': broken['process_before']['uid'] = broken['process_after']['uid'] = 0
                elif mutation == 'dead': broken['process_after']['pid'] += 1
                elif mutation == 'PID_reuse': broken['process_after']['starttime'] += 1
                elif mutation == 'too_early': broken['token']['before_ns'] = 9
                elif mutation == 'too_late': broken['token']['after_ns'] = 201
                elif mutation == 'stopped': broken['ready']['state'] = 3
                elif mutation == 'stale': broken['ack_nonce'] = 'b' * 32
                elif mutation == 'wrong_token': broken['token']['token_id'] += 1
                elif mutation == 'process_order': broken['process_after_observation'] = 0
                else: broken['process_before_observation'] = 1
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    verify_revocation(broken, runtime, result, uid, run)
            for mutation in ('raw_pid', 'raw_starttime', 'raw_uid', 'native_query'):
                original = copy.deepcopy(runtime)
                index = 2 if mutation == 'native_query' else 4
                command, shell = original['orchestration_commands'][index], original['guest_shell_observations'][index]
                path = Path(command['log']); saved = path.read_bytes()
                raw = saved.decode()
                if mutation == 'raw_pid': raw = raw.replace('1234 125 ', '1235 125 ')
                elif mutation == 'raw_starttime': raw = raw.replace('1234 125 ', '1234 126 ')
                elif mutation == 'raw_uid': raw = raw.replace('1234 125 ' + str(uid), '1234 125 ' + str(uid + 1))
                else: raw = raw.replace('"operation": "revoke"', '"operation": "query"')
                path.write_text(raw); command['sha256'] = sha(path); shell['raw'] = raw
                try:
                    with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                        verify_revocation(value, original, result, uid, run)
                finally: path.write_bytes(saved)

    def test_revoke_order_must_be_inside_original_dialog_and_final_queries(self):
        runtime = dict(tokens=[dict(phase='after-dialog', bms_after_observation=0, observation=dict(after_ns=10)),
                               dict(phase='after-capture', bms_before_observation=3, observation=dict(before_ns=40))],
                       guest_shell_observations=[dict(command_index=i) for i in range(4)])
        value = dict(process_before_observation=1, process_after_observation=2,
                     token=dict(before_ns=20, after_ns=30))
        verify_revocation_order(value, runtime)
        for mutate in ('dialog-command', 'final-command', 'dialog-clock', 'final-clock'):
            bad = copy.deepcopy(runtime)
            if mutate == 'dialog-command': bad['guest_shell_observations'][0]['command_index'] = 1
            elif mutate == 'final-command': bad['guest_shell_observations'][3]['command_index'] = 2
            elif mutate == 'dialog-clock': bad['tokens'][0]['observation']['after_ns'] = 21
            else: bad['tokens'][1]['observation']['before_ns'] = 29
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): verify_revocation_order(value, bad)


if __name__ == '__main__': unittest.main()
