"""Real patched helper with a mocked NAPI sink, not guest evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/base/global/i18n/business_error'
PATCH = COMPONENT / '0001-preserve-numeric-business-error-code.patch'
SETTERS = COMPONENT / '0002-reject-invalid-system-setter-parameter-types.patch'


class I18nBusinessErrorTests(unittest.TestCase):
    def test_exact_helper_delegates_integer_and_original_parameters(self):
        helper = '\n'.join(next(iter(patch_sections(PATCH).values()))[0][2])
        helper = helper.split('\nvoid ErrorUtil::NapiThrowBusinessError', 1)[0]
        source = r'''
#include <cassert>
#include <cstdint>
#include <string>
using napi_env = void *;
struct ErrorUtil {
    static void NapiThrow(napi_env, int32_t, const std::string &, const std::string &, bool);
    static void NapiThrowBusinessError(napi_env, int32_t, const std::string &, const std::string &, bool);
};
static int calls = 0, code = 0;
static std::string name, content;
static napi_env observed;
void ErrorUtil::NapiThrowBusinessError(napi_env env, int32_t number, const std::string &key,
    const std::string &value, bool enabled) {
    if (!enabled) return;
    ++calls; code = number; name = key; content = value; observed = env;
}
''' + helper + r'''
int main() {
    int environment = 0;
    for (int number : {201, 202, 401, 890001, 8900001, 890002}) {
        int before = calls;
        ErrorUtil::NapiThrow(&environment, number, "language", "a valid language", false);
        assert(calls == before);
        ErrorUtil::NapiThrow(&environment, number, "language", "a valid language", true);
        assert(calls == before + 1 && code == number && observed == &environment);
        assert(name == "language" && content == "a valid language");
    }
}
'''
        compile_run(source, language='c++')

    def test_component_is_idempotent_and_preserves_undefined_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, (PATCH, SETTERS))
            source = root / next(iter(patch_sections(PATCH)))
            tail = '\n// unrelated special Undefined helper sentinel\n'
            source.write_text(source.read_text() + tail)
            command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(PATCH)], check=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(SETTERS)], check=True)
            self.assertTrue(source.read_text().endswith(tail))

    def test_actual_setter_failure_blocks_throw_401_only_for_throwing_interfaces(self):
        hunks = next(iter(patch_sections(SETTERS).values()))
        source = r'''
#include <cassert>
#include <string>
#define HILOG_ERROR_I18N(...) ((void)0)
static int code = 0, status = 0, calls = 0;
constexpr int napi_ok = 0, I18N_NOT_FOUND = 401;
static std::string observedName, observedType;
struct ErrorUtil {
    static void NapiThrow(void *, int number, const std::string &name, const std::string &type, bool enabled) {
        assert(number == 401);
        if (enabled) { ++calls; observedName = name; observedType = type; }
    }
};
'''
        cases = [('language', 'string'), ('region', 'string'), ('locale', 'string'), ('option', 'boolean')]
        for index, (_, _, new) in enumerate(hunks):
            block = '\n'.join(new[:-1])
            source += f'void *Setter{index}(bool throwError) {{ void *env = nullptr;\n' + block + '\nreturn &calls; }\n'
        source += 'int main() {\n'
        for index, (name, type_) in enumerate(cases):
            source += f'''
code = status = 1; calls = 0;
assert(Setter{index}(true) == nullptr && calls == 1);
assert(observedName == "{name}" && observedType == "{type_}");
assert(Setter{index}(false) == nullptr && calls == 1);
code = status = 0;
assert(Setter{index}(true) == &calls && calls == 1);
'''
        compile_run(source + '}\n', language='c++')


if __name__ == '__main__':
    unittest.main()
