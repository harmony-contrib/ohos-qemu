"""Fixed SDK enum binding fixtures, not location/geofence backend success."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/base/location/location/api26_public_enums'
PATCH=COMPONENT/'0001-register-fixed-sdk-location-enums.patch'
EXPECTED={"LocationIconStatus":{"LOCATING_NOT_STARTED":0,"LOCATING_STARTED":1,"HD_LOCATING_STARTED":2},"GnssFenceType":{"POLYGON":1,"CIRCULAR":2},"WifiFingerprintType":{"SEMANTIC":1,"LOCATION":2},"FusionFenceType":{"GNSS":1,"CELLULAR":2,"WIFI":4,"BLUETOOTH":8},"FusionFenceScene":{"AIRPORT":1,"TRAIN_STATION":2,"SUBWAY":3,"SHOP":4}}


class LocationEnumExportTests(unittest.TestCase):
    def test_all_members_bit_values_and_each_actual_napi_failure(self):
        functions=[]
        for hunks in patch_sections(PATCH).values():
            for _,_,lines in hunks:
                for index,line in enumerate(lines):
                    if line.startswith('static napi_status RegisterPublicLocationEnums('):
                        functions.append('\n'.join(lines[index:lines.index('}',index)+1]))
        self.assertEqual(len(functions),1)
        source=r"""
#include <cassert>
#include <cstdint>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { int32_t number=0; std::map<std::string,Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status { napi_ok=0, napi_generic_failure=9 };
int calls=0,failure=0;
std::vector<std::unique_ptr<Value>> storage;
Value* Make(){storage.push_back(std::make_unique<Value>());return storage.back().get();}
napi_status Step(){return ++calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_create_object(napi_env,Value** value){
 auto status=Step();if(status==napi_ok)*value=Make();return status;}
napi_status napi_create_int32(napi_env,int32_t number,Value** value){
 auto status=Step();if(status==napi_ok){*value=Make();(*value)->number=number;}return status;}
napi_status napi_set_named_property(napi_env,Value* object,const char* name,Value* value){
 auto status=Step();if(status==napi_ok)assert(object->own.emplace(name,value).second);return status;}
"""
        contracts=','.join('{"'+name+'",{'+','.join('{"'+member+'",'+str(value)+'}'
                  for member,value in members.items())+'}}' for name,members in EXPECTED.items())
        main=r"""
int main(){
 const std::map<std::string,std::map<std::string,int32_t>> expected={__CONTRACTS__};
 for(unsigned repeat=0;repeat<128;++repeat)for(failure=0;failure<=40;++failure){
  storage.clear();calls=0;auto exports=Make();
  const auto status=RegisterPublicLocationEnums(nullptr,exports);
  if(failure){assert(status==napi_generic_failure && calls==failure);continue;}
  assert(status==napi_ok && calls==40 && exports->own.size()==5);
  for(const auto& item:expected){
   assert(exports->own.at(item.first)->own.size()==item.second.size());
   for(const auto& member:item.second){
    assert(exports->own.at(item.first)->own.at(member.first)->number==member.second);
   }
  }
  assert((exports->own.at("FusionFenceType")->own.at("GNSS")->number|
          exports->own.at("FusionFenceType")->own.at("CELLULAR")->number|
          exports->own.at("FusionFenceType")->own.at("WIFI")->number|
          exports->own.at("FusionFenceType")->own.at("BLUETOOTH")->number)==15);
 }
}
""".replace('__CONTRACTS__',contracts)
        compile_run(source+functions[0]+main,language='c++')

    def test_component_repeated_patch_and_only_manager_initializer_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);write_preimages(root,PATCH)
            for _ in range(2):
                result=subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],
                                      capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            subprocess.run(['git','-C',str(root),'apply','--check','--reverse',str(PATCH)],check=True)
        text=PATCH.read_text()
        self.assertIn('if (RegisterPublicLocationEnums(env, exports) != napi_ok) {\n'
                      '+        return nullptr;',text)
        self.assertNotIn('static napi_value Init(napi_env',text)
        self.assertFalse(any(line.startswith('-') and not line.startswith('---')
                             for line in text.splitlines()))
        for call in ('AddGnssGeofence','SetMockedLocations','CheckPermission','LocationCallback'):
            self.assertNotIn(call,text)


if __name__=='__main__':unittest.main()

