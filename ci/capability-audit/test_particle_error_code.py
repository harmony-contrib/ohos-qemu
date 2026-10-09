"""FA registration host boundaries; not a substitute for real FA/Stage guests."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/ability/ability_runtime/particle_error_code'
PATCH = COMPONENT / '0001-export-fa-invalid-parameter.patch'


class ParticleErrorCodeTests(unittest.TestCase):
    def test_each_registration_failure_and_exact_single_sdk_member(self):
        hunks = next(iter(patch_sections(PATCH).values()))
        lines = hunks[0][2]
        start = lines.index('static napi_status RegisterParticleErrorCode(napi_env env, napi_value exports)')
        function = '\n'.join(lines[start:lines.index('}', start) + 1])
        compile_run(r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { int32_t number=0; std::map<std::string,Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status { napi_ok=0, napi_generic_failure=9 };
int calls=0,failure=0;
std::vector<std::unique_ptr<Value>> storage;
Value* Make(){storage.push_back(std::make_unique<Value>());return storage.back().get();}
napi_status Step(){return ++calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_create_object(napi_env,Value** value){
 auto status=Step();if(status==napi_ok)*value=Make();return status;}
napi_status napi_create_int32(napi_env,int32_t number,Value** value){
 auto status=Step();if(status==napi_ok){*value=Make();(*value)->number=number;}return status;}
napi_status napi_set_named_property(napi_env,Value* object,const char* name,Value* value){
 auto status=Step();if(status==napi_ok)assert(object->own.emplace(name,value).second);return status;}
''' + function + r'''
int main(){
 for(int repeat=0;repeat<128;++repeat)for(failure=0;failure<=4;++failure){
  calls=0;auto exports=Make();auto existing=Make();exports->own.emplace("existing",existing);
  auto status=RegisterParticleErrorCode(nullptr,exports);
  assert(exports->own.at("existing")==existing);
  if(failure){assert(status==napi_generic_failure && calls==failure);
   assert(exports->own.size()==1 && !exports->own.count("ErrorCode"));continue;}
  assert(status==napi_ok && calls==4 && exports->own.size()==2);
  auto object=exports->own.at("ErrorCode");assert(object->own.size()==1);
  assert(object->own.at("INVALID_PARAMETER")->number==-1);
 }
}
''', language='c++')

    def test_idempotent_lf_crlf_and_preserved_initializers(self):
        for crlf in (False, True):
            with self.subTest(crlf=crlf), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_preimages(root, PATCH)
                source = root / next(iter(patch_sections(PATCH)))
                if crlf:
                    source.write_bytes(source.read_bytes().replace(b'\n', b'\r\n'))
                for _ in range(2):
                    result = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                text = source.read_text()
                for name in ('ParticleAbilityInit', 'ContextPermissionInit', 'DataAbilityHelperInit'):
                    self.assertEqual(text.count(name + '(env, exports);'), 1)
                self.assertIn('if (RegisterParticleErrorCode(env, exports) != napi_ok) {\n        return nullptr;', text)

    def test_both_profiles_use_shared_recipe_and_no_stage_edits(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('bash "${PARTICLE_ERROR_CODE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"', recipe)
        self.assertEqual(list(patch_sections(PATCH)), [
            'foundation/ability/ability_runtime/frameworks/js/napi/particleAbility/native_module.cpp'])


if __name__ == '__main__':
    unittest.main()
