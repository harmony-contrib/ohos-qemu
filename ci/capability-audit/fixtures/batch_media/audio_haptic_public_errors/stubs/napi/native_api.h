// Controlled external NAPI transport only; production callback/common classes remain real.
#pragma once
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct QaNapiValue {
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
inline napi_status napi_create_int32(napi_env env, int32_t number, napi_value *out) { *out = env->Make(); (*out)->number = number; (*out)->numeric = true; return napi_ok; }
inline napi_status napi_create_string_utf8(napi_env env, const char *text, size_t, napi_value *out) { *out = env->Make(); (*out)->text = text; return napi_ok; }
inline napi_status napi_create_object(napi_env env, napi_value *out) { *out = env->Make(); return napi_ok; }
inline napi_status napi_set_named_property(napi_env, napi_value value, const char *name, napi_value property) { value->properties[name] = property; return napi_ok; }
inline napi_status napi_create_error(napi_env env, napi_value, napi_value message, napi_value *out) { *out = env->Make(); (*out)->properties["message"] = message; return napi_ok; }
inline napi_status napi_reject_deferred(napi_env env, napi_deferred, napi_value value) { env->rejected = value; return napi_ok; }
inline napi_status napi_get_reference_value(napi_env, napi_ref ref, napi_value *out) { *out = ref; return napi_ok; }
inline napi_status napi_call_function(napi_env, napi_value, napi_value function, size_t, const napi_value *, napi_value *) { if (function->function) { function->function(); } return napi_ok; }
inline napi_status napi_send_event(napi_env env, std::function<void()> task, napi_event_priority, const char *) { env->pending.push_back(std::move(task)); return napi_ok; }

namespace OHOS {
struct IPCSkeleton { inline static uint64_t token = 1; static uint64_t GetSelfTokenID() { return token; } };
namespace Security { namespace AccessToken {
using AccessTokenID = uint32_t;
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
