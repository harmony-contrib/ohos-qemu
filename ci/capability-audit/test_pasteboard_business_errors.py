"""Execute actual native error delivery with NAPI doubles; never guest acceptance."""
import base64
import gzip
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASE = Path('foundation/distributeddatamgr/pasteboard')
COMPONENT = ROOT/'patches/common'/BASE/'read_business_errors'
PARENT = ROOT/'patches/common'/BASE/'read_permission_errors'
FILES = ('interfaces/kits/napi/src/napi_systempasteboard.cpp',
         'interfaces/kits/napi/src/async_call.cpp', 'interfaces/kits/napi/include/async_call.h')
FIXTURES = Path(__file__).with_name('fixtures')


class PasteboardBusinessErrors(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for relative in FILES:
            path = self.root/BASE/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            fixture = FIXTURES/('pasteboard_business_'+path.name+'.gz.b64')
            path.write_bytes(gzip.decompress(base64.b64decode(fixture.read_text())))

    def apply(self, component=COMPONENT, check=True):
        return subprocess.run(['bash', str(component/'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True, check=check)

    def test_complete_successor_and_parent_repeat_preserve_exact_bytes(self):
        self.apply()
        before = {name: (self.root/BASE/name).read_bytes() for name in FILES}
        self.apply(PARENT)
        self.apply()
        self.assertEqual(before, {name: (self.root/BASE/name).read_bytes() for name in FILES})

    def test_unknown_or_partial_successor_never_mutates_other_files(self):
        self.apply()
        for relative in FILES:
            path = self.root/BASE/relative
            original = path.read_bytes()
            path.write_bytes(original+b'\n// unknown edit\n')
            before = {name: (self.root/BASE/name).read_bytes() for name in FILES}
            self.assertNotEqual(self.apply(check=False).returncode, 0)
            self.assertNotEqual(self.apply(PARENT, check=False).returncode, 0)
            self.assertEqual(before, {name: (self.root/BASE/name).read_bytes() for name in FILES})
            path.write_bytes(original)

    def test_real_async_completion_preserves_legacy_and_numeric_promise_callback_codes(self):
        self.apply()
        header = (self.root/BASE/FILES[2]).read_text()
        header = header.replace('#include "napi/native_api.h"', '').replace(
            '#include "napi/native_node_api.h"', '')
        source = (self.root/BASE/FILES[1]).read_text()
        start = source.index('void AsyncCall::OnComplete(')
        end = source.index('\nvoid AsyncCall::DeleteContext(', start)
        completion = source[start:end]
        harness = r'''
#include <cassert>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
enum napi_status { napi_ok, napi_generic_failure };
struct Value {
    enum Kind { Undefined, String, Number, Error } kind=Undefined;
    std::string text;
    int32_t number=0;
    Value* code=nullptr;
};
using napi_env=void*;using napi_value=Value*;using napi_ref=void*;
using napi_callback_info=void*;using napi_deferred=void*;using napi_async_work=void*;
constexpr size_t NAPI_AUTO_LENGTH=static_cast<size_t>(-1);
Value* delivered=nullptr;bool resolved=false;int completions=0;
napi_status napi_get_undefined(napi_env,napi_value* out) { *out=new Value;return napi_ok; }
napi_status napi_create_string_utf8(napi_env,const char* text,size_t,napi_value* out) {
    *out=new Value;(*out)->kind=Value::String;(*out)->text=text;return napi_ok;
}
napi_status napi_create_int32(napi_env,int32_t number,napi_value* out) {
    *out=new Value;(*out)->kind=Value::Number;(*out)->number=number;return napi_ok;
}
napi_status napi_create_error(napi_env,napi_value code,napi_value message,napi_value* out) {
    assert(code==nullptr || code->kind==Value::String);
    *out=new Value;(*out)->kind=Value::Error;(*out)->text=message->text;(*out)->code=code;return napi_ok;
}
napi_status napi_set_named_property(napi_env,napi_value value,const char* name,napi_value property) {
    assert(std::string(name)=="code");value->code=property;return napi_ok;
}
napi_status napi_resolve_deferred(napi_env,napi_deferred,napi_value value) {
    delivered=value;resolved=true;return napi_ok;
}
napi_status napi_reject_deferred(napi_env,napi_deferred,napi_value value) {
    delivered=value;resolved=false;return napi_ok;
}
napi_status napi_get_reference_value(napi_env,napi_ref ref,napi_value* out) {
    *out=reinterpret_cast<napi_value>(ref);return napi_ok;
}
napi_status napi_call_function(napi_env,napi_value,napi_value,size_t argc,napi_value* argv,napi_value*) {
    assert(argc==2);delivered=argv[0];resolved=argv[0]->kind==Value::Undefined;return napi_ok;
}
#define PASTEBOARD_HILOGD(...) ((void)0)
#define PASTEBOARD_HILOGI(...) ((void)0)
#define private public
__HEADER__
#undef private
namespace OHOS::MiscServicesNapi {
__COMPLETION__
void AsyncCall::DeleteContext(napi_env,AsyncContext* context) { completions++;delete context; }
}
using OHOS::MiscServicesNapi::AsyncCall;
void deliver(bool callback,bool numeric,int32_t code,bool resetToLegacy,bool success=false) {
    auto value=std::make_shared<AsyncCall::Context>();
    value->SetBusinessErrInfo(code,"captured permission boundary");
    if (!numeric || resetToLegacy) value->SetErrInfo(code,"captured permission boundary");
    value->SetAction(AsyncCall::Context::OutputAction([success](napi_env,napi_value* output) {
        *output=nullptr;return success?napi_ok:napi_generic_failure;
    }));
    auto context=new AsyncCall::AsyncContext;context->ctx=value;
    if (callback) context->callback=reinterpret_cast<void*>(1);
    else context->defer=reinterpret_cast<void*>(1);
    int before=completions;
    AsyncCall::OnComplete(nullptr,napi_ok,context);
    assert(completions==before+1 && resolved==success);
    if (success) assert(delivered->kind==Value::Undefined);
    else {
        assert(delivered->kind==Value::Error && delivered->text=="captured permission boundary");
        if (numeric && !resetToLegacy)
            assert(delivered->code->kind==Value::Number && delivered->code->number==code);
        else assert(delivered->code->kind==Value::String && delivered->code->text==std::to_string(code));
    }
}
int main() {
    for (bool callback:{false,true}) {
        for (int32_t code:{201,27787277}) {
            deliver(callback,true,code,false);
            deliver(callback,false,code,false);
            deliver(callback,true,code,true);
        }
        deliver(callback,true,201,false,true);
    }
}
'''.replace('__HEADER__', header).replace('__COMPLETION__', completion)
        self.execute(harness)

    def test_actual_sync_permission_throw_has_numeric_code_and_other_results_survive(self):
        self.apply()
        source = (self.root/BASE/FILES[0]).read_text()
        start = source.index('napi_value SystemPasteboardNapi::GetDataSync(')
        end = source.index('\nnapi_value SystemPasteboardNapi::SetDataSync', start)
        method = source[start:end]
        tail = method[method.index('    int32_t ret = (value != nullptr)'):method.rfind('\n}')]
        harness = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <string>
enum class PasteboardError { E_OK=0,PERMISSION_VERIFICATION_ERROR=71,TIMEOUT_ERROR=72,NO_DATA=73,OTHER=74 };
enum class JSErrorCode { NO_PERMISSION=201 };
enum class EventReportResult { EVENT_REPORT_SUCCESS,EVENT_REPORT_FAIL };
struct DfxAppEvent { void SetEvent(const char*,int32_t,EventReportResult) {} };
struct Value { enum Kind { String,Number,Error } kind;int number;std::string text;Value* code=nullptr; };
using napi_env=void*;using napi_value=Value*;constexpr int napi_ok=0;constexpr size_t NAPI_AUTO_LENGTH=-1;
napi_value thrown=nullptr;
int napi_create_string_utf8(napi_env,const char* text,size_t,napi_value* out) {
    *out=new Value{Value::String,0,text};return napi_ok;
}
int napi_create_error(napi_env,napi_value code,napi_value message,napi_value* out) {
    assert(code==nullptr);*out=new Value{Value::Error,0,message->text};return napi_ok;
}
int napi_create_int32(napi_env,int32_t code,napi_value* out) { *out=new Value{Value::Number,code,{}};return napi_ok; }
int napi_set_named_property(napi_env,napi_value error,const char* name,napi_value code) {
    assert(std::string(name)=="code");error->code=code;return napi_ok;
}
int napi_throw(napi_env,napi_value error) { thrown=error;return napi_ok; }
#define NAPI_CALL(env,expression) do { assert((expression)==napi_ok); } while(false)
napi_value read(PasteboardError result) {
    napi_env env=nullptr;napi_value instance=reinterpret_cast<Value*>(1);
    auto value=std::make_shared<int32_t>(static_cast<int>(result));
    auto processorEvent=std::make_shared<DfxAppEvent>();
__TAIL__
}
int main() {
    for (auto result:{PasteboardError::E_OK,PasteboardError::PERMISSION_VERIFICATION_ERROR,
                     PasteboardError::TIMEOUT_ERROR,PasteboardError::NO_DATA,PasteboardError::OTHER}) {
        thrown=nullptr;auto output=read(result);
        if (result==PasteboardError::PERMISSION_VERIFICATION_ERROR) {
            assert(output==nullptr && thrown && thrown->kind==Value::Error);
            assert(thrown->code->kind==Value::Number && thrown->code->number==201);
            assert(!thrown->text.empty());
        } else assert(output!=nullptr && thrown==nullptr);
    }
}
'''.replace('__TAIL__', tail)
        self.execute(harness)

    def execute(self, source):
        path = self.root/'error-shape.cpp'
        path.write_text(source)
        binary = self.root/'error-shape'
        subprocess.run(['c++', '-std=c++17', str(path), '-o', str(binary)],
                       capture_output=True, text=True, check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
