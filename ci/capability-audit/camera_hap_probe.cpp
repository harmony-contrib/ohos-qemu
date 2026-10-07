// SPDX-License-Identifier: Apache-2.0
#include <napi/native_api.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <exception>
#include <fcntl.h>
#include <string>
#include <thread>
#include <unistd.h>

extern "C" int RunPublicCameraProbe(FILE *, const char *, const char *);
static std::atomic<bool> running {false};

static bool String(napi_env env, napi_value arg, char *out, size_t capacity, size_t *length)
{
    return napi_get_value_string_utf8(env, arg, nullptr, 0, length) == napi_ok && *length < capacity &&
        napi_get_value_string_utf8(env, arg, out, capacity, length) == napi_ok;
}

static bool PrivateFiles(const std::string &path)
{
    return path.rfind("/data/storage/el2/base/", 0) == 0 && path.find("/../") == std::string::npos &&
        path.find("/./") == std::string::npos && path.find("//") == std::string::npos &&
        path.size() >= 6 && path.compare(path.size() - 6, 6, "/files") == 0;
}

static napi_value CreateFile(napi_env env, napi_callback_info info)
{
    size_t count = 1, length = 0;
    napi_value arg = nullptr, value = nullptr;
    char raw[512] {};
    bool accepted = napi_get_cb_info(env, info, &count, &arg, nullptr, nullptr) == napi_ok && count == 1 &&
        String(env, arg, raw, sizeof(raw), &length) && std::strlen(raw) == length;
    const std::string path(raw);
    const auto slash = path.rfind('/');
    accepted = accepted && slash != std::string::npos && PrivateFiles(path.substr(0, slash)) &&
        path.substr(slash + 1).rfind("camera-", 0) == 0;
    if (accepted) {
        const int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
        accepted = fd >= 0;
        if (fd >= 0) accepted = close(fd) == 0;
    }
    napi_get_boolean(env, accepted, &value);
    return value;
}

static napi_value Run(napi_env env, napi_callback_info info)
{
    size_t count = 3, runLength = 0, surfaceLength = 0, directoryLength = 0;
    napi_value args[3] {}, value = nullptr;
    char run[33] {}, surface[21] {}, directory[400] {};
    bool accepted = napi_get_cb_info(env, info, &count, args, nullptr, nullptr) == napi_ok && count == 3 &&
        String(env, args[0], run, sizeof(run), &runLength) && runLength == 32 &&
        String(env, args[1], surface, sizeof(surface), &surfaceLength) && surfaceLength > 0 &&
        String(env, args[2], directory, sizeof(directory), &directoryLength) &&
        std::strlen(directory) == directoryLength && PrivateFiles(directory);
    for (size_t i = 0; accepted && i < runLength; ++i) {
        accepted = (run[i] >= '0' && run[i] <= '9') || (run[i] >= 'a' && run[i] <= 'f');
    }
    for (size_t i = 0; accepted && i < surfaceLength; ++i) accepted = surface[i] >= '0' && surface[i] <= '9';
    accepted = accepted && !running.exchange(true);
    if (accepted) {
        try {
            std::thread([challenge = std::string(run), id = std::string(surface), files = std::string(directory)] {
                FILE *out = fopen((files + "/camera-native-" + challenge + "-results.log").c_str(), "wx");
                if (out) {
                    try { RunPublicCameraProbe(out, challenge.c_str(), id.c_str()); }
                    catch (...) { fprintf(out, "{\"run_id\":\"%s\",\"kind\":\"native_exception\"}\n", challenge.c_str()); }
                    fclose(out);
                }
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
    napi_property_descriptor methods[] = {
        {"run", nullptr, Run, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"createFile", nullptr, CreateFile, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    napi_define_properties(env, exports, 2, methods);
    return exports;
}
static napi_module module {1, 0, nullptr, Init, "camerapublicprobe", nullptr, {0}};
extern "C" __attribute__((constructor)) void RegisterPublicCameraProbe()
{
    napi_module_register(&module);
}
