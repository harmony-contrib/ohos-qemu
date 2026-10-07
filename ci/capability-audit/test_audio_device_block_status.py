"""Exact source/map regression fixtures, not microphone or new-guest proof."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/audio_framework/device_block_status'
PATCH = COMPONENT / '0001-register-the-public-device-block-status-enum.patch'
SOURCE = 'foundation/multimedia/audio_framework/frameworks/js/napi/common/napi_audio_enum.cpp'


class AudioDeviceBlockStatusTests(unittest.TestCase):
    def test_actual_new_map_and_descriptor_use_the_original_cpp_values(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {SOURCE})
        function = '\n'.join(sections[SOURCE][0][2][:6])
        descriptor = next(line for line in sections[SOURCE][1][2] if '"DeviceBlockStatus"' in line)
        program = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { int32_t number = 0; std::map<std::string, Value *> own; };
using napi_env = void *;
using napi_value = Value *;
using napi_status = int;
struct Property { const char *name; Value *value; };
enum DeviceBlockStatus { DEVICE_UNBLOCKED = 0, DEVICE_BLOCKED = 1 };
static std::vector<std::unique_ptr<Value>> storage;
static Value *Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
static Value *CreateEnumObject(napi_env, const std::map<std::string, int32_t> &values) {
    auto object = Make();
    for (const auto &entry : values) { auto number = Make(); number->number = entry.second;
        assert(object->own.emplace(entry.first, number).second); }
    return object;
}
#define DECLARE_NAPI_PROPERTY(name, value) Property{name, value}
static napi_status napi_define_properties(napi_env, napi_value object, size_t count, Property *properties) {
    for (size_t i = 0; i < count; ++i) assert(object->own.emplace(properties[i].name, properties[i].value).second);
    return 0;
}
struct NapiAudioEnum { static napi_status InitAudioEnum(napi_env, napi_value); };
'''
        function += '\n    Property properties[] = {\n' + descriptor + '\n    };\n'
        function += '    return napi_define_properties(env, exports, 1, properties);\n}\n'
        main = r'''
int main() {
    for (int repeat = 0; repeat < 256; ++repeat) {
        auto exports = Make(); assert(NapiAudioEnum::InitAudioEnum(nullptr, exports) == 0);
        assert(exports->own.size() == 1);
        auto mode = exports->own.at("DeviceBlockStatus"); assert(mode->own.size() == 2);
        assert(mode->own.at("UNBLOCKED")->number == DEVICE_UNBLOCKED);
        assert(mode->own.at("BLOCKED")->number == DEVICE_BLOCKED);
    }
}
'''
        compile_run(program + function + main, language='c++')

    def test_exact_component_fresh_repeat_and_partial_state_preserve_unknown_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, PATCH)
            source = root / SOURCE
            original, candidate = source.read_bytes(), source.read_text()
            for _, old, new in patch_sections(PATCH)[SOURCE]:
                before, after = '\n'.join(old), '\n'.join(new)
                self.assertEqual(candidate.count(before), 1)
                candidate = candidate.replace(before, after)
            fixture = root / 'fixture-repository'
            component = fixture / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
            verifier = component / 'verify_source.py'
            verifier.write_text(verifier.read_text().replace(
                '85d14a90c62d33d36c50518bbc258f83067144fc93677a7dafe4af6203b3dd2b',
                hashlib.sha256(original).hexdigest()).replace(
                '351b8bdb04cfe637c05643a050e8a964c3c4b09252461d3ded19b2d1504d51d0',
                hashlib.sha256(candidate.encode()).hexdigest()))
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
            self.assertEqual(source.read_text(), candidate)
            source.write_text(candidate.replace('"DeviceBlockStatus"', '"DeviceBlockStatusTypo"'))
            before = source.read_bytes()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), before)

    def test_common_patch_plan_and_no_permission_callback_or_hardware_changes(self):
        added = [line for line in PATCH.read_text().splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(len(added), 5)
        for forbidden in ('Callback', 'Permission', 'HDI', 'RegisterDevice', 'SetDevice'):
            self.assertNotIn(forbidden, '\n'.join(added))
        plan = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        invocation = 'bash "${AUDIO_DEVICE_BLOCK_STATUS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertEqual(plan.count(invocation), 1)
        patch_plan = plan.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0]
        self.assertIn(invocation, patch_plan)
        main = plan.split('\nmain() {', 1)[1]
        self.assertLess(main.index('  apply_qemu_capability_patch_plan\n'),
                        main.index('    build_product "${product}"'))


if __name__ == '__main__':
    unittest.main()
