"""Exact enum registration/error-path fixtures, not radio or SMS evidence."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'patches/common/base/telephony/core_service/api26_enums'
SMS = ROOT / 'patches/common/base/telephony/sms_mms/api26_enums'
VPN = ROOT / 'patches/common/foundation/communication/netmanager_ext/api26_features'


def added_function(patch, suffix, signature):
    section = next(value for name, value in patch_sections(patch).items() if name.endswith(suffix))
    lines = [line for hunk in section for line in hunk[2]]
    start = next(index for index, line in enumerate(lines) if signature in line)
    end = lines.index('}', start)
    return '\n'.join(lines[start:end + 1])


class Api26TelephonyEnumTests(unittest.TestCase):
    def test_exact_native_registrations_and_each_NAPI_failure_short_circuit(self):
        core_patch = next(CORE.glob('*.patch'))
        sms_patch = next(SMS.glob('*.patch'))
        functions = added_function(core_patch, '/napi_sim.cpp', 'napi_value InitEnumDsdsMode(') + '\n' + \
            added_function(sms_patch, '/napi_sms.cpp', 'napi_value InitEnumSmsShortCodeType(')
        source = r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { int32_t number=0; std::map<std::string, Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status { napi_ok=0, napi_generic_failure=9 };
struct napi_property_descriptor { const char* name; Value* value; };
enum class DsdsMode { DSDS_MODE_V2=0, DSDS_MODE_V3=1, DSDS_MODE_V5_TDM=2, DSDS_MODE_V5_DSDA=3 };
enum class SmsShortCodeType { SMS_SHORT_CODE_TYPE_UNKNOWN=-1, SMS_SHORT_CODE_TYPE_NOT_PREMIUM=0,
                             SMS_SHORT_CODE_TYPE_POSSIBLE_PREMIUM=1 };
std::vector<std::unique_ptr<Value>> storage;
int failure=0, calls=0;
Value* Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
struct NapiUtil { static Value* ToInt32Value(napi_env,int32_t number) {
    auto value=Make(); value->number=number; return value; } };
napi_status Step() { ++calls; return calls==failure ? napi_generic_failure : napi_ok; }
napi_status napi_create_object(napi_env,Value** value) {
    auto status=Step(); if(status==napi_ok) *value=Make(); return status; }
napi_status napi_define_properties(napi_env,Value* object,size_t count,napi_property_descriptor* properties) {
    auto status=Step(); if(status!=napi_ok) return status;
    for(size_t index=0;index<count;++index)
        assert(object->own.emplace(properties[index].name,properties[index].value).second);
    return napi_ok; }
napi_status napi_set_named_property(napi_env,Value* object,const char* name,Value* value) {
    auto status=Step(); if(status==napi_ok) assert(object->own.emplace(name,value).second); return status; }
#define DECLARE_NAPI_STATIC_PROPERTY(name,value) napi_property_descriptor{name,value}
#define NAPI_CALL(env,call) do { if((call)!=napi_ok) return nullptr; } while(false)
'''
        main = r'''
int main() {
  for(unsigned repeat=0;repeat<128;++repeat) {
    for(auto fn:{InitEnumDsdsMode,InitEnumSmsShortCodeType}) {
      for(failure=0;failure<=3;++failure) {
        auto exports=Make(); calls=0; auto result=fn(nullptr,exports);
        if(failure) { assert(result==nullptr); assert(calls==failure); assert(exports->own.empty()); }
        else {
          assert(result==exports); assert(calls==3); assert(exports->own.size()==1);
          if(fn==InitEnumDsdsMode) {
            auto mode=exports->own.at("DsdsMode"); assert(mode->own.size()==4);
            assert(mode->own.at("DSDS_MODE_V2")->number==0);
            assert(mode->own.at("DSDS_MODE_V3")->number==1);
            assert(mode->own.at("DSDS_MODE_V5_TDM")->number==2);
            assert(mode->own.at("DSDS_MODE_V5_DSDA")->number==3);
          } else {
            auto type=exports->own.at("SmsShortCodeType"); assert(type->own.size()==3);
            assert(type->own.at("SMS_SHORT_CODE_TYPE_UNKNOWN")->number==-1);
            assert(type->own.at("SMS_SHORT_CODE_TYPE_NOT_PREMIUM")->number==0);
            assert(type->own.at("SMS_SHORT_CODE_TYPE_POSSIBLE_PREMIUM")->number==1);
          }
        }
      }
    }
  }
}
'''
        compile_run(source + functions + main, language='c++')

    def test_all_component_stacks_apply_fresh_and_repeat_without_repair_drift(self):
        for component in (CORE, SMS, VPN):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for patch in sorted(component.glob('*.patch')):
                    write_preimages(root, patch)
                fixture = root / 'fixture-repository'
                script = fixture / component.relative_to(ROOT)
                shutil.copytree(component, script)
                shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
                argv = ['bash', str(script / 'apply.sh'), '--source-root', str(root)]
                subprocess.run(argv, check=True, capture_output=True)
                paths = {name for patch in component.glob('*.patch') for name in patch_sections(patch)}
                before = {name: (root / name).read_bytes() for name in paths}
                subprocess.run(argv, check=True, capture_output=True)
                self.assertEqual(before, {name: (root / name).read_bytes() for name in paths})

    def test_nr_keeps_real_native_constants_and_vpn_corrects_both_modules(self):
        core = next(CORE.glob('*.patch')).read_text()
        self.assertIn('"NrOptionMode", mode', core)
        self.assertIn('NapiUtil::ToInt32Value(env, static_cast<int32_t>(NR_OPTION_NSA_AND_SA))', core)
        vpn = (VPN / '0003-match-the-public-sysvpn-mschapv2-member-spelling.patch').read_text()
        self.assertEqual(vpn.count('+constexpr const char *IKEV2_IPSEC_MSCHAPv2_TYPE = "IKEV2_IPSEC_MSCHAPV2";'), 2)
        self.assertNotIn('VpnType::', vpn)  # Do not change native protocol values.
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        for variable in ('TELEPHONY_CORE_ENUMS_COMPONENT_SCRIPT', 'TELEPHONY_SMS_ENUMS_COMPONENT_SCRIPT'):
            self.assertEqual(builder.count('bash "${' + variable + '}"'), 1)


if __name__ == '__main__':
    unittest.main()
