"""Exact Settings namespace repair; these tests do not claim guest acceptance."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/settings/tts_namespace'
spec = importlib.util.spec_from_file_location('settings_tts_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class SettingsTtsNamespaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='settings-tts-contract-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / baseline.PROJECT / baseline.FILES[0][0]
        self.path.parent.mkdir(parents=True)
        fixture = Path(__file__).parent / 'fixtures/settings_tts_namespace/napi_settings_init.cpp'
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), baseline.FILES[0][1])
        shutil.copy2(fixture, self.path)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              text=True, capture_output=True)

    def test_exact_apply_and_repeat(self):
        self.assertFalse(baseline.validate(self.root))
        for _ in range(3):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(baseline.validate(self.root, require_patched=True))

    def test_unknown_edit_is_preserved(self):
        with self.path.open('ab') as stream:
            stream.write(b'// unrelated edit\r\n')
        before = self.path.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.path.read_bytes())

    def test_alias_uses_same_object_and_retains_all_values(self):
        before = self.path.read_text()
        self.assertEqual(self.apply().returncode, 0)
        after = self.path.read_text()
        addition = ('    if (name == TTS_CLASS_NAME) {\n'
                    '        // The public SDK spells this namespace TTS; keep the existing alias.\n'
                    '        napi_set_named_property(env, exports, "TTS", result);\n'
                    '    }\n')
        self.assertEqual(after.count(addition), 1)
        self.assertEqual(after.replace(addition, ''), before)
        self.assertIn('const std::string TTS_CLASS_NAME = "tts";', after)
        self.assertIn('napi_set_named_property(env, exports, name.c_str(), result);\n' + addition, after)
        for key in ('PITCH', 'RATE', 'SYNTH'):
            self.assertIn('"settings.tts.default_tts_' + key.lower() + '"', after)
        self.assertIn('"settings.tts.enabled_tts_plugins"', after)

    def test_source_line_endings_are_preserved(self):
        self.assertEqual(self.apply().returncode, 0)
        data = self.path.read_bytes()
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))

    def test_shared_recipe_prepares_before_traversal(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        marker = 'bash "${SETTINGS_TTS_NAMESPACE_COMPONENT_SCRIPT}"'
        self.assertEqual(recipe.count(marker), 1)
        self.assertLess(recipe.index(marker), recipe.index('  write_source_preparation_metadata\n}'))


if __name__ == '__main__':
    unittest.main()
