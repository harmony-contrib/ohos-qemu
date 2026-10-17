"""Failure protocol/control-flow checks; no native/SDK/guest result is implied."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from audio_capture_runtime import CaptureRuntime
from audio_capture_contract import sha
from build_audio_capture_tools import verify_compile_command


class TokenDiagnosticsTests(unittest.TestCase):
    def test_replay_requires_unique_actual_compile_and_object_link_binding(self):
        row = {'binary': '/private/alsa_inject/alsa_inject',
               'compile_command': ['clang', '-c', '/private/alsa_inject/batch_media_alsa_inject.c',
                   '-MF', '/private/alsa_inject/headers.d', '-o', '/private/alsa_inject/alsa_inject.o'],
               'link_command': ['clang', '/private/alsa_inject/alsa_inject.o']}
        command = dict(label='alsa_inject-compile', argv=row['compile_command'], exit_code=0, timed_out=False)
        verify_compile_command({'commands': [command]}, 'alsa_inject', row)
        for commands in ([], [command, command], [dict(command, argv=['different'])],
                         [dict(command, exit_code=1)], [dict(command, timed_out=True)]):
            with self.subTest(commands=commands), self.assertRaises(ValueError):
                verify_compile_command({'commands': commands}, 'alsa_inject', row)
        for key in ('compile_command', 'link_command'):
            bad = dict(row); bad[key] = row[key] + []
            bad[key][-1] = '/private/other.o'
            altered = dict(command, argv=bad['compile_command'])
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_compile_command({'commands': [altered]}, 'alsa_inject', bad)

    def test_HDC_success_cannot_hide_real_token_failure_and_raw_context_is_kept(self):
        runtime = CaptureRuntime.__new__(CaptureRuntime); calls = []
        def shell(script, label):
            calls.append((script, label)); marker = script.split('printf "\\n', 1)[1].split('%s', 1)[0]
            return 'AUDIO_CAPTURE_TOKEN_FAIL stage=hap-token-identity rc=1\n' + marker + '1\n'
        runtime.shell = shell
        with self.assertRaisesRegex(ValueError, 'independent-MIC-token-before-launch'):
            runtime.actual_shell('real-command-not-executed-by-this-test', 'independent-MIC-token-before-launch')
        self.assertEqual(len(calls), 1)
        self.assertIn('task_mic_rc=$?', calls[0][0])

    def test_missing_profile_rejects_before_any_tool_or_guest_command(self):
        runtime = CaptureRuntime.__new__(CaptureRuntime)
        runtime.args = SimpleNamespace(); runtime.output = Path('/unused-host-contract-only')
        runtime.command = lambda *a, **k: self.fail('no actual tool may execute')
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'profile and SHA256 required'): runtime.prepare()

    def test_prebuilt_tools_missing_pair_bad_hash_and_noncanonical_input_fail_without_fallback(self):
        runtime = CaptureRuntime.__new__(CaptureRuntime); runtime.args = SimpleNamespace(arch='arm64')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'original/build.json'; path.parent.mkdir(); path.write_text('{}\n')
            for env in ({'OHOS_QA_MIC_TOOLS_BUILD': str(path)},
                        {'OHOS_QA_MIC_TOOLS_BUILD_SHA256': sha(path)},
                        {'OHOS_QA_MIC_TOOLS_BUILD': str(path), 'OHOS_QA_MIC_TOOLS_BUILD_SHA256': '0' * 64},
                        {'OHOS_QA_MIC_TOOLS_BUILD': str(path.parent / '../original/build.json'),
                         'OHOS_QA_MIC_TOOLS_BUILD_SHA256': sha(path)}):
                with self.subTest(env=env), patch.dict('os.environ', env, clear=True), \
                        patch('audio_capture_runtime.verify_installed_tools') as verify:
                    with self.assertRaises(ValueError): runtime.reuse_tools(Path(directory) / 'case/tools', {})
                    verify.assert_not_called()

    def test_prebuilt_tools_complete_copy_replays_original_and_copy_with_same_profile(self):
        runtime = CaptureRuntime.__new__(CaptureRuntime); runtime.args = SimpleNamespace(arch='arm64')
        runtime.value = {}; runtime.save = lambda: None
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve(); source = base / 'original'; source.mkdir()
            receipt = source / 'build.json'; receipt.write_text('{"historical_path":"/unchanged/build.json"}\n')
            (source / 'product-build').mkdir(); (source / 'product-build/link.log').write_text('actual trace fixture\n')
            tools = base / 'case/tools'; profile = {'host_controlled_profile': True}
            build = {'tools': {'alsa_inject': {'installed_runtime_profile': {'profile': profile}}}}
            env = {'OHOS_QA_MIC_TOOLS_BUILD': str(receipt), 'OHOS_QA_MIC_TOOLS_BUILD_SHA256': sha(receipt)}
            with patch.dict('os.environ', env, clear=True), \
                    patch('audio_capture_runtime.verify_installed_tools', return_value=build) as verify:
                self.assertTrue(runtime.reuse_tools(tools, profile))
                self.assertEqual([call.args for call in verify.call_args_list],
                    [(receipt, 'arm64'), (tools / 'build.json', 'arm64')])
            self.assertEqual((tools / 'build.json').read_bytes(), receipt.read_bytes())
            self.assertEqual((tools / 'product-build/link.log').read_bytes(), (source / 'product-build/link.log').read_bytes())
            self.assertEqual(runtime.value['prebuilt_tools_build_input'], {'path': str(receipt), 'sha256': sha(receipt)})
            with patch.dict('os.environ', env, clear=True), \
                    patch('audio_capture_runtime.verify_installed_tools', return_value=build):
                with self.assertRaisesRegex(ValueError, 'profile differs'):
                    runtime.reuse_tools(base / 'mismatch/tools', {'different_profile': True})

    def test_cleanup_keeps_unknown_ownership_as_failure_and_preserves_files(self):
        runtime = CaptureRuntime.__new__(CaptureRuntime)
        runtime.started = True; runtime.finished = False; runtime.process = None; runtime.producer_log = None
        runtime.boot_id = '12345678-1234-1234-1234-123456789abc'
        runtime.remote = '/data/local/tmp/qemu-mic-' + 'a' * 32; runtime.value = {}; scripts = []
        with tempfile.TemporaryDirectory() as directory:
            runtime.output = Path(directory)
            def actual(script, label):
                scripts.append((script, label))
                if label == 'cleanup-only-owned-PCM-producer': raise ValueError('controlled changed kernel starttime')
                if label == 'PCM-cleanup-boot-before-stop': return runtime.boot_id
            runtime.actual_shell = actual
            with self.assertRaisesRegex(ValueError, 'changed kernel starttime'): runtime.close()
            self.assertFalse(runtime.finished); self.assertFalse(runtime.value['cleanup_complete'])
            self.assertFalse(any('rm -' in script for script, _ in scripts))
            self.assertTrue(runtime.started)

    def test_helper_identity_assertions_are_not_removed_to_make_diagnostics_pass(self):
        source = (Path(__file__).parent / 'probes/audio_capture_token.cpp').read_text()
        for check in ('token == 0', 'queried != 0', 'info.tokenID != token', 'info.userID != 100',
                      'info.instIndex != 0', 'info.bundleName != bundle', 'info.uid != static_cast<int32_t>(expected)'):
            self.assertIn(check, source)
        for context in ('get_hap_info_rc=', 'info_token=', 'info_uid=', 'info_user=', 'info_inst=',
                        'actual_bundle_hex=', 'before_clock_errno=', 'after_clock_errno='):
            self.assertIn(context, source)
        self.assertIn('return Fail("hap-token-identity", 1)', source)
        self.assertIn('return Fail("monotonic-clock", 1)', source)


if __name__ == '__main__': unittest.main()
