"""Execute the patched initializer with explicit NAPI doubles, not guest evidence."""
from pathlib import Path
import unittest

from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/camera_framework/effect_suggestion_record'


class CameraEffectRecordTests(unittest.TestCase):
    def test_initializer_and_constructor_failure_boundaries(self):
        sections = patch_sections(COMPONENT / '0001-register-effect-suggestion-status-record.patch')
        self.assertEqual(len(sections), 1)
        after = next(iter(sections.values()))[0][2]
        body = '\n'.join(after)
        for name in ('PhotoNapi', 'CapturePhotoNapi', 'SecureCameraSessionNapi'):
            body = body.replace('    ' + name + '::Init(env, exports);', '')
        body = body.replace('    MEDIA_DEBUG_LOG("Export is end");', '')
        harness = r'''
#include <cassert>
#include <cstddef>
#include <string>
struct Value {int marker=0;};
struct Info {Value* target; Value* instance;};
using napi_env=void*;
using napi_value=Value*;
using napi_callback_info=Info*;
using Callback=napi_value(*)(napi_env,napi_callback_info);
enum napi_status {napi_ok,napi_generic_failure};
constexpr size_t NAPI_AUTO_LENGTH=static_cast<size_t>(-1);
int calls=0, failure=0, errors=0;
Callback callback=nullptr;
Value klass, published;
napi_status Step(){return ++calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_get_new_target(napi_env,napi_callback_info info,napi_value* target){
    auto status=Step();if(status==napi_ok)*target=info->target;return status;
}
napi_status napi_get_cb_info(napi_env,napi_callback_info info,size_t* count,napi_value* args,
    napi_value* instance,void** data){
    assert(!count && !args && !data);auto status=Step();if(status==napi_ok)*instance=info->instance;return status;
}
napi_status napi_throw_type_error(napi_env,const char* code,const char* text){
    assert(!code && std::string(text)=="EffectSuggestionStatus requires new");++errors;return napi_ok;
}
napi_status napi_define_class(napi_env,const char* name,size_t length,Callback ctor,void* data,
    size_t count,const void* props,napi_value* result){
    assert(std::string(name)=="EffectSuggestionStatus" && length==NAPI_AUTO_LENGTH);
    assert(!data && !count && !props);auto status=Step();if(status==napi_ok){callback=ctor;*result=&klass;}return status;
}
napi_status napi_set_named_property(napi_env,napi_value object,const char* name,napi_value value){
    assert(object==&published && std::string(name)=="EffectSuggestionStatus" && value==&klass);return Step();
}
napi_value Export(napi_env env,napi_value exports){
'''
        main = r'''
int main(){
    for(failure=0;failure<=2;++failure){calls=0;assert(Export(nullptr,&published)==(failure?nullptr:&published));}
    assert(callback);
    Value first,second;
    Info a{&klass,&first},b{&klass,&second};
    for(failure=1;failure<=2;++failure){calls=0;assert(callback(nullptr,&a)==nullptr);assert(calls==failure);}
    failure=0;calls=0;
    assert(callback(nullptr,&a)==&first && callback(nullptr,&b)==&second);
    first.marker=9;assert(second.marker==0);
    Info ordinary{nullptr,&first};errors=0;calls=0;
    assert(callback(nullptr,&ordinary)==nullptr && errors==1 && calls==1);
}
'''
        compile_run(harness + body + main, language='c++')

    def test_recipe_and_typed_test_require_real_constructor(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(recipe.count('bash "${CAMERA_EFFECT_RECORD_COMPONENT_SCRIPT}" --source-root'), 1)
        probe = (ROOT / 'ci/capability-audit/camera_probe.ets').read_text()
        self.assertEqual(probe.count('new camera.EffectSuggestionStatus()'), 2)
        self.assertIn('this.checkEffectSuggestionRecord();', probe)
        from verify_camera_results import ARKTS_PREFIX
        self.assertEqual(ARKTS_PREFIX[:4], ('effect_record_constructor', 'effect_record_unset_fields',
                                          'effect_record_values', 'effect_record_isolation'))


if __name__ == '__main__':
    unittest.main()
