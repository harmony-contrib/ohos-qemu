"""Actual patched error helper under sanitizers; not guest acceptance."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/base/web/webview/business_error'
PATCH = COMPONENT / '0001-use-numeric-codes-on-real-synchronous-BusinessErrors.patch'
CPP = 'base/web/webview/interfaces/kits/napi/common/business_error.cpp'


class WebBusinessErrorTests(unittest.TestCase):
    def test_exact_synchronous_helper_preserves_real_Error_and_numeric_code(self):
        parts = patch_sections(PATCH)[CPP]
        lines = parts[0][2]
        body = '\n'.join(lines[2:lines.index('napi_value BusinessError::CreateError(napi_env env, int32_t err)')])
        throwers = '\n'.join(parts[1][2][:-2])
        source = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { enum Type { STRING, NUMBER, ERROR } type; std::string text; int32_t number=0;
    std::map<std::string, Value *> own; };
using napi_env=void*;
using napi_value=Value*;
constexpr int napi_ok=0, NAPI_AUTO_LENGTH=-1;
int calls=0, fail=-1, throws=0;
Value* thrown=nullptr;
std::vector<std::unique_ptr<Value>> storage;
bool Failed() { return calls++==fail; }
Value* Make(Value::Type type) { storage.push_back(std::make_unique<Value>());
    auto value=storage.back().get(); value->type=type; return value; }
int napi_create_string_utf8(napi_env,const char* text,int,napi_value* out) {
    if(Failed())return 1; *out=Make(Value::STRING); (*out)->text=text; return napi_ok; }
int napi_create_error(napi_env,napi_value code,napi_value message,napi_value* out) {
    if(Failed())return 1; assert(code==nullptr && message->type==Value::STRING);
    *out=Make(Value::ERROR); (*out)->own["message"]=message;
    auto stack=Make(Value::STRING); stack->text="actual Error stack"; (*out)->own["stack"]=stack;
    return napi_ok; }
int napi_create_int32(napi_env,int32_t number,napi_value* out) {
    if(Failed())return 1; *out=Make(Value::NUMBER); (*out)->number=number; return napi_ok; }
int napi_set_named_property(napi_env,napi_value object,const char* name,napi_value value) {
    if(Failed())return 1; object->own[name]=value; return napi_ok; }
int napi_throw(napi_env,napi_value error) { thrown=error; ++throws; return napi_ok; }
std::string GetErrMsgByErrCode(int32_t code) { return "registry:"+std::to_string(code); }
struct BusinessError {
    static void ThrowError(napi_env,int32_t,const std::string&);
    static void ThrowErrorByErrcode(napi_env,int32_t);
    static void ThrowErrorByErrcode(napi_env,int32_t,const std::string&);
};
'''
        main = r'''
int main() {
    for(int32_t code: {401,201,17100001,-123}) for(unsigned mode=0;mode<3;++mode) {
        calls=0; fail=-1; throws=0; thrown=nullptr;
        if(mode==0) BusinessError::ThrowError(nullptr,code,"boundary rejection");
        if(mode==1) BusinessError::ThrowErrorByErrcode(nullptr,code);
        if(mode==2) BusinessError::ThrowErrorByErrcode(nullptr,code,"boundary rejection");
        assert(throws==1 && thrown && thrown->type==Value::ERROR);
        assert(thrown->own.at("code")->type==Value::NUMBER && thrown->own.at("code")->number==code);
        assert(thrown->own.at("name")->text=="BusinessError");
        assert(thrown->own.at("message")->text==(mode==1?GetErrMsgByErrCode(code):"boundary rejection"));
        assert(thrown->own.at("stack")->text=="actual Error stack");
    }
    for(int step=0;step<6;++step) {
        calls=0; fail=step; throws=0; thrown=nullptr;
        BusinessError::ThrowError(nullptr,401,"rejected");
        assert(calls==step+1 && throws==0 && thrown==nullptr);
    }
}
'''
        compile_run(source + body + '\n' + throwers + '\n' + main, language='c++')

    def test_fresh_and_repeat_component_apply_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, PATCH)
            fixture = root / 'fixture-repository'
            component = fixture / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            subprocess.run(command, check=True, capture_output=True)
            candidate = (root / CPP).read_text()
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual((root / CPP).read_text(), candidate)
            self.assertNotIn('napi_throw_error(env', candidate)

    def test_shared_build_plan_patches_before_traversal_and_no_authorization_change(self):
        plan = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        invocation = 'bash "${ARKWEB_BUSINESS_ERROR_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertEqual(plan.count(invocation), 1)
        self.assertIn(invocation, plan.split('apply_qemu_capability_patch_plan() {', 1)[1])
        for forbidden in ('CheckPermission', 'seccomp', 'setuid', 'GrantPermission', 'WebHttpBodyStream'):
            self.assertNotIn(forbidden, PATCH.read_text())
        self.assertIn('three_actual_ArkWeb_BusinessError_TU_objects_NOT_link_or_guest',
                      (ROOT / 'ci/capability-audit/compile_web_business_error.py').read_text())


if __name__ == '__main__':
    unittest.main()
