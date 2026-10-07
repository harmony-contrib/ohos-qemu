// SPDX-License-Identifier: Apache-2.0
#include <napi/native_api.h>
#include <atomic>
#include <cstdio>
#include <exception>
#include <string>
#include <thread>

extern "C" int RunAudioStreamProbe(FILE *out, const char *run);
static std::atomic<bool> running{false};

static napi_value Run(napi_env env, napi_callback_info info)
{
    size_t count = 1, length = 0;
    napi_value arg = nullptr, value = nullptr;
    char run[33] = {};
    bool accepted = napi_get_cb_info(env, info, &count, &arg, nullptr, nullptr) == napi_ok && count == 1 &&
        napi_get_value_string_utf8(env, arg, nullptr, 0, &length) == napi_ok && length == 32 &&
        napi_get_value_string_utf8(env, arg, run, sizeof(run), &length) == napi_ok && length == 32;
    for (size_t i = 0; accepted && i < length; ++i) {
        accepted = (run[i] >= '0' && run[i] <= '9') || (run[i] >= 'a' && run[i] <= 'f');
    }
    accepted = accepted && !running.exchange(true);
    if (accepted) {
        try {
            // Do not block UIAbility lifecycle or access NAPI from the worker.
            std::thread([challenge = std::string(run)] {
                FILE *out = nullptr;
                try {
                    const std::string path = "/data/storage/el2/base/files/audio-stream-" + challenge + "-results.log";
                    out = fopen(path.c_str(), "wx");
                    if (out != nullptr) RunAudioStreamProbe(out, challenge.c_str());
                } catch (...) {
                    if (out != nullptr) fprintf(out, "{\"run_id\":\"%s\",\"type\":\"probe_exception\"}\n", challenge.c_str());
                }
                if (out != nullptr) fclose(out);
                running.store(false);
            }).detach();
        } catch (const std::exception &) {
            running.store(false);
            accepted = false;
        }
    }
    napi_get_boolean(env, accepted, &value);
    return value;
}

static napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor method = {"run", nullptr, Run, nullptr, nullptr, nullptr, napi_default, nullptr};
    napi_define_properties(env, exports, 1, &method);
    return exports;
}
static napi_module module = {1, 0, nullptr, Init, "audiostreamprobe", nullptr, {0}};
extern "C" __attribute__((constructor)) void RegisterAudioStreamProbe()
{
    napi_module_register(&module);
}
