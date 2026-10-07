// SPDX-License-Identifier: Apache-2.0
#include <napi/native_api.h>
#include <cmath>
#include <cstdint>
#include <cstdio>

extern "C" int AccessTokenUserIdProbe(bool privileged, const char *run, uint32_t expected, FILE *out);

static napi_value Run(napi_env env, napi_callback_info info)
{
    size_t count = 2;
    napi_value args[2] = {nullptr, nullptr};
    double expected = -1;
    char run[33] = {};
    size_t length = 0;
    int result = 2;
    if (napi_get_cb_info(env, info, &count, args, nullptr, nullptr) == napi_ok && count == 2 &&
        napi_get_value_double(env, args[0], &expected) == napi_ok && std::isfinite(expected) &&
        expected >= 0 && expected <= UINT32_MAX && std::floor(expected) == expected &&
        napi_get_value_string_utf8(env, args[1], run, sizeof(run), &length) == napi_ok && length == 32) {
        FILE *out = fopen("/data/storage/el2/base/files/userid-results.log", "w");
        if (out != nullptr) {
            result = AccessTokenUserIdProbe(false, run, static_cast<uint32_t>(expected), out);
            if (fclose(out) != 0) result = 1;
        }
    }
    napi_value value = nullptr;
    napi_create_int32(env, result, &value);
    return value;
}

static napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor method = {"run", nullptr, Run, nullptr, nullptr, nullptr, napi_default, nullptr};
    napi_define_properties(env, exports, 1, &method);
    return exports;
}
static napi_module module = {1, 0, nullptr, Init, "useridprobe", nullptr, {0}};
extern "C" __attribute__((constructor)) void RegisterUserIdProbe()
{
    napi_module_register(&module);
}
