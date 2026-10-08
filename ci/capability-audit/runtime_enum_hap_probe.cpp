// SPDX-License-Identifier: Apache-2.0
// Return only actual runtime properties. SDK expected values never enter here.
#include <napi/native_api.h>
#include <cstddef>

namespace {
napi_value Inspect(napi_env env, napi_callback_info info)
{
    napi_value args[3] = {}, result = nullptr, values = nullptr, statuses = nullptr;
    napi_value types = nullptr, own = nullptr, module = nullptr, enumeration = nullptr;
    size_t argc = 3;
    char moduleName[128] = {}, enumName[128] = {};
    size_t copied = 0;
    uint32_t count = 0, statusIndex = 0, typeIndex = 0, ownIndex = 0;
    napi_create_object(env, &result);
    napi_create_array(env, &values);
    napi_create_array(env, &statuses);
    napi_create_array(env, &types);
    napi_create_array(env, &own);
    auto status = [&](napi_status code) {
        napi_value value = nullptr;
        napi_create_int32(env, code, &value);
        napi_set_element(env, statuses, statusIndex++, value);
        return code == napi_ok;
    };
    auto type = [&](napi_value value, napi_valuetype &kind) {
        bool ok = status(napi_typeof(env, value, &kind));
        napi_value number = nullptr;
        napi_create_int32(env, kind, &number);
        napi_set_element(env, types, typeIndex++, number);
        return ok;
    };
    auto hasOwn = [&](napi_value object, napi_value key) {
        bool present = false;
        bool ok = status(napi_has_own_property(env, object, key, &present));
        napi_value value = nullptr;
        napi_get_boolean(env, present, &value);
        napi_set_element(env, own, ownIndex++, value);
        return ok;
    };
    bool ready = status(napi_get_cb_info(env, info, &argc, args, nullptr, nullptr)) && argc == 3;
    ready = ready && status(napi_get_value_string_utf8(env, args[0], moduleName, sizeof(moduleName), &copied));
    ready = ready && status(napi_get_value_string_utf8(env, args[1], enumName, sizeof(enumName), &copied));
    ready = ready && status(napi_get_array_length(env, args[2], &count)) && count > 0 && count < 512;
    ready = ready && status(napi_load_module(env, moduleName, &module));
    napi_valuetype kind = napi_undefined;
    ready = ready && type(module, kind) && (kind == napi_object || kind == napi_function);
    napi_value enumKey = nullptr;
    ready = ready && status(napi_create_string_utf8(env, enumName, NAPI_AUTO_LENGTH, &enumKey));
    ready = ready && hasOwn(module, enumKey);
    ready = ready && status(napi_get_named_property(env, module, enumName, &enumeration));
    kind = napi_undefined;
    ready = ready && type(enumeration, kind) && (kind == napi_object || kind == napi_function);
    for (uint32_t index = 0; ready && index < count; ++index) {
        napi_value key = nullptr, value = nullptr;
        ready = status(napi_get_element(env, args[2], index, &key));
        ready = ready && hasOwn(enumeration, key);
        ready = ready && status(napi_get_property(env, enumeration, key, &value));
        kind = napi_undefined;
        ready = ready && type(value, kind);
        if (ready) {
            // Preserve undefined/wrong-type observations; host verification rejects them.
            napi_set_element(env, values, index, value);
        }
    }
    bool pending = false;
    napi_is_exception_pending(env, &pending);
    if (pending) {
        napi_value exception = nullptr;
        napi_get_and_clear_last_exception(env, &exception);
    }
    napi_value exception = nullptr;
    napi_get_boolean(env, pending, &exception);
    napi_set_named_property(env, result, "values", values);
    napi_set_named_property(env, result, "statuses", statuses);
    napi_set_named_property(env, result, "types", types);
    napi_set_named_property(env, result, "own", own);
    napi_set_named_property(env, result, "exception", exception);
    return result;
}
napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor method = {"inspect", nullptr, Inspect, nullptr, nullptr, nullptr, napi_default, nullptr};
    napi_define_properties(env, exports, 1, &method);
    return exports;
}
napi_module MODULE = {1, 0, nullptr, Init, "runtimeenumprobe", nullptr, {0}};
}
extern "C" __attribute__((constructor)) void RegisterRuntimeEnumProbe()
{
    napi_module_register(&MODULE);
}
