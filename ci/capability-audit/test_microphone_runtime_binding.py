"""Transport framing controls only; these fixtures never attest guest behavior."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import batch_system_build_runtime_helpers as product
from verify_audio_capture_results import verify_guest_tool_runtimes
from verify_audio_focus_results import verify_capture_boot


class MicrophoneRuntimeBindingTests(unittest.TestCase):
    def test_focus_enclosing_target_device_and_boot_reject_joint_transport_rebinding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'boot.json'; boot = {'scope': 'host-only synthetic boot fixture'}
            path.write_text(json.dumps(boot))
            value = dict(target='owned-target', device='phone')
            capture = dict(value, boot=str(path), boot_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            verify_capture_boot(capture, value, boot)
            for change in ({'target': 'other-target'}, {'device': '2in1'}, {'boot_sha256': '0' * 64}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    verify_capture_boot(dict(capture, **change), value, boot)
            path.write_text(json.dumps({'scope': 'another boot'}));capture['boot_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): verify_capture_boot(capture, value, boot)

    def fixture(self, root, focus=False):
        mic, outer = '__MIC_EXIT_' + '1' * 32 + '__=', '__FOCUS_EXIT_' + '2' * 32 + '__='
        body = 'a' * 64 + '  /system/lib/ld-musl-aarch64.so.1'
        script = 'test -f /system/lib/ld-musl-aarch64.so.1 && sha256sum /system/lib/ld-musl-aarch64.so.1'
        wrapped = script + '; task_mic_rc=$?; printf "\\n' + mic + '%s\\n" "$task_mic_rc"'
        mic_output = body + '\n\n' + mic + '0\n'
        persona = 'audio-focus' if focus else 'audio-capture'

        def file(name, text):
            path = root / name
            path.write_text(text)
            return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

        hdc = dict(file('hdc', 'private fake transport fixture'), argv0='approved-hdc')
        if focus:
            wrapped += '; focus_rc=$?; printf "\\n' + outer + '%s\\n" "$focus_rc"'
            stdout = file('stdout', mic_output + '\n' + outer + '0\n')
            stderr = file('stderr', '')
            command = {'stdout_path': stdout['path'], 'stdout_sha256': stdout['sha256'],
                       'stderr_path': stderr['path'], 'stderr_sha256': stderr['sha256']}
        else:
            log = file('log', mic_output)
            command = {'log': log['path'], 'sha256': log['sha256']}
        command.update(argv=['approved-hdc', '-t', 'owned-target', 'shell', wrapped], exit_code=0)
        actual = {'soname': 'libc.so', 'path': '/system/lib/ld-musl-aarch64.so.1', 'sha256': 'a' * 64}
        runtime = {'parent_persona': persona, 'hdc': hdc, 'target': 'owned-target',
            'archive_sha256': 'f' * 64, 'orchestration_commands': [command],
            'guest_shell_observations': [{'script': script, 'label': 'DSO', 'exit_marker': mic,
                'command_index': 0, 'raw': mic_output.rstrip('\n') if focus else mic_output,
                'guest_exit_code': 0}],
            'guest_runtime_DSOs': [{'tool': 'token', 'script': script, 'raw': body,
                'observation': actual, 'shell_observation': 0, 'command_index': 0}]}
        tools = {'tools': {'token': {'DT_NEEDED': ['libc.so']}}}
        return runtime, tools, persona, script, body, actual

    def replay(self, data):
        runtime, tools, persona, script, body, actual = data
        def observed(row, soname, raw, *, archive_sha256):
            if raw != body or soname != 'libc.so' or archive_sha256 != 'f' * 64:
                raise ValueError('wrong actual runtime bytes')
            return actual
        with patch.object(product, 'runtime_guest_script', return_value=script), \
                patch.object(product, 'verify_guest_runtime_raw', side_effect=observed):
            verify_guest_tool_runtimes(runtime, tools, parent_persona=persona)

    def test_exact_single_and_nested_guest_footers(self):
        for focus in (False, True):
            with self.subTest(focus=focus), tempfile.TemporaryDirectory() as directory:
                self.replay(self.fixture(Path(directory), focus))

    def test_hdc_success_cannot_mask_guest_failure_wrong_target_or_duplicate(self):
        for change in ('guest-error', 'target', 'hdc', 'duplicate', 'missing', 'persona', 'runtime-bytes'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                data = self.fixture(Path(directory))
                runtime = data[0]
                if change == 'guest-error': runtime['guest_shell_observations'][0]['guest_exit_code'] = 1
                if change == 'target': runtime['orchestration_commands'][0]['argv'][2] = 'other-target'
                if change == 'hdc': runtime['orchestration_commands'][0]['argv'][0] = 'other-hdc'
                if change == 'duplicate': runtime['guest_runtime_DSOs'] *= 2
                if change == 'missing': runtime['guest_runtime_DSOs'] = []
                if change == 'persona': runtime['parent_persona'] = 'audio-focus'
                if change == 'runtime-bytes': runtime['guest_runtime_DSOs'][0]['observation'] = dict(
                    runtime['guest_runtime_DSOs'][0]['observation'], sha256='b' * 64)
                with self.assertRaises(ValueError): self.replay(data)

    def test_rehashed_truncated_or_failed_outer_output_still_fails(self):
        for focus in (False, True):
            for change in ('truncated', 'failed', 'extra'):
                with self.subTest(focus=focus, change=change), tempfile.TemporaryDirectory() as directory:
                    data = self.fixture(Path(directory), focus)
                    command = data[0]['orchestration_commands'][0]
                    path = Path(command['stdout_path'] if focus else command['log'])
                    text = path.read_text()
                    text = text[:-2] if change == 'truncated' else text[:-2] + '1\n' if change == 'failed' else text + 'extra\n'
                    path.write_text(text)
                    command['stdout_sha256' if focus else 'sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                    with self.assertRaises(ValueError): self.replay(data)


if __name__ == '__main__':
    unittest.main()
