"""Exact public metadata registration fixtures, not provider or guest proof."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/player_framework/api26_fetch_result'
PATCH = COMPONENT / '0001-register-public-metadata-fetch-result.patch'


class MediaFetchResultTests(unittest.TestCase):
    def test_exact_registration_values_all_errors_and_init_failure_propagation(self):
        sections = patch_sections(PATCH)
        name = next(name for name in sections if name.endswith('/media_enum_napi.cpp'))
        function = '\n'.join(sections[name][0][2]) + '\n}\n'
        source = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <vector>
struct JsEnumInt {std::string_view enumName; int32_t enumInt;};
struct Value {int32_t number=0; std::map<std::string,Value*> own;};
using napi_env=void*; using napi_value=Value*;
enum napi_status {napi_ok=0,napi_generic_failure=9};
std::vector<std::unique_ptr<Value>> storage;
int failure=0,calls=0,legacyCalls=0;
Value* Make() {storage.push_back(std::make_unique<Value>());return storage.back().get();}
napi_status Step(){++calls;return calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_create_object(napi_env,Value** value){auto s=Step();if(s==napi_ok)*value=Make();return s;}
napi_status napi_create_int32(napi_env,int32_t number,Value** value){auto s=Step();
 if(s==napi_ok){*value=Make();(*value)->number=number;}return s;}
napi_status napi_set_named_property(napi_env,Value* object,const char* name,Value* value){auto s=Step();
 if(s==napi_ok)assert(object->own.emplace(name,value).second);return s;}
#define CHECK_AND_RETURN_RET(condition,result) do {if(!(condition))return result;} while(0)
struct MediaEnumNapi {static napi_value Init(napi_env,napi_value);};
void JsEnumIntInit(napi_env,napi_value){++legacyCalls;}
void JsEnumStringInit(napi_env,napi_value){++legacyCalls;}
'''
        main = r'''
int main(){
 const std::map<std::string,int32_t> expected={
  {"FETCH_FAILED",0},{"FETCH_SUCCEEDED",1},{"FETCH_CANCELED",2}};
 for(int repeat=0;repeat<128;++repeat){
  for(failure=0;failure<=8;++failure){
   storage.clear();auto exports=Make();calls=0;legacyCalls=0;
   auto result=MediaEnumNapi::Init(nullptr,exports);
   assert(failure?result==nullptr:result==exports);
   assert(calls==(failure?failure:8));
   assert(legacyCalls==(failure?0:2));
   // No incomplete enum object is published, including final export failure.
   assert(exports->own.size()==(failure?0:1));
   if(!failure){
    const auto& members=exports->own.at("FetchResult")->own;
    assert(members.size()==expected.size());
    for(const auto& member:expected)assert(members.at(member.first)->number==member.second);
   }
  }
 }
}
'''
        compile_run(source + function + main, language='c++')

    def test_native_entry_checks_the_real_initializer_before_feature_exports(self):
        sections = patch_sections(PATCH)
        name = next(name for name in sections if name.endswith('/native_module_ohos_media.cpp'))
        before, after = sections[name][0][1:]
        self.assertEqual(before[2], '    OHOS::Media::MediaEnumNapi::Init(env, exports);')
        self.assertEqual(after[2], '    CHECK_AND_RETURN_RET(OHOS::Media::MediaEnumNapi::Init(env, exports) != nullptr, nullptr);')
        self.assertEqual(before[:2] + before[3:], after[:2] + after[3:])
        self.assertIn('#ifdef SUPPORT_PLAYER', after)

    def test_component_repeated_application_and_original_feature_gates(self):
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
                argv = ['bash', str(fixture / COMPONENT.relative_to(ROOT) / 'apply.sh'),
                        '--source-root', str(root)]
                subprocess.run(argv, check=True, capture_output=True)
                first = {name: (root / name).read_bytes() for name in patch_sections(PATCH)}
                # Delete marker files so reverse applicability, not a marker, proves idempotence.
                for marker in (root / '.ohos-qemu-patches').glob('*.applied'):
                    marker.unlink()
                subprocess.run(argv, check=True, capture_output=True)
                self.assertEqual(first, {name: (root / name).read_bytes() for name in patch_sections(PATCH)})
                self.assertIn(b'JsEnumIntInit(env, exports);', first[next(iter(first))])
                self.assertIn(b'JsEnumStringInit(env, exports);', first[next(iter(first))])

    def test_common_pretraversal_plan_keeps_the_native_provider_and_permissions(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        invocation = 'bash "${METADATA_FETCH_RESULT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        plan = builder.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0]
        self.assertIn(invocation, plan)
        self.assertEqual(builder.count(invocation), 1)
        added = [line[1:] for line in PATCH.read_text().splitlines()
                 if line.startswith('+') and not line.startswith('+++')]
        self.assertFalse(any('Permission' in line or 'SUPPORT_' in line or 'callback' in line.lower()
                             for line in added if not line.lstrip().startswith('//')))


if __name__ == '__main__':
    unittest.main()
