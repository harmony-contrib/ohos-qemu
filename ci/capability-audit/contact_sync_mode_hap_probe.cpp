// SPDX-License-Identifier: Apache-2.0
// Read actual public module members; do not return SDK expectations.
#include <napi/native_api.h>
#include <cstddef>

namespace {
template<size_t Count>
napi_value InspectEnum(napi_env env, const char *moduleName, const char *enumName, const char *const (&names)[Count])
{
    napi_value result = nullptr, module = nullptr, mode = nullptr;
    napi_value values = nullptr, statuses = nullptr, types = nullptr, own = nullptr;
    napi_create_object(env, &result);
    napi_create_array(env, &values);
    napi_create_array(env, &statuses);
    napi_create_array(env, &types);
    napi_create_array(env, &own);
    uint32_t statusIndex = 0, ownIndex = 0, typeIndex = 0;
    auto status = [&](napi_status code) {
        napi_value value = nullptr;
        napi_create_int32(env, code, &value);
        napi_set_element(env, statuses, statusIndex++, value);
    };
    auto type = [&](napi_value value) {
        napi_valuetype kind = napi_undefined;
        status(napi_typeof(env, value, &kind));
        napi_value number = nullptr;
        napi_create_int32(env, kind, &number);
        napi_set_element(env, types, typeIndex++, number);
    };
    auto hasOwn = [&](napi_value object, const char *name) {
        napi_value key = nullptr, value = nullptr;
        bool present = false;
        status(napi_create_string_utf8(env, name, NAPI_AUTO_LENGTH, &key));
        status(napi_has_own_property(env, object, key, &present));
        napi_get_boolean(env, present, &value);
        napi_set_element(env, own, ownIndex++, value);
    };
    status(napi_load_module(env, moduleName, &module));
    type(module);
    hasOwn(module, enumName);
    status(napi_get_named_property(env, module, enumName, &mode));
    type(mode);
    for (uint32_t index = 0; index < Count; ++index) {
        napi_value value = nullptr;
        hasOwn(mode, names[index]);
        status(napi_get_named_property(env, mode, names[index], &value));
        type(value);
        napi_valuetype kind = napi_undefined;
        if (value != nullptr && napi_typeof(env, value, &kind) == napi_ok && kind == napi_number) {
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
napi_value Inspect(napi_env env, napi_callback_info)
{
    const char *names[] = {"MODE_INCREMENTAL", "MODE_CLOUD_BASED"};
    return InspectEnum(env, "@ohos.contact", "ContactSyncMode", names);
}
napi_value InspectAudio(napi_env env, napi_callback_info)
{
    const char *names[] = {"UNBLOCKED", "BLOCKED"};
    return InspectEnum(env, "@ohos.multimedia.audio", "DeviceBlockStatus", names);
}
napi_value InspectPhoto(napi_env env, napi_callback_info)
{
    const char *names[] = {"COMPATIBLE_ASSET"};
    return InspectEnum(env, "@ohos.file.photoAccessHelper", "FusionAssetType", names);
}
napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor methods[] = {
        {"inspect", nullptr, Inspect, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"inspectAudio", nullptr, InspectAudio, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"inspectPhoto", nullptr, InspectPhoto, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    napi_define_properties(env, exports, 3, methods);
    return exports;
}
napi_module MODULE = {1, 0, nullptr, Init, "contactsyncmodeprobe", nullptr, {0}};
}
extern "C" __attribute__((constructor)) void RegisterContactSyncModeProbe()
{
    napi_module_register(&MODULE);
}
