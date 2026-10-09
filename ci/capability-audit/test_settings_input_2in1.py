"""Compile real route tables and preserve non-input device boundaries."""
import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/settings/input_2in1_navigation'
spec = importlib.util.spec_from_file_location('settings_input_2in1_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class SettingsInput2in1Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='settings-input-2in1-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / baseline.PROJECT / baseline.FILES[0][0]
        self.source.parent.mkdir(parents=True)
        fixture = Path(__file__).parent / 'fixtures/settings_input_2in1' / self.source.name
        # The pinned upstream file has no final newline. The checked-in text
        # fixture has exactly one for tooling; reconstruct then hash every byte.
        data = fixture.read_bytes()
        self.assertTrue(data.endswith(b'}\n'))
        self.original = data[:-1]
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), baseline.FILES[0][1])
        self.source.write_bytes(self.original)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_exact_idempotent(self):
        self.assertFalse(baseline.validate(self.root))
        for _ in range(3):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(baseline.validate(self.root, require_patched=True))

    def test_unknown_edit_preserved(self):
        self.source.write_bytes(self.original + b'\n// unrelated edit\n')
        before = self.source.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(before, self.source.read_bytes())

    def test_compiled_actual_routes_only_two_changes(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('requires a C++ compiler')
        original = self.original.decode()
        declarations = []
        for cls in ('SettingsPageUrl', 'DeviceType'):
            names = re.findall(r'const std::string ' + cls + r'::(\w+) =', original)
            declarations.append('struct ' + cls + ' { ' + ''.join(
                'static const std::string ' + name + ';' for name in names) + ' };')
        header = ('#include <string>\n#include <map>\n#include <unordered_set>\n'
                  '#define SETTING_LOG_INFO(...)\n#define SETTING_LOG_ERROR(...)\n'
                  'namespace OHOS { namespace Settings {\n' + '\n'.join(declarations) +
                  '\nbool IsPageSupportJump(const std::string &, const std::string &); }}\n')
        self.source.with_suffix('.h').write_text(header)
        pages = re.findall(r'const std::string SettingsPageUrl::\w+ = "([^"]+)";', original)
        devices = ['phone', 'tablet', '2in1', 'wearable', 'unknown', '']
        main = self.root / 'main.cpp'
        main.write_text('#include "napi_open_settings_page_util.h"\n#include <iostream>\n'
                        'int main() {\n' + ''.join(
                            'std::cout << OHOS::Settings::IsPageSupportJump("' + device + '","' + page + '");\n'
                            for device in devices for page in pages + ['unknown', '']) + '}\n')

        def run(name):
            executable = self.root / name
            result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                     '-I', str(self.source.parent), str(self.source), str(main),
                                     '-o', str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return subprocess.check_output([str(executable)], text=True)

        before = run('original')
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = run('patched')
        pairs = [(device, page) for device in devices for page in pages + ['unknown', '']]
        self.assertEqual(len(before), len(pairs))
        self.assertEqual(len(after), len(pairs))
        changed = []
        for pair, old, new in zip(pairs, before, after):
            if old != new:
                self.assertEqual((old, new), ('0', '1'))
                changed.append(pair)
        self.assertEqual(changed, [('2in1', 'set_input'), ('2in1', 'other_input_detail_settings')])


if __name__ == '__main__':
    unittest.main()
