"""Exact remaining regular-enum fixtures; not backend or fresh-guest acceptance."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages
from test_photo_public_enums import function as photo_function

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = (
    ('foundation/arkui/ace_engine/api26_image_partial_type',
     '0001-export-public-partial-result-type.patch', 'IMAGE_PARTIAL_TYPE_COMPONENT_SCRIPT'),
    ('foundation/barrierfree/accessibility/api26_blink_enums',
     '0001-export-public-blinking-contracts.patch', 'ACCESSIBILITY_BLINK_ENUMS_COMPONENT_SCRIPT'),
    ('foundation/multimedia/media_library/api26_photo_search_enums',
     '0001-register-and-forward-photo-source-and-search-enums.patch', 'PHOTO_SEARCH_ENUMS_COMPONENT_SCRIPT'),
)

MOCK = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { int32_t number=-1; std::map<std::string,Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status {napi_ok=0,napi_generic_failure=9};
std::vector<std::unique_ptr<Value>> storage;
int failure=0,calls=0;
Value* Make(){storage.push_back(std::make_unique<Value>());return storage.back().get();}
napi_status Step(){++calls;return calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_create_object(napi_env,Value** value){auto s=Step();if(s==napi_ok)*value=Make();return s;}
napi_status napi_create_int32(napi_env,int32_t number,Value** value){auto s=Step();
 if(s==napi_ok){*value=Make();(*value)->number=number;}return s;}
napi_status napi_set_named_property(napi_env,Value* object,const char* key,Value* value){auto s=Step();
 if(s==napi_ok)assert(object->own.emplace(key,value).second);return s;}
#define NAPI_CALL(env,call) do {if((call)!=napi_ok)return nullptr;} while(0)
'''

def exercise(function, call, expected, count, status_result=False):
    main = r'''
int main(){
 const std::map<std::string,std::map<std::string,int32_t>> expected=__EXPECTED__;
 for(int repeat=0;repeat<128;++repeat){
  for(failure=0;failure<=__COUNT__;++failure){
   storage.clear();calls=0;auto exports=Make();auto sentinel=Make();exports->own.emplace("existing",sentinel);
   auto result=__CALL__(nullptr,exports);
   ASSERT_RESULT;
   assert(calls==(failure?failure:__COUNT__));assert(exports->own.at("existing")==sentinel);
   if(!failure){assert(exports->own.size()==expected.size()+1);
    for(const auto& contract:expected){const auto& members=exports->own.at(contract.first)->own;
     assert(members.size()==contract.second.size());
     for(const auto& member:contract.second)assert(members.at(member.first)->number==member.second);}
   }
  }
 }
}
'''.replace('__COUNT__', str(count)).replace('__CALL__', call).replace('__EXPECTED__', expected)
    assertion = 'assert(failure?result==napi_generic_failure:result==napi_ok);' if status_result else \
                'assert(failure?result==nullptr:result==exports);'
    compile_run(MOCK + function + main.replace('ASSERT_RESULT;', assertion), language='c++')


class FinalRegularEnumTests(unittest.TestCase):
    def test_image_partial_values_every_failure_and_initializer_guard(self):
        relative, name, _ = COMPONENTS[0]
        patch = ROOT / 'patches/common' / relative / name
        lines = next(iter(patch_sections(patch).values()))[0][2]
        end = lines.index('static napi_value Export(napi_env env, napi_value exports)')
        exercise('\n'.join(lines[:end]), 'RegisterPublicPartialResultType',
            '{{"PartialResultType",{{"PARTIAL",0},{"COMPLETED",1},{"PARTIAL_FAIL",2}}}}', 8)
        self.assertLess(lines.index('    NAPI_ASSERT(env, RegisterPublicPartialResultType(env, exports) != nullptr, "failed to create partial result object");'),
                        lines.index('    napi_property_descriptor properties[] = {'))

    def test_blink_three_enums_every_failure_and_initializer_guard(self):
        relative, name, _ = COMPONENTS[1]
        patch = ROOT / 'patches/common' / relative / name
        lines = next(iter(patch_sections(patch).values()))[0][2]
        end = lines.index('static napi_value InitConfigModule(napi_env env, napi_value exports)')
        expected = r'''{
            {"BlinkingMode",{{"SINGLE_BLINK",1},{"CONTINUOUS_BLINK",2}}},
            {"BlinkingScenario",{{"ALARM",1},{"NOTIFICATION",2},{"CALL",3},{"TESTING",4}}},
            {"BlinkResultCode",{{"SUCCESS",0},{"ALREADY_FLASHING",1},{"DEVICE_IN_USE",2},
                {"FLASH_BLINKING_UNSUPPORTED",3},{"SCREEN_BLINKING_UNSUPPORTED",4},{"FEATURE_DISABLED",5}}}
        }'''
        exercise('\n'.join(lines[:end]), 'RegisterPublicBlinkEnums', expected, 30)
        self.assertIn('    NAPI_ASSERT(env, RegisterPublicBlinkEnums(env, exports) != nullptr, "failed to create blinking enum objects");', lines)

    def test_photo_four_enums_actual_native_discriminator_all_failures_and_legacy_exports(self):
        relative, name, _ = COMPONENTS[2]
        patch = ROOT / 'patches/common' / relative / name
        hunks = next(values for key, values in patch_sections(patch).items() if key.endswith('media_library_napi.cpp'))
        addition = '\n'.join(hunks[1][2][1:-2])
        function = photo_function('RegisterPublicPhotoEnums').replace(
            '    const Contract contracts[] = {', '    const Contract contracts[] = {\n' + addition)
        native = r'''
enum class PhotoRiskStatus:int32_t { UNIDENTIFIED=0, APPROVED=1, SUSPICIOUS=2, REJECTED=3 };
enum class LivePhoto4dStatusType:int32_t {TYPE_UNIDENTIFIED=0,TYPE_UNSUPPORTED=1,TYPE_SUPPORTED=2,TYPE_USED=3,TYPE_LIVEPHOTO_4D=4};
enum class DeepOptimizeSpaceState:int32_t {RUNNING=0,COMPLETED=1,FAILED=2,STOPPED=3,INTERRUPTED=4};
enum CoverUriSource:int32_t {DEFAULT_COVER=0,MANUAL_CLOUD_COVER=1,MANUAL_LOCAL_COVER=2,MANUAL_WAIT_PULL_COVER=3};
enum ThumbnailVisibility:int32_t {INVISIBLE=0,VISIBLE=1};
const std::vector<std::string> appLinkStateEnum{"DEFAULT","HAS_NO_LINK","HAS_LINK"};
enum class FileSourceTypes:int32_t {MEDIA=MEDIA_VALUE,FILE_MANAGER=MANAGER_VALUE};
'''
        expected = r'''{
            {"AssetSourceType",{{"MEDIA",MEDIA_VALUE},{"FILE_MANAGER",MANAGER_VALUE}}},
            {"FieldType",{{"NONE",0},{"ANALYSIS_PEOPLE",1},{"ANALYSIS_LABEL",2},{"ANALYSIS_CITY",3},
                {"YEAR",4},{"MONTH",5},{"DAY",6},{"HOLIDAY",7},{"MEDIA_TYPE",8}}},
            {"RankingMethod",{{"RANDOM_VOTE",0}}},
            {"SearchSuggestionType",{{"TIME_GEO_LABEL",0},{"TIME_GEO",1},{"TIME_LABEL",2},
                {"TIME_PEOPLE_GEO_LABEL",3},{"TIME_PEOPLE_GEO",4},{"TIME_PEOPLE_LABEL",5},{"TIME_PEOPLE",6}}},
            {"PhotoRiskStatus",{{"UNIDENTIFIED",0},{"APPROVED",1},{"SUSPICIOUS",2},{"REJECTED",3}}},
            {"AppLinkState",{{"DEFAULT",0},{"HAS_NO_LINK",1},{"HAS_LINK",2}}},
            {"LivePhoto4dStatus",{{"UNIDENTIFIED",0},{"UNSUPPORTED",1},{"SUPPORTED",2},{"USED",3},{"LIVEPHOTO_4D",4}}},
            {"DeepOptimizeState",{{"RUNNING",0},{"COMPLETED",1},{"FAILED",2},{"STOPPED",3},{"INTERRUPTED",4}}},
            {"CoverUriSource",{{"DEFAULT_COVER",0},{"MANUAL_COVER",1}}},
            {"ThumbnailVisibility",{{"INVISIBLE",0},{"VISIBLE",1}}}
        }'''
        for media, manager in ((0, 1), (7, 13)):
            values = lambda text: text.replace('MEDIA_VALUE', str(media)).replace('MANAGER_VALUE', str(manager))
            exercise(values(native) + function, 'RegisterPublicPhotoEnums', values(expected), 100, True)

    def test_photo_wrapper_forwards_only_native_objects(self):
        relative, name, _ = COMPONENTS[2]
        sections = patch_sections(ROOT / 'patches/common' / relative / name)
        old, new = next(values for key, values in sections.items() if key.endswith('.js'))[0][1:]
        additions = [line for line in new if line not in old]
        names = ['AssetSourceType', 'FieldType', 'RankingMethod', 'SearchSuggestionType']
        self.assertEqual(additions, ['  ' + name + ': photoAccessHelper.' + name + ',' for name in names])
        script = r'''
const assert=require('node:assert/strict');
const forward=new Function('photoAccessHelper','return ({'+process.argv[1]+'});');
for(let i=0;i<128;i++) {
 const native={AssetSourceType:{MEDIA:i},FieldType:{YEAR:i},RankingMethod:{RANDOM_VOTE:i},SearchSuggestionType:{TIME_PEOPLE:i}};
 const actual=forward(native);
 for(const name of Object.keys(native))assert.equal(actual[name],native[name]);
 for(const value of Object.values(forward({})))assert.equal(value,undefined);
}
'''
        subprocess.run(['node', '-e', script, '\n'.join(additions)], capture_output=True, check=True)

    def test_exact_component_repeats_and_rejects_unknown_partial_or_symlink_inputs(self):
        for relative, name, _ in COMPONENTS:
            with self.subTest(component=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                component = ROOT / 'patches/common' / relative
                patch = component / name
                write_preimages(root, patch)
                originals = {key: (root / key).read_bytes() for key in patch_sections(patch)}
                subprocess.run(['git', '-C', str(root), 'apply', str(patch)], check=True, capture_output=True)
                repaired = {key: (root / key).read_bytes() for key in originals}
                subprocess.run(['git', '-C', str(root), 'apply', '--reverse', str(patch)], check=True, capture_output=True)
                spec = importlib.util.spec_from_file_location('enum_baseline', component / 'verify_source.py')
                baseline = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(baseline)
                fixture = root / 'fixture'
                copied = fixture / component.relative_to(ROOT)
                shutil.copytree(component, copied)
                shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
                verifier = copied / 'verify_source.py'
                text = verifier.read_text()
                for path, before, after in baseline.FILES:
                    key = baseline.PROJECT + '/' + path
                    text = text.replace(before, hashlib.sha256(originals[key]).hexdigest())
                    text = text.replace(after, hashlib.sha256(repaired[key]).hexdigest())
                verifier.write_text(text)
                argv = ['bash', str(copied / 'apply.sh'), '--source-root', str(root)]
                for _ in range(2):
                    subprocess.run(argv, check=True, capture_output=True)
                    self.assertEqual(repaired, {key: (root / key).read_bytes() for key in repaired})
                if len(originals) > 1:
                    key = next(iter(originals))
                    (root / key).write_bytes(originals[key])
                    snapshot = {key: (root / key).read_bytes() for key in originals}
                    self.assertNotEqual(subprocess.run(argv, capture_output=True).returncode, 0)
                    self.assertEqual(snapshot, {key: (root / key).read_bytes() for key in originals})
                for corrupted in originals:
                    for key, value in repaired.items():
                        (root / key).write_bytes(value)
                    (root / corrupted).write_bytes(b'unknown user source')
                    snapshot = {key: (root / key).read_bytes() for key in originals}
                    self.assertNotEqual(subprocess.run(argv, capture_output=True).returncode, 0)
                    self.assertEqual(snapshot, {key: (root / key).read_bytes() for key in originals})
                key = next(iter(originals))
                outside = root / 'outside'
                outside.write_bytes(originals[key])
                (root / key).unlink()
                (root / key).symlink_to(outside)
                self.assertNotEqual(subprocess.run(argv, capture_output=True).returncode, 0)
                self.assertEqual(outside.read_bytes(), originals[key])

    def test_single_common_plan_and_no_backend_permission_or_callback_changes(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        plan = builder.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0]
        for relative, name, variable in COMPONENTS:
            self.assertEqual(plan.count('bash "${' + variable + '}" --source-root "${OHOS_ROOT}"'), 1)
            text = (ROOT / 'patches/common' / relative / name).read_text()
            self.assertFalse(any(line.startswith('-') and not line.startswith('---') for line in text.splitlines()))
        self.assertLess(plan.index('${PHOTO_PUBLIC_ENUMS_COMPONENT_SCRIPT}'), plan.index('${PHOTO_SEARCH_ENUMS_COMPONENT_SCRIPT}'))

if __name__ == '__main__':
    unittest.main()
