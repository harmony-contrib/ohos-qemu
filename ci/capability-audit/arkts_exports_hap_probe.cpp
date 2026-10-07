// SPDX-License-Identifier: Apache-2.0
// Actual public NAPI module loading/reflection; no service/permission bypass.
#include <napi/native_api.h>
#include <cstdint>
#include <cstring>

namespace {
void Number(napi_env env, napi_value object, const char *name, int32_t number)
{
    napi_value value = nullptr;
    napi_create_int32(env, number, &value);
    napi_set_named_property(env, object, name, value);
}

bool Exception(napi_env env)
{
    bool pending = false;
    napi_is_exception_pending(env, &pending);
    if (pending) {
        napi_value exception = nullptr;
        napi_get_and_clear_last_exception(env, &exception);
    }
    return pending;
}

void Boolean(napi_env env, napi_value object, const char *name, bool flag)
{
    napi_value value = nullptr;
    napi_get_boolean(env, flag, &value);
    napi_set_named_property(env, object, name, value);
}

struct EnumMember {
    const char *name;
    int32_t value;
};

bool CheckMembers(napi_env env, napi_value object, const EnumMember *members, size_t count)
{
    for (size_t index = 0; index < count; ++index) {
        napi_value key = nullptr, value = nullptr;
        bool own = false;
        int32_t actual = 0;
        if (napi_create_string_utf8(env, members[index].name, NAPI_AUTO_LENGTH, &key) != napi_ok ||
            napi_has_own_property(env, object, key, &own) != napi_ok || !own ||
            napi_get_property(env, object, key, &value) != napi_ok ||
            napi_get_value_int32(env, value, &actual) != napi_ok || actual != members[index].value) {
            Exception(env);
            return false;
        }
    }
    return !Exception(env);
}

bool CheckAccessibilityEnum(napi_env env, napi_value object, const char *name)
{
    static constexpr EnumMember source[] = {
        {"DEFAULT", 1}, {"ADDED_FROM_ACCESSIBILITY_VIRTUAL_NODE", 2},
        {"UPDATED_FROM_ACCESSIBILITY_VIRTUAL_NODE", 3},
    };
    static constexpr EnumMember focus[] = {
        {"NOT_SUPPORTED", -1}, {"SEARCH_SUCCESS", 0}, {"SEARCH_SUCCESS_NEXT_BYPASS_DESCENDANTS", 1},
        {"SEARCH_FAILURE", 2}, {"SEARCH_FAILURE_IN_CHILD_TREE", 3}, {"SEARCH_FAILURE_LOST_NODE", 4},
        {"SEARCH_NEXT", 5}, {"DOUBLE_CHECK_CHILD_PROPERTY", 6},
        {"DOUBLE_CHECK_CHILD_PROPERTY_AND_GET_LAST", 7}, {"SEARCH_FAILURE_IN_SCROLL", 8},
    };
    static constexpr EnumMember virtualNode[] = {
        {"SUCCESS", 0}, {"ACCESSIBILITY_ELEMENT_NOT_EXIST", 1}, {"CANNOT_MODIFY_ROOT_NODE", 2},
        {"ACCESSIBILITY_PROPERTY_IS_EMPTY", 3}, {"ALLOCATE_ID_FAILED", 4},
        {"VIRTUAL_NODE_PARAMETER_IS_EMPTY", 5}, {"INTERNAL_ERROR", 6}, {"VIRTUAL_NODE_NOT_SUPPORTED", 7},
    };
    if (std::strcmp(name, "AccessibilitySourceType") == 0) {
        return CheckMembers(env, object, source, sizeof(source) / sizeof(source[0]));
    }
    if (std::strcmp(name, "FocusMoveResultCode") == 0) {
        return CheckMembers(env, object, focus, sizeof(focus) / sizeof(focus[0]));
    }
    if (std::strcmp(name, "OperateVirtualNodeResult") == 0) {
        return CheckMembers(env, object, virtualNode, sizeof(virtualNode) / sizeof(virtualNode[0]));
    }
    return false;
}

bool IsAccessibilityEnum(const char *module, const char *name)
{
    return std::strcmp(module, "@ohos.accessibility") == 0 &&
        (std::strcmp(name, "AccessibilitySourceType") == 0 ||
        std::strcmp(name, "FocusMoveResultCode") == 0 ||
        std::strcmp(name, "OperateVirtualNodeResult") == 0);
}

napi_value Inspect(napi_env env, napi_callback_info info)
{
    size_t argc = 1;
    napi_value argv[1] = {nullptr};
    bool array = false;
    uint32_t count = 0;
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 1 ||
        napi_is_array(env, argv[0], &array) != napi_ok || !array ||
        napi_get_array_length(env, argv[0], &count) != napi_ok || count == 0 || count > 128) {
        napi_throw_type_error(env, nullptr, "require a bounded actual SDK-module list");
        return nullptr;
    }
    napi_value results = nullptr;
    napi_create_array_with_length(env, count, &results);
    for (uint32_t index = 0; index < count; ++index) {
        napi_value name = nullptr;
        char moduleName[256] = {};
        size_t length = 0;
        if (napi_get_element(env, argv[0], index, &name) != napi_ok ||
            napi_get_value_string_utf8(env, name, moduleName, sizeof(moduleName), &length) != napi_ok ||
            length == 0 || length >= sizeof(moduleName) - 1) {
            napi_throw_type_error(env, nullptr, "invalid SDK module name");
            return nullptr;
        }
        napi_value result = nullptr, module = nullptr, properties = nullptr;
        napi_create_object(env, &result);
        napi_set_named_property(env, result, "module", name);
        const napi_status loaded = napi_load_module(env, moduleName, &module);
        const bool exception = Exception(env);
        napi_valuetype type = napi_undefined;
        if (loaded == napi_ok && !exception && module != nullptr) napi_typeof(env, module, &type);
        Number(env, result, "load_status", loaded);
        Boolean(env, result, "load_exception", exception);
        Number(env, result, "module_type", type);
        napi_create_array(env, &properties);
        napi_value keys = nullptr;
        napi_status collected = napi_object_expected;
        uint32_t size = 0;
        if (loaded == napi_ok && !exception && module != nullptr) {
            collected = napi_get_all_property_names(env, module, napi_key_own_only,
                static_cast<napi_key_filter>(napi_key_all_properties | napi_key_skip_symbols),
                napi_key_numbers_to_strings, &keys);
            if (collected == napi_ok) collected = napi_get_array_length(env, keys, &size);
        }
        const bool collectionException = Exception(env);
        if (collected == napi_ok && !collectionException) {
            for (uint32_t offset = 0; offset < size; ++offset) {
                napi_value key = nullptr, value = nullptr, property = nullptr;
                char propertyName[128] = {};
                size_t propertyNameLength = 0;
                napi_status status = napi_get_element(env, keys, offset, &key);
                if (status != napi_ok) return nullptr;
                napi_create_object(env, &property);
                napi_set_named_property(env, property, "name", key);
                const bool named = napi_get_value_string_utf8(env, key, propertyName, sizeof(propertyName),
                    &propertyNameLength) == napi_ok && propertyNameLength > 0 &&
                    propertyNameLength < sizeof(propertyName) - 1;
                status = napi_get_property(env, module, key, &value);
                napi_valuetype valueType = napi_undefined;
                if (status == napi_ok) status = napi_typeof(env, value, &valueType);
                const bool readException = Exception(env);
                const bool enumApplicable = named && IsAccessibilityEnum(moduleName, propertyName);
                const bool enumValid = enumApplicable && status == napi_ok && !readException &&
                    valueType == napi_object && CheckAccessibilityEnum(env, value, propertyName);
                Number(env, property, "read_status", status);
                Number(env, property, "value_type", valueType);
                Boolean(env, property, "read_exception", readException);
                Boolean(env, property, "enum_contract_applicable", enumApplicable);
                Boolean(env, property, "enum_contract_valid", enumValid);
                napi_set_element(env, properties, offset, property);
            }
        }
        Number(env, result, "collection_status", collected);
        Boolean(env, result, "collection_exception", collectionException);
        napi_set_named_property(env, result, "properties", properties);
        napi_set_element(env, results, index, result);
    }
    return results;
}

napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor method = {"inspect", nullptr, Inspect, nullptr, nullptr, nullptr, napi_default, nullptr};
    napi_define_properties(env, exports, 1, &method);
    return exports;
}
napi_module MODULE = {1, 0, nullptr, Init, "arktsexportsprobe", nullptr, {0}};
}
extern "C" __attribute__((constructor)) void RegisterArktsExportsProbe()
{
    napi_module_register(&MODULE);
}
