"""Exact native Bluetooth enums and registration failures, not radio acceptance."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/bluetooth/api26_control_enums'
PATCH = COMPONENT / '0001-register-native-control-enums.patch'


class BluetoothControlEnumTests(unittest.TestCase):
    def test_exact_native_values_and_every_registration_failure(self):
        sections = patch_sections(PATCH)
        lines = [line for hunks in sections.values() for hunk in hunks for line in hunk[2]]
        start = lines.index('static napi_status RegisterControlEnums(napi_env env, napi_value exports)')
        function = '\n'.join(lines[start:lines.index('}', start) + 1])
        compile_run(r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
enum ControlObject { LEFT_EAR=0, RIGHT_EAR=1, LEFT_RIGHT_EAR=2 };
enum ControlType { PLAY=0, VIBRATE=1, FLASH=2, LOCK=3, ERASE=4 };
enum ControlTypeVal { DISABLE=0, ENABLE=1, QUERY=2 };
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
    for(failure=0;failure<=28;++failure) {
      auto exports=Make(); calls=0;
      auto status=RegisterControlEnums(nullptr,exports);
      if(failure) { assert(status==napi_generic_failure && calls==failure); continue; }
      assert(status==napi_ok && calls==28 && exports->own.size()==3);
      auto object=exports->own.at("ControlObject"); assert(object->own.size()==3);
      assert(object->own.at("LEFT_EAR")->number==0);
      assert(object->own.at("RIGHT_EAR")->number==1);
      assert(object->own.at("LEFT_RIGHT_EAR")->number==2);
      auto type=exports->own.at("ControlType"); assert(type->own.size()==5);
      assert(type->own.at("PLAY")->number==0 && type->own.at("VIBRATE")->number==1);
      assert(type->own.at("FLASH")->number==2 && type->own.at("LOCK")->number==3);
      assert(type->own.at("ERASE")->number==4);
      auto value=exports->own.at("ControlTypeValue"); assert(value->own.size()==3);
      assert(value->own.at("DISABLE")->number==0 && value->own.at("ENABLE")->number==1);
      assert(value->own.at("QUERY")->number==2 && !exports->own.count("ControlTypeVal"));
    }
  }
}
''', language='c++')

    def test_component_applies_twice_and_propagates_registration_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, PATCH)
            command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(PATCH)], check=True)
        self.assertIn('if (RegisterControlEnums(env, exports) != napi_ok) {\n+        return nullptr;', PATCH.read_text())


if __name__ == '__main__':
    unittest.main()
