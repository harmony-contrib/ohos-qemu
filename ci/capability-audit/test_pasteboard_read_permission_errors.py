"""Execute the patched native branches and preserve exact source/ABI boundaries."""
import base64
import gzip
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT/'patches/common/foundation/distributeddatamgr/pasteboard/read_permission_errors'
RELATIVE = Path('foundation/distributeddatamgr/pasteboard/interfaces/kits/napi/src/napi_systempasteboard.cpp')
FIXTURE = Path(__file__).with_name('fixtures')/'napi_systempasteboard_permission.cpp.gz.b64'


class PasteboardReadPermissionErrors(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name);self.source = self.root/RELATIVE
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(gzip.decompress(base64.b64decode(FIXTURE.read_text())))
    def apply(self,check=True):
        return subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(self.root)],
            capture_output=True,text=True,check=check)
    def test_exact_application_and_repeat_are_idempotent(self):
        self.apply();before=self.source.read_bytes();self.apply();self.assertEqual(before,self.source.read_bytes())
        spec=importlib.util.spec_from_file_location('pasteboard_permission_baseline',COMPONENT/'verify_source.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(hashlib.sha256(before).hexdigest(),module.FILES[0][2])
        self.assertTrue(module.validate(self.root,require_patched=True))
    def test_unknown_edits_are_rejected_without_mutation(self):
        self.source.write_bytes(self.source.read_bytes()+b'\n');before=self.source.read_bytes()
        self.assertNotEqual(self.apply(False).returncode,0);self.assertEqual(self.source.read_bytes(),before)
    def test_actual_async_and_sync_branch_errors_and_unchanged_results(self):
        self.apply();text=self.source.read_text()
        start=text.index('napi_value SystemPasteboardNapi::GetData(')
        end=text.index('\nvoid SystemPasteboardNapi::SetDataCommon',start);method=text[start:end]
        start=method.index('    auto exec = ');end=method.index('\n    // 0:',start)
        asynchronous=method[start:end]
        start=text.index('napi_value SystemPasteboardNapi::GetDataSync(')
        end=text.index('\nnapi_value SystemPasteboardNapi::SetDataSync',start);method=text[start:end]
        tail=method[method.index('    int32_t ret = (value != nullptr)'):method.rfind('\n}')]
        harness=r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <string>
constexpr int napi_ok=0, napi_generic_failure=1;
enum class PasteboardError { E_OK=0, PERMISSION_VERIFICATION_ERROR=71, TASK_PROCESSING=27787277,
                            TIMEOUT_ERROR=72, NO_DATA=73, OTHER_ERROR=74 };
enum class JSErrorCode { NO_PERMISSION=201 };
enum class EventReportResult { EVENT_REPORT_SUCCESS, EVENT_REPORT_FAIL };
struct PasteData { bool populated=false; };
struct AsyncCall { struct Context {}; };
struct GetContextInfo : AsyncCall::Context {
    std::shared_ptr<PasteData> pasteData=std::make_shared<PasteData>();
    int status=napi_generic_failure, error=0;
    void SetErrInfo(int32_t code,const std::string&) { error=code; }
};
struct DfxAppEvent {
    int calls=0,ret=-1;EventReportResult result=EventReportResult::EVENT_REPORT_FAIL;
    void SetEvent(const char*,int32_t code,EventReportResult outcome) { calls++;ret=code;result=outcome; }
};
struct PasteboardClient {
    int result=0;static PasteboardClient* GetInstance() { static PasteboardClient value;return &value; }
    int GetPasteData(PasteData& data) { data.populated=result==0;return result; }
};
int sync_error=0;
bool CheckExpression(void*,bool valid,JSErrorCode code,const char*) {
    if (!valid) sync_error=static_cast<int>(code);return valid;
}
#define PASTEBOARD_HILOGD(...) ((void)0)
#define PASTEBOARD_CHECK_AND_RETURN_LOGE(value,...) if (!(value)) return
void asynchronous_case(PasteboardError code) {
    auto context=std::make_shared<GetContextInfo>();auto processorEvent=std::make_shared<DfxAppEvent>();
    PasteboardClient::GetInstance()->result=static_cast<int32_t>(code);
__ASYNC__
    exec(context.get());
    assert(processorEvent->calls==1 && processorEvent->ret==static_cast<int>(code));
    if (code==PasteboardError::PERMISSION_VERIFICATION_ERROR)
        assert(context->status==napi_generic_failure && context->error==201 && !context->pasteData->populated);
    else if (code==PasteboardError::TASK_PROCESSING)
        assert(context->status==napi_generic_failure && context->error==27787277);
    else assert(context->status==napi_ok && context->error==0);
    assert(context->pasteData->populated==(code==PasteboardError::E_OK));
}
void* sync_case(PasteboardError code) {
    void* env=nullptr;void* instance=reinterpret_cast<void*>(1);
    auto value=std::make_shared<int32_t>(static_cast<int>(code));
    auto processorEvent=std::make_shared<DfxAppEvent>();
__SYNC__
}
int main() {
    for (auto code:{PasteboardError::E_OK,PasteboardError::PERMISSION_VERIFICATION_ERROR,
                   PasteboardError::TASK_PROCESSING,PasteboardError::NO_DATA,PasteboardError::OTHER_ERROR}) {
        asynchronous_case(code);sync_error=0;auto value=sync_case(code);
        if (code==PasteboardError::PERMISSION_VERIFICATION_ERROR) assert(value==nullptr && sync_error==201);
        else assert(value!=nullptr && sync_error==0);
    }
}
'''.replace('__ASYNC__',asynchronous).replace('__SYNC__',tail)
        path=self.root/'branches.cpp';path.write_text(harness);binary=self.root/'branches'
        subprocess.run(['c++','-std=c++17',str(path),'-o',str(binary)],capture_output=True,text=True,check=True)
        subprocess.run([str(binary)],check=True)


if __name__=='__main__':unittest.main()
