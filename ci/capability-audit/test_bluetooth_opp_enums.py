"""Exact OPP wire enums/error branches, not a transfer backend."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/bluetooth/api26_opp_enums'
PATCH = COMPONENT / '0001-register-opp-transfer-wire-enums.patch'


class BluetoothOppEnumTests(unittest.TestCase):
    def test_every_member_and_registration_failure(self):
        sections = patch_sections(PATCH)
        lines = [line for hunks in sections.values() for hunk in hunks for line in hunk[2]]
        start = lines.index('static napi_status RegisterOppEnums(napi_env env, napi_value exports)')
        function = '\n'.join(lines[start:lines.index('}', start) + 1])
        compile_run(r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
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
    for(failure=0;failure<=32;++failure) {
      auto exports=Make(); calls=0;
      auto status=RegisterOppEnums(nullptr,exports);
      if(failure) { assert(status==napi_generic_failure && calls==failure); continue; }
      assert(status==napi_ok && calls==32 && exports->own.size()==3);
      auto direction=exports->own.at("DirectionType"); assert(direction->own.size()==2);
      assert(direction->own.at("OUTBOUND")->number==0 && direction->own.at("INBOUND")->number==1);
      auto state=exports->own.at("TransferStatus"); assert(state->own.size()==3);
      assert(state->own.at("PENDING")->number==0 && state->own.at("RUNNING")->number==1);
      assert(state->own.at("FINISH")->number==2);
      auto result=exports->own.at("TransferResult"); assert(result->own.size()==8);
      const char* names[]={"SUCCESS","ERROR_UNSUPPORTED_TYPE","ERROR_BAD_REQUEST","ERROR_NOT_ACCEPTABLE",
                          "ERROR_CANCELED","ERROR_CONNECTION_FAILED","ERROR_TRANSFER_FAILED","ERROR_UNKNOWN"};
      for(int i=0;i<8;++i) assert(result->own.at(names[i])->number==i);
    }
  }
}
''', language='c++')

    def test_original_crlf_and_lf_apply_twice_and_init_rejects_error(self):
        for ending in ('lf', 'crlf'):
            with self.subTest(ending=ending), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                write_preimages(root, PATCH)
                if ending=='crlf':
                    for name in patch_sections(PATCH):
                        source=root/name
                        source.write_bytes(source.read_bytes().replace(b'\n',b'\r\n'))
                command=['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)]
                for _ in range(2): subprocess.run(command,check=True,capture_output=True)
                subprocess.run(['git','-C',str(root),'apply','--check','--reverse','--ignore-space-change',str(PATCH)],
                               check=True,capture_output=True)
        self.assertIn('if (RegisterOppEnums(env, exports) != napi_ok) {\n+        return nullptr;', PATCH.read_text())


if __name__=='__main__': unittest.main()
