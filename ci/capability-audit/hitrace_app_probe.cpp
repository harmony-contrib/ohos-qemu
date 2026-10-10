// SPDX-License-Identifier: Apache-2.0
// Emit only public HiTrace calls. Kernel capture, not return values, proves tracing.
#include <hitrace/trace.h>
#include <napi/native_api.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <sys/syscall.h>
#include <unistd.h>

namespace {
napi_value Run(napi_env env, napi_callback_info info)
{
    size_t argc = 2;
    napi_value argv[2] = {nullptr, nullptr};
    char nonce[33] = {};
    size_t length = 0;
    int32_t generation = -1;
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 2 ||
        napi_get_value_string_utf8(env, argv[0], nonce, sizeof(nonce), &length) != napi_ok || length != 32 ||
        std::strspn(nonce, "0123456789abcdef") != 32 ||
        napi_get_value_int32(env, argv[1], &generation) != napi_ok || generation < 0 || generation > 1) {
        napi_throw_type_error(env, nullptr, "fresh nonce and bounded generation required");
        return nullptr;
    }
    const bool enabled = OH_HiTrace_IsTraceEnabled();
    char sync[96], nested[96], async[96], counter[96];
    std::snprintf(sync, sizeof(sync), "oqht-%s-n%d-sync", nonce, generation);
    std::snprintf(nested, sizeof(nested), "oqht-%s-n%d-nested", nonce, generation);
    std::snprintf(async, sizeof(async), "oqht-%s-n%d-async", nonce, generation);
    std::snprintf(counter, sizeof(counter), "oqht-%s-n%d-count", nonce, generation);
    OH_HiTrace_StartTrace(sync);
    OH_HiTrace_StartTrace(nested);
    OH_HiTrace_CountTrace(counter, -2147483649LL);
    OH_HiTrace_CountTrace(counter, 0);
    OH_HiTrace_CountTrace(counter, 2147483648LL);
    OH_HiTrace_FinishTrace();
    OH_HiTrace_FinishTrace();
    OH_HiTrace_StartAsyncTrace(async, 0);
    OH_HiTrace_StartAsyncTrace(async, INT32_MAX);
    OH_HiTrace_FinishAsyncTrace(async, INT32_MAX);
    OH_HiTrace_FinishAsyncTrace(async, 0);
    napi_value result = nullptr;
    napi_create_array_with_length(env, 5, &result);
    const int64_t values[] = {getpid(), getuid(), geteuid(), enabled ? 1 : 0, syscall(SYS_gettid)};
    for (uint32_t index = 0; index < 5; index++) {
        napi_value value = nullptr;
        napi_create_int64(env, values[index], &value);
        napi_set_element(env, result, index, value);
    }
    return result;
}

napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor method = {"run", nullptr, Run, nullptr, nullptr, nullptr, napi_default, nullptr};
    napi_define_properties(env, exports, 1, &method);
    return exports;
}
napi_module MODULE = {1, 0, nullptr, Init, "hitraceprobe", nullptr, {0}};
}
extern "C" __attribute__((constructor)) void RegisterHiTraceProbe()
{
    napi_module_register(&MODULE);
}
