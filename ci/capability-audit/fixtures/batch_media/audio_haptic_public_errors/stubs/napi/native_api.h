// Controlled external NAPI transport only; production callback/common classes remain real.
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct QaNapiEnv;
struct QaNapiValue;
using QaNapiCallback = QaNapiValue *(*)(QaNapiEnv *, void *);
struct QaNapiValue {
    int kind = 0;
    double realNumber = 0;
    bool boolean = false;
    void *native = nullptr;
    QaNapiCallback constructor = nullptr;
    std::map<std::string, QaNapiCallback> methods;
    int32_t number = 0;
    bool numeric = false;
    std::string text;
    std::map<std::string, QaNapiValue *> properties;
    std::function<void()> function;
};
struct QaNapiEnv {
    std::vector<std::unique_ptr<QaNapiValue>> values;
    std::vector<std::function<void()>> pending;
    QaNapiValue *rejected = nullptr;
    QaNapiValue *resolved = nullptr;
    QaNapiValue *thrown = nullptr;
    QaNapiValue *thisValue = nullptr;
    std::vector<QaNapiValue *> arguments;
    std::function<void(void *)> beforeComplete;
    int resolvedCount = 0, rejectedCount = 0, createdWork = 0, queuedWork = 0, deletedWork = 0;
    QaNapiValue *Make() { values.push_back(std::make_unique<QaNapiValue>()); return values.back().get(); }
    void Drain() { auto queue = std::move(pending); pending.clear(); for (auto &task : queue) { task(); } }
};
using napi_env = QaNapiEnv *;
using napi_value = QaNapiValue *;
using napi_ref = QaNapiValue *;
using napi_deferred = void *;
using napi_async_work = void *;
using napi_callback_info = void *;
using napi_handle_scope = void *;
enum napi_status { napi_ok, napi_generic_failure };
enum napi_event_priority { napi_eprio_high };
constexpr size_t NAPI_AUTO_LENGTH = static_cast<size_t>(-1);
inline napi_status napi_delete_reference(napi_env, napi_ref) { return napi_ok; }
inline napi_status napi_create_reference(napi_env, napi_value value, uint32_t, napi_ref *out) { *out = value; return napi_ok; }
inline napi_status napi_open_handle_scope(napi_env env, napi_handle_scope *out) { *out = env; return napi_ok; }
inline napi_status napi_close_handle_scope(napi_env, napi_handle_scope) { return napi_ok; }
inline napi_status napi_create_int32(napi_env env, int32_t number, napi_value *out) { *out = env->Make(); (*out)->number = number; (*out)->numeric = true; (*out)->realNumber = number; (*out)->kind = 3; return napi_ok; }
inline napi_status napi_create_string_utf8(napi_env env, const char *text, size_t, napi_value *out) { *out = env->Make(); (*out)->text = text; (*out)->kind = 4; return napi_ok; }
inline napi_status napi_create_object(napi_env env, napi_value *out) { *out = env->Make(); (*out)->kind = 6; return napi_ok; }
inline napi_status napi_set_named_property(napi_env, napi_value value, const char *name, napi_value property) { value->properties[name] = property; return napi_ok; }
inline napi_status napi_create_error(napi_env env, napi_value, napi_value message, napi_value *out) { *out = env->Make(); (*out)->properties["message"] = message; return napi_ok; }
inline napi_status napi_reject_deferred(napi_env env, napi_deferred, napi_value value) { env->rejected = value; ++env->rejectedCount; return napi_ok; }
inline napi_status napi_get_reference_value(napi_env, napi_ref ref, napi_value *out) { *out = ref; return napi_ok; }
inline napi_status napi_call_function(napi_env, napi_value, napi_value function, size_t, const napi_value *, napi_value *) { if (function->function) { function->function(); } return napi_ok; }
inline napi_status napi_send_event(napi_env env, std::function<void()> task, napi_event_priority, const char *) { env->pending.push_back(std::move(task)); return napi_ok; }

namespace OHOS {
struct IPCSkeleton { inline static uint64_t token = 1; static uint64_t GetSelfTokenID() { return token; } };
namespace Security { namespace AccessToken {
using AccessTokenID = uint32_t;
using FullTokenID = uint64_t;
struct TokenIdKit { inline static bool system = true; static bool IsSystemAppByFullTokenID(FullTokenID) { return system; } };
constexpr int PERMISSION_GRANTED = 0;
struct AccessTokenKit {
    inline static int result = 0;
    inline static int queries = 0;
    static int VerifyAccessToken(AccessTokenID, const std::string &permission) {
        ++queries; return permission == "ohos.permission.VIBRATE" ? result : -1;
    }
};
} }
}

// Additional controlled external transport for the complete actual player CPP.
// This does not redefine AudioHapticPlayerAsyncContext or its native result type.
using napi_callback = QaNapiCallback;
using napi_finalize = void (*)(napi_env, void *, void *);
enum napi_valuetype { napi_undefined=0, napi_null=1, napi_boolean=2, napi_number=3,
                     napi_string=4, napi_symbol=5, napi_object=6, napi_function=7 };
