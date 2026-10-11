"""Execute actual dynamic methods and abort helper, not the guest drag backend."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'patches/common/foundation/arkui/ace_engine'


class SpringLoadingSemanticsTests(unittest.TestCase):
    def test_real_context_methods_begin_validation_and_cancel_omission(self):
        patch = BASE / 'spring_loading_semantics/0001-enforce-begin-config-and-cancel-optional-fields.patch'
        actual = '\n'.join('\n'.join(after) for hunks in patch_sections(patch).values()
                           for _, _, after in hunks)
        compile_run(r'''
#include <cassert>
#include <climits>
#include <cmath>
#include <map>
#include <memory>
#include <string>
#include <type_traits>
#include <utility>
enum class DragSpringLoadingState { BEGIN, UPDATE, END, CANCEL };
namespace NG {
constexpr int DEFAULT_STILL_TIME_LIMIT=500, DEFAULT_UPDATE_INTERVAL=100;
constexpr int DEFAULT_UPDATE_NOTIFY_COUNT=3, DEFAULT_UPDATE_TO_FINISH_INTERVAL=100;
struct DragSpringLoadingConfiguration {
    int stillTimeLimit=500, updateInterval=100, updateNotifyCount=3, updateToFinishInterval=100;
};
}
int allocations=0, summaries=0;
struct JSVal { bool object=false, undefined=false; virtual ~JSVal()=default;
    bool IsObject() const { return object; }
    static JSVal Undefined() { JSVal v; v.undefined=true; return v; } };
template<class T> class JSRef;
struct JSObject : JSVal {
    std::map<std::string,double> numbers;
    std::map<std::string,std::string> strings;
    std::map<std::string,std::shared_ptr<JSVal>> objects;
    JSObject() { object=true; ++allocations; }
    template<class T> void SetProperty(const char* key,T value) {
        if constexpr(std::is_same_v<T,std::string>) strings[key]=value; else numbers[key]=value; }
    template<class T> void SetPropertyObject(const char* key,JSRef<T> value) { objects[key]=value; }
    template<class T> T GetPropertyValue(const char* key,T fallback) {
        return numbers.count(key) ? static_cast<T>(numbers[key]) : fallback; }
};
template<class T> class JSRef : public std::shared_ptr<T> {
public:
    using std::shared_ptr<T>::shared_ptr;
    JSRef(std::shared_ptr<T> p) : std::shared_ptr<T>(std::move(p)) {}
    template<class U> JSRef(JSRef<U> p) : std::shared_ptr<T>(std::move(p)) {}
    static JSRef<T> New() { return std::make_shared<T>(); }
    template<class U> static JSRef<T> Cast(JSRef<U> p) {
        return std::static_pointer_cast<T>(static_cast<std::shared_ptr<U>>(p)); }
};
struct JSCallbackInfo {
    JSRef<JSObject> input=JSRef<JSObject>::New();
    mutable std::shared_ptr<JSVal> returned;
    mutable bool gotUndefined=false;
    JSRef<JSObject> operator[](int) const { return input; }
    void SetReturnValue(JSVal value) const { gotUndefined=value.undefined; returned.reset(); }
    void SetReturnValue(JSRef<JSVal> value) const { returned=value; gotUndefined=false; }
};
template<class T> std::shared_ptr<T> MakeRefPtr() { return std::make_shared<T>(); }
struct Context {
    DragSpringLoadingState state=DragSpringLoadingState::BEGIN;
    std::shared_ptr<NG::DragSpringLoadingConfiguration> config=MakeRefPtr<NG::DragSpringLoadingConfiguration>();
    bool aborted=false;
    DragSpringLoadingState GetState() const { return state; }
    int GetSummary() { return 17; }
    std::string GetExtraInfos() { return "real-owned-nonce"; }
    const auto& GetDragSpringLoadingConfiguration() { return config; }
    void SetDragSpringLoadingConfiguration(std::shared_ptr<NG::DragSpringLoadingConfiguration> p) {
        config=std::move(p); }
    void SetSpringLoadingAborted() { aborted=true; }
};
using napi_value=std::shared_ptr<JSVal>;
struct UdmfClient {
    static UdmfClient* GetInstance() { static UdmfClient client; return &client; }
    napi_value TransformSummary(int summary) { assert(summary==17); ++summaries; return JSRef<JSObject>::New(); }
};
struct JsConverter { static JSRef<JSVal> ConvertNapiValueToJsVal(napi_value v) { return v; } };
#define CHECK_NULL_VOID(value) do { if(!(value)) return; } while(0)
#define TAG_LOGD(...) ((void)0)
struct JsDragSpringLoadingContext {
    Context* context_=nullptr;
    void GetDragInfos(const JSCallbackInfo&);
    void SetDragInfos(const JSCallbackInfo&);
    void GetCurrentConfig(const JSCallbackInfo&);
    void SetCurrentConfig(const JSCallbackInfo&);
    void Abort(const JSCallbackInfo&);
    void UpdateConfiguration(const JSCallbackInfo&);
};
''' + actual + r'''
int main() {
    Context native; JsDragSpringLoadingContext value{&native};
    for(int repeat=0;repeat<128;++repeat) {
        for(auto state : {DragSpringLoadingState::BEGIN,DragSpringLoadingState::UPDATE,
                          DragSpringLoadingState::END,DragSpringLoadingState::CANCEL}) {
            native.state=state;
            JSCallbackInfo args;
            int before=allocations, calls=summaries;
            value.GetDragInfos(args);
            if(state==DragSpringLoadingState::CANCEL) {
                assert(args.gotUndefined && !args.returned && allocations==before && summaries==calls);
            } else {
                auto result=std::static_pointer_cast<JSObject>(args.returned);
                assert(!args.gotUndefined && result->objects.count("dataSummary")==1);
                assert(result->strings.at("extraInfos")=="real-owned-nonce" && summaries==calls+1);
            }
            before=allocations;
            value.GetCurrentConfig(args);
            if(state==DragSpringLoadingState::CANCEL) {
                assert(args.gotUndefined && !args.returned && allocations==before);
            } else {
                auto result=std::static_pointer_cast<JSObject>(args.returned);
                assert(result->numbers.at("stillTimeLimit")==native.config->stillTimeLimit);
                assert(result->numbers.at("updateInterval")==native.config->updateInterval);
                assert(result->numbers.at("updateNotifyCount")==native.config->updateNotifyCount);
                assert(result->numbers.at("updateToFinishInterval")==native.config->updateToFinishInterval);
            }
            auto prior=native.config;
            args.input->numbers={{"stillTimeLimit",11.9},{"updateInterval",22.9},
                {"updateNotifyCount",0.9},{"updateToFinishInterval",33.9}};
            value.UpdateConfiguration(args);
            if(state==DragSpringLoadingState::BEGIN) {
                assert(native.config!=prior && native.config->stillTimeLimit==11);
                assert(native.config->updateInterval==22 && native.config->updateNotifyCount==0);
                assert(native.config->updateToFinishInterval==33);
            } else assert(native.config==prior);
        }
    }
    native.state=DragSpringLoadingState::BEGIN;
    JSCallbackInfo invalid;
    invalid.input->numbers={{"stillTimeLimit",NAN},{"updateInterval",-1},
        {"updateNotifyCount",static_cast<double>(INT32_MAX)+1},{"updateToFinishInterval",INFINITY}};
    value.UpdateConfiguration(invalid);
    assert(native.config->stillTimeLimit==500 && native.config->updateInterval==100);
    assert(native.config->updateNotifyCount==3 && native.config->updateToFinishInterval==100);
    auto prior=native.config;
    invalid.input->object=false;
    value.UpdateConfiguration(invalid); assert(native.config==prior);
    value.Abort(invalid); assert(native.aborted);
    value.context_=nullptr;
    value.GetDragInfos(invalid); value.GetCurrentConfig(invalid);
    value.UpdateConfiguration(invalid); value.Abort(invalid);
}
''', language='c++')

    def test_actual_abort_helper_cancels_timer_without_reset_or_notification(self):
        patch = BASE / 'spring_loading_lifecycle/0001-abort-hover-without-cancel-notification.patch'
        sections = patch_sections(patch)
        header = '\n'.join('\n'.join(after) for name, hunks in sections.items()
                           if name.endswith('.h') for _, _, after in hunks)
        helper = '    void AbortWithoutNotify()' + header.split('    void AbortWithoutNotify()', 1)[1].split(
            '\n    bool IsInSpringLoadingState()', 1)[0]
        compile_run(r'''
#include <cassert>
#include <initializer_list>
enum class DragDropSpringLoadingState { IDLE, BEGIN, UPDATE, END, CANCEL };
struct Timer { bool pending=true; int cancelled=0; void Cancel() { pending=false; ++cancelled; } };
struct Machine {
    Timer timer_;
    DragDropSpringLoadingState currentState_=DragDropSpringLoadingState::BEGIN;
    bool isWaitingForIdleFinish_=true;
    int currentNotifySequence_=4, currentUpdateNotifyCount_=2, callbackCount=3;
''' + helper + r'''
};
int main() {
    for(int repeat=0;repeat<128;++repeat) {
        for(auto state : {DragDropSpringLoadingState::BEGIN,DragDropSpringLoadingState::UPDATE}) {
            Machine machine; machine.currentState_=state;
            machine.AbortWithoutNotify();
            assert(!machine.timer_.pending && machine.timer_.cancelled==1);
            assert(machine.currentState_==DragDropSpringLoadingState::END && !machine.isWaitingForIdleFinish_);
            assert(machine.callbackCount==3 && machine.currentNotifySequence_==4 && machine.currentUpdateNotifyCount_==2);
        }
    }
}
''', language='c++')
        for name, hunks in sections.items():
            if name.endswith('.cpp'):
                changed = '\n'.join('\n'.join(after) for _, _, after in hunks)
                aborted = changed.split('if (context->IsSpringLoadingAborted()) {')[1].split('return;')[0]
                self.assertIn('stateMachine->AbortWithoutNotify();', aborted)
                self.assertNotIn('RequestStatusTransition', aborted)
                self.assertNotIn('ResetMachine', aborted)


if __name__ == '__main__': unittest.main()
