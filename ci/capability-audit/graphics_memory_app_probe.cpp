// SPDX-License-Identifier: Apache-2.0
// Ordinary application: allocate real native buffers, never inject accounting data.
#include <hidebug/hidebug.h>
#include <native_buffer/native_buffer.h>
#include <native_buffer/buffer_common.h>
#include <napi/native_api.h>
#include <cstdint>
#include <cstring>
#include <unistd.h>

namespace {
OH_NativeBuffer *buffers[2] = {nullptr, nullptr};
int64_t sizesKiB[2] = {0, 0};
int phase = 0;

napi_value Fail(napi_env env, const char *reason)
{
    napi_throw_error(env, nullptr, reason);
    return nullptr;
}

napi_value Action(napi_env env, napi_callback_info info)
{
    size_t argc = 1;
    napi_value arg = nullptr;
    int32_t requested = 0;
    if (napi_get_cb_info(env, info, &argc, &arg, nullptr, nullptr) != napi_ok || argc != 1 ||
        napi_get_value_int32(env, arg, &requested) != napi_ok || requested != phase + 1 || requested > 4) {
        return Fail(env, "ordered buffer lifecycle required");
    }
    const int index = (requested - 1) % 2;
    if (requested <= 2) {
        OH_NativeBuffer_Config config = {2048, 2048, NATIVEBUFFER_PIXEL_FMT_RGBA_8888,
            NATIVEBUFFER_USAGE_CPU_READ | NATIVEBUFFER_USAGE_CPU_WRITE | NATIVEBUFFER_USAGE_MEM_DMA, 0};
        buffers[index] = OH_NativeBuffer_Alloc(&config);
        if (buffers[index] == nullptr) return Fail(env, "actual native buffer allocation failed");
        void *address = nullptr;
        if (OH_NativeBuffer_Map(buffers[index], &address) != 0 || address == nullptr) {
            return Fail(env, "actual native buffer mapping failed");
        }
        // Touch each row within the requested RGBA extent, respecting actual stride.
        OH_NativeBuffer_GetConfig(buffers[index], &config);
        if (config.width != 2048 || config.height != 2048 || config.stride < 8192) {
            OH_NativeBuffer_Unmap(buffers[index]);
            return Fail(env, "native buffer geometry does not match the request");
        }
        sizesKiB[index] = static_cast<int64_t>(config.stride) * config.height / 1024;
        for (int row = 0; row < config.height; ++row) {
            std::memset(static_cast<unsigned char *>(address) + row * config.stride, 0x5a + index, 8192);
        }
        if (OH_NativeBuffer_Unmap(buffers[index]) != 0) return Fail(env, "native buffer unmap failed");
    } else {
        void *address = nullptr;
        if (buffers[index] == nullptr || OH_NativeBuffer_Map(buffers[index], &address) != 0 ||
            address == nullptr) return Fail(env, "retained native buffer missing");
        const bool preserved = *static_cast<unsigned char *>(address) == 0x5a + index;
        const int unmap = OH_NativeBuffer_Unmap(buffers[index]);
        const int release = OH_NativeBuffer_Unreference(buffers[index]);
        buffers[index] = nullptr;
        if (!preserved || unmap != 0 || release != 0) return Fail(env, "buffer contents or release failed");
    }
    phase = requested;
    napi_value result = nullptr;
    napi_create_int32(env, phase, &result);
    return result;
}

napi_value Snapshot(napi_env env, napi_callback_info)
{
    uint32_t total = UINT32_MAX;
    HiDebug_GraphicsMemorySummary summary = {UINT32_MAX, UINT32_MAX};
    const int totalResult = OH_HiDebug_GetGraphicsMemory(&total);
    const int summaryResult = OH_HiDebug_GetGraphicsMemorySummary(2, &summary);
    const int64_t values[] = {getpid(), getuid(), geteuid(), totalResult, total, summaryResult,
        summary.gl, summary.graph, OH_HiDebug_GetGraphicsMemory(nullptr),
        OH_HiDebug_GetGraphicsMemorySummary(2, nullptr), phase,
        (buffers[0] != nullptr ? 1 : 0) + (buffers[1] != nullptr ? 1 : 0), sizesKiB[0], sizesKiB[1]};
    napi_value result = nullptr;
    napi_create_array_with_length(env, 14, &result);
    for (uint32_t i = 0; i < 14; ++i) {
        napi_value value = nullptr;
        napi_create_int64(env, values[i], &value);
        napi_set_element(env, result, i, value);
    }
    return result;
}

napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor methods[] = {
        {"action", nullptr, Action, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"snapshot", nullptr, Snapshot, nullptr, nullptr, nullptr, napi_default, nullptr}};
    napi_define_properties(env, exports, 2, methods);
    return exports;
}
napi_module MODULE = {1, 0, nullptr, Init, "graphicsmemoryprobe", nullptr, {0}};
}
extern "C" __attribute__((constructor)) void RegisterGraphicsMemoryProbe()
{
    napi_module_register(&MODULE);
}
