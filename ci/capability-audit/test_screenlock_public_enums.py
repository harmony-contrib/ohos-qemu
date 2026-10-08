"""Exact native enum moves and checked NAPI registration, not unlock proof."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/base/theme/screenlock_mgr/api26_enums'
PATCH=next(COMPONENT.glob('*.patch'))

def definition(lines, signature, end):
    start=lines.index(signature)
    return '\n'.join(lines[start:lines.index(end,start)+1])

class ScreenLockPublicEnumsTests(unittest.TestCase):
    def test_shared_native_definition_unchanged_and_internal_states_not_exported(self):
        sections=patch_sections(PATCH)
        common=sections['base/theme/screenlock_mgr/interfaces/inner_api/include/screenlock_common.h']
        service=sections['base/theme/screenlock_mgr/services/include/screenlock_system_ability.h']
        old=[line for hunk in service for line in hunk[1]]
        new=[line for hunk in common for line in hunk[2]]
        self.assertEqual(definition(old,'enum class AuthState : int32_t {','};'),
                         definition(new,'enum class AuthState : int32_t {','};'))
        cpp=sections['base/theme/screenlock_mgr/frameworks/js/napi/src/napi_screenlock_ability.cpp']
        new=[line for hunk in cpp for line in hunk[2]]
        self.assertNotIn('"PRE_AUTHED_RESULT_BY_CREDENTIAL"', '\n'.join(new))
        self.assertNotIn('"SECURITY_ENHANCEMENT"', '\n'.join(new))
        self.assertIn('        return nullptr;',new)
        self.assertIn('    return RegisterPublicScreenLockEnums(env, exports);',new)
        self.assertNotIn('CheckPermission',PATCH.read_text())

    def test_exact_registration_all_values_and_every_napi_failure(self):
        sections=patch_sections(PATCH)
        common=[line for hunk in sections['base/theme/screenlock_mgr/interfaces/inner_api/include/screenlock_common.h']
                for line in hunk[2]]
        native=definition(common,'enum class AuthState : int32_t {','};')+'\n'+definition(
            common,'enum class UnlockPolicy : int32_t {','};')
        lines=[line for hunk in sections['base/theme/screenlock_mgr/frameworks/js/napi/src/napi_screenlock_ability.cpp']
               for line in hunk[2]]
        start=lines.index('struct PublicScreenLockEnumMember {')
        end=lines.index('napi_status Init(napi_env env, napi_value exports)',start)
        function='\n'.join(lines[start:end])
        source=r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
enum class StrongAuthReasonFlags:int32_t {NONE=0,AFTER_BOOT=1,AFTER_TIMEOUT=2,
 ACTIVE_REQUEST=4,DPM_RESTRICT=8,SECURITY_ENHANCEMENT=0x16};
struct Value {int32_t number=0;std::map<std::string,Value*> own;};
using napi_env=void*;using napi_value=Value*;
enum napi_status {napi_ok=0,napi_generic_failure=9};
std::vector<std::unique_ptr<Value>> storage;
int calls=0,failure=0;
Value* Make(){storage.push_back(std::make_unique<Value>());return storage.back().get();}
napi_status Step(){++calls;return calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_create_object(napi_env,Value** value){auto s=Step();if(s==napi_ok)*value=Make();return s;}
napi_status napi_create_int32(napi_env,int32_t number,Value** value){auto s=Step();
 if(s==napi_ok){*value=Make();(*value)->number=number;}return s;}
napi_status napi_set_named_property(napi_env,Value* object,const char* name,Value* value){auto s=Step();
 if(s==napi_ok)assert(object->own.emplace(name,value).second);return s;}
'''
        main=r'''
int main(){
 const std::map<std::string,std::map<std::string,int32_t>> expected={
  {"StrongAuthReasonFlags",{{"NONE",0},{"AFTER_BOOT",1},{"AFTER_TIMEOUT",2},{"ACTIVE_REQUEST",4},{"POLICY_RESTRICTION",8}}},
  {"AuthState",{{"NOT_AUTHED",0},{"PRE_AUTHED_BY_CREDENTIAL",1},{"PRE_AUTHED_BY_FINGERPRINT",2},
   {"PRE_AUTHED_BY_FACE",3},{"AUTHED_BY_CREDENTIAL",4},{"AUTHED_BY_FINGERPRINT",5},{"AUTHED_BY_FACE",6}}},
  {"UnlockPolicy",{{"DEFAULT",0},{"EXTENDED_AUTH_ONLY",1},{"EXTENDED_AUTH_AND_SYSTEM",2}}}};
 for(int repeat=0;repeat<64;++repeat){
  for(failure=0;failure<=36;++failure){
   auto exports=Make();calls=0;
   auto status=RegisterPublicScreenLockEnums(nullptr,exports);
   assert(status==(failure?napi_generic_failure:napi_ok));
   assert(calls==(failure?failure:36));
   assert(failure?exports->own.size()<3:exports->own.size()==3);
   for(const auto& item:exports->own){
    const auto& members=expected.at(item.first);assert(members.size()==item.second->own.size());
    for(const auto& member:members)assert(item.second->own.at(member.first)->number==member.second);
   }
  }
 }
}
'''
        compile_run(source+native+function+main,language='c++')

    def test_component_apply_twice_without_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            write_preimages(root,PATCH)
            fixture=root/'fixture'
            shutil.copytree(COMPONENT,fixture/COMPONENT.relative_to(ROOT))
            shutil.copytree(ROOT/'patches/lib',fixture/'patches/lib')
            argv=['bash',str(fixture/COMPONENT.relative_to(ROOT)/'apply.sh'),'--source-root',str(root)]
            subprocess.run(argv,check=True,capture_output=True)
            paths=list(patch_sections(PATCH))
            before={name:(root/name).read_bytes() for name in paths}
            subprocess.run(argv,check=True,capture_output=True)
            self.assertEqual(before,{name:(root/name).read_bytes() for name in paths})

if __name__=='__main__':
    unittest.main()
