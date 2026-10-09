"""Exact Settings namespace repair; these tests do not claim guest acceptance."""
import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run

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

    def test_actual_initializer_alias_and_unrelated_names_under_sanitizers(self):
        self.assertEqual(self.apply().returncode, 0)
        source = self.path.read_text()
        def function(name):
            start = source.index('void ' + name + '(')
            return source[start:source.index('\n}', start) + 2]
        initializer = function('InitConstClassByName')
        constants = '\n'.join(line for line in source.splitlines()
                              if re.match(r'const std::string (\w+_CLASS_NAME|TTS::)', line))
        declaration = source[source.index('class TTS\n'):source.index('\n};', source.index('class TTS\n'))+3]
        helpers = '\n'.join('void '+name+'(napi_env, std::map<const char*, napi_value>& values) '
                            '{ values["unrelated-fixture"] = Make(); }'
                            for name in sorted(set(re.findall(r'\b(Init\w+Map)\(', initializer)))
                            if name != 'InitTTSMap')
        mock = r'''
// Preserve the fixed upstream initializer's VLA; do not rewrite the exercised method.
#pragma clang diagnostic ignored "-Wvla-cxx-extension"
#include <cassert>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { std::string text; std::map<std::string, Value*> own; };
using napi_env = void*;
using napi_value = Value*;
std::vector<std::unique_ptr<Value>> storage;
Value* Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
constexpr size_t NAPI_AUTO_LENGTH = 0;
constexpr void* ClassConstructor = nullptr;
struct napi_property_descriptor { const char* name; napi_value value; };
#define DECLARE_NAPI_STATIC_PROPERTY(name, value) {name, value}
void napi_create_string_utf8(napi_env, const char* text, size_t, napi_value* value)
{ *value = Make(); (*value)->text = text; }
void napi_define_class(napi_env, const char*, size_t, void*, void*, size_t count,
    napi_property_descriptor* properties, napi_value* value)
{ *value = Make(); for(size_t i = 0; i < count; ++i) (*value)->own[properties[i].name] = properties[i].value; }
void napi_set_named_property(napi_env, napi_value object, const char* name, napi_value value)
{ object->own[name] = value; }
'''
        main = r'''
int main() {
 for (int repeat = 0; repeat < 128; ++repeat) {
  storage.clear(); auto exports = Make(); auto sentinel = Make(); exports->own["existing"] = sentinel;
  InitConstClassByName(nullptr, exports, "tts");
  assert(exports->own.size() == 3 && exports->own.at("existing") == sentinel);
  auto tts = exports->own.at("TTS"); assert(tts == exports->own.at("tts") && tts->own.size() == 4);
  assert(tts->own.at("DEFAULT_TTS_PITCH")->text == "settings.tts.default_tts_pitch");
  assert(tts->own.at("DEFAULT_TTS_RATE")->text == "settings.tts.default_tts_rate");
  assert(tts->own.at("DEFAULT_TTS_SYNTH")->text == "settings.tts.default_tts_synth");
  assert(tts->own.at("ENABLED_TTS_PLUGINS")->text == "settings.tts.enabled_tts_plugins");
  InitConstClassByName(nullptr, exports, "date");
  assert(exports->own.size() == 4 && exports->own.at("TTS") == tts);
  InitConstClassByName(nullptr, exports, "unknown");
  assert(exports->own.size() == 4 && exports->own.at("existing") == sentinel);
 }
}
'''
        compile_run(mock + declaration + constants + helpers + function('InitTTSMap') + initializer + main,
                    language='c++')

    def test_shared_recipe_prepares_before_traversal(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        marker = 'bash "${SETTINGS_TTS_NAMESPACE_COMPONENT_SCRIPT}"'
        self.assertEqual(recipe.count(marker), 1)
        self.assertLess(recipe.index(marker), recipe.index('  write_source_preparation_metadata\n}'))


if __name__ == '__main__':
    unittest.main()
