"""Real host NAPI for exact error/callback helpers; no Binder transport claim."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_access_token_kernel import patch_sections

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / ('patches/common/foundation/communication/ipc/remote_interface_base/'
                '0002-align-request-callbacks-and-numeric-errors.patch')
COMMON = 'foundation/communication/ipc/ipc/native/src/napi_common/source/'

SUPPORT = r'''
#include <node_api.h>
#include <map>
#include <string>
#define NAPI_CALL(env, expression) do { if ((expression) != napi_ok) { \
    napi_throw_error(env, nullptr, "actual NAPI call failed"); return nullptr; } } while (false)
#define ZLOGD(...) ((void)0)
enum errorDesc { CHECK_PARAM_ERROR, COMMUNICATION_ERROR };
struct errorInfo { int errorCode; std::string errorMsg; };
class NapiError {
public:
    explicit NapiError(int code): errorCode_(code) {}
    bool IsError() const { return errorCode_ != -1; }
    napi_value GetError(napi_env& env) const;
    // Error mapping is a test fixture; GetError and callback helper below are
    // extracted unchanged from the reviewed exact product patch.
    static std::map<int, errorInfo> napiErrMap_;
private: int errorCode_;
};
std::map<int, errorInfo> NapiError::napiErrMap_ = {
    {CHECK_PARAM_ERROR, {401, "parameter fixture"}},
    {COMMUNICATION_ERROR, {1900007, "communication fixture"}}};
struct SendRequestParam { napi_env env; int errCode; };
'''

TAIL = r'''
static napi_value Dispatch(napi_env env, napi_callback_info info) {
    size_t argc = 3; napi_value argv[3] = {}, output = nullptr;
    NAPI_CALL(env, napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr));
    if (argc != 3) { napi_throw_error(env, nullptr, "three fixture args required"); return nullptr; }
    int32_t code = 0; NAPI_CALL(env, napi_get_value_int32(env, argv[1], &code));
    SendRequestParam param{env, code}; napi_value args[2] = {};
    MakeSendRequestCallbackArgs(&param, argv[2], args);
    // Pinned OHOS NAPI accepts nullptr recv; Node requires an explicit value.
    // Only this host adapter changes recv, never the exact candidate helpers.
    napi_value receiver = nullptr; NAPI_CALL(env, napi_get_undefined(env, &receiver));
    NAPI_CALL(env, napi_call_function(env, receiver, argv[0], 2, args, &output));
    return output;
}
static napi_value Error(napi_env env, napi_callback_info info) {
    size_t argc = 1; napi_value argv[1] = {};
    NAPI_CALL(env, napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr));
    int32_t code = 0; NAPI_CALL(env, napi_get_value_int32(env, argv[0], &code));
    return NapiError(code).GetError(env);
}
static napi_value Init(napi_env env, napi_value exports) {
    napi_value method = nullptr;
    NAPI_CALL(env, napi_create_function(env, "dispatch", NAPI_AUTO_LENGTH, Dispatch, nullptr, &method));
    NAPI_CALL(env, napi_set_named_property(env, exports, "dispatch", method));
    NAPI_CALL(env, napi_create_function(env, "error", NAPI_AUTO_LENGTH, Error, nullptr, &method));
    NAPI_CALL(env, napi_set_named_property(env, exports, "error", method));
    return exports;
}
NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
'''

SCRIPT = r'''
const assert = require('node:assert/strict');
const addon = require(process.argv[2]);
const result = Object.freeze({errCode:0, code:701, data:{}, reply:{}});
let calls = 0;
for (let iteration = 0; iteration < 64; iteration++) {
  assert.equal(addon.dispatch(function(error, value) {
    calls++; assert.equal(arguments.length, 2); assert.equal(error, null);
    assert.equal(value, result); return 37;
  }, 0, result), 37);
  for (const code of [-1, -32, 1, 1900008]) {
    assert.equal(addon.dispatch(function(error, value) {
      calls++; assert.equal(arguments.length, 2); assert.ok(error instanceof Error);
      assert.equal(typeof error.code, 'number'); assert.equal(error.code, 1900007);
      assert.equal(error.message, 'communication fixture'); assert.equal(value, undefined);
      return 41;
    }, code, result), 41);
  }
}
assert.equal(calls, 320);
assert.equal(addon.error(-1), undefined);
for (const [index, code, message] of [[0,401,'parameter fixture'],[1,1900007,'communication fixture']]) {
  const error = addon.error(index); assert.ok(error instanceof Error);
  assert.equal(typeof error.code, 'number'); assert.equal(error.code, code);
  assert.equal(error.message, message);
}
assert.throws(() => addon.dispatch(() => { throw new Error('actual consumer exception'); }, 0, result),
  /actual consumer exception/);
addon.dispatch((error, value) => { assert.equal(error,null); assert.equal(value,result); }, 0, result);
console.log('host native RPC callback regressions passed');
'''


class RpcRequestCallbackTests(unittest.TestCase):
    def test_both_real_completion_sites_share_two_argument_helper(self):
        sections = patch_sections(PATCH)
        for name in (COMMON + 'napi_remote_object.cpp',
                     'foundation/communication/ipc/ipc/native/src/napi/src/napi_remote_proxy.cpp'):
            source = '\n'.join('\n'.join(hunk[2]) for hunk in sections[name])
            self.assertIn('MakeSendRequestCallbackArgs(param, result, args);', source)
            self.assertRegex(source, r'napi_call_function\([^\n]*, 2, args, &cbResult\);')
            self.assertNotRegex(source, r'napi_call_function\([^\n]*, 1, &result')
        header = '\n'.join('\n'.join(hunk[2]) for hunk in sections[
            'foundation/communication/ipc/ipc/native/src/napi_common/include/napi_remote_object_internal.h'])
        self.assertIn('void MakeSendRequestCallbackArgs(', header)
        self.assertNotIn('bool ', header)  # No new layout/compatibility flag.

    def test_real_host_napi_error_values_success_failure_and_consumer_exception(self):
        if sys.platform != 'darwin':
            self.skipTest('macOS bundled Node NAPI toolchain required')
        sections = patch_sections(PATCH)
        common = '\n'.join('\n'.join(hunk[2]) for hunk in sections[COMMON + 'napi_remote_object.cpp'])
        helper = common[common.index('void MakeSendRequestCallbackArgs('):].split(
            '\nstatic void AfterWorkCallback(', 1)[0]
        error = '\n'.join('\n'.join(hunk[2]) for hunk in sections[COMMON + 'napi_rpc_error.cpp'])
        error = error[error.index('napi_value NapiError::GetError('):].split(
            '\nnapi_value NapiError::ThrowError(', 1)[0]
        node = Path('/Applications/DevEco-Studio.app/Contents/tools/node')
        compiler = subprocess.check_output(['xcrun', '--find', 'clang++'], text=True).strip()
        sdk = Path(subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip())
        with tempfile.TemporaryDirectory(prefix='rpc-request-napi-fixture-') as directory:
            root = Path(directory)
            source, addon, script = root / 'probe.cpp', root / 'probe.node', root / 'probe.js'
            source.write_text(SUPPORT + error + helper + TAIL)
            script.write_text(SCRIPT)
            compiled = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-shared', '-undefined', 'dynamic_lookup', '-isysroot', str(sdk),
                '-isystem', str(sdk / 'usr/include/c++/v1'), '-I' + str(node / 'include/node'),
                str(source), '-o', str(addon)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(node / 'bin/node'), str(script), str(addon)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('host native RPC callback regressions passed', result.stdout)


if __name__ == '__main__': unittest.main()
