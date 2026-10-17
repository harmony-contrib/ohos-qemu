"""Signer policy mutations only; synthetic command rows never attest a guest."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from run_root_probe import require_signer_executor, TRUSTED_SIGNER_IMAGE_ID, TRUSTED_SIGNER_SOURCE_VOLUME
import run_selection_contract_probe as runner
from verify_selection_evidence import (ROOT, selection_signing_argv, verify_evidence,
                                       verify_signing_installation)

PIN = 'sha256:8f7a960c7dc515a597d43a510d6d8a5e634e5c94a55aa5d9e22bfbf6b0f42c55'
UDID = 'A' * 64
SIGN_LOG = '\n'.join(('verify codesign success', 'Digest verify result: true',
                       'verify-app success', 'verify permission sign success'))


class SelectionExecutorBinding(unittest.TestCase):
    def fixture(self, role='normal'):
        output = Path('/owned/selection')
        unsigned = output / role / 'project/entry/build/default/outputs/default/entry-default-unsigned.hap'
        signed = output / role / 'selection-signed.hap'
        app = dict(unsigned_hap=dict(path=str(unsigned)), signed_hap=dict(path=str(signed)))
        # Independent expected transport: do not obtain this row from the
        # production builder that the verifier itself uses.
        argv = ['docker', 'run', '--rm', '--platform', 'linux/amd64',
                '--mount', 'type=volume,src=ohos-qemu-7_0-release-source,dst=/ohos,readonly',
                '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
                '--mount', 'type=bind,src=/owned/selection,dst=/probe', PIN,
                'python3', '/work/ci/capability-audit/sign_arkui_selection_probe.py',
                '--signer-dist', '/ohos/developtools/hapsigner/dist',
                '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
                '--unsigned', '/probe/' + unsigned.relative_to(output).as_posix(),
                '--output', '/probe/' + signed.relative_to(output).as_posix(),
                '--role', role, '--udid', UDID]
        signing = [2, dict(argv=argv, exit_code=0), SIGN_LOG]
        installation = [3, dict(argv=['/fixed/hdc', '-t', 'owned-target', 'install', str(signed)],
                                exit_code=0), 'install bundle successfully.']
        return app, signing, installation

    def check(self, app, signing, installation, role='normal', build_index=1):
        return verify_signing_installation(app, role, UDID, '/fixed/hdc', 'owned-target',
                                           build_index, signing, installation)

    def test_only_the_independently_frozen_pin_and_source_are_trusted(self):
        self.assertEqual(TRUSTED_SIGNER_IMAGE_ID, PIN)
        self.assertEqual(TRUSTED_SIGNER_SOURCE_VOLUME, 'ohos-qemu-7_0-release-source')
        require_signer_executor(PIN)
        for image in ('ohos-qemu-m144-build-env:7.0-release', 'untrusted:latest',
                      'sha256:' + '0' * 64, PIN + '\n', 'registry.invalid/image@' + PIN):
            with self.subTest(image=image), self.assertRaises(ValueError):
                require_signer_executor(image)
        with self.assertRaises(ValueError):
            require_signer_executor(PIN, 'other-source')

    def test_exact_pinned_signing_and_installation_accept_all_three_roles(self):
        for role in ('normal', 'reader-denied', 'reader'):
            app, signing, installation = self.fixture(role)
            with self.subTest(role=role):
                self.assertEqual(selection_signing_argv(app, role, UDID), signing[1]['argv'])
                self.check(app, signing, installation, role)

    def test_report_or_actual_image_cannot_select_its_own_expected_executor(self):
        for image in ('ohos-qemu-m144-build-env:7.0-release', 'other:latest', 'sha256:' + 'f' * 64):
            app, signing, installation = self.fixture()
            signing[1]['argv'][11] = image
            app['docker_image'] = app['expected_image'] = image
            signing[1]['docker_image'] = image
            with self.subTest(image=image), self.assertRaises(ValueError):
                self.check(app, signing, installation)

    def test_exact_platform_mounts_readonly_signer_role_device_and_paths_are_required(self):
        changes = {4: 'linux/arm64', 6: 'type=volume,src=other,dst=/ohos,readonly',
                   8: 'type=bind,src=' + str(ROOT) + ',dst=/work',
                   10: 'type=bind,src=/different,dst=/probe', 12: 'sh',
                   13: '/work/ci/capability-audit/other_signer.py', 15: '/other/signer',
                   17: '/other/hap-sign-tool.jar', 19: '/probe/other-unsigned.hap',
                   21: '/probe/other-signed.hap', 23: 'reader', 25: 'B' * 64}
        for index, value in changes.items():
            app, signing, installation = self.fixture()
            signing[1]['argv'][index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.check(app, signing, installation)
        app, signing, installation = self.fixture()
        signing[1]['argv'].insert(3, '--privileged')
        with self.assertRaises(ValueError):
            self.check(app, signing, installation)

    def test_real_installation_transport_path_success_and_order_remain_required(self):
        for index, value in ((0, '/other/hdc'), (2, 'other-target'), (3, 'uninstall'), (4, '/other.hap')):
            app, signing, installation = self.fixture()
            installation[1]['argv'][index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.check(app, signing, installation)
        for log in ('', 'failed to install; a previous attempt was successful'):
            app, signing, installation = self.fixture()
            installation[2] = log
            with self.subTest(log=log), self.assertRaises(ValueError):
                self.check(app, signing, installation)
        for build_index, sign_index, install_index in ((2, 2, 3), (1, 3, 2), (3, 2, 4)):
            app, signing, installation = self.fixture()
            signing[0], installation[0] = sign_index, install_index
            with self.subTest(order=(build_index, sign_index, install_index)), self.assertRaises(ValueError):
                self.check(app, signing, installation, build_index=build_index)

    def test_each_actual_signature_verification_marker_is_required(self):
        for marker in SIGN_LOG.splitlines():
            app, signing, installation = self.fixture()
            signing[2] = SIGN_LOG.replace(marker, '')
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                self.check(app, signing, installation)

    def test_nonzero_signature_or_install_exit_cannot_use_success_text(self):
        for failed in ('sign', 'install'):
            app, signing, installation = self.fixture()
            (signing if failed == 'sign' else installation)[1]['exit_code'] = 1
            with self.subTest(failed=failed), self.assertRaises(ValueError):
                self.check(app, signing, installation)

    def test_wrong_executor_is_rejected_before_output_or_any_subprocess(self):
        for image, volume in (('sha256:' + '0' * 64, TRUSTED_SIGNER_SOURCE_VOLUME), (PIN, 'other-source')):
            with self.subTest(image=image, volume=volume), patch.object(runner.subprocess, 'Popen') as launch:
                with self.assertRaisesRegex(ValueError, 'frozen signer'):
                    runner.run(SimpleNamespace(docker_image=image, source_volume=volume))
                launch.assert_not_called()

    def test_existing_failed_report_is_not_promoted_by_fixing_the_executor(self):
        with self.assertRaisesRegex(ValueError, 'complete three-role'):
            verify_evidence(dict(status='fail', failures=['original failure'], docker_image=PIN),
                            'a' * 64, 'boot', 'arm64', 'phone', 'target')

    def test_diagnostic_sign_commands_use_the_fixed_pin_and_check_environment(self):
        here = Path(__file__).parent
        for name in ('run_hitrace_diagnostic.py', 'run_graphics_memory_diagnostic.py'):
            tree = ast.parse((here / name).read_text())
            dispatches = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and
                          isinstance(node.func, ast.Name) and node.func.id == 'command' and node.args and
                          isinstance(node.args[0], ast.List) and node.args[0].elts and
                          isinstance(node.args[0].elts[0], ast.Constant) and node.args[0].elts[0].value == 'docker']
            with self.subTest(runner=name):
                self.assertEqual(len(dispatches), 1)
                self.assertIsInstance(dispatches[0].args[0].elts[11], ast.Name)
                self.assertEqual(dispatches[0].args[0].elts[11].id, 'TRUSTED_SIGNER_IMAGE_ID')
                guards = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and
                          isinstance(node.func, ast.Name) and node.func.id == 'require_signer_executor']
                self.assertEqual(len(guards), 1)
                self.assertEqual(len(guards[0].args), 2)


if __name__ == '__main__':
    unittest.main()
