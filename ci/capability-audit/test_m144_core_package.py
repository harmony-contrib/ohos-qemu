"""Packaging regression/unit checks, not an actual engine HAP or guest gate."""
from pathlib import Path
import subprocess
import tempfile
import textwrap
from types import SimpleNamespace
import unittest

from test_access_token_kernel import patch_sections, write_preimages
from check_m144_core_package import verified_profile_content
from check_m144_hap_python_closure import copied_modules, verify as verify_python_closure
import shutil
import ast

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "patches/common/web/arkweb/m144_core_package"


class M144CorePackageTests(unittest.TestCase):
    def test_actual_hap_checker_copied_python_imports_are_closed_and_missing_helper_fails(self):
        result = verify_python_closure(ROOT)
        self.assertEqual(result['status'], 'pass', result)
        self.assertIn('verify_runtime_elf_contract.py', result['copied_modules'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); scripts = root / 'scripts'; scripts.mkdir()
            original = ROOT / 'scripts/package_m144_arkweb_core_in_docker.sh'
            for name in copied_modules(original):
                shutil.copy2(ROOT / 'scripts' / name, scripts / name)
            (scripts / original.name).write_text(original.read_text().replace(
                '  "${NATIVE_FROZEN}/scripts/verify_runtime_elf_contract.py" \\\n', ''))
            failed = verify_python_closure(root)
            self.assertEqual(failed['status'], 'fail')
            self.assertIn('ModuleNotFoundError', failed['stderr'])
            self.assertIn('verify_runtime_elf_contract', failed['stderr'])

    def test_actual_sdk_verifier_envelope_requires_signature_success(self):
        profile = {"bundle-info": {"bundle-name": "com.ohos.arkwebcore"}}
        self.assertEqual(verified_profile_content({"verifiedPassed": True, "content": profile}), profile)
        import json
        self.assertEqual(verified_profile_content({"verifiedPassed": True, "content": json.dumps(profile)}), profile)
        for envelope in ({"content": profile}, {"verifiedPassed": False, "content": profile},
                         {"verifiedPassed": "true", "content": profile}, {"verifiedPassed": True}):
            with self.subTest(envelope=envelope), self.assertRaises(ValueError):
                verified_profile_content(envelope)

    def preimages(self, source):
        patches = tuple(sorted(COMPONENT.glob("*.patch")))
        for patch in patches:
            patch_sections(patch)
        write_preimages(source, tuple(p for p in patches if not p.name.startswith('0008-')))
        package = source / 'src/third_party/ohos_nweb_hap/oh-package.json5'
        package.write_text('{\n  "modelVersion": "5.0.0",\n  "name": "nweb",\n'
                           '  "description": "",\n  "version": "1.0.0",\n  "dependencies": {}\n}\n')
        config = source / 'src/third_party/ohos_nweb_hap/hvigor/hvigor-config.json5'
        config.parent.mkdir(parents=True, exist_ok=True)
        # Supplied by the patched source template through official prepare,
        # not a patch to this generated project copy.
        config.write_text('{\n  "modelVersion": "6.0.0",\n  "dependencies": {},\n'
                          '  "properties": {"hvigor.dependency.useNpm": true}\n}\n')
        return patches

    def prepare(self, source):
        self.preimages(source)
        command = ["bash", str(COMPONENT / "apply.sh"), "--source-root", str(source)]
        for _ in range(2):
            subprocess.run(command, capture_output=True, check=True)
        return command

    def test_all_contiguous_old_prefixes_upgrade_from_content_despite_false_markers(self):
        for count in (0, 1, 5, 7, 8):
            with self.subTest(prefix=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                patches = self.preimages(root)
                for patch in patches[:count]:
                    subprocess.run(['git', '-C', str(root), 'apply', str(patch)], check=True)
                marker = root / '.ohos-qemu-patches'; marker.mkdir()
                import hashlib
                for patch in patches:
                    (marker / (hashlib.sha256(patch.read_bytes()).hexdigest() + '.applied')).write_text('false marker fixture')
                subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)],
                               check=True, capture_output=True)
                self.assertIn('"compileSdkVersion": "26.0.0"',
                              (root / 'src/third_party/ohos_nweb_hap/build-profile.json5').read_text())
                self.assertIn('"modelVersion": "6.0.0"',
                              (root / 'src/third_party/ohos_nweb_hap/oh-package.json5').read_text())

    def test_noncontiguous_partial_stack_fails_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); patches = self.preimages(root)
            for patch in (patches[0], patches[2]):
                subprocess.run(['git', '-C', str(root), 'apply', str(patch)], check=True)
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            failed = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)], capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in before})

    def test_pristine_repeat_and_unknown_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            command = self.prepare(source)
            path = source / "src/third_party/ohos_nweb_hap/build-profile.json5"
            self.assertIn('"compileSdkVersion": "26.0.0"', path.read_text())
            self.assertIn('"compatibleSdkVersion": 12', path.read_text())
            path.write_text(path.read_text().replace('"compileSdkVersion": "26.0.0"', '"compileSdkVersion": 99'))
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def function(self, root):
        self.prepare(root)
        path = root / "src/arkweb/build/hap/build_hap_rk.py"
        body = path.read_text().split('  def Hvigor(self, cmd_array):\n', 1)[1].split('\n  def Build(', 1)[0]
        namespace = {"subprocess": subprocess}
        exec('def Hvigor(self, cmd_array):\n' + textwrap.indent(textwrap.dedent(body), '  '), namespace)
        return namespace["Hvigor"]

    def test_hvigor_runs_once_with_original_arguments_environment_and_cwd(self):
        for exit_code in (0, 9):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                function = self.function(root)
                executable = root / "hvigorw"
                executable.write_text('#!/bin/sh\n'
                    'test "$OHOS_BASE_SDK_HOME" = release26 || exit 71\n'
                    'test "$1" = assembleHar || exit 72\n'
                    'printf "call\\n" >> calls\n'
                    'printf "sdk26-body\\n"\n'
                    f'exit {exit_code}\n')
                executable.chmod(0o700)
                project = SimpleNamespace(hvigor_wrapper=str(executable), root=str(root),
                                          env={"OHOS_BASE_SDK_HOME": "release26"})
                if exit_code:
                    with self.assertRaisesRegex(RuntimeError, 'sdk26-body'):
                        function(project, ["assembleHar"])
                else:
                    self.assertEqual(function(project, ["assembleHar"]), b"sdk26-body\n")
                self.assertEqual((root / "calls").read_text(), "call\n")

    def test_hvigor_launch_error_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            function = self.function(root)
            project = SimpleNamespace(hvigor_wrapper=str(root / "missing"), root=str(root), env={})
            with self.assertRaises(FileNotFoundError):
                function(project, ["assembleHap"])

    def test_hap_build_selects_exact_real_module_and_product_without_accepting_missing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root)
            source = (root / 'src/arkweb/build/hap/build_hap_rk.py').read_text()
            body = source.split('  def Build(self, auto_signed):\n', 1)[1]
            literal = '[' + body.split('self._build([', 1)[1].split('])', 1)[0] + ']'
            args = ast.literal_eval(literal)
            self.assertEqual(args, ['--mode=module', '-p', 'module=entry@default', '-p',
                                    'product=default', 'clean', '-p', 'debuggable=false',
                                    'assembleHap', '--no-daemon'])
            patch = COMPONENT / '0006-select-the-real-entry-module-and-product-for-hap.patch'
            self.assertNotIn('FileNotFoundError', patch.read_text())
            self.assertNotIn('entry-default-%s.hap', patch.read_text())

    def test_profile_changes_validity_not_permissions_or_application_identity(self):
        patch = COMPONENT / "0003-sign-public-core-with-valid-normal-release-profile.patch"
        sections = patch_sections(patch)
        profile = "src/third_party/ohos_nweb_hap/dependencies/rk/signature/UnsgnedReleasedProfileTemplate.json"
        changed = [line for line in patch.read_text().split('diff --git ')[1].splitlines()
                   if line.startswith(('+', '-')) and not line.startswith(('+++', '---'))]
        self.assertEqual(changed, ['-        "not-after": 1689473258', '+        "not-after": 2208988800'])
        self.assertIn(profile, sections)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            self.prepare(source)
            signer = source / "src/arkweb/build/sign.sh"
            subprocess.run(["bash", "-n", str(signer)], check=True)
            self.assertIn('26/toolchains/lib', signer.read_text())
            self.assertNotIn('set -x', signer.read_text())


if __name__ == "__main__":
    unittest.main()
