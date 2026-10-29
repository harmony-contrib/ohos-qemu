/*
 * Copyright (c) 2023 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "audio_haptic_player_callback_napi.h"

#include <uv.h>

#include "media_errors.h"
#include "audio_haptic_log.h"

namespace {
const std::string AUDIO_INTERRUPT_CALLBACK_NAME = "audioInterrupt";
const std::string END_OF_STREAM_CALLBACK_NAME = "endOfStream";

constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_AUDIO_NAPI, "AudioHapticPlayerCallbackNapi"};
}

namespace OHOS {
namespace Media {
// Diagnostic addresses originate at the actual callback and captured Session.
// Pending events strongly retain Session; historical address reuse is not a JS epoch.
static void TracePublication(const char *stage, const char *eventName, void *instance,
    const std::shared_ptr<AudioHapticPlaybackSession> &session, bool loop, bool accepted)
{
    MEDIA_LOGI("AHPublication stage=%{public}s event=%{public}s scope=%{public}s callback=%{public}p "
        "session=%{public}p backend=%{public}p end_observed=%{public}d confirmed=%{public}d "
        "loop=%{public}d accepted=%{public}d", stage, eventName,
        session ? "normal" : "legacy-fast-unidentified", instance, session.get(),
        session ? reinterpret_cast<void *>(session->backendDiagnosticIdentity) : nullptr,
        session ? static_cast<int32_t>(session->end.load()) : -1,
        session ? static_cast<int32_t>(session->playConfirmed.load()) : 0, loop, accepted);
}

AudioHapticPlayerCallbackNapi::AudioHapticPlayerCallbackNapi(napi_env env)
    : env_(env)
{
    MEDIA_LOGI("AudioHapticPlayerCallbackNapi: instance create");
}

AudioHapticPlayerCallbackNapi::~AudioHapticPlayerCallbackNapi()
{
    MEDIA_LOGI("~AudioHapticPlayerCallbackNapi: instance destroy");
}

void AudioHapticPlayerCallbackNapi::SaveCallbackReference(const std::string &callbackName, napi_value args)
{
    std::lock_guard<std::mutex> lock(cbMutex_);

    napi_ref callback = nullptr;
    const int32_t refCount = 1;
    napi_status status = napi_create_reference(env_, args, refCount, &callback);
    CHECK_AND_RETURN_LOG(status == napi_ok && callback != nullptr,
        "SaveCallbackReference: creating reference for callback fail");

    std::shared_ptr<AutoRef> cb = std::make_shared<AutoRef>(env_, callback);
    if (callbackName == AUDIO_INTERRUPT_CALLBACK_NAME) {
        audioInterruptCb_ = cb;
    } else if (callbackName == END_OF_STREAM_CALLBACK_NAME) {
        endOfStreamCb_ = cb;
    } else {
        MEDIA_LOGE("SaveCallbackReference: Unknown callback type: %{public}s", callbackName.c_str());
    }
}

void AudioHapticPlayerCallbackNapi::RemoveCallbackReference(const std::string &callbackName)
{
    std::lock_guard<std::mutex> lock(cbMutex_);

    if (callbackName == AUDIO_INTERRUPT_CALLBACK_NAME) {
        audioInterruptCb_ = nullptr;
    } else if (callbackName == END_OF_STREAM_CALLBACK_NAME) {
        endOfStreamCb_ = nullptr;
    } else {
        MEDIA_LOGE("RemoveCallbackReference: Unknown callback type: %{public}s", callbackName.c_str());
    }
}

static void SetValueInt32(const napi_env& env, const std::string& fieldStr, const int intValue, napi_value& result)
{
    napi_handle_scope scope = nullptr;
    napi_status status = napi_open_handle_scope(env, &scope);
    CHECK_AND_RETURN_LOG(status == napi_ok && scope != nullptr, "open handle scope failed!");

    napi_value value = nullptr;
    napi_create_int32(env, intValue, &value);
    napi_set_named_property(env, result, fieldStr.c_str(), value);

    napi_close_handle_scope(env, scope);
}

static void NativeInterruptEventToJsObj(const napi_env& env, napi_value& jsObj,
    const AudioStandard::InterruptEvent& interruptEvent)
{
    napi_create_object(env, &jsObj);
    SetValueInt32(env, "eventType", static_cast<int32_t>(interruptEvent.eventType), jsObj);
    SetValueInt32(env, "forceType", static_cast<int32_t>(interruptEvent.forceType), jsObj);
    SetValueInt32(env, "hintType", static_cast<int32_t>(interruptEvent.hintType), jsObj);
}

void AudioHapticPlayerCallbackNapi::OnInterrupt(const AudioStandard::InterruptEvent &interruptEvent)
{
    QueueInterrupt(nullptr, interruptEvent); // legacy/fast public delivery
}

void AudioHapticPlayerCallbackNapi::OnSessionInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    const AudioStandard::InterruptEvent &interruptEvent)
{
    CHECK_AND_RETURN_LOG(session != nullptr, "normal interrupt requires its source Session");
    QueueInterrupt(session, interruptEvent);
}

void AudioHapticPlayerCallbackNapi::QueueInterrupt(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    const AudioStandard::InterruptEvent &interruptEvent)
{
    std::lock_guard<std::mutex> lock(cbMutex_);
    MEDIA_LOGI("OnInterrupt: hintType: %{public}d for js", interruptEvent.hintType);
    CHECK_AND_RETURN_LOG(audioInterruptCb_ != nullptr, "Cannot find the reference of interrupt callback");

    std::unique_ptr<AudioHapticPlayerJsCallback> cb = std::make_unique<AudioHapticPlayerJsCallback>();
    CHECK_AND_RETURN_LOG(cb != nullptr, "No memory");
    cb->callback = audioInterruptCb_;
    cb->callbackName = AUDIO_INTERRUPT_CALLBACK_NAME;
    cb->interruptEvent = interruptEvent;
    cb->playbackSession = session;
    cb->callbackIdentity = this;
    TracePublication("queue-attempt", "interrupt", this, session, false, true);
    return OnInterruptJsCallback(cb);
}

void AudioHapticPlayerCallbackNapi::OnInterruptJsCallback(std::unique_ptr<AudioHapticPlayerJsCallback> &jsCb)
{
    if (jsCb.get() == nullptr) {
        MEDIA_LOGE("AudioHapticPlayerJsCallback: jsCb.get() is null");
        return;
    }
    AudioHapticPlayerJsCallback *event = jsCb.release();
    // The JS thread may finish/delete event before napi_send_event returns.
    // Keep diagnostic snapshots independently of the queued context lifetime.
    const auto sourceSession = event->playbackSession;
    void *sourceCallbackIdentity = event->callbackIdentity;
    const bool sourceLoop = event->loopEOS;
    auto task = [event]() {
        std::shared_ptr<AudioHapticPlayerJsCallback> context(
            static_cast<AudioHapticPlayerJsCallback*>(event),
            [](AudioHapticPlayerJsCallback* ptr) {
                delete ptr;
        });
        CHECK_AND_RETURN_LOG(event != nullptr, "event is nullptr");
        const bool accepted = IsAudioHapticPublicationLive(event->playbackSession, false, false);
        TracePublication(accepted ? "task-admitted" : "task-dropped", "interrupt", event->callbackIdentity,
            event->playbackSession, false, accepted);
        CHECK_AND_RETURN_LOG(accepted, "discard retired normal interrupt before JS publication");
        std::string request = event->callbackName;
        napi_env env = event->callback->env_;
        napi_ref callback = event->callback->cb_;
        napi_handle_scope scope = nullptr;
        napi_status status = napi_open_handle_scope(env, &scope);
        CHECK_AND_RETURN_LOG(status == napi_ok && scope != nullptr, "open handle scope failed!");
        MEDIA_LOGI("AudioHapticPlayerJsCallback: %{public}s JsCallBack, uv_queue_work start", request.c_str());
        do {
            CHECK_AND_BREAK_LOG(event != nullptr, "event is nullptr");

            napi_value jsCallback = nullptr;
            napi_status napiStatus = napi_get_reference_value(env, callback, &jsCallback);
            CHECK_AND_BREAK_LOG(napiStatus == napi_ok && jsCallback != nullptr,
                "%{public}s get reference value fail", request.c_str());

            // Call back function
            napi_value args[1] = { nullptr };
            NativeInterruptEventToJsObj(env, args[0], event->interruptEvent);
            CHECK_AND_BREAK_LOG(napiStatus == napi_ok && args[0] != nullptr,
                "%{public}s fail to create Interrupt callback", request.c_str());

            const size_t argCount = 1;
            napi_value result = nullptr;
            napiStatus = napi_call_function(env, nullptr, jsCallback, argCount, args, &result);
            CHECK_AND_BREAK_LOG(napiStatus == napi_ok, "%{public}s fail to send interrupt callback", request.c_str());
        } while (0);
        napi_close_handle_scope(env, scope);
    };
    auto ret = napi_send_event(env_, task, napi_eprio_high, "audioInterrupt");
    TracePublication(ret == napi_status::napi_ok ? "enqueue" : "enqueue-failed", "interrupt",
        sourceCallbackIdentity, sourceSession, sourceLoop, ret == napi_status::napi_ok);
    if (ret != napi_status::napi_ok) {
        MEDIA_LOGE("Failed to SendEvent, ret = %{public}d", ret);
        delete event;
    }
}

void AudioHapticPlayerCallbackNapi::OnEndOfStream(void)
{
    QueueEndOfStream(nullptr, false); // legacy/fast public delivery
}

void AudioHapticPlayerCallbackNapi::OnSessionEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    bool isLoop)
{
    CHECK_AND_RETURN_LOG(session != nullptr, "normal EOS requires its source Session");
    QueueEndOfStream(session, isLoop);
}

void AudioHapticPlayerCallbackNapi::QueueEndOfStream(const std::shared_ptr<AudioHapticPlaybackSession> &session,
    bool isLoop)
{
    std::lock_guard<std::mutex> lock(cbMutex_);
    MEDIA_LOGI("OnEndOfStream in succeed");
    CHECK_AND_RETURN_LOG(endOfStreamCb_ != nullptr, "Cannot find the reference of endOfStream callback");

    std::unique_ptr<AudioHapticPlayerJsCallback> cb = std::make_unique<AudioHapticPlayerJsCallback>();
    CHECK_AND_RETURN_LOG(cb != nullptr, "No memory");
    cb->callback = endOfStreamCb_;
    cb->callbackName = END_OF_STREAM_CALLBACK_NAME;
    cb->playbackSession = session;
    cb->loopEOS = isLoop;
    cb->callbackIdentity = this;
    TracePublication("queue-attempt", "eos", this, session, isLoop, true);
    return OnEndOfStreamJsCallback(cb);
}

void AudioHapticPlayerCallbackNapi::OnError(int32_t errorCode)
{
    MEDIA_LOGI("OnError from audio haptic player. errorCode %{public}d", errorCode);
}

void AudioHapticPlayerCallbackNapi::OnEndOfStreamJsCallback(std::unique_ptr<AudioHapticPlayerJsCallback> &jsCb)
{
    if (jsCb.get() == nullptr) {
        MEDIA_LOGE("AudioHapticPlayerJsCallback: jsCb.get() is null");
        return;
    }
    AudioHapticPlayerJsCallback *event = jsCb.release();
    // The JS thread may finish/delete event before napi_send_event returns.
    // Keep diagnostic snapshots independently of the queued context lifetime.
    const auto sourceSession = event->playbackSession;
    void *sourceCallbackIdentity = event->callbackIdentity;
    const bool sourceLoop = event->loopEOS;
    auto task = [event]() {
        std::shared_ptr<AudioHapticPlayerJsCallback> context(
            static_cast<AudioHapticPlayerJsCallback*>(event),
            [](AudioHapticPlayerJsCallback* ptr) {
                delete ptr;
        });
        CHECK_AND_RETURN_LOG(event != nullptr, "event is nullptr");
        const bool accepted = IsAudioHapticPublicationLive(event->playbackSession, true, event->loopEOS);
        TracePublication(accepted ? "task-admitted" : "task-dropped", "eos", event->callbackIdentity,
            event->playbackSession, event->loopEOS, accepted);
        CHECK_AND_RETURN_LOG(accepted, "discard retired normal EOS before JS publication");
        std::string request = event->callbackName;
        napi_env env = event->callback->env_;
        napi_ref callback = event->callback->cb_;
        napi_handle_scope scope = nullptr;
        napi_status status = napi_open_handle_scope(env, &scope);
        CHECK_AND_RETURN_LOG(status == napi_ok && scope != nullptr, "open handle scope failed!");
        MEDIA_LOGI("OnEndOfStreamJsCallback: %{public}s JsCallBack, uv_queue_work start", request.c_str());
        do {
            CHECK_AND_BREAK_LOG(event != nullptr, "event is nullptr");

            napi_value jsCallback = nullptr;
            napi_status napiStatus = napi_get_reference_value(env, callback, &jsCallback);
            CHECK_AND_BREAK_LOG(napiStatus == napi_ok && jsCallback != nullptr,
                "%{public}s get reference value fail", request.c_str());

            // Call back function
            napi_value result = nullptr;
            napiStatus = napi_call_function(env, nullptr, jsCallback, 0, nullptr, &result);
            CHECK_AND_BREAK_LOG(napiStatus == napi_ok, "%{public}s fail to send interrupt callback", request.c_str());
        } while (0);
        napi_close_handle_scope(env, scope);
    };
    auto ret = napi_send_event(env_, task, napi_eprio_high, "endOfStream");
    TracePublication(ret == napi_status::napi_ok ? "enqueue" : "enqueue-failed", "eos",
        sourceCallbackIdentity, sourceSession, sourceLoop, ret == napi_status::napi_ok);
    if (ret != napi_status::napi_ok) {
        MEDIA_LOGE("Failed to SendEvent, ret = %{public}d", ret);
        delete event;
    }
}
}  // namespace Media
}  // namespace OHOS
