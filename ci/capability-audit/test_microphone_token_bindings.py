"""Original shell/identity binding regressions; fixtures attest no guest behavior."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from verify_audio_capture_results import verify_token_observation, token


BUNDLE = 'org.harmonycontrib.capabilityaudit'
UID, TOKEN, RUN = 20010040, 537042608, 'a' * 32


class MicrophoneTokenBindings(unittest.TestCase):
    def fixture(self, root, focus=False, operation='query'):
        def file(name, text):
            path = root / name
            path.write_text(text)
            return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        app = dict(name=BUNDLE, bundleName=BUNDLE, uid=UID, accessTokenId=TOKEN,
                   appIndex=0, appPrivilegeLevel='normal', isSystemApp=False)
        bms = BUNDLE + ':\n' + json.dumps(dict(name=BUNDLE, appIndex=0, applicationInfo=app,
            userInfo=[dict(bundleUserInfo=dict(userId=100), bundleName=BUNDLE, uid=UID, accessTokenId=TOKEN)]))
        native = dict(identity_schema='hap-bms-access-token/v1', expected_uid=UID, at_reported_uid=0,
            at_query_rc=0, at_token_id=TOKEN, at_user_id=100, at_inst_index=0, at_bundle=BUNDLE,
            bundle=BUNDLE, token_id=TOKEN, user_id=100, run_id=RUN, permission='ohos.permission.MICROPHONE',
            operation=operation, result=0, before=0, after=-1 if operation == 'revoke' else 0,
            before_ns=100, after_ns=101)
        runtime = dict(parent_persona='audio-focus' if focus else 'audio-capture',
            hdc=dict(file('hdc', 'host-only transport fixture'), argv0='approved-hdc'),
            target='owned-target', remote_root_directory='/data/local/tmp/qemu-mic-' + RUN,
            orchestration_commands=[], guest_shell_observations=[])
        scripts = ['bm dump -n ' + BUNDLE,
            'unset LD_LIBRARY_PATH LD_PRELOAD; ' + runtime['remote_root_directory'] +
            '/audio_capture_token ' + RUN + ' ' + str(UID) + ' ' + operation + (' ' + BUNDLE if focus else ''),
            'bm dump -n ' + BUNDLE]
        for i, (script, body) in enumerate(zip(scripts, [bms, json.dumps(native), bms])):
            marker = '__MIC_EXIT_' + str(i + 1) * 32 + '__='
            raw = body + '\n\n' + marker + '0\n'
            wrapped = script + '; task_mic_rc=$?; printf "\\n' + marker + '%s\\n" "$task_mic_rc"'
            command = dict(exit_code=0, timed_out=False)
            if focus:
                outer = '__FOCUS_EXIT_' + str(i + 4) * 32 + '__='
                wrapped += '; focus_rc=$?; printf "\\n' + outer + '%s\\n" "$focus_rc"'
                out, err = file(str(i) + '.stdout', raw + '\n' + outer + '0\n'), file(str(i) + '.stderr', '')
                command.update(stdout_path=out['path'], stdout_sha256=out['sha256'],
                               stderr_path=err['path'], stderr_sha256=err['sha256'])
            else:
                log = file(str(i) + '.log', raw)
                command.update(log=log['path'], sha256=log['sha256'])
            command['argv'] = ['approved-hdc', '-t', 'owned-target', 'shell', wrapped]
            runtime['orchestration_commands'].append(command)
            runtime['guest_shell_observations'].append(dict(script=script, command_index=i,
                exit_marker=marker, raw=raw.rstrip('\n') if focus else raw, guest_exit_code=0))
        row = dict(phase='host-fixture', observation=native, bms_before_observation=0,
                   token_observation=1, bms_after_observation=2)
        return runtime, row

    def replay(self, runtime, row, focus=False, operation='query'):
        actual = verify_token_observation(row, runtime, RUN, UID, explicit_bundle=focus, operation=operation)
        self.assertEqual(actual, dict(bundle=BUNDLE, uid=UID, token_id=TOKEN, user_id=100, inst_index=0))
        token(row['observation'], RUN, UID, operation=operation, allow_transition=operation == 'revoke')

    def test_actual_normal_focus_and_revoke_frames_join_BMS(self):
        for focus, operation in [(False, 'query'), (True, 'query'), (False, 'revoke')]:
            with self.subTest(focus=focus, operation=operation), tempfile.TemporaryDirectory() as directory:
                runtime, row = self.fixture(Path(directory), focus, operation)
                self.replay(runtime, row, focus, operation)

    def test_summary_edits_cannot_replace_original_BMS_native_BMS(self):
        for focus in (False, True):
            for change in ('uid-echo', 'native-tuple', 'order', 'command-order', 'script', 'target',
                           'transport', 'guest-exit', 'timeout', 'raw', 'hash'):
                with self.subTest(focus=focus, change=change), tempfile.TemporaryDirectory() as directory:
                    runtime, row = self.fixture(Path(directory), focus)
                    shell, command = runtime['guest_shell_observations'][1], runtime['orchestration_commands'][1]
                    if change == 'uid-echo': row['observation']['expected_uid'] += 1
                    if change == 'native-tuple': row['observation']['at_token_id'] += 1
                    if change == 'order': row['bms_before_observation'] = 2
                    if change == 'command-order': shell['command_index'] = 0
                    if change == 'script': command['argv'][4] = 'true'
                    if change == 'target': command['argv'][2] = 'another-target'
                    if change == 'transport': command['argv'][0] = 'another-hdc'
                    if change == 'guest-exit': shell['guest_exit_code'] = 1
                    if change == 'timeout': command['timed_out'] = True
                    if change == 'raw': shell['raw'] = '{}'
                    if change == 'hash': command['stdout_sha256' if focus else 'sha256'] = '0' * 64
                    with self.assertRaises(ValueError): self.replay(runtime, row, focus)

    def test_rehashed_BMS_rotation_native_mismatch_and_truncated_footer_fail(self):
        for focus in (False, True):
            for change in ('bms-rotation', 'native-mismatch', 'duplicate-json', 'footer', 'outer-footer'):
                if change == 'outer-footer' and not focus:
                    continue
                with self.subTest(focus=focus, change=change), tempfile.TemporaryDirectory() as directory:
                    runtime, row = self.fixture(Path(directory), focus)
                    index = 2 if change == 'bms-rotation' else 1
                    command, shell = runtime['orchestration_commands'][index], runtime['guest_shell_observations'][index]
                    path = Path(command['stdout_path' if focus else 'log'])
                    raw = path.read_text()
                    if change == 'bms-rotation': raw = raw.replace(str(TOKEN), str(TOKEN + 1))
                    if change == 'native-mismatch': raw = raw.replace('"at_query_rc": 0', '"at_query_rc": 1')
                    if change == 'duplicate-json': raw = raw.replace('"result": 0', '"result": 0, "result": 0')
                    if change == 'footer': raw = raw.replace(shell['exit_marker'] + '0', shell['exit_marker'] + '1')
                    if change == 'outer-footer': raw = raw[:-2]
                    path.write_text(raw)
                    command['stdout_sha256' if focus else 'sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                    # Even a recomputed summary and file hash cannot repair original semantics.
                    shell['raw'] = raw.split('\n__FOCUS_EXIT_', 1)[0].rstrip('\n') if focus else raw
                    with self.assertRaises(ValueError): self.replay(runtime, row, focus)

    def test_earlier_BMS_command_cannot_be_reused_as_a_new_shell_observation(self):
        for focus in (False, True):
            with self.subTest(focus=focus), tempfile.TemporaryDirectory() as directory:
                runtime, row = self.fixture(Path(directory), focus)
                verify_token_observation(row, runtime, RUN, UID, explicit_bundle=focus, previous_command=-1)
                for previous in (0, 1, 2, True):
                    with self.subTest(previous=previous), self.assertRaises(ValueError):
                        verify_token_observation(row, runtime, RUN, UID,
                                                 explicit_bundle=focus, previous_command=previous)


if __name__ == '__main__':
    unittest.main()
