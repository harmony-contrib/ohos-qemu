#!/usr/bin/env python3
"""Execute the patched RTT removal/queue functions against a bounded N-API/UV harness.

The fixture contains original fixed-source slices; every production diff hunk is
applied to it before extracting functions. This tests C++ lifecycle behavior, not
an IMS/modem backend or an OHOS package.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/common/base/telephony/call_manager/api26_rtt_lifecycle/0001-honor-RTT-listener-removal-and-queued-event-lifetime.patch'
FIXTURE = Path(__file__).parent / 'fixtures/batch_location/rtt_before.json'


def patched_sources():
    files = json.loads(FIXTURE.read_text())['files']
    sections = re.split(r'^--- a/base/telephony/call_manager/frameworks/js/napi/', PATCH.read_text(), flags=re.M)[1:]
    for section in sections:
        name = section.splitlines()[0]
        hunks = re.split(r'^@@[^\n]*\n', section, flags=re.M)[1:]
        for hunk in hunks:
            old = ''.join(line if line == '\n' else line[1:] for line in hunk.splitlines(keepends=True) if line == '\n' or line.startswith((' ', '-')))
            new = ''.join(line if line == '\n' else line[1:] for line in hunk.splitlines(keepends=True) if line == '\n' or line.startswith((' ', '+')))
            if files[name].count(old) != 1:
                raise AssertionError(f'Production hunk is not unique in fixture: {name}')
            files[name] = files[name].replace(old, new, 1)
    return files


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1] + '\n'
    raise AssertionError(signature)


PREAMBLE = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <vector>
struct Value { bool function = true; };
struct Env;
using napi_env = Env*;
using napi_value = Value*;
struct Ref { napi_env env; napi_value value; bool live = true; };
using napi_ref = Ref*;
using napi_status = int;
constexpr int napi_ok = 0, napi_function = 1;
using Hook = void (*)(void*);
struct Env { bool alive = true; std::vector<std::pair<Hook,void*>> hooks; std::vector<std::unique_ptr<Ref>> refs; };
struct Info { std::vector<napi_value> args; };
using napi_callback_info = Info*;
Value undefinedValue;
int errors = 0, deliveries = 0, queueFailure = 0, cleanupFailure = 0;
std::function<void()> duringDelivery;
struct uv_loop_s {};
struct uv_work_t { void* data = nullptr; };
struct Job { uv_work_t* work; void (*done)(uv_work_t*,int32_t); };
std::vector<Job> jobs;
constexpr int uv_qos_default = 0;
int napi_get_uv_event_loop(napi_env env, uv_loop_s** loop) { assert(env->alive); static uv_loop_s l; *loop = &l; return 0; }
int uv_queue_work_with_qos(uv_loop_s*,uv_work_t* work,void (*)(uv_work_t*),void (*done)(uv_work_t*,int32_t),int) {
    if (queueFailure) return -1;
    jobs.push_back({work,done}); return 0;
}
void drain(int status = 0) { auto queued = std::move(jobs); jobs.clear(); for (auto job:queued) job.done(job.work,status); }
int napi_get_reference_value(napi_env env,napi_ref ref,napi_value* value) {
    assert(env->alive && ref && ref->live && ref->env == env); *value = ref->value; return 0;
}
int napi_delete_reference(napi_env env,napi_ref ref) { assert(env->alive && ref->env == env && ref->live); ref->live = false; return 0; }
int napi_strict_equals(napi_env env,napi_value lhs,napi_value rhs,bool* equal) { assert(env->alive); *equal = lhs == rhs; return 0; }
int napi_add_env_cleanup_hook(napi_env env,Hook hook,void* data) {
    assert(env->alive); if (cleanupFailure) return -1; env->hooks.push_back({hook,data}); return 0;
}
int napi_remove_env_cleanup_hook(napi_env env,Hook hook,void* data) {
    assert(env->alive); auto it=std::find(env->hooks.begin(),env->hooks.end(),std::make_pair(hook,data));
    assert(it!=env->hooks.end()); env->hooks.erase(it); return 0;
}
int napi_throw_error(napi_env,const char*,const char*) { ++errors; return 0; }
int liveRefs(const Env& env) { int result=0; for(const auto& ref:env.refs) result+=ref->live; return result; }
void closeEnv(Env& env) {
    auto hooks = std::move(env.hooks); env.hooks.clear(); for(auto hook:hooks) hook.first(hook.second);
    for(auto& ref:env.refs) ref->live=false; env.alive=false;
}
napi_ref makeRef(napi_env env,napi_value value) { env->refs.push_back(std::make_unique<Ref>(Ref{env,value,true})); return env->refs.back().get(); }
struct EventCallback { napi_env env = nullptr; napi_ref thisVar = nullptr; napi_ref callbackRef = nullptr; };
EventCallback listener(Env& env,Value& value) { return {&env,makeRef(&env,&undefinedValue),makeRef(&env,&value)}; }
struct RttEvent {};
struct RttError {};
namespace AppExecFwk { struct PacMap {}; }
constexpr int TELEPHONY_SUCCESS = 0, CALL_ERR_CALLBACK_NOT_EXIST = -1, TELEPHONY_ERR_LOCAL_PTR_NULL = -2, TELEPHONY_ERROR = -3;
#define TELEPHONY_LOGE(...) ((void)0)
#define TELEPHONY_LOGI(...) ((void)0)
#define TELEPHONY_LOGD(...) ((void)0)
#define NAPI_VERSION 2
'''

CLASS = r'''
class NapiCallAbilityCallback {
public:
    void RegisterRttModifyIndCallback(EventCallback);
    void UnRegisterRttModifyIndCallback(napi_env,napi_value = nullptr);
    void RegisterRttErrCauseCallback(EventCallback);
    void UnRegisterRttErrCauseCallback(napi_env,napi_value = nullptr);
    void RegisterRttCallMessageCallback(EventCallback);
    void UnRegisterRttCallMessageCallback(napi_env,napi_value = nullptr);
    int32_t ReportRttCallEventInfo(const RttEvent&);
    int32_t ReportRttCallErrorInfo(const RttError&);
    int32_t ReportRttCallMessageInfo(AppExecFwk::PacMap&);
    static void ReportRttCallEventInfoWork(uv_work_t*,int32_t);
    static void ReportRttCallErrorInfoWork(uv_work_t*,int32_t);
    static void ReportRttCallMessageWork(uv_work_t*,int32_t);
    static int32_t delivered(EventCallback cb) {
        napi_value fn; napi_get_reference_value(cb.env,cb.callbackRef,&fn); ++deliveries;
        if (duringDelivery) { auto action=std::move(duringDelivery); duringDelivery=nullptr; action(); }
        return 0;
    }
    static int32_t ReportRttCallEventInfo(RttEvent&,EventCallback cb) { return delivered(cb); }
    static int32_t ReportRttCallErrorInfo(RttError&,EventCallback cb) { return delivered(cb); }
    static int32_t ReportRttCallMessage(AppExecFwk::PacMap&,EventCallback cb) { return delivered(cb); }
FIELDS
};
NapiCallAbilityCallback instance;
template<class T> struct DelayedSingleton { static T* GetInstance() { return &instance; } };
constexpr int ONLY_ONE_VALUE=1,TWO_VALUE_LIMIT=2,ARRAY_INDEX_FIRST=0,TELEPHONY_ERR_PERMISSION_ERR=-5,JS_ERROR_TELEPHONY_PERMISSION_DENIED=201;
const char* OBSERVER_OFF_JS_PERMISSION_ERROR_STRING="permission";
struct JsError { int errorCode=8400003; const char* errorMessage="error"; };
struct NapiUtil {
    static void ThrowParameterError(napi_env) { ++errors; }
    static void ThrowError(napi_env,int,const char*) { ++errors; }
    static JsError ConverErrorMessageForJs(int) { return {}; }
};
struct NapiCallManagerUtils {
    static bool MatchValueType(napi_env,napi_value value,int) { return value && value->function; }
    static napi_value CreateUndefined(napi_env) { return &undefinedValue; }
};
#define GET_PARAMS(env,info,limit) size_t argc=std::min(size_t(limit),info->args.size()); napi_value argv[limit]={}; for(size_t i=0;i<argc;++i) argv[i]=info->args[i]
class NapiCallManager {
public:
    static int registerStatus_;
    static napi_value OffRttModifyInd(napi_env,napi_callback_info);
    static napi_value OffRttErrCause(napi_env,napi_callback_info);
    static napi_value OffReceiveRttMessage(napi_env,napi_callback_info);
};
int NapiCallManager::registerStatus_=0;
'''

MAIN = r'''
int main() {
    using Register=void (NapiCallAbilityCallback::*)(EventCallback);
    using Remove=napi_value (*)(napi_env,napi_callback_info);
    Register registers[]={&NapiCallAbilityCallback::RegisterRttModifyIndCallback,&NapiCallAbilityCallback::RegisterRttErrCauseCallback,&NapiCallAbilityCallback::RegisterRttCallMessageCallback};
    Remove removes[]={NapiCallManager::OffRttModifyInd,NapiCallManager::OffRttErrCause,NapiCallManager::OffReceiveRttMessage};
    for(int group=0;group<3;++group) {
        Env env,other; Value a,b,unknown,bad{false};
        auto add=[&](Env& owner,Value& value) { (instance.*registers[group])(listener(owner,value)); };
        auto off=[&](Env& owner,std::vector<napi_value> args) { Info info{args}; return removes[group](&owner,&info); };
        auto report=[&]() {
            if(group==0) { RttEvent event; return instance.ReportRttCallEventInfo(event); }
            if(group==1) { RttError event; return instance.ReportRttCallErrorInfo(event); }
            AppExecFwk::PacMap event; return instance.ReportRttCallMessageInfo(event);
        };
        int calls=deliveries;
        add(env,a); add(env,a); assert(liveRefs(env)==2); // idempotent subscription releases duplicate refs
        add(env,b); assert(liveRefs(env)==4);
        off(env,{&unknown}); assert(liveRefs(env)==4); // wrong callback does not remove another listener
        report(); drain(); assert(deliveries==calls+2);
        report(); off(env,{&a}); assert(liveRefs(env)==2); drain(); assert(deliveries==calls+3);
        report(); assert(off(env,{})==&undefinedValue); assert(liveRefs(env)==0); drain(); assert(deliveries==calls+3);
        off(env,{}); assert(liveRefs(env)==0); // repeated removal is harmless
        add(env,a); report(); off(env,{&a}); add(env,a); // old queued registration must not target its replacement
        drain(); assert(deliveries==calls+3); report(); drain(); assert(deliveries==calls+4);
        add(other,a); off(env,{}); assert(liveRefs(env)==0 && liveRefs(other)==2);
        report(); drain(); assert(deliveries==calls+5); // removal is scoped to its owning environment
        report(); closeEnv(other); drain(); assert(deliveries==calls+5); // env exit suppresses queued work
        add(env,a); duringDelivery=[&] { off(env,{}); }; report(); drain(); assert(liveRefs(env)==0); // callback can unsubscribe itself
        int previous=errors;
        off(env,{&bad}); off(env,{&a,&b}); assert(errors==previous+2);
        add(env,a); NapiCallManager::registerStatus_=TELEPHONY_ERR_PERMISSION_ERR; off(env,{});
        assert(liveRefs(env)==2 && errors==previous+3); NapiCallManager::registerStatus_=0; off(env,{});
        add(env,a); queueFailure=1; assert(report()==TELEPHONY_ERROR); queueFailure=0; off(env,{}); assert(liveRefs(env)==0);
        add(env,a); report(); drain(-1); off(env,{}); assert(liveRefs(env)==0);
        cleanupFailure=1; add(env,a); cleanupFailure=0; assert(liveRefs(env)==0 && env.hooks.empty());
        closeEnv(env); assert(jobs.empty());
    }
    std::cout << "RTT 3 event families: optional/identity/multiple listeners/environment/queue/reentry/reference/error cases passed\n";
}
'''


class RttLifecycleTest(unittest.TestCase):
    def test_component_applies_idempotently(self):
        with tempfile.TemporaryDirectory(prefix='batch-location-apply-') as directory:
            root = Path(directory)
            files = json.loads(FIXTURE.read_text())['files']
            prefix = 'base/telephony/call_manager/frameworks/js/napi/'
            for name, source in files.items():
                path = root / (prefix + name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            component = PATCH.parent
            fixture = root / 'fixture'
            shutil.copytree(component, fixture / component.relative_to(ROOT))
            shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
            args = ['bash', str(fixture / component.relative_to(ROOT) / 'apply.sh'), '--source-root', str(root)]
            subprocess.run(args, check=True, capture_output=True)
            applied = {name: (root / (prefix + name)).read_text() for name in files}
            self.assertEqual(patched_sources(), applied)
            subprocess.run(args, check=True, capture_output=True)
            self.assertEqual(applied, {name: (root / (prefix + name)).read_text() for name in files})
            shutil.rmtree(root / '.ohos-qemu-patches')
            subprocess.run(args, check=True, capture_output=True)
            self.assertEqual(applied, {name: (root / (prefix + name)).read_text() for name in files})

    def test_execute_patched_lifecycle(self):
        files = patched_sources()
        callback = files['src/napi_call_ability_callback.cpp']
        types = files['include/napi_call_manager_types.h']
        structs = ''.join(function(types, 'struct ' + name + ' {').rstrip() + ';\n' for name in [
            'RttCallbackRegistration', 'RttCallEvtWork', 'RttCallErrorWork', 'RttCallMessageWork'])
        header = files['include/napi_call_ability_callback.h']
        fields = '\n'.join(line for line in header.splitlines() if re.search(
            r'(std::vector<std::shared_ptr<RttCallbackRegistration>>|std::mutex rttCall)', line))
        bodies = ''.join(function(callback, 'static void ' + name + '(') for name in [
            'CleanupRttCallback', 'DeleteRttCallbackReferences', 'RegisterRttCallback', 'UnregisterRttCallback'])
        for suffix in ['RttModifyInd', 'RttErrCause', 'RttCallMessage']:
            for verb in ['Register', 'UnRegister']:
                bodies += function(callback, f'void NapiCallAbilityCallback::{verb}{suffix}Callback(')
        for signature in [
            'int32_t NapiCallAbilityCallback::ReportRttCallEventInfo(const',
            'int32_t NapiCallAbilityCallback::ReportRttCallErrorInfo(const',
            'int32_t NapiCallAbilityCallback::ReportRttCallMessageInfo(',
            'void NapiCallAbilityCallback::ReportRttCallEventInfoWork(',
            'void NapiCallAbilityCallback::ReportRttCallErrorInfoWork(',
            'void NapiCallAbilityCallback::ReportRttCallMessageWork(',
        ]:
            bodies += function(callback, signature)
        for suffix in ['RttModifyInd', 'RttErrCause', 'ReceiveRttMessage']:
            bodies += function(files['src/napi_call_manager.cpp'], f'napi_value NapiCallManager::Off{suffix}(')
        source = PREAMBLE + structs + CLASS.replace('FIELDS', fields) + bodies + MAIN
        with tempfile.TemporaryDirectory(prefix='batch-location-rtt-') as directory:
            cpp, exe = Path(directory) / 'test.cpp', Path(directory) / 'test'
            cpp.write_text(source)
            subprocess.run(['clang++', '-std=c++17', '-pthread', '-fsanitize=address,undefined', '-g', str(cpp), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