enum napi_property_attributes { napi_default=0 };
struct napi_property_descriptor {
    const char *utf8name; napi_value name; napi_callback method; napi_callback getter;
    napi_callback setter; napi_value value; napi_property_attributes attributes; void *data;
};
#define DECLARE_NAPI_FUNCTION(name, func) {name, nullptr, func, nullptr, nullptr, nullptr, napi_default, nullptr}
struct QaAsyncWork {
    void (*execute)(napi_env,void *);
    void (*complete)(napi_env,napi_status,void *);
    void *data;
};
inline napi_status napi_get_undefined(napi_env env,napi_value *out) { *out=env->Make(); return napi_ok; }
inline napi_status napi_resolve_deferred(napi_env env,napi_deferred,napi_value value) {
    env->resolved=value; ++env->resolvedCount; return napi_ok;
}
inline napi_status napi_create_promise(napi_env env,napi_deferred *deferred,napi_value *out) {
    *deferred=env; *out=env->Make(); (*out)->kind=napi_object; return napi_ok;
}
inline napi_status napi_get_cb_info(napi_env env,napi_callback_info,size_t *argc,napi_value *argv,napi_value *self,void **) {
    if (argc) {
        if (argv) for (size_t i=0;i<std::min(*argc,env->arguments.size());++i) argv[i]=env->arguments[i];
        *argc=env->arguments.size();
    }
    if (self) *self=env->thisValue;
    return napi_ok;
}
inline napi_status napi_unwrap(napi_env,napi_value self,void **out) {
    if (!self) return napi_generic_failure;
    *out=self->native; return napi_ok;
}
inline napi_status napi_wrap(napi_env,napi_value self,void *native,napi_finalize,void *,napi_ref *) {
    self->native=native; return napi_ok;
}
inline napi_status napi_define_class(napi_env env,const char *,size_t,napi_callback constructor,void *,
    size_t count,const napi_property_descriptor *properties,napi_value *out) {
    *out=env->Make(); (*out)->kind=napi_function; (*out)->constructor=constructor;
    for (size_t i=0;i<count;++i) (*out)->methods[properties[i].utf8name]=properties[i].method;
    return napi_ok;
}
inline napi_status napi_new_instance(napi_env env,napi_value ctor,size_t count,const napi_value *args,napi_value *out) {
    if (!ctor || !ctor->constructor) return napi_generic_failure;
    auto savedSelf=env->thisValue; auto savedArgs=env->arguments;
    auto object=env->Make(); object->kind=napi_object; object->methods=ctor->methods;
    env->thisValue=object; env->arguments.clear();
    if (count) env->arguments.assign(args,args+count);
    auto result=ctor->constructor(env,nullptr);
    env->thisValue=savedSelf; env->arguments=std::move(savedArgs);
    *out=result; return result ? napi_ok : napi_generic_failure;
}
inline napi_status napi_create_async_work(napi_env env,napi_value,napi_value,
    void (*execute)(napi_env,void *),void (*complete)(napi_env,napi_status,void *),void *data,napi_async_work *out) {
    *out=new QaAsyncWork{execute,complete,data}; ++env->createdWork; return napi_ok;
}
inline napi_status napi_queue_async_work(napi_env env,napi_async_work opaque) {
    auto work=static_cast<QaAsyncWork *>(opaque); ++env->queuedWork;
    env->pending.push_back([env,work] {
        work->execute(env,work->data);
        if (env->beforeComplete) env->beforeComplete(work->data);
        work->complete(env,napi_ok,work->data); // actual completion deletes work/data
    });
    return napi_ok;
}
inline napi_status napi_delete_async_work(napi_env env,napi_async_work work) {
    delete static_cast<QaAsyncWork *>(work); ++env->deletedWork; return napi_ok;
}
inline napi_status napi_typeof(napi_env,napi_value value,napi_valuetype *out) {
    *out=value ? (value->function ? napi_function : static_cast<napi_valuetype>(value->kind)) : napi_undefined;
    return napi_ok;
}
inline napi_status napi_get_boolean(napi_env env,bool value,napi_value *out) {
    *out=env->Make(); (*out)->kind=napi_boolean; (*out)->boolean=value; return napi_ok;
}
inline napi_status napi_get_value_bool(napi_env,napi_value value,bool *out) {
    if (!value || value->kind!=napi_boolean) return napi_generic_failure;
    *out=value->boolean; return napi_ok;
}
inline napi_status napi_get_value_int32(napi_env,napi_value value,int32_t *out) {
    if (!value || !value->numeric) return napi_generic_failure;
    *out=value->number; return napi_ok;
}
inline napi_status napi_get_value_double(napi_env,napi_value value,double *out) {
    if (!value || !value->numeric) return napi_generic_failure;
    *out=value->realNumber; return napi_ok;
}
inline napi_status napi_get_value_string_utf8(napi_env,napi_value value,char *out,size_t size,size_t *count) {
    if (!value || value->kind!=napi_string) return napi_generic_failure;
    *count=value->text.size();
    if (out && size) { size_t n=std::min(size-1,value->text.size()); std::memcpy(out,value->text.data(),n); out[n]='\0'; *count=n; }
    return napi_ok;
}
inline napi_status napi_throw_error(napi_env env,const char *code,const char *message) {
    napi_value text=nullptr; napi_create_string_utf8(env,message,NAPI_AUTO_LENGTH,&text);
    napi_create_error(env,nullptr,text,&env->thrown);
    if (code) { napi_value property=nullptr; napi_create_string_utf8(env,code,NAPI_AUTO_LENGTH,&property); napi_set_named_property(env,env->thrown,"code",property); }
    return napi_ok;
}
