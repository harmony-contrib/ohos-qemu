"""Exact patch/NAPI descriptor fixtures, not public-wrapper or guest proof."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/contacts_data/sync_mode'
PATCH = COMPONENT / '0001-register-the-api26-contact-sync-mode-enum.patch'
SOURCE = 'applications/standard/contacts_data/contacts/src/contacts_api.cpp'


class ContactSyncModeTests(unittest.TestCase):
    def test_actual_declaration_exports_both_sdk_names_and_values_under_sanitizers(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {SOURCE})
        function = '\n'.join(sections[SOURCE][0][2])
        mock = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { std::string name; int32_t number = 0; std::map<std::string, Value *> own; };
using napi_env = void *;
using napi_value = Value *;
using napi_callback_info = void *;
using napi_callback = napi_value (*)(napi_env, napi_callback_info);
struct napi_property_descriptor { const char *name; napi_value value; };
constexpr int NAPI_AUTO_LENGTH = -1, MODE_INCREMENTAL = 1, MODE_CLOUD_BASED = 2;
static std::vector<std::unique_ptr<Value>> storage;
static napi_value Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
struct ContactsNapiUtils {
    static napi_value ToInt32Value(napi_env, int32_t number) { auto value = Make(); value->number = number; return value; }
    static napi_value CreateClassConstructor(napi_env, napi_callback_info) { return nullptr; }
};
#define DECLARE_NAPI_STATIC_PROPERTY(name, value) {name, value}
static int napi_define_class(napi_env, const char *name, int, napi_callback, void *,
    size_t count, const napi_property_descriptor *properties, napi_value *result) {
    *result = Make(); (*result)->name = name;
    for (size_t i = 0; i < count; ++i) assert((*result)->own.emplace(properties[i].name, properties[i].value).second);
    return 0;
}
static int napi_set_named_property(napi_env, napi_value object, const char *name, napi_value value) {
    object->own[name] = value; return 0;
}
'''
        main = r'''
int main() {
    for (int repeat = 0; repeat < 256; ++repeat) {
        auto exports = Make(); assert(DeclareModeConst(nullptr, exports) == exports);
        assert(exports->own.size() == 1 && exports->own.count("ContactSyncMode") == 1);
        auto modes = exports->own.at("ContactSyncMode");
        assert(modes->name == "ContactSyncMode" && modes->own.size() == 2);
        assert(modes->own.at("MODE_INCREMENTAL")->number == 1);
        assert(modes->own.at("MODE_CLOUD_BASED")->number == 2);
        assert(!modes->own.count("DEFAULT_SELECT") && !exports->own.count("ContactsSyncMode"));
    }
}
'''
        compile_run(mock + function + main, language='c++')

    def test_known_fresh_repeat_and_unknown_partial_state_are_not_marker_driven(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, PATCH)
            source = root / SOURCE
            original = source.read_bytes()
            candidate = original.decode()
            for _, before, after in patch_sections(PATCH)[SOURCE]:
                old, new = '\n'.join(before), '\n'.join(after)
                self.assertEqual(candidate.count(old), 1)
                candidate = candidate.replace(old, new)
            fixture = root / 'fixture-repository'
            component = fixture / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
            verifier = component / 'verify_source.py'
            verifier.write_text(verifier.read_text().replace(
                '018501eb1fe4ac1792a7150004512c45238ef9a38b1b2e98d468de9c87b827e7',
                hashlib.sha256(original).hexdigest()).replace(
                '1e695abbda171e24ba756d670f635ff5ee3cad748b5cdfe05a29f14002d85303',
                hashlib.sha256(candidate.encode()).hexdigest()))
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(source.read_text(), candidate)
            (root / '.ohos-qemu-patches' / 'false-legacy-marker').write_text('not evidence')
            source.write_text(candidate.replace('    DeclareModeConst(env, exports);\n', ''))
            before = source.read_bytes()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), before)

    def test_real_registration_is_added_without_sync_or_permissions_edits(self):
        changes = []
        for _, old, new in patch_sections(PATCH)[SOURCE]:
            # Compare only non-context lines of each diff, below.
            self.assertLessEqual(abs(len(new) - len(old)), 1)
        for line in PATCH.read_text().splitlines():
            if line.startswith(('+', '-')) and not line.startswith(('+++', '---')):
                changes.append(line)
        self.assertEqual(changes[-1], '+    DeclareModeConst(env, exports);')
        self.assertEqual(sum(line.startswith('+') for line in changes), 5)
        for forbidden in ('CheckPermission', 'SyncContacts(', 'DataShare'):
            self.assertNotIn(forbidden, '\n'.join(changes))
        old_class = next(line[1:] for line in changes if line.startswith('-    napi_define_class'))
        new_class = next(line[1:] for line in changes if line.startswith('+    napi_define_class'))
        self.assertEqual(old_class.replace('"ContactsSyncMode"', '"ContactSyncMode"'), new_class)
        plan = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        invocation = 'bash "${CONTACT_SYNC_MODE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertEqual(plan.count(invocation), 1)
        self.assertNotIn('if [ "${DEVICE_TYPE}"', plan[plan.index(invocation) - 100:plan.index(invocation)])


if __name__ == '__main__':
    unittest.main()
