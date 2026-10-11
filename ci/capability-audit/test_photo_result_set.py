"""Exact source/real host NAPI boundaries; RDB is an explicit backend fixture."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_access_token_kernel import patch_sections

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = ROOT / 'patches/common/foundation/multimedia/media_library'
COMPONENT = BASE / 'result_set_boundaries'
spec = importlib.util.spec_from_file_location('result_set_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    cursor = opening + 1
    while depth:
        depth += (source[cursor] == '{') - (source[cursor] == '}')
        cursor += 1
    return source[start:cursor] + '\n'


SUPPORT = r'''
#include <node_api.h>
#include <cmath>
#include <limits>
#include <memory>
#include <string>
using std::string;
static constexpr int E_OK = 0, E_ROW_OUT_RANGE = -31, E_COLUMN_OUT_RANGE = -32;
static constexpr int JS_E_INNER_FAIL = 23800301, JS_E_PARAM_INVALID = 23800151;
#define NAPI_CALL_RETURN_VOID(env, call) do { if ((call) != napi_ok) return; } while (false)
#define NAPI_ERR_LOG(...) ((void)0)
#define NAPI_WARN_LOG(...) ((void)0)
struct MediaLibraryNapiUtils {
    static void CreateNapiErrorObject(napi_env, napi_value &, const int32_t, const string);
};
static void ThrowNumericBusinessError(napi_env, int32_t, const std::string &);
struct NapiError {
    static void ThrowError(napi_env env, int32_t code, const char *, int32_t, const string &message) {
        ThrowNumericBusinessError(env, code, message);
    }
};
#define CHECK_COND_WITH_ERR_MESSAGE(env, cond, err, msg) do { if (!(cond)) { \
    NapiError::ThrowError(env, err, __FUNCTION__, __LINE__, msg); return nullptr; } } while (false)
#define GET_JS_OBJ_WITH_ZERO_ARGS(env, info, status, self) do { \
    status = napi_get_cb_info(env, info, nullptr, nullptr, &self, nullptr); } while (false)
struct ValueObject { int32_t value = 0; };
// Explicit RDB double. It never proves real query/permission/provider behavior.
struct ResultSet {
    int rows = 0, index = -1, calls = 0;
    bool databaseFailure = false;
    int GetRowCount(int32_t &value) { value = rows; return databaseFailure ? -99 : E_OK; }
    int GoToRow(int32_t value) {
        ++calls;
        if (databaseFailure) return -99;
        if (value < 0 || value >= rows) return E_ROW_OUT_RANGE;
        index = value; return E_OK;
    }
    int GoToFirstRow() { return GoToRow(0); }
    int GoToNextRow() { return GoToRow(index + 1); }
    int Get(int32_t column, ValueObject &value) {
        ++calls;
        if (databaseFailure || index < 0 || index >= rows) return -99;
        if (column < 0 || column >= 3) return E_COLUMN_OUT_RANGE;
        value.value = 100 * index + column; return E_OK;
    }
};
struct ResultSetNapi {
    std::shared_ptr<ResultSet> resultSetPtr;
    static napi_value JSGoToRow(napi_env, napi_callback_info);
    static napi_value JSGoToFirstRow(napi_env, napi_callback_info);
    static napi_value JSGoToNextRow(napi_env, napi_callback_info);
    static napi_value JSGetValue(napi_env, napi_callback_info);
    static napi_value JSClose(napi_env, napi_callback_info);
};
static napi_value Convert2JSValue(napi_env env, bool value) {
    napi_value out = nullptr; napi_get_boolean(env, value, &out); return out;
}
static napi_value Convert2JSValue(napi_env env, const ValueObject &value) {
    napi_value out = nullptr; napi_create_int32(env, value.value, &out); return out;
}
'''

TAIL = r'''
static void Finalize(napi_env, void *value, void *) { delete static_cast<ResultSetNapi *>(value); }
static napi_value Create(napi_env env, napi_callback_info info) {
    size_t argc = 2; napi_value args[2] = {}, object = nullptr; int32_t rows = 0; bool failure = false;
    napi_get_cb_info(env, info, &argc, args, nullptr, nullptr);
    if (argc >= 1) napi_get_value_int32(env, args[0], &rows);
    if (argc >= 2) napi_get_value_bool(env, args[1], &failure);
    napi_create_object(env, &object);
    const char *names[] = {"goToRow", "goToFirstRow", "goToNextRow", "getValue", "close"};
    const napi_callback callbacks[] = {ResultSetNapi::JSGoToRow, ResultSetNapi::JSGoToFirstRow,
        ResultSetNapi::JSGoToNextRow, ResultSetNapi::JSGetValue, ResultSetNapi::JSClose};
    for (size_t i = 0; i < 5; ++i) {
        napi_value method = nullptr;
        napi_create_function(env, names[i], NAPI_AUTO_LENGTH, callbacks[i], nullptr, &method);
        napi_set_named_property(env, object, names[i], method);
    }
    // Negative rows intentionally produce an unwrapped object for the close regression.
    if (rows >= 0) {
        auto backend = std::make_shared<ResultSet>(); backend->rows = rows; backend->databaseFailure = failure;
        auto holder = new ResultSetNapi{backend}; napi_wrap(env, object, holder, Finalize, nullptr, nullptr);
    }
    return object;
}
static napi_value Calls(napi_env env, napi_callback_info info) {
    size_t argc = 1; napi_value self = nullptr, out = nullptr; ResultSetNapi *holder = nullptr;
    napi_get_cb_info(env, info, &argc, &self, nullptr, nullptr);
    napi_unwrap(env, self, reinterpret_cast<void **>(&holder));
    napi_create_int32(env, holder && holder->resultSetPtr ? holder->resultSetPtr->calls : -1, &out);
    return out;
}
static napi_value ErrorObject(napi_env env, napi_callback_info info) {
    size_t argc = 2; napi_value args[2] = {}, error = nullptr; int32_t code = 0;
    napi_get_cb_info(env, info, &argc, args, nullptr, nullptr);
    napi_get_value_int32(env, args[0], &code);
    MediaLibraryNapiUtils::CreateNapiErrorObject(env, error, code, "original message");
    if (argc == 2) { napi_throw(env, args[1]); ThrowNumericBusinessError(env, code, "must not replace"); return nullptr; }
    return error;
}
static napi_value Init(napi_env env, napi_value exports) {
    for (const auto &entry : {std::pair<const char *, napi_callback>{"create", Create},
            {"calls", Calls}, {"error", ErrorObject}}) {
        napi_value method = nullptr;
        napi_create_function(env, entry.first, NAPI_AUTO_LENGTH, entry.second, nullptr, &method);
        napi_set_named_property(env, exports, entry.first, method);
    }
    return exports;
}
NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
'''

SCRIPT = r'''
const assert = require('node:assert/strict');
const addon = require(process.argv[2]);
function rejects(call, code) {
  assert.throws(call, error => error instanceof Error && typeof error.code === 'number' && error.code === code);
}
for (let round = 0; round < 64; round++) {
  const rs = addon.create(2);
  assert.equal(rs.goToFirstRow(), true); assert.equal(rs.getValue(0), 0);
  const invalid = [undefined, null, '0', true, {}, [], NaN, Infinity, -Infinity, .5, -.5,
    2147483648, -2147483649, 4294967296, Number.MAX_SAFE_INTEGER];
  for (const method of ['goToRow', 'getValue']) {
    for (const value of invalid) {
      const before = addon.calls(rs); rejects(() => rs[method](value), 23800151);
      assert.equal(addon.calls(rs), before); assert.equal(rs.getValue(0), 0);
    }
    for (const args of [[], [0, 1], [0, 1, 2]]) {
      const before = addon.calls(rs); rejects(() => rs[method](...args), 23800151);
      assert.equal(addon.calls(rs), before);
    }
    for (const value of [-2147483648, -1, 2147483647]) rejects(() => rs[method](value), 23800151);
  }
  assert.equal(rs.goToRow(-0), true); assert.equal(rs.getValue(-0), 0);
  assert.equal(rs.goToNextRow(), true); assert.equal(rs.getValue(2), 102);
  assert.equal(rs.goToNextRow(), false); assert.equal(rs.getValue(0), 100);
  assert.equal(rs.goToFirstRow(), true); assert.equal(rs.getValue(0), 0);
  rs.close(); rs.close(); rejects(() => rs.goToRow(0), 23800301);
  rejects(() => rs.goToFirstRow(), 23800301); rejects(() => rs.getValue(0), 23800301);
  const empty = addon.create(0);
  assert.equal(empty.goToFirstRow(), false); assert.equal(empty.goToNextRow(), false); empty.close(); empty.close();
  const bare = addon.create(-1); rejects(() => bare.close(), 23800301);
  const broken = addon.create(1, true); rejects(() => broken.goToFirstRow(), 23800301); broken.close();
}
for (const code of [201, 202, 401, 23800151, 23800301]) {
  const error = addon.error(code); assert.ok(error instanceof Error);
  assert.equal(typeof error.code, 'number'); assert.equal(error.code, code);
  assert.equal(error.message, 'original message');
}
const original = new Error('original pending validation'); original.code = 23800151;
assert.throws(() => addon.error(23800301, original), error => error === original);
assert.equal(addon.error(201).code, 201);
console.log('real host NAPI ResultSet boundaries passed; RDB backend is a fixture');
'''


class PhotoResultSetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='photo-resultset-boundaries-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / baseline.PROJECT / baseline.FILES[0][0]
        self.source.parent.mkdir(parents=True)
        # Fixture is reviewable LF with one repository EOF newline. Restore the
        # pinned CRLF/no-EOF-newline bytes mechanically and verify their hash.
        original = (HERE / 'fixtures/result_set/result_set_napi.cpp').read_text()
        data = original.removesuffix('\n').replace('\n', '\r\n').encode()
        self.assertEqual(hashlib.sha256(data).hexdigest(), baseline.FILES[0][1])
        self.source.write_bytes(data)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_complete_pinned_crlf_application_repeat_and_unknown_rejection(self):
        self.assertEqual(self.apply().returncode, 0)
        after = self.source.read_bytes()
        self.assertEqual(hashlib.sha256(after).hexdigest(), baseline.FILES[0][2])
        self.assertEqual(after.count(b'\n'), after.count(b'\r\n'))
        self.assertFalse(after.endswith(b'\n'))
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(self.source.read_bytes(), after)
        self.source.write_bytes(after + b'\r\n// unknown edit')
        unknown = self.source.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.source.read_bytes(), unknown)

    def test_lf_drift_symlink_and_wrong_revision_fail_without_mutation(self):
        original = self.source.read_bytes()
        self.source.write_bytes(original.replace(b'\r\n', b'\n'))
        changed = self.source.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.source.read_bytes(), changed)
        self.source.write_bytes(original)
        preserved = self.source.with_suffix('.preserved')
        self.source.rename(preserved)
        self.source.symlink_to(preserved)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(preserved.read_bytes(), original)
        self.source.unlink(); preserved.rename(self.source)
        project = self.root / baseline.PROJECT
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        subprocess.run(['git', '-C', str(project), '-c', 'user.name=fixture', '-c',
            'user.email=fixture@example.invalid', 'commit', '-q', '--allow-empty', '-m', 'wrong revision'], check=True)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.source.read_bytes(), original)

    def test_common_pre_gn_wiring_and_existing_real_factory_registration(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        for marker in ('PHOTO_BUSINESS_ERROR_COMPONENT_SCRIPT', 'PHOTO_RESULT_SET_COMPONENT_SCRIPT'):
            invocation = 'bash "${' + marker + '}" --source-root "${OHOS_ROOT}"'
            self.assertEqual(recipe.count(invocation), 1)
            self.assertLess(recipe.index(invocation), recipe.index('  write_source_preparation_metadata\n}'))
        source = self.source.read_text()
        self.assertIn('MediaLibraryNapiUtils::NapiDefineClass(env, exports, info);', source)
        self.assertIn('ResultSetNapi::CreateResultSetNapi(', source)
        self.assertIn('napi_uint8_array', source)  # Already implemented; not patched as a missing export.

    def test_real_host_napi_boundaries_and_pending_error_identity(self):
        if sys.platform != 'darwin':
            self.skipTest('macOS bundled Node NAPI toolchain required')
        applied = self.apply()
        self.assertEqual(applied.returncode, 0, applied.stderr)
        source = self.source.read_text()
        selected = ''.join(function(source, signature) for signature in (
            'static std::shared_ptr<ResultSet> GetInt32AndResultSet(',
            'static ResultSetNapi *GetResultSetNapi(', 'static std::shared_ptr<ResultSet> GetResultSet(',
            'napi_value ResultSetNapi::JSGoToRow(', 'napi_value ResultSetNapi::JSGoToFirstRow(',
            'napi_value ResultSetNapi::JSGoToNextRow(', 'napi_value ResultSetNapi::JSGetValue(',
            'napi_value ResultSetNapi::JSClose('))
        patch = BASE / 'business_error/0001-preserve-numeric-business-errors-and-first-pending-exception.patch'
        sections = patch_sections(patch)
        prefix = baseline.PROJECT + '/frameworks/js/src/'
        error = '\n'.join('\n'.join(hunk[2]) for hunk in sections[prefix + 'napi_error.cpp'])
        utils = '\n'.join('\n'.join(hunk[2]) for hunk in sections[prefix + 'medialibrary_napi_utils.cpp'])
        helpers = function(utils, 'void MediaLibraryNapiUtils::CreateNapiErrorObject(')
        helpers += function(error, 'static void ThrowNumericBusinessError(')
        self.assertEqual(error.count('ThrowNumericBusinessError(env, err, message);'), 2)
        probe, addon, script = self.root / 'probe.cpp', self.root / 'probe.node', self.root / 'probe.js'
        probe.write_text(SUPPORT + helpers + selected + TAIL)
        script.write_text(SCRIPT)
        node = Path('/Applications/DevEco-Studio.app/Contents/tools/node')
        compiler = subprocess.check_output(['xcrun', '--find', 'clang++'], text=True).strip()
        sdk = Path(subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip())
        compiled = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
            '-shared', '-undefined', 'dynamic_lookup', '-isysroot', str(sdk),
            '-isystem', str(sdk / 'usr/include/c++/v1'), '-I' + str(node / 'include/node'),
            str(probe), '-o', str(addon)], capture_output=True, text=True)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = subprocess.run([str(node / 'bin/node'), str(script), str(addon)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('real host NAPI ResultSet boundaries passed', result.stdout)


if __name__ == '__main__': unittest.main()
