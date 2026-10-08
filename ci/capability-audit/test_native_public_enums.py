"""Exact candidate enum/translation fixtures, not guest/backend acceptance."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = (
    ROOT / 'patches/common/base/global/i18n/api26_suggestion_type',
    ROOT / 'patches/common/foundation/distributedhardware/device_manager/api26_auth_form',
    ROOT / 'patches/common/foundation/multimedia/player_framework/api26_tone_haptics_feature',
)

def function(section, signature):
    lines = [line for hunk in section for line in hunk[2]]
    start = next(index for index, line in enumerate(lines) if signature in line)
    end = lines.index('}', start)
    return '\n'.join(lines[start:end + 1])

class NativePublicEnumTests(unittest.TestCase):
    def test_exact_functions_native_values_and_every_napi_error(self):
        patches = [next(path.glob('*.patch')) for path in COMPONENTS]
        intl = next(iter(patch_sections(patches[0]).values()))
        dm = list(patch_sections(patches[1]).values())
        tone = next(iter(patch_sections(patches[2]).values()))
        self.assertEqual(function(dm[0], 'static napi_value RegisterAuthForm('),
                         function(dm[1], 'static napi_value RegisterAuthForm('))
        functions = '\n'.join((
            function(intl, 'static bool ToPublicSuggestionType('),
            function(intl, 'static napi_status RegisterSuggestionType('),
            function(dm[0], 'static napi_value RegisterAuthForm('),
            function(tone, 'static napi_status RegisterToneHapticsFeature('),
            function(intl, 'napi_value SystemLocaleManagerAddon::CreateSuggestionType(')))
        source = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { int32_t number=0; std::map<std::string, Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status { napi_ok=0, napi_invalid_arg=1, napi_generic_failure=9 };
// Native definitions deliberately differ from the public SDK for I18n.
enum SuggestionType { SUGGESTION_TYPE_NONE=0, SUGGESTION_TYPE_SIM=1, SUGGESTION_TYPE_RELATED=2 };
enum DmAuthForm { INVALID_TYPE=-1, PEER_TO_PEER=0, IDENTICAL_ACCOUNT=1, ACROSS_ACCOUNT=2, SHARE=3 };
enum ToneHapticsFeature : int32_t { STANDARD=0, GENTLE=1 };
struct SystemLocaleManagerAddon {
    static napi_value CreateSuggestionType(napi_env, SuggestionType);
};
#define HILOG_ERROR_I18N(...) ((void)0)
std::vector<std::unique_ptr<Value>> storage;
int failure=0, calls=0;
Value* Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
napi_status Step() { ++calls; return calls==failure ? napi_generic_failure : napi_ok; }
napi_status napi_create_object(napi_env, Value** value) {
    auto status=Step(); if(status==napi_ok) *value=Make(); return status; }
napi_status napi_create_int32(napi_env, int32_t number, Value** value) {
    auto status=Step(); if(status==napi_ok) { *value=Make(); (*value)->number=number; } return status; }
napi_status napi_set_named_property(napi_env, Value* object, const char* name, Value* value) {
    auto status=Step(); if(status==napi_ok) assert(object->own.emplace(name,value).second); return status; }
'''
        main = r'''
int main() {
  int32_t number=77;
  assert(ToPublicSuggestionType(SUGGESTION_TYPE_NONE,number) && number==0);
  assert(ToPublicSuggestionType(SUGGESTION_TYPE_RELATED,number) && number==1);
  assert(ToPublicSuggestionType(SUGGESTION_TYPE_SIM,number) && number==2);
  number=77; assert(!ToPublicSuggestionType(static_cast<SuggestionType>(-1),number) && number==77);
  assert(!ToPublicSuggestionType(static_cast<SuggestionType>(3),number) && number==77);
  for(auto native:{SUGGESTION_TYPE_NONE,SUGGESTION_TYPE_RELATED,SUGGESTION_TYPE_SIM}) {
    failure=0; calls=0;
    assert(ToPublicSuggestionType(native,number));
    auto result=SystemLocaleManagerAddon::CreateSuggestionType(nullptr,native);
    assert(result && result->number==number && calls==1);
    failure=1; calls=0;
    assert(SystemLocaleManagerAddon::CreateSuggestionType(nullptr,native)==nullptr && calls==1);
  }
  failure=0; calls=0;
  assert(SystemLocaleManagerAddon::CreateSuggestionType(nullptr,static_cast<SuggestionType>(-1))==nullptr);
  assert(SystemLocaleManagerAddon::CreateSuggestionType(nullptr,static_cast<SuggestionType>(3))==nullptr);
  assert(calls==0);
  for(unsigned repeat=0;repeat<128;++repeat) {
    for(int kind=0;kind<3;++kind) {
      const int steps=kind==0?8:kind==1?10:6;
      for(failure=0;failure<=steps;++failure) {
        auto exports=Make(); calls=0;
        bool ok=kind==0 ? RegisterSuggestionType(nullptr,exports)==napi_ok :
                kind==1 ? RegisterAuthForm(nullptr,exports)!=nullptr :
                          RegisterToneHapticsFeature(nullptr,exports)==napi_ok;
        if(failure) { assert(!ok); assert(calls==failure); assert(exports->own.empty()); }
        else {
          assert(ok); assert(calls==steps); assert(exports->own.size()==1);
          if(kind==0) {
            auto value=exports->own.at("SuggestionType"); assert(value->own.size()==3);
            assert(value->own.at("SUGGESTION_TYPE_NONE")->number==0);
            assert(value->own.at("SUGGESTION_TYPE_RELATED")->number==1);
            assert(value->own.at("SUGGESTION_TYPE_SIM")->number==2);
          } else if(kind==1) {
            auto value=exports->own.at("AuthForm"); assert(value->own.size()==4);
            assert(value->own.at("INVALID_TYPE")->number==-1);
            assert(value->own.at("PEER_TO_PEER")->number==0);
            assert(value->own.at("IDENTICAL_ACCOUNT")->number==1);
            assert(value->own.at("ACROSS_ACCOUNT")->number==2);
          } else {
            auto value=exports->own.at("ToneHapticsFeature"); assert(value->own.size()==2);
            assert(value->own.at("STANDARD")->number==0); assert(value->own.at("GENTLE")->number==1);
          }
        }
      }
    }
  }
}
'''
        compile_run(source+functions+main, language='c++')

    def test_components_apply_twice_without_drift(self):
        for component in COMPONENTS:
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                for patch in sorted(component.glob('*.patch')):
                    write_preimages(root,patch)
                fixture=root/'fixture'
                shutil.copytree(component,fixture/component.relative_to(ROOT))
                shutil.copytree(ROOT/'patches/lib',fixture/'patches/lib')
                argv=['bash',str(fixture/component.relative_to(ROOT)/'apply.sh'),'--source-root',str(root)]
                result=subprocess.run(argv,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                paths={name for patch in component.glob('*.patch') for name in patch_sections(patch)}
                before={name:(root/name).read_bytes() for name in paths}
                subprocess.run(argv,check=True,capture_output=True)
                self.assertEqual(before,{name:(root/name).read_bytes() for name in paths})

    def test_result_translation_is_shared_and_no_backend_claims(self):
        intl=next(COMPONENTS[0].glob('*.patch')).read_text()
        self.assertIn('+    if (!ToPublicSuggestionType(suggestionType, number)) {',intl)
        self.assertIn('+        if (!ToPublicSuggestionType(nativeTypes[index], number)) {',intl)
        for component in COMPONENTS:
            patch=next(component.glob('*.patch')).read_text()
            self.assertNotIn('+    return true;',patch.replace('+            return true;',''))
        dm=next(COMPONENTS[1].glob('*.patch')).read_text()
        self.assertNotIn('js4.0',dm)
        self.assertEqual(dm.count('+    return RegisterAuthForm(env, exports);'),2)
        self.assertNotIn('SHARE",',dm)

if __name__=='__main__':
    unittest.main()
