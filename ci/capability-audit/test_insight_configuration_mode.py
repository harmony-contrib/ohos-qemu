"""Additive native registration/error fixtures, not actual intent execution."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/ability/ability_runtime/api26_insight_configuration_mode'
PATCH = COMPONENT / '0001-export-existing-configured-execution-modes.patch'


class InsightConfigurationModeTests(unittest.TestCase):
    def test_exact_helper_native_values_reverse_mapping_and_each_napi_failure(self):
        hunks = next(iter(patch_sections(PATCH).values()))
        body = hunks[0][2]
        begin = body.index('static napi_value InitExecuteModeForConfigurationObject(napi_env env)')
        end = body.index('napi_value JsInsightIntentDriverInit(napi_env env, napi_value exportObj)')
        function = '\n'.join(body[begin:end])
        source = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
enum ExecuteMode {UI_ABILITY_FOREGROUND=0,UI_ABILITY_BACKGROUND=1,
 UI_EXTENSION_ABILITY=2,SERVICE_EXTENSION_ABILITY=3};
struct Value {bool number=false; int32_t integer=0; std::string text;
 std::map<std::string,Value*> own;};
using napi_env=void*; using napi_value=Value*;
enum napi_status {napi_ok=0,napi_generic_failure=9};
std::vector<std::unique_ptr<Value>> storage;
int failure=0,calls=0;
Value* Make() {storage.push_back(std::make_unique<Value>());return storage.back().get();}
napi_status Step(){++calls;return calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_create_object(napi_env,Value** value){auto s=Step();if(s==napi_ok)*value=Make();return s;}
napi_status napi_create_string_utf8(napi_env,const char* text,size_t,Value** value){auto s=Step();
 if(s==napi_ok){*value=Make();(*value)->text=text;}return s;}
napi_status napi_create_int32(napi_env,int32_t number,Value** value){auto s=Step();
 if(s==napi_ok){*value=Make();(*value)->number=true;(*value)->integer=number;}return s;}
napi_status napi_set_property(napi_env,Value* object,Value* key,Value* value){auto s=Step();
 if(s==napi_ok)assert(object->own.emplace(key->number?std::to_string(key->integer):key->text,value).second);
 return s;}
#define NAPI_AUTO_LENGTH static_cast<size_t>(-1)
#define NAPI_CALL_BASE(env,call,result) do {if((call)!=napi_ok)return result;} while(0)
#define NAPI_CALL(env,call) NAPI_CALL_BASE(env,call,nullptr)
struct HandleScope {explicit HandleScope(napi_env){}};
struct HandleEscape {explicit HandleEscape(napi_env){} napi_value Escape(napi_value value){return value;}};
static napi_status SetEnumItem(napi_env env, napi_value napiObject, const char* name, int32_t value)
{
    HandleScope handleScope(env);
    napi_status status;
    napi_value itemName;
    napi_value itemValue;
    NAPI_CALL_BASE(env, status = napi_create_string_utf8(env, name, NAPI_AUTO_LENGTH, &itemName), status);
    NAPI_CALL_BASE(env, status = napi_create_int32(env, value, &itemValue), status);
    NAPI_CALL_BASE(env, status = napi_set_property(env, napiObject, itemName, itemValue), status);
    NAPI_CALL_BASE(env, status = napi_set_property(env, napiObject, itemValue, itemName), status);
    return napi_ok;
}
'''
        main = r'''
int main(){
 for(int repeat=0;repeat<128;++repeat){
  for(failure=0;failure<=9;++failure){
   storage.clear();calls=0;
   auto result=InitExecuteModeForConfigurationObject(nullptr);
   assert(failure?result==nullptr:result!=nullptr);
   assert(calls==(failure?failure:9));
   if(!failure){
    assert(result->own.size()==4);
    assert(result->own.at("FOREGROUND")->number && result->own.at("FOREGROUND")->integer==UI_ABILITY_FOREGROUND);
    assert(result->own.at("BACKGROUND")->number && result->own.at("BACKGROUND")->integer==UI_ABILITY_BACKGROUND);
    assert(result->own.at("0")->text=="FOREGROUND" && result->own.at("1")->text=="BACKGROUND");
    assert(!result->own.count("UI_EXTENSION_ABILITY") && !result->own.count("SERVICE_EXTENSION_ABILITY"));
   }
  }
 }
}
'''
        compile_run(source + function + main, language='c++')

    def test_initializer_keeps_all_old_exports_and_checks_new_object_before_publication(self):
        before, after = next(iter(patch_sections(PATCH).values()))[1][1:]
        added = [line for line in after if line not in before]
        self.assertEqual(added, [
            '    napi_value executeModeForConfiguration = InitExecuteModeForConfigurationObject(env);',
            '    NAPI_ASSERT(env, executeModeForConfiguration != nullptr, "failed to create configuration execute mode object");',
            '        DECLARE_NAPI_PROPERTY("ExecuteModeForConfiguration", executeModeForConfiguration),'])
        self.assertEqual([line for line in after if line not in added], before)
        self.assertLess(after.index(added[1]), after.index('    napi_property_descriptor exportObjs[] = {'))
        self.assertIn('    NAPI_ASSERT(env, status == napi_ok, "failed to define properties for exportObj");', after)

    def test_marker_free_repeated_component_application_on_both_line_endings(self):
        for line_ending in ('\n', '\r\n'):
            with self.subTest(line_ending=line_ending), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_preimages(root, PATCH)
                for name in patch_sections(PATCH):
                    path = root / name
                    path.write_bytes(path.read_text().replace('\n', line_ending).encode())
                fixture = root / 'fixture'
                shutil.copytree(COMPONENT, fixture / COMPONENT.relative_to(ROOT))
                shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
                argv = ['bash', str(fixture / COMPONENT.relative_to(ROOT) / 'apply.sh'), '--source-root', str(root)]
                subprocess.run(argv, check=True, capture_output=True)
                first = {name: (root / name).read_bytes() for name in patch_sections(PATCH)}
                for marker in (root / '.ohos-qemu-patches').glob('*.applied'):
                    marker.unlink()
                subprocess.run(argv, check=True, capture_output=True)
                self.assertEqual(first, {name: (root / name).read_bytes() for name in patch_sections(PATCH)})

    def test_common_pretraversal_plan_changes_no_permission_or_dispatch(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        invocation = 'bash "${INSIGHT_CONFIGURATION_MODE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertEqual(builder.count(invocation), 1)
        self.assertIn(invocation, builder.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0])
        text = PATCH.read_text()
        self.assertFalse(any(line.startswith('-') and not line.startswith('---') for line in text.splitlines()))
        self.assertNotIn('PermissionVerification', text)
        self.assertNotIn('AbilityManagerClient', text)


if __name__ == '__main__':
    unittest.main()
