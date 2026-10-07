// SPDX-License-Identifier: Apache-2.0
// Ordinary-app public Camera NDK preview lifecycle, not a root/InnerAPI probe.
#include <ohcamera/camera_manager.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <unistd.h>

namespace {
struct Frames {
    std::atomic<unsigned> starts {0}, ends {0}, errors {0};
    std::atomic<int32_t> maximum {0};
};
std::mutex callbackMutex;
std::unordered_map<Camera_PreviewOutput *, std::shared_ptr<Frames>> callbacks;
std::shared_ptr<Frames> Find(Camera_PreviewOutput *output)
{
    std::lock_guard<std::mutex> lock(callbackMutex);
    const auto it = callbacks.find(output);
    return it == callbacks.end() ? nullptr : it->second;
}
void FrameStart(Camera_PreviewOutput *output)
{
    if (auto state = Find(output)) ++state->starts;
}
void FrameEnd(Camera_PreviewOutput *output, int32_t count)
{
    if (auto state = Find(output)) {
        ++state->ends;
        int32_t observed = state->maximum.load();
        while (observed < count && !state->maximum.compare_exchange_weak(observed, count)) {}
    }
}
void FrameError(Camera_PreviewOutput *output, Camera_ErrorCode)
{
    if (auto state = Find(output)) ++state->errors;
}
struct Log {
    FILE *out;
    std::string run;
    unsigned checks {0}, failures {0};
    bool Check(unsigned cycle, const char *name, bool pass, int64_t value = 0)
    {
        ++checks;
        failures += !pass;
        fprintf(out, "{\"run_id\":\"%s\",\"kind\":\"native_case\",\"cycle\":%u,\"name\":\"%s\","
                     "\"pass\":%s,\"value\":%lld}\n", run.c_str(), cycle, name, pass ? "true" : "false",
                     static_cast<long long>(value));
        fflush(out);
        return pass;
    }
};

bool Wait(const std::atomic<unsigned> &value, unsigned seconds)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
    while (value.load() == 0 && std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    return value.load() > 0;
}

void Cycle(Log &log, unsigned cycle, const char *surface)
{
    Camera_Manager *manager = nullptr;
    Camera_Device *devices = nullptr;
    uint32_t count = 0;
    Camera_OutputCapability *capability = nullptr;
    Camera_Input *input = nullptr;
    Camera_PreviewOutput *preview = nullptr;
    Camera_CaptureSession *session = nullptr;
    auto frames = std::make_shared<Frames>();
    PreviewOutput_Callbacks callback {FrameStart, FrameEnd, FrameError};
    bool opened = false, registered = false, started = false;
    auto Call = [&](const char *name, Camera_ErrorCode code, Camera_ErrorCode expected = CAMERA_OK) {
        return log.Check(cycle, name, code == expected, code);
    };
    auto Object = [&](const char *name, Camera_ErrorCode code, const void *value) {
        return log.Check(cycle, name, code == CAMERA_OK && value != nullptr, code);
    };
    [&] {
        auto code = OH_Camera_GetCameraManager(&manager);
        if (!Object("manager_create", code, manager)) return;
        const auto found = OH_CameraManager_GetSupportedCameras(manager, &devices, &count);
        if (!log.Check(cycle, "real_camera_enumeration", found == CAMERA_OK && devices && count > 0 && count <= 16, count)) return;
        code = OH_CameraManager_GetSupportedCameraOutputCapabilityWithSceneMode(
                manager, &devices[0], NORMAL_PHOTO, &capability);
        if (!Object("capabilities", code, capability)) return;
        Camera_Profile *profile = nullptr;
        if (capability->previewProfiles && capability->previewProfilesSize <= 1024) {
            for (uint32_t i = 0; i < capability->previewProfilesSize; ++i) {
                auto candidate = capability->previewProfiles[i];
                if (candidate && candidate->format == CAMERA_FORMAT_YUV_420_SP &&
                    candidate->size.width >= 160 && candidate->size.width <= 1280 &&
                    candidate->size.height >= 120 && candidate->size.height <= 720 &&
                    (!profile || candidate->size.width < profile->size.width)) profile = candidate;
            }
        }
        if (!log.Check(cycle, "real_YUV_preview_profile", profile != nullptr)) return;
        fprintf(log.out, "{\"run_id\":\"%s\",\"kind\":\"native_profile\",\"cycle\":%u,\"format\":%d,"
                         "\"width\":%u,\"height\":%u}\n", log.run.c_str(), cycle, profile->format,
                         profile->size.width, profile->size.height);
        code = OH_CameraManager_CreateCameraInput(manager, &devices[0], &input);
        if (!Object("input_create", code, input)) return;
        if (!Call("input_open", OH_CameraInput_Open(input))) return;
        opened = true;
        code = OH_CameraManager_CreatePreviewOutput(manager, profile, surface, &preview);
        if (!Object("preview_create", code, preview)) return;
        {
            std::lock_guard<std::mutex> lock(callbackMutex);
            if (callbacks.count(preview)) {
                log.Check(cycle, "no_stale_callback_pointer", false);
                return;
            }
            callbacks.emplace(preview, frames);
        }
        if (!Call("callback_register", OH_PreviewOutput_RegisterCallback(preview, &callback))) return;
        registered = true;
        code = OH_CameraManager_CreateCaptureSession(manager, &session);
        if (!Object("session_create", code, session)) return;
        if (!Call("start_before_config_rejected", OH_CaptureSession_Start(session), CAMERA_SESSION_NOT_CONFIG) ||
            !Call("config_begin", OH_CaptureSession_BeginConfig(session)) ||
            !Call("config_add_input", OH_CaptureSession_AddInput(session, input)) ||
            !Call("config_add_preview", OH_CaptureSession_AddPreviewOutput(session, preview)) ||
            !Call("config_commit", OH_CaptureSession_CommitConfig(session)) ||
            !Call("session_start", OH_CaptureSession_Start(session))) return;
        started = true;
        if (!log.Check(cycle, "real_frame_start", Wait(frames->starts, 15))) return;
        std::this_thread::sleep_for(std::chrono::seconds(3));
        if (!Call("session_stop", OH_CaptureSession_Stop(session))) return;
        started = false;
        Wait(frames->ends, 5);
        const auto starts = frames->starts.load(), ends = frames->ends.load(), errors = frames->errors.load();
        const auto maximum = frames->maximum.load();
        fprintf(log.out, "{\"run_id\":\"%s\",\"kind\":\"native_frames\",\"cycle\":%u,"
                         "\"starts\":%u,\"ends\":%u,\"errors\":%u,\"maximum\":%d}\n",
                         log.run.c_str(), cycle, starts, ends, errors, maximum);
        log.Check(cycle, "real_frame_completion", starts > 0 && ends > 0 && maximum >= 8 && errors == 0, maximum);
    }();
    if (started) Call("failed_run_stop_cleanup", OH_CaptureSession_Stop(session));
    if (registered) Call("callback_unregister", OH_PreviewOutput_UnregisterCallback(preview, &callback));
    if (preview) {
        const auto code = OH_PreviewOutput_Release(preview);
        Call("preview_release", code);
        if (code == CAMERA_OK) {
            std::lock_guard<std::mutex> lock(callbackMutex);
            callbacks.erase(preview);
        }
        // On failed release the heap registry intentionally retains callback
        // storage; a failure must never become an asynchronous use-after-free.
    }
    if (session) Call("session_release", OH_CaptureSession_Release(session));
    if (opened) Call("input_close", OH_CameraInput_Close(input));
    if (input) Call("input_release", OH_CameraInput_Release(input));
    if (capability) Call("capabilities_release", OH_CameraManager_DeleteSupportedCameraOutputCapability(manager, capability));
    if (devices) Call("cameras_release", OH_CameraManager_DeleteSupportedCameras(manager, devices, count));
    if (manager) Call("manager_release", OH_Camera_DeleteCameraManager(manager));
}
} // namespace

