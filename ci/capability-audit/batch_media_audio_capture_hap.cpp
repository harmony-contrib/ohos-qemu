// SPDX-License-Identifier: Apache-2.0
#include <napi/native_api.h>
#include <atomic>
#include <cstdio>
#include <fcntl.h>
#include <string>
#include <thread>
#include <unistd.h>
extern "C" int RunBatchMediaAudioCaptureProbe(FILE *, const char *, bool);
static std::atomic<bool> running{false};
static napi_value Run(napi_env env, napi_callback_info info)
{
    napi_value argv[3]{}, result = nullptr;
    size_t argc = 3, length = 0;
    char run[33]{};
    bool denied = false;
    bool accepted = napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) == napi_ok && argc == 2 &&
        napi_get_value_string_utf8(env, argv[0], nullptr, 0, &length) == napi_ok && length == 32 &&
        napi_get_value_string_utf8(env, argv[0], run, sizeof(run), &length) == napi_ok && length == 32 &&
        napi_get_value_bool(env, argv[1], &denied) == napi_ok;
    for (size_t i = 0; accepted && i < length; ++i) accepted =
        (run[i] >= '0' && run[i] <= '9') || (run[i] >= 'a' && run[i] <= 'f');
    accepted = accepted && !running.exchange(true);
    if (accepted) {
        try {
            std::thread([challenge = std::string(run), denied] {
                const std::string path = "/data/storage/el2/base/files/audio-capture-" + challenge + "-results.log";
                int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
                FILE *out = fd < 0 ? nullptr : fdopen(fd, "w");
                if (out == nullptr && fd >= 0) close(fd);
                if (out != nullptr) {
                    try { RunBatchMediaAudioCaptureProbe(out, challenge.c_str(), denied); }
                    catch (...) { fprintf(out, "{\"type\":\"exception\",\"run_id\":\"%s\"}\n", challenge.c_str()); }
                    fclose(out);
                }
                running.store(false);
            }).detach();
        } catch (...) { running.store(false); accepted = false; }
    }
    napi_get_boolean(env, accepted, &result);
    return result;
}
static napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor method = {"run", nullptr, Run, nullptr, nullptr, nullptr, napi_default, nullptr};
    napi_define_properties(env, exports, 1, &method);
    return exports;
}
static napi_module module = {1, 0, nullptr, Init, "batchmediacapture", nullptr, {0}};
extern "C" __attribute__((constructor)) void RegisterBatchMediaCapture() { napi_module_register(&module); }
