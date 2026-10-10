"""Actual patched synchronous helper, mocked NAPI sink; no guest claim."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/communication/wifi/business_error/0001-preserve-numeric-synchronous-business-error.patch'


class WifiBusinessErrorTests(unittest.TestCase):
    def test_numeric_code_mapping_message_and_no_error_paths_preserved(self):
        helper = '\n'.join(next(iter(patch_sections(PATCH).values()))[0][2])
        helper = helper.split('\nvoid HandleSyncErrCodeByNum', 1)[0]
        source = r'''
#include <cassert>
#include <cstdint>
#include <string>
using napi_env = void *;
#define WIFI_LOGI(...) ((void)0)
namespace ErrCode { constexpr int WIFI_OPT_SUCCESS = 0; }
static int calls = 0, code = 0, mappings = 0;
static int expectedError = -1, expectedCap = 7, mappedCode = 201;
static std::string message = "permission denied", seen;
static napi_env expectedEnv;
std::string GetNapiErrMsg(napi_env env, int error, int cap) {
    assert(env == expectedEnv && error == expectedError && cap == expectedCap);
    ++mappings; return message;
}
int GetNapiErrCode(napi_env env, int error, int cap) {
    assert(env == expectedEnv && error == expectedError && cap == expectedCap);
    ++mappings; return mappedCode;
}
void napi_throw_business_error(napi_env env, int number, const char *text) {
    assert(env == expectedEnv); ++calls; code = number; seen = text;
}
''' + helper + r'''
int main() {
    int environment; expectedEnv = &environment;
    HandleSyncErrCode(expectedEnv, 0, expectedCap);
    assert(calls == 0 && mappings == 0);
    for (int value : {201, 202, 401, 801, 2501000, 2501001}) {
        mappedCode = value;
        int before = calls;
        HandleSyncErrCode(expectedEnv, expectedError, expectedCap);
        assert(calls == before + 1 && code == value && seen == message);
    }
    int before = calls;
    message.clear();
    HandleSyncErrCode(expectedEnv, expectedError, expectedCap);
    assert(calls == before);
}
'''
        compile_run(source, language='c++')

    def test_component_is_in_common_build(self):
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('common/foundation/communication/wifi/business_error/apply.sh', script)
        self.assertIn('bash "${QEMU_WIFI_BUSINESS_ERROR_COMPONENT_SCRIPT}"', script)


if __name__ == '__main__':
    unittest.main()
