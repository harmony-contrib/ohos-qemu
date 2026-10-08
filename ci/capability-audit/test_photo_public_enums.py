"""Exact photo registration and native-to-public boundary fixtures; not guest/provider proof."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/api26_photo_enums'
PATCH = COMPONENT / '0001-register-public-photo-enums-and-normalize-cover-source.patch'
WRAPPER_PATCH = COMPONENT / '0002-forward-public-cover-and-thumbnail-enums.patch'


def function(name):
    for hunks in patch_sections(PATCH).values():
        for _, _, lines in hunks:
            for i, line in enumerate(lines):
                if line.startswith('static ') and (name + '(') in line:
                    return '\n'.join(lines[i:lines.index('}', i) + 1])
    raise AssertionError('exact patched function missing')


class PhotoPublicEnumTests(unittest.TestCase):
    def test_public_wrapper_forwards_real_native_objects_and_never_synthesizes_members(self):
        added = [line[1:] for line in WRAPPER_PATCH.read_text().splitlines()
                 if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(added, ['  CoverUriSource: photoAccessHelper.CoverUriSource,',
                                 '  ThumbnailVisibility: photoAccessHelper.ThumbnailVisibility,'])
        script = r'''
const assert=require('node:assert/strict');
const forward=new Function('photoAccessHelper','return ({'+process.argv[1]+'});');
for(let i=0;i<128;i++) {
 const native={CoverUriSource:{DEFAULT_COVER:i,MANUAL_COVER:i+1},ThumbnailVisibility:{INVISIBLE:i,VISIBLE:i+1}};
 const actual=forward(native);
 assert.equal(actual.CoverUriSource,native.CoverUriSource);
 assert.equal(actual.ThumbnailVisibility,native.ThumbnailVisibility);
 assert.equal(actual.CoverUriSource.DEFAULT_COVER,i);
 assert.equal(actual.ThumbnailVisibility.VISIBLE,i+1);
}
assert.equal(forward({}).CoverUriSource,undefined);
assert.equal(forward({}).ThumbnailVisibility,undefined);
'''
        subprocess.run(['node', '-e', script, '\n'.join(added)], capture_output=True, check=True)

    def test_every_member_every_napi_failure_and_repeated_initialization(self):
        source = r"""
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
enum class PhotoRiskStatus:int32_t { UNIDENTIFIED=0, APPROVED=1, SUSPICIOUS=2, REJECTED=3 };
enum class LivePhoto4dStatusType:int32_t {
 TYPE_UNIDENTIFIED=0, TYPE_UNSUPPORTED=1, TYPE_SUPPORTED=2, TYPE_USED=3, TYPE_LIVEPHOTO_4D=4 };
enum class DeepOptimizeSpaceState:int32_t { RUNNING=0, COMPLETED=1, FAILED=2, STOPPED=3, INTERRUPTED=4 };
enum CoverUriSource:int32_t { DEFAULT_COVER=0, MANUAL_CLOUD_COVER=1, MANUAL_LOCAL_COVER=2, MANUAL_WAIT_PULL_COVER=3 };
enum ThumbnailVisibility:int32_t { INVISIBLE=0, VISIBLE=1 };
const std::vector<std::string> appLinkStateEnum {"DEFAULT", "HAS_NO_LINK", "HAS_LINK"};
struct Value { int32_t number=0; std::map<std::string, Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status { napi_ok=0, napi_generic_failure=9 };
int calls=0, failure=0;
std::vector<std::unique_ptr<Value>> storage;
Value* Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
napi_status Step() { return ++calls==failure ? napi_generic_failure : napi_ok; }
napi_status napi_create_object(napi_env, Value** value) {
 auto status=Step(); if(status==napi_ok) *value=Make(); return status; }
napi_status napi_create_int32(napi_env, int32_t number, Value** value) {
 auto status=Step(); if(status==napi_ok) { *value=Make(); (*value)->number=number; } return status; }
napi_status napi_set_named_property(napi_env, Value* object, const char* name, Value* value) {
 auto status=Step(); if(status==napi_ok) assert(object->own.emplace(name,value).second); return status; }
"""
        main = r"""
int main() {
 const std::map<std::string, std::vector<std::string>> expected {
  {"PhotoRiskStatus", {"UNIDENTIFIED","APPROVED","SUSPICIOUS","REJECTED"}},
  {"AppLinkState", {"DEFAULT","HAS_NO_LINK","HAS_LINK"}},
  {"LivePhoto4dStatus", {"UNIDENTIFIED","UNSUPPORTED","SUPPORTED","USED","LIVEPHOTO_4D"}},
  {"DeepOptimizeState", {"RUNNING","COMPLETED","FAILED","STOPPED","INTERRUPTED"}},
  {"CoverUriSource", {"DEFAULT_COVER","MANUAL_COVER"}},
  {"ThumbnailVisibility", {"INVISIBLE","VISIBLE"}},
 };
 for(unsigned repeat=0; repeat<128; ++repeat) {
  for(failure=0; failure<=54; ++failure) {
   auto exports=Make(); calls=0;
   auto status=RegisterPublicPhotoEnums(nullptr,exports);
   if(failure) { assert(status==napi_generic_failure && calls==failure); continue; }
   assert(status==napi_ok && calls==54 && exports->own.size()==expected.size());
   for(const auto &item:expected) {
    auto object=exports->own.at(item.first); assert(object->own.size()==item.second.size());
    for(size_t i=0; i<item.second.size(); ++i)
     assert(object->own.at(item.second[i])->number==static_cast<int32_t>(i));
   }
   assert(!exports->own.at("LivePhoto4dStatus")->own.count("FOURD_LIVEPHOTO"));
   assert(!exports->own.at("CoverUriSource")->own.count("MANUAL_LOCAL_COVER"));
  }
 }
}
"""
        compile_run(source + function('RegisterPublicPhotoEnums') + main, language='c++')

    def test_manual_cover_mapping_is_only_a_js_boundary_and_unknown_values_survive(self):
        source = r"""
#include <cassert>
#include <cstdint>
#include <climits>
#include <initializer_list>
enum CoverUriSource:int32_t { DEFAULT_COVER=0, MANUAL_CLOUD_COVER=1, MANUAL_LOCAL_COVER=2, MANUAL_WAIT_PULL_COVER=3 };
"""
        main = r"""
int main() {
 for(unsigned repeat=0; repeat<2048; ++repeat) {
  assert(PublicCoverUriSource(0)==0);
  assert(PublicCoverUriSource(1)==1 && PublicCoverUriSource(2)==1 && PublicCoverUriSource(3)==1);
  for(auto unknown:{INT32_MIN,-1,4,INT32_MAX}) assert(PublicCoverUriSource(unknown)==unknown);
 }
}
"""
        compile_run(source + function('PublicCoverUriSource') + main, language='c++')
        text = PATCH.read_text()
        self.assertIn('CHECK_COND_LOG_THROW_RETURN_RET(env, MediaLibraryNapiUtils::IsSystemApp()', text)
        self.assertIn('PublicCoverUriSource(obj->GetCoverUriSource())', text)
        self.assertNotIn('SetCoverUriSource', text)

    def test_component_applies_twice_and_initializer_propagates_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, PATCH)
            write_preimages(root, WRAPPER_PATCH)
            for _ in range(2):
                subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)],
                               check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(PATCH)], check=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(WRAPPER_PATCH)], check=True)
        self.assertIn('if (RegisterPublicPhotoEnums(env, exports) != napi_ok) {\n+        return nullptr;', PATCH.read_text())


if __name__ == '__main__':
    unittest.main()
