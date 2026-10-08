"""Exact public registration/getter descriptors, not depth-camera acceptance."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/camera_framework/api26_depth_contracts'
PATCH = COMPONENT / '0001-register-depth-contracts-and-correct-accuracy-getter.patch'


class CameraDepthContractTests(unittest.TestCase):
    def test_exact_accuracy_quality_values_and_every_napi_failure(self):
        sections = patch_sections(PATCH)
        module = next(hunks for name, hunks in sections.items() if name.endswith('native_module_ohos_camera.cpp'))
        lines = [line for hunk in module for line in hunk[2]]
        start = lines.index('static napi_status RegisterDepthEnums(napi_env env, napi_value exports)')
        function = '\n'.join(lines[start:lines.index('}', start) + 1])
        compile_run(r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
enum DepthDataAccuracy { DEPTH_DATA_ACCURACY_INVALID=-1,
    DEPTH_DATA_ACCURACY_RELATIVE=0, DEPTH_DATA_ACCURACY_ABSOLUTE=1 };
struct Value { int32_t number=0; std::map<std::string,Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status { napi_ok=0, napi_generic_failure=9 };
int calls=0, failure=0;
std::vector<std::unique_ptr<Value>> storage;
Value* Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
napi_status Step() { return ++calls==failure ? napi_generic_failure : napi_ok; }
napi_status napi_create_object(napi_env, Value** value) {
    auto status=Step(); if(status==napi_ok) *value=Make(); return status; }
napi_status napi_create_int32(napi_env,int32_t number,Value** value) {
    auto status=Step(); if(status==napi_ok) { *value=Make(); (*value)->number=number; } return status; }
napi_status napi_set_named_property(napi_env,Value* object,const char* name,Value* value) {
    auto status=Step(); if(status==napi_ok) assert(object->own.emplace(name,value).second); return status; }
''' + function + r'''
int main() {
  for(unsigned repeat=0;repeat<128;++repeat) {
    for(failure=0;failure<=14;++failure) {
      auto exports=Make(); calls=0;
      auto status=RegisterDepthEnums(nullptr,exports);
      if(failure) { assert(status==napi_generic_failure && calls==failure); continue; }
      assert(status==napi_ok && calls==14 && exports->own.size()==2);
      auto accuracy=exports->own.at("DepthDataAccuracy"); assert(accuracy->own.size()==2);
      assert(accuracy->own.at("DEPTH_DATA_ACCURACY_RELATIVE")->number==0);
      assert(accuracy->own.at("DEPTH_DATA_ACCURACY_ABSOLUTE")->number==1);
      assert(!accuracy->own.count("DEPTH_DATA_ACCURACY_INVALID"));
      auto quality=exports->own.at("DepthDataQualityLevel"); assert(quality->own.size()==3);
      assert(quality->own.at("DEPTH_DATA_QUALITY_BAD")->number==0);
      assert(quality->own.at("DEPTH_DATA_QUALITY_FAIR")->number==1);
      assert(quality->own.at("DEPTH_DATA_QUALITY_GOOD")->number==2);
    }
  }
}
''', language='c++')

    def test_corrected_descriptor_uses_the_existing_real_accuracy_getter(self):
        sections = patch_sections(PATCH)
        hunks = next(hunks for name, hunks in sections.items() if name.endswith('/depth_data_napi.cpp'))
        self.assertEqual(len(hunks), 1)
        before, after = hunks[0][1:]
        self.assertEqual([line for line in before if line not in after],
                         ['        DECLARE_NAPI_GETTER("dataAccurary", GetAccuracy),'])
        self.assertEqual([line for line in after if line not in before],
                         ['        DECLARE_NAPI_GETTER("dataAccuracy", GetAccuracy),'])
        # The member/data path is not replaced with an enum or a synthetic value.
        self.assertNotIn('napi_create_int32', '\n'.join(after))

    def test_component_applies_twice_and_propagates_registration_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, PATCH)
            command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(PATCH)], check=True)
        self.assertIn('if (RegisterDepthEnums(env, exports) != napi_ok) {\n+        return nullptr;', PATCH.read_text())


if __name__ == '__main__':
    unittest.main()
