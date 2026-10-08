"""Exact call enum/error fixtures; no modem or guest behavior is simulated."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/base/telephony/call_manager/api26_enums'
PATCH=next(COMPONENT.glob('*.patch'))

class CallPublicEnumsTests(unittest.TestCase):
    def test_exact_registration_all_values_failures_and_both_feature_variants(self):
        section=next(iter(patch_sections(PATCH).values()))
        added=[line for hunk in section for line in hunk[2]]
        start=next(index for index,line in enumerate(added) if line=='struct PublicCallEnumMember {')
        end=added.index('NapiCallManager::NapiCallManager() {}',start)
        function='\n'.join(added[start:end])
        source=r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
enum class TelCallState {CALL_STATUS_UNKNOWN=-1,CALL_STATUS_ACTIVE=0,CALL_STATUS_HOLDING=1,
 CALL_STATUS_DIALING=2,CALL_STATUS_ALERTING=3,CALL_STATUS_INCOMING=4,CALL_STATUS_WAITING=5,
 CALL_STATUS_DISCONNECTED=6,CALL_STATUS_DISCONNECTING=7,CALL_STATUS_IDLE=8,CALL_STATUS_ANSWERED=9};
enum class CallStateToApp {CALL_STATE_UNKNOWN=-1,CALL_STATE_IDLE=0,CALL_STATE_RINGING=1,
 CALL_STATE_OFFHOOK=2,CALL_STATE_ANSWERED=3};
enum class RttCallState {RTT_STATE_NO=0,RTT_STATE_YES=1,RTT_STATE_REMOTE_TTY=2,RTT_STATE_REMOTE_NOT_SUPPORT=3};
#ifdef SUPPORT_RTT_CALL
enum ImsRTTCallMode:int32_t {LOCAL_REQUEST_UPGRADE=0,LOCAL_REQUEST_DOWNGRADE=1,
 REMOTE_REQUEST_UPGRADE_LOCAL_ACCEPT=2,REMOTE_REQUEST_UPGRADE_LOCAL_REJECT=3};
#endif
struct Value {int32_t number=0; std::map<std::string,Value*> own;};
using napi_env=void*; using napi_value=Value*;
enum napi_status {napi_ok=0,napi_generic_failure=9};
std::vector<std::unique_ptr<Value>> storage;
int failure=0,calls=0;
Value* Make() {storage.push_back(std::make_unique<Value>());return storage.back().get();}
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
  {"CCallState",{{"CCALL_STATE_UNKNOWN",-1},{"CCALL_STATE_ACTIVE",0},{"CCALL_STATE_HOLDING",1},
   {"CCALL_STATE_DIALING",2},{"CCALL_STATE_ALERTING",3},{"CCALL_STATE_INCOMING",4},{"CCALL_STATE_WAITING",5},
   {"CCALL_STATE_DISCONNECTED",6},{"CCALL_STATE_DISCONNECTING",7},{"CCALL_STATE_IDLE",8},{"CCALL_STATE_ANSWERED",9}}},
  {"TelCallState",{{"TEL_CALL_STATE_UNKNOWN",-1},{"TEL_CALL_STATE_IDLE",0},{"TEL_CALL_STATE_RINGING",1},
   {"TEL_CALL_STATE_OFFHOOK",2},{"TEL_CALL_STATE_ANSWERED",3},{"TEL_CALL_STATE_CONNECTED",4}}},
  {"RttState",{{"RTT_STATE_NO",0},{"RTT_STATE_YES",1},{"RTT_STATE_REMOTE_TTY",2},{"RTT_STATE_REMOTE_NOT_SUPPORT",3}}},
  {"ImsRttMode",{{"LOCAL_REQUEST_UPGRADE",0},{"LOCAL_REQUEST_DOWNGRADE",1},
   {"REMOTE_REQUEST_UPGRADE_LOCAL_ACCEPT",2},{"REMOTE_REQUEST_UPGRADE_LOCAL_REJECT",3}}},
  {"XCallType",{{"XCALL_ECALL_TYPE",0},{"XCALL_BCALL_TYPE",1},{"XCALL_ICALL_TYPE",2}}}};
 for(int repeat=0;repeat<64;++repeat){
  for(failure=0;failure<=66;++failure){
   auto exports=Make();calls=0;
   auto result=RegisterPublicCallEnums(nullptr,exports);
   assert(failure?result==nullptr:result==exports);
   assert(calls==(failure?failure:66));
   assert(failure?exports->own.size()<5:exports->own.size()==5);
   for(const auto& item:exports->own){
    const auto& members=expected.at(item.first);
    assert(members.size()==item.second->own.size());
    for(const auto& member:members)assert(item.second->own.at(member.first)->number==member.second);
   }
  }
 }
}
'''
        for flag in ('','#define SUPPORT_RTT_CALL\n'):
            with self.subTest(feature=bool(flag)):
                compile_run(flag+source+function+main,language='c++')

    def test_component_apply_twice_keeps_original_enum_names_and_callbacks(self):
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
            text=PATCH.read_text()
            self.assertIn('     DeclareMarkTypeEnum(env, exports);',text)
            self.assertIn('     RegisterCallBack();',text)
            self.assertNotIn('-    Init();',text)
            self.assertNotIn('CheckPermission',text)

    def test_phone_features_enable_both_real_endpoints_only(self):
        text=(ROOT/'patches/phone/product_profile/apply.py').read_text()
        self.assertIn('("telephony", "call_manager"): {"call_manager_feature_support_rtt": True}',text)
        self.assertIn('("telephony", "cellular_call"): {"cellular_call_support_rtt": True}',text)
        two=(ROOT/'patches/2in1/product_profile/apply.py').read_text()
        self.assertNotIn('"call_manager_feature_support_rtt": True',two)
        self.assertNotIn('"cellular_call_support_rtt": True',two)

if __name__=='__main__':
    unittest.main()
