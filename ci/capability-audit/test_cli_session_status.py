"""Checked CLI enum registration, not shell execution/session provider proof."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/ability/ability_runtime/api26_cli_session_status'
PATCH = COMPONENT / '0001-export-existing-session-status-protocol.patch'


class CliSessionStatusTests(unittest.TestCase):
    def test_exact_helper_all_values_and_napi_failures_without_partial_publication(self):
        body = next(iter(patch_sections(PATCH).values()))[0][2]
        end = body.index('napi_value JSCliManagerInit(napi_env env, napi_value exportObj)')
        function = '\n'.join(body[:end])
        source = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value {std::string text; std::map<std::string,Value*> own;};
using napi_env=void*; using napi_value=Value*;
enum napi_status {napi_ok=0,napi_generic_failure=9};
std::vector<std::unique_ptr<Value>> storage;
int failure=0,calls=0;
Value* Make() {storage.push_back(std::make_unique<Value>());return storage.back().get();}
napi_status Step(){++calls;return calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_create_object(napi_env,Value** value){auto s=Step();if(s==napi_ok)*value=Make();return s;}
napi_status napi_create_string_utf8(napi_env,const char* text,size_t,Value** value){auto s=Step();
 if(s==napi_ok){*value=Make();(*value)->text=text;}return s;}
napi_status napi_set_named_property(napi_env,Value* object,const char* key,Value* value){auto s=Step();
 if(s==napi_ok)assert(object->own.emplace(key,value).second);return s;}
#define NAPI_AUTO_LENGTH static_cast<size_t>(-1)
#define NAPI_CALL(env,call) do {if((call)!=napi_ok)return nullptr;} while(0)
'''
        main = r'''
int main(){
 const std::map<std::string,std::string> expected={
  {"RUNNING","running"},{"COMPLETED","completed"},{"FAILED","failed"}};
 for(int repeat=0;repeat<128;++repeat){
  for(failure=0;failure<=8;++failure){
   storage.clear();calls=0;auto exports=Make();
   // Existing exports must survive success and every failed registration.
   auto sentinel=Make();exports->own.emplace("original",sentinel);
   auto result=RegisterPublicSessionStatus(nullptr,exports);
   assert(failure?result==nullptr:result==exports);
   assert(calls==(failure?failure:8));
   assert(exports->own.at("original")==sentinel);
   assert(exports->own.size()==(failure?1:2));
   if(!failure){
    const auto& members=exports->own.at("SessionStatus")->own;
    assert(members.size()==expected.size());
    for(const auto& member:expected)assert(members.at(member.first)->text==member.second);
   }
  }
 }
}
'''
        compile_run(source + function + main, language='c++')

    def test_initializer_checks_registration_before_wrapper_ownership(self):
        before, after = next(iter(patch_sections(PATCH).values()))[1][1:]
        added = [line for line in after if line not in before]
        self.assertEqual(added, ['    NAPI_ASSERT(env, RegisterPublicSessionStatus(env, exportObj) != nullptr, "failed to create session status object");'])
        self.assertEqual([line for line in after if line not in added], before)
        self.assertLess(after.index(added[0]), after.index('    std::unique_ptr<JSCliManager> jsCliManager = std::make_unique<JSCliManager>();'))

    def test_marker_free_component_repeated_application_on_both_line_endings(self):
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

    def test_common_pretraversal_plan_changes_no_session_or_permission_behavior(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        invocation = 'bash "${CLI_SESSION_STATUS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertEqual(builder.count(invocation), 1)
        self.assertIn(invocation, builder.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0])
        self.assertFalse(any(line.startswith('-') and not line.startswith('---') for line in PATCH.read_text().splitlines()))
        self.assertEqual(set(patch_sections(PATCH)), {'foundation/ability/ability_runtime/cli_tool_framework/frameworks/js/napi/cli_tool_manager/src/js_cli_manager.cpp'})


if __name__ == '__main__':
    unittest.main()
