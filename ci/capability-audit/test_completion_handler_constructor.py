"""Constructor N-API error-path injection, not Ark/service guest evidence."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/foundation/ability/ability_runtime/completion_handler/0001-export-completion-handler-constructor.patch'


class CompletionHandlerConstructorTests(unittest.TestCase):
    def test_constructor_failures_do_not_return_an_instance_or_continue(self):
        hunks = next(iter(patch_sections(PATCH).values()))
        source = '\n'.join(hunks[0][2])
        start = source.index('static napi_value CompletionHandlerConstructor(')
        end = source.index('\nstatic napi_value CompletionHandlerForAbilityStartCallbackInit(', start)
        compile_run(r'''
#include <cassert>
#include <cstring>
using napi_env = void*;
using napi_value = int*;
using napi_callback_info = void*;
enum napi_status { napi_ok, napi_generic_failure };
int target = 1, instance = 2, calls = 0, failure = 0, thrown = 0;
bool constructed = true;
#define NAPI_CALL(env, expr) do { if ((expr) != napi_ok) return nullptr; } while (0)
napi_status napi_get_new_target(napi_env, napi_callback_info, napi_value* out) {
 if (++calls == failure) return napi_generic_failure;
 *out = constructed ? &target : nullptr; return napi_ok;
}
napi_status napi_get_cb_info(napi_env, napi_callback_info, void*, void*, napi_value* out, void*) {
 if (++calls == failure) return napi_generic_failure;
 *out = &instance; return napi_ok;
}
napi_status napi_throw_type_error(napi_env, const char* code, const char* message) {
 assert(code == nullptr && std::strstr(message, "requires new"));
 ++thrown; return napi_ok;
}
''' + source[start:end] + r'''
int main() {
 for (int repeat = 0; repeat < 128; ++repeat) {
  for (failure = 0; failure <= 2; ++failure) {
   constructed = true; calls = thrown = 0;
   auto value = CompletionHandlerConstructor(nullptr, nullptr);
   assert(value == (failure ? nullptr : &instance));
   assert(calls == (failure ? failure : 2));
   assert(thrown == 0);
  }
  for (failure = 0; failure <= 1; ++failure) {
   constructed = false; calls = thrown = 0;
   assert(CompletionHandlerConstructor(nullptr, nullptr) == nullptr);
   assert(calls == 1 && thrown == (failure ? 0 : 1));
  }
 }
}
''', language='c++')

    def test_only_missing_export_added_without_changing_existing_enum(self):
        sections = patch_sections(PATCH)
        self.assertEqual(len(sections), 1)
        hunks = next(iter(sections.values()))
        self.assertEqual(len(hunks), 2)
        before, after = hunks[1][1:3]
        existing = '        DECLARE_NAPI_PROPERTY("AbilityStartFailureCode", failureCode),'
        self.assertIn(existing, before)
        self.assertIn(existing, after)
        self.assertIn('        DECLARE_NAPI_PROPERTY("CompletionHandlerForAbilityStartCallback", constructor),', after)


if __name__ == '__main__':
    unittest.main()
