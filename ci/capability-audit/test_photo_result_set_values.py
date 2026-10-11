"""Real host NAPI conversion from exact source functions; no real RDB claim."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_access_token_kernel import patch_sections
from test_photo_result_set import BASE, HERE, function

SUPPORT = r'''
#include <node_api.h>
#include <map>
#include <string>
#include <variant>
#include <vector>
#include <algorithm>
#define NAPI_ERR_LOG(...) ((void)0)
using Value = std::variant<std::monostate, int32_t, int64_t, double, bool, std::string, std::vector<uint8_t>>;
struct ValueObject { Value value; };
struct RowEntity {
    std::map<std::string, ValueObject> values;
    const std::map<std::string, ValueObject> &Get() const { return values; }
};
// The two unchanged generic dispatch templates are the pinned header's
// behavior. Variant/row containers here are explicitly backend fixtures.
template <typename T> napi_value Convert2JSValue(napi_env, const T &) { return nullptr; }
template <typename... Types> napi_value Convert2JSValue(napi_env env, const std::variant<Types...> &value) {
    return std::visit([&](const auto &v) -> napi_value { return Convert2JSValue(env, v); }, value);
}
'''

TAIL = r'''
static napi_value ValueCall(napi_env env, napi_callback_info info) {
    size_t argc = 1; napi_value arg = nullptr; int32_t index = -1;
    napi_get_cb_info(env, info, &argc, &arg, nullptr, nullptr); napi_get_value_int32(env, arg, &index);
    const std::vector<ValueObject> values = {{std::monostate{}}, {int32_t{-7}}, {int64_t{4294967296LL}},
        {1.25}, {true}, {std::string("native UTF8 \xe4\xb8\xad\xe6\x96\x87")},
        {std::vector<uint8_t>{0,17,127,255}}, {std::vector<uint8_t>{}}};
    if (index < 0 || static_cast<size_t>(index) >= values.size()) return nullptr;
    return Convert2JSValue(env, values[index]);
}
static napi_value RowCall(napi_env env, napi_callback_info) {
    RowEntity row{{{"nil", {std::monostate{}}}, {"number", {int64_t{7}}},
        {"blob", {std::vector<uint8_t>{0,17,127,255}}}, {"empty", {std::vector<uint8_t>{}}},
        {"text", {std::string("row")}}, {"real", {1.25}}, {"flag", {false}}}};
    return Convert2JSValue(env, row);
}
static napi_value Init(napi_env env, napi_value exports) {
    for (const auto &entry : {std::pair<const char *, napi_callback>{"value", ValueCall}, {"row", RowCall}}) {
        napi_value method = nullptr;
        napi_create_function(env, entry.first, NAPI_AUTO_LENGTH, entry.second, nullptr, &method);
        napi_set_named_property(env, exports, entry.first, method);
    }
    return exports;
}
NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
'''

SCRIPT = r'''
const assert = require('node:assert/strict'); const addon = require(process.argv[2]);
if (process.argv[3] === 'old') {
  assert.equal(addon.value(0), undefined); assert.equal(Object.hasOwn(addon.row(), 'nil'), false);
  console.log('old SQL NULL converter defect reproduced'); process.exit(0);
}
for (let cycle = 0; cycle < 128; cycle++) {
  assert.equal(addon.value(0), null); assert.equal(addon.value(1), -7);
  assert.equal(addon.value(2), 4294967296); assert.equal(addon.value(3), 1.25);
  assert.equal(addon.value(4), true); assert.equal(addon.value(5), 'native UTF8 中文');
  const bytes = addon.value(6); assert.ok(bytes instanceof Uint8Array);
  assert.deepEqual([...bytes], [0,17,127,255]); bytes[0] = 255;
  assert.deepEqual([...addon.value(6)], [0,17,127,255]);
  assert.ok(addon.value(7) instanceof Uint8Array); assert.equal(addon.value(7).length, 0);
  const row = addon.row(); assert.equal(Object.hasOwn(row, 'nil'), true); assert.equal(row.nil, null);
  assert.deepEqual(Object.keys(row).sort(), ['blob','empty','flag','nil','number','real','text']);
  assert.equal(row.number, 7); assert.equal(row.real, 1.25); assert.equal(row.text, 'row');
  assert.equal(row.flag, false); assert.deepEqual([...row.blob], [0,17,127,255]);
  assert.ok(row.empty instanceof Uint8Array); assert.equal(row.empty.length, 0);
}
console.log('real host NAPI SQL NULL and unchanged typed converters passed');
'''


class PhotoResultSetValueTests(unittest.TestCase):
    def test_old_null_defect_and_real_patched_napi_types_without_backend_claim(self):
        if sys.platform != 'darwin':
            self.skipTest('macOS bundled Node NAPI toolchain required')
        original = (HERE / 'fixtures/result_set/result_set_napi.cpp').read_text()
        signatures = ('const int32_t &value', 'const int64_t &value', 'const std::string &value',
                      'const double &value', 'const bool &value', 'const std::vector<uint8_t> &value',
                      'const ValueObject &value', 'const RowEntity &rowEntity')
        functions = ''.join('template <>\n' + function(original,
            'napi_value Convert2JSValue(napi_env env, ' + signature + ')') for signature in signatures)
        patch = BASE / 'result_set_boundaries/0002-preserve-real-sql-null-values.patch'
        section = next(iter(patch_sections(patch).values()))
        candidate = '\n'.join('\n'.join(hunk[2]) for hunk in section)
        null_function = 'template <>\n' + function(candidate,
            'napi_value Convert2JSValue(napi_env env, const std::monostate &)')
        node = Path('/Applications/DevEco-Studio.app/Contents/tools/node')
        compiler = subprocess.check_output(['xcrun', '--find', 'clang++'], text=True).strip()
        sdk = Path(subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip())
        with tempfile.TemporaryDirectory(prefix='resultset-value-napi-') as directory:
            root = Path(directory); script = root / 'probe.js'; script.write_text(SCRIPT)
            for version in ('old', 'patched'):
                with self.subTest(version=version):
                    source, addon = root / (version + '.cpp'), root / (version + '.node')
                    source.write_text(SUPPORT + (null_function if version == 'patched' else '') + functions + TAIL)
                    compiled = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-shared', '-undefined', 'dynamic_lookup', '-isysroot', str(sdk),
                        '-isystem', str(sdk / 'usr/include/c++/v1'), '-I' + str(node / 'include/node'),
                        str(source), '-o', str(addon)], capture_output=True, text=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    result = subprocess.run([str(node / 'bin/node'), str(script), str(addon), version],
                                            capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('old SQL NULL converter defect reproduced' if version == 'old' else
                                  'real host NAPI SQL NULL and unchanged typed converters passed', result.stdout)


if __name__ == '__main__': unittest.main()
