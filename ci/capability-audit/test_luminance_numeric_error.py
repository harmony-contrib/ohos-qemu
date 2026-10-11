"""Execute the actual patched helper with injected NAPI failures, not guest proof."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/arkui/ace_engine/luminance_numeric_error'

STUB = r"""
#pragma once
#include <cstdint>
#include <string>
struct Value { std::string text; int32_t number = 0; Value* code = nullptr; };
struct Env {
    int step = 0, failAt = 0, thrown = 0;
    bool pending = false;
    Value values[4];
    Value* exception = nullptr;
};
using napi_env = Env*;
using napi_value = Value*;
enum napi_status { napi_ok, napi_generic_failure };
inline napi_status Step(Env* e) {
    return ++e->step == e->failAt ? napi_generic_failure : napi_ok;
}
inline napi_status napi_is_exception_pending(Env* e, bool* pending) {
    if (Step(e) != napi_ok) return napi_generic_failure;
    *pending = e->pending;
    return napi_ok;
}
inline napi_status napi_create_string_utf8(Env* e, const char* s, size_t n, Value** out) {
    if (Step(e) != napi_ok) return napi_generic_failure;
    e->values[0].text.assign(s, n); *out = &e->values[0]; return napi_ok;
}
inline napi_status napi_create_error(Env* e, Value* code, Value* msg, Value** out) {
    if (Step(e) != napi_ok) return napi_generic_failure;
    if (code) return napi_generic_failure;
    e->values[1].text = msg->text; *out = &e->values[1]; return napi_ok;
}
inline napi_status napi_create_int32(Env* e, int32_t code, Value** out) {
    if (Step(e) != napi_ok) return napi_generic_failure;
    e->values[2].number = code; *out = &e->values[2]; return napi_ok;
}
inline napi_status napi_set_named_property(Env* e, Value* obj, const char* name, Value* code) {
    if (Step(e) != napi_ok) return napi_generic_failure;
    if (std::string(name) != "code") return napi_generic_failure;
    obj->code = code; return napi_ok;
}
inline napi_status napi_throw(Env* e, Value* error) {
    ++e->thrown; e->pending = true; e->exception = error; return napi_ok;
}
#define LOGE(...) ((void)0)
namespace OHOS::Ace::Napi {
inline std::string ErrorToMessage(int32_t code) {
    return code == 100001 ? "Internal error. " : "";
}
}
"""

HARNESS = r"""
#include <cassert>
#include "luminance_error.h"
using OHOS::Ace::Napi::ThrowLuminanceError;
int main() {
    Env e;
    ThrowLuminanceError(&e, "boundary", 100001);
    assert(e.thrown == 1 && e.pending && e.exception);
    assert(e.exception->text == "Internal error. boundary");
    assert(e.exception->code && e.exception->code->number == 100001);
    assert(e.exception->code->text.empty());
    Env unknown;
    ThrowLuminanceError(&unknown, "other", -7);
    assert(unknown.exception->text == "other" && unknown.exception->code->number == -7);
    Value existing;
    Env pending;
    pending.pending = true; pending.exception = &existing;
    ThrowLuminanceError(&pending, "must not replace", 100001);
    assert(pending.step == 1 && pending.thrown == 0 && pending.exception == &existing);
    for (int step = 1; step <= 5; ++step) {
        Env failed;
        failed.failAt = step;
        ThrowLuminanceError(&failed, "failure", 100001);
        assert(failed.step == step && failed.thrown == 0 && !failed.exception);
    }
}
"""


class LuminanceNumericErrorTests(unittest.TestCase):
    def test_actual_helper_numeric_type_messages_pending_and_napi_failures(self):
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler, 'native helper regression needs clang++')
        patch = (COMPONENT / '0001-use-module-local-numeric-business-error.patch').read_text()
        tail = patch.split('+++ b/foundation/arkui/ace_engine/interfaces/napi/kits/'
                           'luminance_sampler/luminance_error.h\n', 1)[1]
        header = '\n'.join(line[1:] for line in tail.splitlines() if line.startswith('+')) + '\n'
        spec = importlib.util.spec_from_file_location('luma_baseline', COMPONENT / 'verify_source.py')
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        self.assertEqual(hashlib.sha256(header.encode()).hexdigest(), baseline.FILES[-1][2])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'luminance_error.h').write_text(header)
            for name in ('interfaces/napi/kits/utils/napi_utils.h', 'napi/native_api.h'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#include "stub.h"\n')
            (root / 'stub.h').write_text(STUB)
            (root / 'test.cpp').write_text(HARNESS)
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(root), str(root / 'test.cpp'),
                '-o', str(root / 'test')], check=True, capture_output=True)
            subprocess.run([str(root / 'test')], check=True, capture_output=True)

    def test_module_scope_and_shared_build_entry(self):
        patch = (COMPONENT / '0001-use-module-local-numeric-business-error.patch').read_text()
        targets = [line[6:] for line in patch.splitlines() if line.startswith('+++ b/')]
        self.assertEqual(len(targets), 3)
        self.assertTrue(all('/luminance_sampler/' in path for path in targets))
        self.assertNotIn('+        NapiThrow(', patch)
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(script.count('bash "${LUMINANCE_NUMERIC_ERROR_COMPONENT_SCRIPT}"'), 1)


if __name__ == '__main__':
    unittest.main()
