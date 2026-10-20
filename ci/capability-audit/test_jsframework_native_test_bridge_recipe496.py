"""Execute real source-verification recipe fragments on authentic paired files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/third_party/jsframework/native_test_bridge'
FIXTURE = COMPONENT / 'fixtures/original'
BUILDER = ROOT / 'scripts/build_standard_qemu_in_docker.sh'
PACKAGER = ROOT / 'scripts/package_standard_qemu.sh'


class JSRecipe(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='js-bridge-recipe-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / 'source with spaces'
        shutil.copytree(FIXTURE, self.source)
        (self.base / 'cache/logs').mkdir(parents=True)
        (self.source / 'out/arm64_virt').mkdir(parents=True)
        self.package = self.base / 'old package'
        self.package.mkdir()
        (self.package / 'payload').write_bytes(b'existing artifact')
        self.environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.environment.update(
            OHOS_ROOT=str(self.source), SOURCE_ROOT=str(self.source),
            CACHE_ROOT=str(self.base / 'cache'), SCRIPT_DIR=str(ROOT / 'scripts'),
            JSFRAMEWORK_NATIVE_TEST_BRIDGE_COMPONENT_SCRIPT=str(COMPONENT / 'apply.sh'),
            PRODUCT='arm64_virt', DEVICE_TYPE_PROFILE='qemu_phone_full_source',
            PACKAGE_DIR=str(self.package), GIT_CEILING_DIRECTORIES=str(self.base),
            GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
            PYTHONDONTWRITEBYTECODE='1')

    def run_shell(self, program, **updates):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', program],
                              env=dict(self.environment, **updates),
                              capture_output=True, text=True, timeout=30)

    def snapshot(self):
        return {str(p.relative_to(self.source)): p.read_bytes()
                for p in self.source.rglob('*') if p.is_file()
                and 'out' not in p.relative_to(self.source).parts}

    def source_fragment(self):
        text = BUILDER.read_text()
        begin = text.index('  bash "${JSFRAMEWORK_NATIVE_TEST_BRIDGE_COMPONENT_SCRIPT}"')
        end = text.index('  bash "${AUDIO_HAPTIC_SYNC_ID_COMPONENT_SCRIPT}"', begin)
        return text[begin:end]

    def package_function(self):
        text = PACKAGER.read_text()
        begin = text.index('verify_jsframework_native_test_bridge_source() {\n')
        end = text.index('verify_number_native_observation_source() {\n', begin)
        return text[begin:end]

    def test_real_apply_verify_and_repeat(self):
        first = self.run_shell(self.source_fragment())
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        after = self.snapshot()
        second = self.run_shell(self.source_fragment())
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(self.snapshot(), after)

    def test_source_guard_failure_preserves_all_input_files(self):
        guard = self.source / 'third_party/jsframework/test/lib.ts'
        guard.write_bytes(guard.read_bytes() + b'\n# unknown input\n')
        before = self.snapshot()
        result = self.run_shell(self.source_fragment())
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_package_preimage_refused_before_artifact_mutation(self):
        before = self.snapshot()
        result = self.run_shell(self.package_function() +
                                '\nverify_jsframework_native_test_bridge_source\nrm -rf "${PACKAGE_DIR}"\n')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.package / 'payload').read_bytes(), b'existing artifact')
        self.assertEqual(before, self.snapshot())
        applied = self.run_shell(self.source_fragment())
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        for profile in ('qemu_phone_full_source', 'qemu_2in1_full_source'):
            result = self.run_shell(self.package_function() + '\nverify_jsframework_native_test_bridge_source\n',
                                    DEVICE_TYPE_PROFILE=profile)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((self.source / 'out/arm64_virt/jsframework-native-test-bridge-source.json').read_text())
            self.assertTrue(receipt['patched'])
            for key in ('compiled', 'native_linux_mocha_passed', 'runtime_passed', 'first_artifact_behavior_gate_passed'):
                self.assertFalse(receipt[key])

    def test_package_gate_order_and_other_profiles(self):
        text = PACKAGER.read_text()
        call = text.index('\nverify_jsframework_native_test_bridge_source\n')
        self.assertLess(call, text.index('rm -rf "${PACKAGE_DIR}"'))
        self.assertLess(text.index('rewrite_package_launchers "${REWRITE_PACKAGE}"'), call)
        for profile in ('default', 'param_only'):
            result = self.run_shell(self.package_function() + '\nverify_jsframework_native_test_bridge_source\n',
                                    DEVICE_TYPE_PROFILE=profile)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((self.source / 'out/arm64_virt/jsframework-native-test-bridge-source.json').exists())


if __name__ == '__main__':
    unittest.main()
