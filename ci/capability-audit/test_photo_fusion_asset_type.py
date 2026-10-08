"""Exact source/NAPI fixtures, not a photo provider or new-image pass."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/fusion_asset_type'
PATCH = COMPONENT / '0001-register-the-existing-fusion-asset-type-enum.patch'
WRAPPER_PATCH = COMPONENT / '0002-forward-the-native-enum-through-the-public-ArkTS-wrapper.patch'
SOURCE = 'foundation/multimedia/media_library/frameworks/js/src/media_library_napi.cpp'
WRAPPER = 'foundation/multimedia/media_library/frameworks/js/src/photoaccesshelperinf.js'


class PhotoFusionAssetTypeTests(unittest.TestCase):
    def test_exact_full_photo_composition_repeats_but_unknown_or_partial_composition_does_not(self):
        composed_source = b'host fixture: exact Fusion and Photo native composition\n'
        getter = b'host fixture: exact Photo public getter\n'
        wrapper = b'host fixture: exact Fusion public wrapper\n'
        final_wrapper = b'host fixture: exact Fusion and Photo public wrapper\n'
        original_wrapper = b'host fixture: original public wrapper\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / 'fixture-repository'
            component = fixture / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
            verifier = component / 'verify_source.py'
            text = verifier.read_text()
            for actual, synthetic in (
                ('c45cb3a1a9b65df3dddd37a816660309b82c5c40af4605d63932b5d338335b30', composed_source),
                ('e24265bb5563eddd384c7c11181ca53697b075f7f3df8c4484178daac7a6535c', getter),
                ('b283d47255e633b5ed1b0f0ae27ef98ddc835d69ab60cdd2137e50da55ef1439', wrapper),
                ('5e5035b8b3913f49bc568798ebf83e737e627bec154331f2177db20dba519b4c', final_wrapper),
                ('804aea4300b31167be5a2fed86f0870c95f605ac689ea906f128ecc03dc37127', original_wrapper)):
                text = text.replace(actual, hashlib.sha256(synthetic).hexdigest())
            verifier.write_text(text)
            values = {SOURCE: composed_source, WRAPPER: wrapper,
                      'foundation/multimedia/media_library/frameworks/js/src/photo_album_napi.cpp': getter}
            for name, value in values.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
                self.assertEqual({name: (root / name).read_bytes() for name in values}, values)
            values[WRAPPER] = final_wrapper
            (root / WRAPPER).write_bytes(final_wrapper)
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
                self.assertEqual({name: (root / name).read_bytes() for name in values}, values)
            (root / WRAPPER).write_bytes(original_wrapper)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual((root / WRAPPER).read_bytes(), original_wrapper)
            for corrupted in values:
                for name, value in values.items():
                    (root / name).write_bytes(value)
                (root / corrupted).write_bytes(values[corrupted] + b'unknown edit\n')
                before = {name: (root / name).read_bytes() for name in values}
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
                self.assertEqual({name: (root / name).read_bytes() for name in values}, before)
            for name, value in values.items():
                (root / name).write_bytes(value)
            outside = root / 'outside'
            outside.write_bytes(composed_source)
            (root / SOURCE).unlink()
            (root / SOURCE).symlink_to(outside)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(outside.read_bytes(), composed_source)

    def test_actual_helper_checks_all_napi_failures_and_exports_only_the_real_cpp_value(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {SOURCE})
        function = '\n'.join(sections[SOURCE][0][2][3:-3])
        descriptor = next(line for line in sections[SOURCE][1][2] if '"FusionAssetType"' in line)
        program = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { int32_t number = -1; std::map<std::string, Value *> own; };
using napi_env = void *;
using napi_value = Value *;
using napi_status = int;
static constexpr napi_status napi_ok = 0;
enum FusionAssetType { COMPATIBLE_ASSET = 0 };
static std::vector<std::unique_ptr<Value>> storage;
static int failAt = -1, calls = 0;
static Value *Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
static napi_status Status() { return calls++ == failAt ? 1 : 0; }
static napi_status napi_create_object(napi_env, napi_value *result) {
    auto status = Status(); if (status == napi_ok) *result = Make(); return status;
}
static napi_status napi_create_int32(napi_env, int32_t number, napi_value *result) {
    auto status = Status(); if (status == napi_ok) { *result = Make(); (*result)->number = number; } return status;
}
static napi_status napi_set_named_property(napi_env, napi_value object, const char *name, napi_value value) {
    auto status = Status(); if (status == napi_ok) assert(object->own.emplace(name, value).second); return status;
}
#define NAPI_CALL(env, operation) do { if ((operation) != napi_ok) return nullptr; } while (false)
struct Property { const char *name; Value *value; };
#define DECLARE_NAPI_PROPERTY(name, value) Property{name, value}
'''
        main = r'''
int main() {
    for (int repeat = 0; repeat < 512; ++repeat) {
        calls = 0; failAt = -1;
        auto mode = CreateFusionAssetTypeEnum(nullptr);
        assert(mode && mode->own.size() == 1 && calls == 3);
        assert(mode->own.at("COMPATIBLE_ASSET")->number == COMPATIBLE_ASSET);
        napi_env env = nullptr;
        Property property[] = { DESCRIPTOR };
        assert(std::string(property[0].name) == "FusionAssetType");
        assert(property[0].value->own.at("COMPATIBLE_ASSET")->number == 0);
        for (int failure = 0; failure < 3; ++failure) {
            calls = 0; failAt = failure;
            assert(CreateFusionAssetTypeEnum(nullptr) == nullptr && calls == failure + 1);
        }
    }
}
'''.replace('DESCRIPTOR', descriptor.strip().rstrip(','))
        compile_run(program + function + main, language='c++')

    def test_exact_component_fresh_repeat_and_unknown_partial_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, candidate = {}, {}
            for patch, name in ((PATCH, SOURCE), (WRAPPER_PATCH, WRAPPER)):
                write_preimages(root, patch)
                source = root / name
                original[name], candidate[name] = source.read_bytes(), source.read_text()
                for _, old, new in patch_sections(patch)[name]:
                    before, after = '\n'.join(old), '\n'.join(new)
                    self.assertEqual(candidate[name].count(before), 1)
                    candidate[name] = candidate[name].replace(before, after)
            fixture = root / 'fixture-repository'
            component = fixture / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
            verifier = component / 'verify_source.py'
            hashes = {
                'd8a1c5d24e24b8029dc1e5e59cfff529b7edc15ce8a8dfe3105c6b48031bd363':
                    hashlib.sha256(original[SOURCE]).hexdigest(),
                '4be781efd4c1ab2be368facd0dce7eb66ce1243dcec2f1a5e43f7672fc4c312e':
                    hashlib.sha256(candidate[SOURCE].encode()).hexdigest(),
                '804aea4300b31167be5a2fed86f0870c95f605ac689ea906f128ecc03dc37127':
                    hashlib.sha256(original[WRAPPER]).hexdigest(),
                'b283d47255e633b5ed1b0f0ae27ef98ddc835d69ab60cdd2137e50da55ef1439':
                    hashlib.sha256(candidate[WRAPPER].encode()).hexdigest(),
            }
            source_text = verifier.read_text()
            for actual, synthetic in hashes.items():
                source_text = source_text.replace(actual, synthetic)
            verifier.write_text(source_text)
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
            for name in (SOURCE, WRAPPER):
                self.assertEqual((root / name).read_text(), candidate[name])
            # An exact native-only prefix is a legitimate prior build input.
            (root / WRAPPER).write_bytes(original[WRAPPER])
            subprocess.run(command, capture_output=True, check=True)
            self.assertEqual((root / WRAPPER).read_text(), candidate[WRAPPER])
            # A wrapper-only state is not a contiguous stack and changes none
            # of the source, even though both individual hashes are known.
            (root / SOURCE).write_bytes(original[SOURCE])
            before = {name: (root / name).read_bytes() for name in (SOURCE, WRAPPER)}
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual({name: (root / name).read_bytes() for name in before}, before)
            for corrupted in (SOURCE, WRAPPER):
                for name in (SOURCE, WRAPPER):
                    (root / name).write_text(candidate[name])
                (root / corrupted).write_text(candidate[corrupted] + '// unknown edit\n')
                before = {name: (root / name).read_bytes() for name in (SOURCE, WRAPPER)}
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
                self.assertEqual({name: (root / name).read_bytes() for name in before}, before)

    def test_public_wrapper_forwards_the_actual_native_object_without_inventing_values(self):
        sections = patch_sections(WRAPPER_PATCH)
        self.assertEqual(set(sections), {WRAPPER})
        before, after = sections[WRAPPER][0][1:]
        added = [line for line in after if line not in before]
        self.assertEqual(added, ['  FusionAssetType: photoAccessHelper.FusionAssetType,'])
        # A named native-module fixture verifies forwarding/identity, not any
        # actual Ark VM, permissions or photo backend.
        script = r'''
import assert from 'node:assert/strict';
const forward = new Function('photoAccessHelper', 'return ({' + process.argv[1] + '});');
for (const number of [0, 17]) {
  const actualNative = { FusionAssetType: Object.freeze({ COMPATIBLE_ASSET: number }) };
  const publicWrapper = forward(actualNative);
  assert.equal(publicWrapper.FusionAssetType, actualNative.FusionAssetType);
  assert.equal(publicWrapper.FusionAssetType.COMPATIBLE_ASSET, number);
}
assert.equal(forward({}).FusionAssetType, undefined);
'''
        subprocess.run(['node', '--input-type=module', '-e', script, added[0]],
                       capture_output=True, check=True)

    def test_common_patch_plan_has_no_provider_permission_or_backend_change(self):
        added = [line for line in PATCH.read_text().splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(len(added), 11)
        for forbidden in ('Permission', 'CreateAsset', 'UserFileClient', 'Sync', 'create_reference'):
            self.assertNotIn(forbidden, '\n'.join(added))
        plan = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        invocation = 'bash "${PHOTO_FUSION_ASSET_TYPE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertEqual(plan.count(invocation), 1)
        patch_plan = plan.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0]
        self.assertIn(invocation, patch_plan)
        self.assertLess(patch_plan.index(invocation),
                        patch_plan.index('bash "${PHOTO_PUBLIC_ENUMS_COMPONENT_SCRIPT}"'))
        main = plan.split('\nmain() {', 1)[1]
        self.assertLess(main.index('  apply_qemu_capability_patch_plan\n'),
                        main.index('    build_product "${product}"'))


if __name__ == '__main__':
    unittest.main()