extern "C" int RunPublicCameraProbe(FILE *out, const char *run, const char *surface)
{
    if (!out || !run || std::strlen(run) != 32 || std::strspn(run, "0123456789abcdef") != 32 ||
        !surface || !*surface || std::strlen(surface) > 20 || std::strspn(surface, "0123456789") != std::strlen(surface)) return 2;
    Log log {out, run};
#if defined(__aarch64__)
    const char *arch = "arm64";
#elif defined(__arm__)
    const char *arch = "armv7a";
#elif defined(__x86_64__)
    const char *arch = "x86_64";
#else
    const char *arch = "unknown";
#endif
    fprintf(out, "{\"run_id\":\"%s\",\"kind\":\"native_identity\",\"arch\":\"%s\","
                 "\"uid\":%u,\"euid\":%u}\n", run, arch, getuid(), geteuid());
    if (!log.Check(0, "ordinary_application", getuid() == geteuid() && getuid() / 200000 == 100 && getuid() % 200000 >= 10000)) return 1;
    log.Check(0, "null_manager_create", OH_Camera_GetCameraManager(nullptr) == CAMERA_INVALID_ARGUMENT);
    log.Check(0, "null_manager_delete", OH_Camera_DeleteCameraManager(nullptr) == CAMERA_INVALID_ARGUMENT);
    log.Check(0, "null_input_open", OH_CameraInput_Open(nullptr) == CAMERA_INVALID_ARGUMENT);
    log.Check(0, "null_input_close", OH_CameraInput_Close(nullptr) == CAMERA_INVALID_ARGUMENT);
    log.Check(0, "null_session_begin", OH_CaptureSession_BeginConfig(nullptr) == CAMERA_INVALID_ARGUMENT);
    log.Check(0, "null_session_start", OH_CaptureSession_Start(nullptr) == CAMERA_INVALID_ARGUMENT);
    log.Check(0, "null_preview_start", OH_PreviewOutput_Start(nullptr) == CAMERA_INVALID_ARGUMENT);
    log.Check(0, "null_preview_release", OH_PreviewOutput_Release(nullptr) == CAMERA_INVALID_ARGUMENT);
    for (unsigned cycle = 1; cycle <= 2 && !log.failures; ++cycle) Cycle(log, cycle, surface);
    fprintf(out, "{\"run_id\":\"%s\",\"kind\":\"native_complete\",\"checks\":%u,\"failures\":%u,"
                 "\"exit_code\":%d,\"scope\":\"public_NDK_preview_callbacks_not_pixel_or_photo_validation\"}\n",
                 run, log.checks, log.failures, log.failures ? 1 : 0);
    fflush(out);
    return log.failures ? 1 : 0;
}
