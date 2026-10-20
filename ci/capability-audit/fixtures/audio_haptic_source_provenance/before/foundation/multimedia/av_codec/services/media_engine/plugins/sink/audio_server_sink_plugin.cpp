/*
 * Copyright (C) 2023-2026 Huawei Device Co., Ltd.
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

#define MEDIA_PLUGIN
#define HST_LOG_TAG "ASSP"

#include "audio_server_sink_plugin.h"
#include <functional>
#include "audio_errors.h"
#include "avcodec_trace.h"
#include "common/log.h"
#include "common/media_core.h"
#include "meta/meta_key.h"
#include "osal/task/autolock.h"
#include "osal/task/jobutils.h"
#include "common/status.h"
#include "common/media_core.h"
#include "audio_info.h"
#include "cpp_ext/algorithm_ext.h"
#include "osal/utils/steady_clock.h"
#include "plugin/plugin_time.h"
#include "param_wrapper.h"
#include "scoped_timer.h"

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = { LOG_CORE, LOG_DOMAIN_SYSTEM_PLAYER, "HiStreamer" };
using namespace OHOS::Media::Plugins;
constexpr int TUPLE_SECOND_ITEM_INDEX = 2;
constexpr int32_t DEFAULT_BUFFER_NUM = 8;
constexpr int32_t WRITE_WAIT_TIME = 5;
constexpr int64_t ON_WRITE_WARNING_MS = 15; // Reference value, Modify as needed
constexpr int64_t GET_AUDIO_POSITION_WARNING_MS = 10; // Reference value, Modify as needed
constexpr int64_t RELEASE_RENDER_WARNING_MS = 10; // Reference value, Modify as needed
constexpr int32_t LOG_PRINT_LIMIT = 8; // Reference value, Modify as needed
constexpr int32_t ON_WRITE_ZERO_COUNT = 500; // Reference value, Modify as needed

const std::pair<AudioInterruptMode, OHOS::AudioStandard::InterruptMode> g_auInterruptMap[] = {
    {AudioInterruptMode::SHARE_MODE, OHOS::AudioStandard::InterruptMode::SHARE_MODE},
    {AudioInterruptMode::INDEPENDENT_MODE, OHOS::AudioStandard::InterruptMode::INDEPENDENT_MODE},
};

const std::vector<std::tuple<AudioSampleFormat, OHOS::AudioStandard::AudioSampleFormat, AVSampleFormat>> g_aduFmtMap = {
    {AudioSampleFormat::SAMPLE_S8, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_U8, OHOS::AudioStandard::AudioSampleFormat::SAMPLE_U8, AV_SAMPLE_FMT_U8},
    {AudioSampleFormat::SAMPLE_S8P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_U8P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_U8P},
    {AudioSampleFormat::SAMPLE_S16LE, OHOS::AudioStandard::AudioSampleFormat::SAMPLE_S16LE, AV_SAMPLE_FMT_S16},
    {AudioSampleFormat::SAMPLE_U16, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_S16P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_S16P},
    {AudioSampleFormat::SAMPLE_U16P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_S24LE, OHOS::AudioStandard::AudioSampleFormat::SAMPLE_S24LE, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_U24, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_S24P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_U24P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_S32LE, OHOS::AudioStandard::AudioSampleFormat::SAMPLE_S32LE, AV_SAMPLE_FMT_S32},
    {AudioSampleFormat::SAMPLE_U32, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_S32P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_S32P},
    {AudioSampleFormat::SAMPLE_U32P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_F32LE, OHOS::AudioStandard::AudioSampleFormat::SAMPLE_F32LE, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_F32P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_FLTP},
    {AudioSampleFormat::SAMPLE_F64, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_DBL},
    {AudioSampleFormat::SAMPLE_F64P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_DBLP},
    {AudioSampleFormat::SAMPLE_S64, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_S64},
    {AudioSampleFormat::SAMPLE_U64, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
    {AudioSampleFormat::SAMPLE_S64P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_S64P},
    {AudioSampleFormat::SAMPLE_U64P, OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH, AV_SAMPLE_FMT_NONE},
};

const std::unordered_map<std::string, OHOS::AudioStandard::AudioEncodingType> mimeTypeToEncodingMap = {
    { MimeType::AUDIO_AC3, OHOS::AudioStandard::ENCODING_AC3 },
    { MimeType::AUDIO_EAC3, OHOS::AudioStandard::ENCODING_EAC3 },
    { MimeType::AUDIO_TRUEHD, OHOS::AudioStandard::ENCODING_TRUE_HD },
    { MimeType::AUDIO_DTS, OHOS::AudioStandard::ENCODING_DTS_X },
    { MimeType::AUDIO_AVS3DA, OHOS::AudioStandard::ENCODING_AUDIOVIVID_DIRECT },
};

void AudioInterruptMode2InterruptMode(AudioInterruptMode audioInterruptMode,
    OHOS::AudioStandard::InterruptMode &interruptMode)
{
    for (const auto &item : g_auInterruptMap) {
        if (item.first == audioInterruptMode) {
            interruptMode = item.second;
        }
    }
}

void UpdateSupportedSampleRate(Capability &inCaps)
{
    auto supportedSampleRateList = OHOS::AudioStandard::AudioRenderer::GetSupportedSamplingRates();
    if (!supportedSampleRateList.empty()) {
        DiscreteCapability<uint32_t> values;
        for (const auto &rate : supportedSampleRateList) {
            values.push_back(static_cast<uint32_t>(rate));
        }
        if (!values.empty()) {
            inCaps.AppendDiscreteKeys<uint32_t>(OHOS::Media::Tag::AUDIO_SAMPLE_RATE, values);
        }
    }
}

void UpdateSupportedSampleFormat(Capability &inCaps)
{
    DiscreteCapability<AudioSampleFormat> values(g_aduFmtMap.size());
    for (const auto &item : g_aduFmtMap) {
        if (std::get<1>(item) != OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH ||
            std::get<TUPLE_SECOND_ITEM_INDEX>(item) != AV_SAMPLE_FMT_NONE) {
            values.emplace_back(std::get<0>(item));
        }
    }
    inCaps.AppendDiscreteKeys(OHOS::Media::Tag::AUDIO_SAMPLE_FORMAT, values);
}

OHOS::Media::Status AudioServerSinkRegister(const std::shared_ptr<Register> &reg)
{
    AudioSinkPluginDef definition;
    definition.name = "AudioServerSink";
    definition.description = "Audio sink for audio server of media standard";
    definition.rank = 100; // 100: max rank
    auto func = [](const std::string &name) -> std::shared_ptr<AudioSinkPlugin> {
        return std::make_shared<OHOS::Media::Plugins::AudioServerSinkPlugin>(name);
    };
    definition.SetCreator(func);
    Capability inCaps(MimeType::AUDIO_RAW);
    UpdateSupportedSampleRate(inCaps);
    UpdateSupportedSampleFormat(inCaps);
    definition.AddInCaps(inCaps);
    return reg->AddPlugin(definition);
}

PLUGIN_DEFINITION(AudioServerSink, LicenseType::APACHE_V2, AudioServerSinkRegister, [] {});

inline void ResetAudioRendererParams(OHOS::AudioStandard::AudioRendererParams &param)
{
    using namespace OHOS::AudioStandard;
    param.sampleFormat = OHOS::AudioStandard::INVALID_WIDTH;
    param.sampleRate = SAMPLE_RATE_8000;
    param.channelCount = OHOS::AudioStandard::MONO;
    param.encodingType = ENCODING_INVALID;
}
constexpr int32_t CALLBACK_BUFFER_DURATION_IN_MILLISECONDS = 40;
constexpr int32_t CALLBACK_BUFFER_DURATION_IN_MILLISECONDS_100 = 100;
constexpr int32_t MS_IN_SECOND = 1000;
} // namespace

namespace OHOS {
namespace Media {
namespace Plugins {
using namespace OHOS::Media::Plugins;

AudioServerSinkPlugin::AudioRendererCallbackImpl::AudioRendererCallbackImpl(
    const std::shared_ptr<Pipeline::EventReceiver> &receiver, const bool &isPaused) : playerEventReceiver_(receiver),
    isPaused_(isPaused)
{
}

AudioServerSinkPlugin::AudioServiceDiedCallbackImpl::AudioServiceDiedCallbackImpl(
    std::shared_ptr<Pipeline::EventReceiver> &receiver) : playerEventReceiver_(receiver)
{
}

AudioServerSinkPlugin::AudioFirstFrameCallbackImpl::AudioFirstFrameCallbackImpl(
    std::shared_ptr<Pipeline::EventReceiver> &receiver, const std::weak_ptr<AudioServerSinkPlugin> &plugin)
{
    FALSE_RETURN(receiver != nullptr);
    playerEventReceiver_ = receiver;
    plugin_ = plugin;
}

void AudioServerSinkPlugin::AudioRendererCallbackImpl::OnInterrupt(
    const OHOS::AudioStandard::InterruptEvent &interruptEvent)
{
    MEDIA_LOG_D_T("OnInterrupt forceType is " PUBLIC_LOG_U32, static_cast<uint32_t>(interruptEvent.forceType));
    FALSE_RETURN_MSG(isNeedResponseCallback_, "AudioRendererCallbackImpl is not need response callback");
    if (interruptEvent.forceType == OHOS::AudioStandard::INTERRUPT_FORCE) {
        switch (interruptEvent.hintType) {
            case OHOS::AudioStandard::INTERRUPT_HINT_PAUSE:
                isPaused_ = true;
                break;
            default:
                isPaused_ = false;
                break;
        }
    }
    Event event {
        .srcFilter = "Audio interrupt event",
        .type = EventType::EVENT_AUDIO_INTERRUPT,
        .param = interruptEvent
    };
    FALSE_RETURN(playerEventReceiver_ != nullptr);
    MEDIA_LOG_D_T("OnInterrupt event upload ");
    playerEventReceiver_->OnEvent(event);
}

void AudioServerSinkPlugin::AudioRendererCallbackImpl::SetResponseCallback(bool isNeedResponseCallback)
{
    isNeedResponseCallback_ = isNeedResponseCallback;
}

void AudioServerSinkPlugin::AudioRendererCallbackImpl::OnStateChange(
    const OHOS::AudioStandard::RendererState state, const OHOS::AudioStandard::StateChangeCmdType cmdType)
{
    MEDIA_LOG_D_T("RenderState is " PUBLIC_LOG_U32, static_cast<uint32_t>(state));
    if (cmdType == AudioStandard::StateChangeCmdType::CMD_FROM_SYSTEM) {
        Event event {
            .srcFilter = "Audio state change event",
            .type = EventType::EVENT_AUDIO_STATE_CHANGE,
            .param = state
        };
        FALSE_RETURN(playerEventReceiver_ != nullptr);
        playerEventReceiver_->OnEvent(event);
    }
}

void AudioServerSinkPlugin::AudioRendererCallbackImpl::OnOutputDeviceChange(
    const AudioStandard::AudioDeviceDescriptor &deviceInfo, const AudioStandard::AudioStreamDeviceChangeReason reason)
{
    MEDIA_LOG_D_T("DeviceChange reason is " PUBLIC_LOG_D32, static_cast<int32_t>(reason));
    auto param = std::make_pair(deviceInfo, reason);
    Event event {
        .srcFilter = "Audio deviceChange change event",
        .type = EventType::EVENT_AUDIO_DEVICE_CHANGE,
        .param = param
    };
    FALSE_RETURN(playerEventReceiver_ != nullptr);
    playerEventReceiver_->OnEvent(event);
}

void AudioServerSinkPlugin::AudioFirstFrameCallbackImpl::OnFirstFrameWriting(uint64_t latency)
{
    MEDIA_LOG_I_T("OnFirstFrameWriting latency: " PUBLIC_LOG_U64, latency);
    Event event {
        .srcFilter = "Audio render first frame writing event",
        .type = EventType::EVENT_AUDIO_FIRST_FRAME,
        .param = latency
    };
    FALSE_RETURN(playerEventReceiver_ != nullptr);
    playerEventReceiver_->OnEvent(event);
    MEDIA_LOG_I_T("OnFirstFrameWriting event upload ");

    auto plugin = plugin_.lock();
    FALSE_RETURN_MSG(plugin != nullptr, "AudioServerSinkPlugin OnFirstFrameWriting plugin_ is nullptr");
    plugin->OnFirstFrameWriting();
}

void AudioServerSinkPlugin::AudioServiceDiedCallbackImpl::OnAudioPolicyServiceDied()
{
    MEDIA_LOG_I_T("OnAudioPolicyServiceDied enter");
    Event event {
        .srcFilter = "Audio service died event",
        .type = EventType::EVENT_AUDIO_SERVICE_DIED
    };
    FALSE_RETURN(playerEventReceiver_ != nullptr);
    playerEventReceiver_->OnEvent(event);
    MEDIA_LOG_I_T("OnAudioPolicyServiceDied end");
}

AudioServerSinkPlugin::AudioServerSinkPlugin(std::string name)
    : Plugins::AudioSinkPlugin(std::move(name)), audioRenderer_(nullptr)
{
    SetUpParamsSetterMap();
    SetAudioDumpBySysParam();
}

AudioServerSinkPlugin::~AudioServerSinkPlugin()
{
    MEDIA_LOG_I_T("~AudioServerSinkPlugin() entered.");
    ReleaseRender();
    ReleaseFile();
}

Status AudioServerSinkPlugin::Init()
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::Init");
    MEDIA_LOG_I_T("Init entered.");
    FALSE_RETURN_V_MSG(audioRenderer_ == nullptr, Status::OK, "audio renderer already create ");
    AudioStandard::AppInfo appInfo;
    appInfo.appPid = appPid_;
    appInfo.appUid = appUid_;
    MEDIA_LOG_I_T("Create audio renderer for apppid_ " PUBLIC_LOG_D32 " appuid_ " PUBLIC_LOG_D32
                " contentType " PUBLIC_LOG_D32 " streamUsage " PUBLIC_LOG_D32 " rendererFlags " PUBLIC_LOG_D32
                " audioInterruptMode_ " PUBLIC_LOG_U32,
                appPid_, appUid_, audioRenderInfo_.contentType, audioRenderInfo_.streamUsage,
                audioRenderInfo_.rendererFlags, static_cast<uint32_t>(audioInterruptMode_));
    rendererOptions_.rendererInfo.contentType = static_cast<AudioStandard::ContentType>(audioRenderInfo_.contentType);
    rendererOptions_.rendererInfo.streamUsage = static_cast<AudioStandard::StreamUsage>(audioRenderInfo_.streamUsage);
    rendererOptions_.rendererInfo.rendererFlags = audioRenderInfo_.rendererFlags;
    rendererOptions_.rendererInfo.volumeMode = static_cast<AudioStandard::AudioVolumeMode>(ChooseVolumeMode());
    rendererOptions_.streamInfo.samplingRate = rendererParams_.sampleRate;
    rendererOptions_.streamInfo.customSampleRate = customSampleRate_;
    if (isAudioPass_) {
        rendererOptions_.streamInfo.encoding = GetEncodingType(mimeType_);
    } else {
        rendererOptions_.streamInfo.encoding =
            mimeType_ == MimeType::AUDIO_AVS3DA ? AudioStandard::ENCODING_AUDIOVIVID : AudioStandard::ENCODING_PCM;
    }
    rendererOptions_.streamInfo.format = rendererParams_.sampleFormat;
    rendererOptions_.streamInfo.channels = rendererParams_.channelCount;
    rendererOptions_.rendererInfo.playerType = AudioStandard::PlayerType::PLAYER_TYPE_AV_PLAYER;
    rendererOptions_.privacyType = static_cast<AudioStandard::AudioPrivacyType>(privacyType_);
    MEDIA_LOG_I_T("Create audio renderer for samplingRate " PUBLIC_LOG_D32 " encoding " PUBLIC_LOG_D32
                " sampleFormat " PUBLIC_LOG_D32 " channels " PUBLIC_LOG_D32,
                rendererOptions_.streamInfo.samplingRate, rendererOptions_.streamInfo.encoding,
                rendererOptions_.streamInfo.format, rendererOptions_.streamInfo.channels);
    audioRenderer_ = AudioStandard::AudioRenderer::Create(rendererOptions_, appInfo);
    if (audioRenderer_ == nullptr && playerEventReceiver_ != nullptr) {
        playerEventReceiver_->OnEvent(
            {"audioSinkPlugin", EventType::EVENT_ERROR, MSERR_UNSUPPORT_AUD_SAMPLE_RATE, ""});
    }
    FALSE_RETURN_V(audioRenderer_ != nullptr, Status::ERROR_NULL_POINTER);
    if (audioRenderSetFlag_ && (audioRenderInfo_.streamUsage == AudioStandard::STREAM_USAGE_MUSIC ||
        audioRenderInfo_.streamUsage == AudioStandard::STREAM_USAGE_AUDIOBOOK)) {
        audioRenderer_->SetOffloadAllowed(true);
    } else {
        audioRenderer_->SetOffloadAllowed(false);
    }
    audioRenderer_->SetInterruptMode(audioInterruptMode_);
    audioRenderer_->SetSourceDuration(sourceDuraionMs_);
    return Status::OK;
}

AudioStandard::AudioEncodingType AudioServerSinkPlugin::GetEncodingType(std::string mime)
{
    auto it = mimeTypeToEncodingMap.find(mime);
    if (it != mimeTypeToEncodingMap.end()) {
        return it->second;
    }
    return AudioStandard::ENCODING_PCM;
}

void AudioServerSinkPlugin::SetAudioPassFlag(bool isAudioPass)
{
    isAudioPass_ = isAudioPass;
}

int32_t AudioServerSinkPlugin::ChooseVolumeMode()
{
    MEDIA_LOG_I_SHORT("volumeMode_ = %{public}d, audioRenderInfo_.volumeMode = %{public}d", volumeMode_,
        audioRenderInfo_.volumeMode);
    int32_t mode = static_cast<int32_t>(AudioStandard::AudioVolumeMode::AUDIOSTREAM_VOLUMEMODE_SYSTEM_GLOBAL);
    if (volumeMode_ ==
        static_cast<int32_t>(AudioStandard::AudioVolumeMode::AUDIOSTREAM_VOLUMEMODE_APP_INDIVIDUAL)) {
        mode = volumeMode_;
    } else if (audioRenderInfo_.volumeMode ==
        static_cast<int32_t>(AudioStandard::AudioVolumeMode::AUDIOSTREAM_VOLUMEMODE_APP_INDIVIDUAL)) {
        mode = audioRenderInfo_.volumeMode;
    }
    return mode;
}

AudioSampleFormat AudioServerSinkPlugin::GetSampleFormat()
{
    return static_cast<AudioSampleFormat>(rendererOptions_.streamInfo.format);
}

void AudioServerSinkPlugin::ReleaseRender()
{
    std::unique_lock<std::mutex> lock(releaseRenderMutex_);
    OHOS::Media::AutoLock renderlock(renderMutex_);
    ScopedTimer timer("ReleaseRender", RELEASE_RENDER_WARNING_MS);
    if (audioRenderer_ != nullptr && audioRenderer_->GetStatus() != AudioStandard::RendererState::RENDERER_RELEASED) {
        MEDIA_LOG_I_T("AudioRenderer::Release start");
        // ensure OnWriteData callback untied
        isReleasingRender_ = true;
        // Then release
        FALSE_RETURN_MSG(audioRenderer_->Release(), "AudioRenderer::Release failed");
        MEDIA_LOG_I_T("AudioRenderer::Release end");
    }
    audioRenderer_.reset();
}

void AudioServerSinkPlugin::ReleaseFile()
{
    if (entireDumpFile_ != nullptr) {
        (void)fclose(entireDumpFile_);
        entireDumpFile_ = nullptr;
    }
    if (sliceDumpFile_ != nullptr) {
        (void)fclose(sliceDumpFile_);
        sliceDumpFile_ = nullptr;
    }
}

Status AudioServerSinkPlugin::Deinit()
{
    MEDIA_LOG_D_T("Deinit entered");
    ReleaseRender();
    return Status::OK;
}

Status AudioServerSinkPlugin::Prepare()
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::Prepare");
    MEDIA_LOG_D_T("Prepare >>");
    auto types = AudioStandard::AudioRenderer::GetSupportedEncodingTypes();
    bool ret = CppExt::AnyOf(types.begin(), types.end(), [](AudioStandard::AudioEncodingType tmp) -> bool {
        return tmp == AudioStandard::ENCODING_PCM;
    });
    FALSE_RETURN_V_MSG(ret, Status::ERROR_INVALID_PARAMETER, "audio renderer do not support pcm encoding");
    {
        FALSE_RETURN_V(audioRenderer_ != nullptr, Status::ERROR_NULL_POINTER);
        if (audioRendererCallback_ == nullptr) {
            audioRendererCallback_ = std::make_shared<AudioRendererCallbackImpl>(playerEventReceiver_, isForcePaused_);
            audioRenderer_->SetRendererCallback(audioRendererCallback_);
            audioRenderer_->RegisterOutputDeviceChangeWithInfoCallback(audioRendererCallback_);
        }
        if (audioFirstFrameCallback_ == nullptr) {
            audioFirstFrameCallback_ = std::make_shared<AudioFirstFrameCallbackImpl>(playerEventReceiver_,
                weak_from_this());
            audioRenderer_->SetRendererFirstFrameWritingCallback(audioFirstFrameCallback_);
        }
        if (audioServiceDiedCallback_ == nullptr) {
            audioServiceDiedCallback_ = std::make_shared<AudioServiceDiedCallbackImpl>(playerEventReceiver_);
            audioRenderer_->RegisterAudioPolicyServerDiedCb(getprocpid(), audioServiceDiedCallback_);
        }
    }
    MEDIA_LOG_I_T("Prepare <<");
    return Status::OK;
}

bool AudioServerSinkPlugin::StopRender()
{
    if (audioRenderer_) {
        //The audio stop interface cannot be quickly stopped.
        if (audioRenderer_->GetStatus() == OHOS::AudioStandard::RENDERER_RUNNING) {
            MEDIA_LOG_I_T("pause entered.");
            return audioRenderer_->Pause();
        }
        FALSE_RETURN_V_MSG(audioRenderer_->GetStatus() != AudioStandard::RendererState::RENDERER_STOPPED,
            true, "AudioRenderer is already in stopped state.");
        sliceCount_++;
        return audioRenderer_->Stop();
    }
    return true;
}

Status AudioServerSinkPlugin::Reset()
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::Reset");
    MEDIA_LOG_I_T("Reset entered.");
    FALSE_RETURN_V_MSG(StopRender(), Status::ERROR_UNKNOWN, "stop render error");
    ResetAudioRendererParams(rendererParams_);
    fmtSupported_ = false;
    reSrcFfFmt_ = AV_SAMPLE_FMT_NONE;
    channels_ = 0;
    bitRate_ = 0;
    sampleRate_ = 0;
    samplesPerFrame_ = 0;
    customSampleRate_ = 0;
    needReformat_ = false;
    if (resample_) {
        resample_.reset();
    }
    return Status::OK;
}

Status AudioServerSinkPlugin::Start()
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::Start");
    MEDIA_LOG_D_T("Start entered.");
    if (audioRenderer_ == nullptr) {
        return Status::ERROR_WRONG_STATE;
    }
    ApplyAudioHapticsSyncId();
    bool ret = audioRenderer_->Start();
    if (!ret) {
        playerEventReceiver_->OnDfxEvent({"AudioServerSinkPlugin", DfxEventType::DFX_EVENT_AUDIO_ERROR, true});
    }
    FALSE_RETURN_V_MSG(ret, Status::ERROR_UNKNOWN, "AudioRenderer::Start failed");
    MEDIA_LOG_I_T("AudioRenderer::Start end");
    return Status::OK;
}

Status AudioServerSinkPlugin::Stop()
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::Stop");
    MEDIA_LOG_D_T("Stop entered.");
    FALSE_RETURN_V_MSG(StopRender(), Status::ERROR_UNKNOWN, "stop render failed");
    MEDIA_LOG_I_T("stop render success");
    return Status::OK;
}

int32_t AudioServerSinkPlugin::SetVolumeWithRamp(float targetVolume, int32_t duration)
{
    MEDIA_LOG_D_T("SetVolumeWithRamp entered.");
    int32_t ret = 0;
    {
        if (audioRenderer_ == nullptr) {
            return 0;
        }
        if (duration == 0) {
            ret = audioRenderer_->SetVolume(targetVolume);
        } else {
            MEDIA_LOG_I_T("plugin set vol AudioRenderer::SetVolumeWithRamp start");
            ret = audioRenderer_->SetVolumeWithRamp(targetVolume, duration);
            MEDIA_LOG_I_T("plugin set vol AudioRenderer::SetVolumeWithRamp end");
        }
    }
    OHOS::Media::SleepInJob(duration + 40); // fade out sleep more 40 ms
    MEDIA_LOG_I_T("SetVolumeWithRamp end.");
    return ret;
}

Status AudioServerSinkPlugin::GetParameter(std::shared_ptr<Meta> &meta)
{
    AudioStandard::AudioRendererParams params;
    meta->Set<Tag::MEDIA_BITRATE>(bitRate_);
    meta->Set<Tag::MIME_TYPE>(mimeType_);
    if (audioRenderer_ && audioRenderer_->GetParams(params) == AudioStandard::SUCCESS) {
        MEDIA_LOG_I_T("get param with fmt " PUBLIC_LOG_D32 " sampleRate " PUBLIC_LOG_D32 " channel " PUBLIC_LOG_D32
                    " encode type " PUBLIC_LOG_D32,
                    params.sampleFormat, params.sampleRate, params.channelCount, params.encodingType);
        if (params.sampleRate != rendererParams_.sampleRate) {
            MEDIA_LOG_W("samplingRate has changed from " PUBLIC_LOG_U32 " to " PUBLIC_LOG_U32,
                        rendererParams_.sampleRate, params.sampleRate);
        }
        meta->Set<Tag::AUDIO_SAMPLE_RATE>(params.sampleRate);
        if (mimeType_ == MimeType::AUDIO_FLAC && customSampleRate_ != 0) {
            MEDIA_LOG_I_SHORT("mimeType is FLAC, customSampleRate: " PUBLIC_LOG_U32, customSampleRate_);
            meta->Set<Tag::AUDIO_SAMPLE_RATE>(customSampleRate_);
        }
        if (params.sampleFormat != rendererParams_.sampleFormat) {
            MEDIA_LOG_W("sampleFormat has changed from " PUBLIC_LOG_U32 " to " PUBLIC_LOG_U32,
                        rendererParams_.sampleFormat, params.sampleFormat);
        }
        for (const auto &item : g_aduFmtMap) {
            if (std::get<1>(item) == params.sampleFormat) {
                meta->Set<Tag::AUDIO_SAMPLE_FORMAT>(std::get<0>(item));
            }
        }
        meta->Set<Tag::AUDIO_CHANNEL_COUNT>(params.channelCount);
    }
    return Status::OK;
}

bool AudioServerSinkPlugin::AssignSampleRateIfSupported(uint32_t sampleRate)
{
    sampleRate_ = sampleRate;
    auto supportedSampleRateList = OHOS::AudioStandard::AudioRenderer::GetSupportedSamplingRates();
    FALSE_RETURN_V_MSG(!supportedSampleRateList.empty(), false, "GetSupportedSamplingRates fail");
    for (const auto &rate : supportedSampleRateList) {
        if (static_cast<uint32_t>(rate) == sampleRate) {
            rendererParams_.sampleRate = rate;
            MEDIA_LOG_D_T("sampleRate: " PUBLIC_LOG_U32, rendererParams_.sampleRate);
            return true;
        }
    }
    FALSE_RETURN_V_MSG(OHOS::AudioStandard::AudioRenderer::CheckSupportedSamplingRates(sampleRate), false,
        "sampleRate is invaild %{public}d", sampleRate);
    customSampleRate_ = sampleRate;
    MEDIA_LOG_I_SHORT("customSampleRate: " PUBLIC_LOG_U32, customSampleRate_);
    return true;
}

bool AudioServerSinkPlugin::AssignChannelNumIfSupported(uint32_t channelNum)
{
    auto supportedChannelsList = OHOS::AudioStandard::AudioRenderer::GetSupportedChannels();
    FALSE_RETURN_V_MSG(!supportedChannelsList.empty(), false, "GetSupportedChannels fail");
    for (const auto &channel : supportedChannelsList) {
        if (static_cast<uint32_t>(channel) == channelNum) {
            rendererParams_.channelCount = channel;
            MEDIA_LOG_D_T("channelCount: " PUBLIC_LOG_U32, rendererParams_.channelCount);
            return true;
        }
    }
    MEDIA_LOG_E_T("channel num " PUBLIC_LOG_U32 "not supported", channelNum);
    return false;
}

bool AudioServerSinkPlugin::AssignSampleFmtIfSupported(Plugins::AudioSampleFormat sampleFormat)
{
    MEDIA_LOG_I_T("AssignSampleFmtIfSupported AudioSampleFormat " PUBLIC_LOG_D32, sampleFormat);
    const auto &item = std::find_if(g_aduFmtMap.begin(), g_aduFmtMap.end(), [&sampleFormat](const auto &tmp) -> bool {
        return std::get<0>(tmp) == sampleFormat;
    });
    auto stdFmt = std::get<1>(*item);
    if (stdFmt == OHOS::AudioStandard::AudioSampleFormat::INVALID_WIDTH) {
        if (std::get<2>(*item) == AV_SAMPLE_FMT_NONE) { // 2
            MEDIA_LOG_I_T("AssignSampleFmtIfSupported AV_SAMPLE_FMT_NONE");
            fmtSupported_ = false;
        } else {
            MEDIA_LOG_I_T("AssignSampleFmtIfSupported needReformat_");
            fmtSupported_ = true;
            needReformat_ = true;
            reSrcFfFmt_ = std::get<2>(*item); // 2
            rendererParams_.sampleFormat = reStdDestFmt_;
        }
    } else {
        auto supportedFmts = OHOS::AudioStandard::AudioRenderer::GetSupportedFormats();
        if (CppExt::AnyOf(supportedFmts.begin(), supportedFmts.end(),
                          [&stdFmt](const auto &tmp) -> bool { return tmp == stdFmt; })) {
            MEDIA_LOG_I_T("AssignSampleFmtIfSupported needReformat_ false");
            fmtSupported_ = true;
            needReformat_ = false;
        } else {
            fmtSupported_ = false;
            needReformat_ = false;
        }
        rendererParams_.sampleFormat = stdFmt;
    }
    return fmtSupported_;
}

bool AudioServerSinkPlugin::IsFormatSupported(const std::shared_ptr<Meta> &meta)
{
    FALSE_RETURN_V_MSG_E(meta != nullptr, false, "Audio format is nullptr");

    int32_t sampleRate = 0;
    FALSE_RETURN_V(meta->GetData(Tag::AUDIO_SAMPLE_RATE, sampleRate), false);
    FALSE_RETURN_V_MSG_E(AssignSampleRateIfSupported(static_cast<uint32_t>(sampleRate)), false,
        "UnSupported sampleRate %{public}d", sampleRate);

    int32_t channels = 0;
    FALSE_RETURN_V(meta->GetData(Tag::AUDIO_OUTPUT_CHANNELS, channels), false);
    FALSE_RETURN_V_MSG_E(AssignChannelNumIfSupported(static_cast<uint32_t>(channels)), false,
        "UnSupported channel count %{public}d", channels);

    int32_t sampleFormat = 0;
    FALSE_RETURN_V(meta->GetData(Tag::AUDIO_SAMPLE_FORMAT, sampleFormat), false);
    FALSE_RETURN_V_MSG_E(AssignSampleFmtIfSupported(static_cast<Plugins::AudioSampleFormat>(sampleFormat)), false,
        "UnSupported sampleFormat %{public}d", sampleFormat);
    return true;
}

void AudioServerSinkPlugin::SetInterruptMode(AudioStandard::InterruptMode interruptMode)
{
    if (audioRenderer_) {
        audioRenderer_->SetInterruptMode(interruptMode);
    }
}

void AudioServerSinkPlugin::SetUpParamsSetterMap()
{
    SetUpMimeTypeSetter();
    SetUpSampleRateSetter();
    SetUpAudioOutputChannelsSetter();
    SetUpMediaBitRateSetter();
    SetUpAudioSampleFormatSetter();
    SetUpAudioOutputChannelLayoutSetter();
    SetUpAudioSamplePerFrameSetter();
    SetUpBitsPerCodedSampleSetter();
    SetUpMediaSeekableSetter();
    SetUpAppPidSetter();
    SetUpAppUidSetter();
    SetUpAudioRenderInfoSetter();
    SetPrivacyType();
    SetUpAudioRenderSetFlagSetter();
    SetUpAudioInterruptModeSetter();
    SetUpAudioRenderSourceDurationSetter();
}

void AudioServerSinkPlugin::SetUpMimeTypeSetter()
{
    paramsSetterMap_[Tag::MIME_TYPE] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<std::string>(para), Status::ERROR_MISMATCHED_TYPE,
                             "mimeType type should be string");
        mimeType_ = AnyCast<std::string>(para);
        MEDIA_LOG_I_T("Set mimeType: " PUBLIC_LOG_S, mimeType_.c_str());
        return Status::OK;
    };
}

void AudioServerSinkPlugin::SetUpSampleRateSetter()
{
    paramsSetterMap_[Tag::AUDIO_SAMPLE_RATE] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int32_t>(para), Status::ERROR_MISMATCHED_TYPE,
                             "sample rate type should be int32_t");
        if (!AssignSampleRateIfSupported(AnyCast<int32_t>(para))) {
            MEDIA_LOG_E_T("sampleRate isn't supported");
            playerEventReceiver_->OnEvent({"sampleRate isn't supported",
                EventType::EVENT_ERROR, MSERR_UNSUPPORT_AUD_SAMPLE_RATE, "sample_rate"});
            return Status::ERROR_INVALID_PARAMETER;
        }
        return Status::OK;
    };
}

void AudioServerSinkPlugin::SetUpAudioOutputChannelsSetter()
{
    paramsSetterMap_[Tag::AUDIO_OUTPUT_CHANNELS] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int32_t>(para), Status::ERROR_MISMATCHED_TYPE,
                             "channels type should be int32_t");
        channels_ = AnyCast<uint32_t>(para);
        MEDIA_LOG_I_T("Set outputChannels: " PUBLIC_LOG_U32, channels_);
        if (!AssignChannelNumIfSupported(channels_)) {
            MEDIA_LOG_E_T("channel isn't supported");
            playerEventReceiver_->OnEvent({"channel isn't supported",
                EventType::EVENT_ERROR, MSERR_UNSUPPORT_AUD_CHANNEL_NUM, "channel_num"});
            return Status::ERROR_INVALID_PARAMETER;
        }
        return Status::OK;
    };
}

void AudioServerSinkPlugin::SetUpMediaBitRateSetter()
{
    paramsSetterMap_[Tag::MEDIA_BITRATE] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int64_t>(para), Status::ERROR_MISMATCHED_TYPE,
                             "bit rate type should be int64_t");
        bitRate_ = AnyCast<int64_t>(para);
        return Status::OK;
    };
}
void AudioServerSinkPlugin::SetUpAudioSampleFormatSetter()
{
    paramsSetterMap_[Tag::AUDIO_SAMPLE_FORMAT] = [this](const ValueType &para) {
        MEDIA_LOG_I_T("SetUpAudioSampleFormat");
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<AudioSampleFormat>(para), Status::ERROR_MISMATCHED_TYPE,
                             "AudioSampleFormat type should be AudioSampleFormat");
        if (!AssignSampleFmtIfSupported(AnyCast<AudioSampleFormat>(para))) {
            MEDIA_LOG_E_T("sampleFmt isn't supported by audio renderer or resample lib");
            playerEventReceiver_->OnEvent({"sampleFmt isn't supported",
                EventType::EVENT_ERROR, MSERR_UNSUPPORT_AUD_PARAMS, "sample_format"});
            return Status::ERROR_INVALID_PARAMETER;
        }
        return Status::OK;
    };
}
void AudioServerSinkPlugin::SetUpAudioOutputChannelLayoutSetter()
{
    paramsSetterMap_[Tag::AUDIO_OUTPUT_CHANNEL_LAYOUT] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<AudioChannelLayout>(para), Status::ERROR_MISMATCHED_TYPE,
                             "channel layout type should be AudioChannelLayout");
        channelLayout_ = AnyCast<AudioChannelLayout>(para);
        MEDIA_LOG_I_T("Set outputChannelLayout: " PUBLIC_LOG_U64, channelLayout_);
        return Status::OK;
    };
}
void AudioServerSinkPlugin::SetUpAudioSamplePerFrameSetter()
{
    paramsSetterMap_[Tag::AUDIO_SAMPLE_PER_FRAME] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int32_t>(para), Status::ERROR_MISMATCHED_TYPE,
                             "SAMPLE_PER_FRAME type should be int32_t");
        samplesPerFrame_ = AnyCast<uint32_t>(para);
        return Status::OK;
    };
}
void AudioServerSinkPlugin::SetUpBitsPerCodedSampleSetter()
{
    paramsSetterMap_[Tag::AUDIO_BITS_PER_CODED_SAMPLE] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int32_t>(para), Status::ERROR_MISMATCHED_TYPE,
                             "BITS_PER_CODED_SAMPLE type should be int32_t");
        bitsPerSample_ = AnyCast<uint32_t>(para);
        return Status::OK;
    };
}
void AudioServerSinkPlugin::SetUpMediaSeekableSetter()
{
    paramsSetterMap_[Tag::MEDIA_SEEKABLE] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<Seekable>(para), Status::ERROR_MISMATCHED_TYPE,
                             "MEDIA_SEEKABLE type should be Seekable");
        seekable_ = AnyCast<Plugins::Seekable>(para);
        return Status::OK;
    };
}
void AudioServerSinkPlugin::SetUpAppPidSetter()
{
    paramsSetterMap_[Tag::APP_PID] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int32_t>(para), Status::ERROR_MISMATCHED_TYPE,
                             "APP_PID type should be int32_t");
        appPid_ = AnyCast<int32_t>(para);
        return Status::OK;
    };
}
void AudioServerSinkPlugin::SetUpAppUidSetter()
{
    paramsSetterMap_[Tag::APP_UID] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int32_t>(para), Status::ERROR_MISMATCHED_TYPE,
                             "APP_UID type should be int32_t");
        appUid_ = AnyCast<int32_t>(para);
        return Status::OK;
    };
}
void AudioServerSinkPlugin::SetUpAudioRenderInfoSetter()
{
    paramsSetterMap_[Tag::AUDIO_RENDER_INFO] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<AudioRenderInfo>(para), Status::ERROR_MISMATCHED_TYPE,
                             "AUDIO_RENDER_INFO type should be AudioRenderInfo");
        audioRenderInfo_ = AnyCast<AudioRenderInfo>(para);
        return Status::OK;
    };
}

void AudioServerSinkPlugin::SetPrivacyType()
{
    paramsSetterMap_["PRIVACY_TYPE"] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int32_t>(para), Status::ERROR_MISMATCHED_TYPE,
                             "PRIVACY_TYPE type should be int32_t");
        privacyType_ = AnyCast<int32_t>(para);
        return Status::OK;
    };
}

void AudioServerSinkPlugin::SetUpAudioRenderSetFlagSetter()
{
    paramsSetterMap_[Tag::AUDIO_RENDER_SET_FLAG] = [this](const ValueType &para) {
        if (!Any::IsSameTypeWith<bool>(para)) {
            MEDIA_LOG_E_T("AUDIO_RENDER_SET_FLAG type should be bool");
            playerEventReceiver_->OnEvent({"AUDIO_RENDER_SET_FLAG type is not bool",
                EventType::EVENT_ERROR, MSERR_EXT_API9_INVALID_PARAMETER});
            return Status::ERROR_MISMATCHED_TYPE;
        }
        audioRenderSetFlag_ = AnyCast<bool>(para);
        return Status::OK;
    };
}

void AudioServerSinkPlugin::SetUpAudioInterruptModeSetter()
{
    paramsSetterMap_[Tag::AUDIO_INTERRUPT_MODE] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int32_t>(para), Status::ERROR_MISMATCHED_TYPE,
            "AUDIO_INTERRUPT_MODE type should be int32_t");
        AudioInterruptMode2InterruptMode(AnyCast<AudioInterruptMode>(para), audioInterruptMode_);
        SetInterruptMode(audioInterruptMode_);
        return Status::OK;
    };
}

void AudioServerSinkPlugin::SetUpAudioRenderSourceDurationSetter()
{
    paramsSetterMap_[Tag::MEDIA_DURATION] = [this](const ValueType &para) {
        FALSE_RETURN_V_MSG_E(Any::IsSameTypeWith<int64_t>(para), Status::ERROR_MISMATCHED_TYPE,
            "MEDIA_DURATION type should be int64_t");
        sourceDuraionMs_ = AnyCast<int64_t>(para);
        return Status::OK;
    };
}

Status AudioServerSinkPlugin::SetParameter(const std::shared_ptr<Meta> &meta)
{
    for (MapIt iter = meta->begin(); iter != meta->end(); iter++) {
        MEDIA_LOG_D_T("SetParameter iter->first " PUBLIC_LOG_S, iter->first.c_str());
        if (paramsSetterMap_.find(iter->first) == paramsSetterMap_.end()) {
            continue;
        }
        std::function<Status(const ValueType &para)> paramSetter = paramsSetterMap_[iter->first];
        paramSetter(iter->second);
    }
    return Status::OK;
}

Status AudioServerSinkPlugin::GetVolume(float &volume)
{
    MEDIA_LOG_I_T("GetVolume entered.");
    if (audioRenderer_ != nullptr) {
        volume = audioRenderer_->GetVolume();
        return Status::OK;
    }
    return Status::ERROR_WRONG_STATE;
}

Status AudioServerSinkPlugin::SetVolume(float volume)
{
    MEDIA_LOG_D("SetVolume entered.");
    if (audioRenderer_ != nullptr) {
        int32_t ret = audioRenderer_->SetVolume(volume);
        FALSE_RETURN_V_MSG_E(ret == OHOS::AudioStandard::SUCCESS, Status::ERROR_UNKNOWN,
            "set volume failed with code " PUBLIC_LOG_D32, ret);
        MEDIA_LOG_D("SetVolume succ");
        audioRendererVolume_ = volume;
        return Status::OK;
    }
    return Status::ERROR_WRONG_STATE;
}

Status AudioServerSinkPlugin::SetVolumeMode(int32_t mode)
{
    MEDIA_LOG_D("SetVolumeMode entered. mode = %{public}d", mode);
    volumeMode_ = mode;
    return Status::OK;
}

Status AudioServerSinkPlugin::GetAudioEffectMode(int32_t &effectMode)
{
    MEDIA_LOG_I_T("GetAudioEffectMode entered.");
    if (audioRenderer_ != nullptr) {
        effectMode = audioRenderer_->GetAudioEffectMode();
        MEDIA_LOG_I_T("GetAudioEffectMode %{public}d", effectMode);
        return Status::OK;
    }
    return Status::ERROR_WRONG_STATE;
}

Status AudioServerSinkPlugin::SetAudioEffectMode(int32_t effectMode)
{
    MEDIA_LOG_I_T("SetAudioEffectMode %{public}d", effectMode);
    if (audioRenderer_ != nullptr) {
        int32_t ret = audioRenderer_->SetAudioEffectMode(static_cast<OHOS::AudioStandard::AudioEffectMode>(effectMode));
        FALSE_RETURN_V_MSG(ret == OHOS::AudioStandard::SUCCESS, Status::ERROR_UNKNOWN,
            "set AudioEffectMode failed with code " PUBLIC_LOG_D32, ret);
        return Status::OK;
    }
    return Status::ERROR_WRONG_STATE;
}

Status AudioServerSinkPlugin::GetSpeed(float &speed)
{
    MEDIA_LOG_I_T("GetSpeed entered.");
    if (audioRenderer_ != nullptr) {
        speed = audioRenderer_->GetSpeed();
        return Status::OK;
    }
    return Status::ERROR_WRONG_STATE;
}

Status AudioServerSinkPlugin::SetSpeed(float speed)
{
    MEDIA_LOG_I_T("SetSpeed entered.");
    if (audioRenderer_ != nullptr) {
        int32_t ret = audioRenderer_->SetSpeed(speed);
        FALSE_RETURN_V_MSG(ret == OHOS::AudioStandard::SUCCESS, Status::ERROR_UNKNOWN,
            "set speed failed with code " PUBLIC_LOG_D32, ret);
        return Status::OK;
    }
    return Status::ERROR_WRONG_STATE;
}

Status AudioServerSinkPlugin::Resume()
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::Resume");
    MEDIA_LOG_D_T("Resume entered");
    return Start();
}

Status AudioServerSinkPlugin::Pause()
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::Pause");
    MEDIA_LOG_I_T("Pause entered");
    OHOS::Media::AutoLock renderlock(renderMutex_);
    FALSE_RETURN_V_MSG(audioRenderer_ != nullptr, Status::ERROR_UNKNOWN, "audio renderer pause fail");
    FALSE_RETURN_V_MSG(audioRenderer_->GetStatus() == OHOS::AudioStandard::RENDERER_RUNNING,
        Status::OK, "audio renderer no need pause");
    sliceCount_++;
    FALSE_RETURN_V_MSG_W(audioRenderer_->Pause(), Status::ERROR_UNKNOWN, "renderer pause fail.");
    MEDIA_LOG_I_T("audio renderer pause success");
    return Status::OK;
}

Status AudioServerSinkPlugin::PauseTransitent()
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::PauseTransitent");
    MEDIA_LOG_I_T("PauseTransitent entered.");
    OHOS::Media::AutoLock renderlock(renderMutex_);
    FALSE_RETURN_V_MSG(audioRenderer_ != nullptr, Status::ERROR_UNKNOWN, "audio renderer pauseTransitent fail");
    FALSE_RETURN_V_MSG(audioRenderer_->GetStatus() == OHOS::AudioStandard::RENDERER_RUNNING,
        Status::OK, "audio renderer no need pauseTransitent");
    sliceCount_++;
    FALSE_RETURN_V_MSG_W(audioRenderer_->PauseTransitent(), Status::ERROR_UNKNOWN, "renderer pauseTransitent fail.");
    MEDIA_LOG_I_T("audio renderer pauseTransitent success");
    return Status::OK;
}

Status AudioServerSinkPlugin::GetLatency(uint64_t &hstTime)
{
    FALSE_RETURN_V(audioRenderer_ != nullptr, Status::ERROR_NULL_POINTER);
    audioRenderer_->GetLatency(hstTime); // audioRender->getLatency lack accuracy
    return Status::OK;
}

Status AudioServerSinkPlugin::DrainCacheData(bool render)
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::DrainCacheData " + std::to_string(render));
    if (!render) {
        MEDIA_LOG_D("Drop cache buffer because render=false");
        cachedBuffers_.clear();
        return Status::OK;
    }
    if (cachedBuffers_.empty()) {
        return Status::OK;
    }
    AudioStandard::RendererState rendererState = (audioRenderer_ != nullptr) ?
        audioRenderer_->GetStatus() : AudioStandard::RendererState::RENDERER_INVALID;
    FALSE_RETURN_V_MSG(rendererState != AudioStandard::RendererState::RENDERER_PAUSED
        && rendererState != AudioStandard::RendererState::RENDERER_STOPPED,
        Status::ERROR_AGAIN, "audioRenderer_ is still paused or stopped, try again later");
    if (rendererState != AudioStandard::RendererState::RENDERER_RUNNING) {
        cachedBuffers_.clear();
        MEDIA_LOG_W("Drop cache buffer because audioRenderer_ state invalid");
        return Status::ERROR_UNKNOWN;
    }
    while (cachedBuffers_.size() > 0) { // do drain cache buffers
        auto currBuffer = cachedBuffers_.front();
        uint8_t* destBuffer = currBuffer.data();
        size_t destLength = currBuffer.size();
        bool shouldDrop = false;
        size_t remained = WriteAudioBuffer(destBuffer, destLength, shouldDrop);
        if (remained == 0) { // write ok
            cachedBuffers_.pop_front();
            continue;
        }
        if (shouldDrop) { // write error and drop buffer
            cachedBuffers_.clear();
            MEDIA_LOG_W("Drop cache buffer, error happens during drain");
            return Status::ERROR_UNKNOWN;
        }
        if (remained < destLength) { // some data written, then audioRender paused again, update cache
            std::vector<uint8_t> tmpBuffer(destBuffer + destLength - remained, destBuffer + destLength);
            cachedBuffers_.pop_front();
            cachedBuffers_.emplace_front(std::move(tmpBuffer));
        } // else no data written, no need to update front cache
        MEDIA_LOG_W("Audiorender pause again during drain cache buffers");
        return Status::ERROR_AGAIN;
    }
    MEDIA_LOG_I("Drain cache buffer success");
    return Status::OK;
}

void AudioServerSinkPlugin::CacheData(uint8_t* inputBuffer, size_t bufferSize)
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::CacheData " + std::to_string(bufferSize));
    std::vector<uint8_t> tmpBuffer(inputBuffer, inputBuffer + bufferSize);
    cachedBuffers_.emplace_back(std::move(tmpBuffer));
    MEDIA_LOG_I("Cache one audio buffer, data size is " PUBLIC_LOG_U64, bufferSize);
    while (cachedBuffers_.size() > DEFAULT_BUFFER_NUM) {
        auto dropSize = cachedBuffers_.front().size();
        MEDIA_LOG_W("Drop one cached buffer size " PUBLIC_LOG_U64 " because max cache size reached.", dropSize);
        cachedBuffers_.pop_front();
    }
}

size_t AudioServerSinkPlugin::WriteAudioBuffer(uint8_t* inputBuffer, size_t bufferSize, bool& shouldDrop)
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::WriteAudioBuffer-size:" + std::to_string(bufferSize));
    uint8_t* destBuffer = inputBuffer;
    size_t destLength = bufferSize;
    while (destLength > 0) {
        MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::WriteAudioBuffer: " + std::to_string(destLength));
        auto systemTimeBeforeWriteMs = Plugins::GetCurrentMillisecond();
        int32_t ret = audioRenderer_->Write(destBuffer, destLength);
        writeDuration_ = std::max(Plugins::GetCurrentMillisecond() - systemTimeBeforeWriteMs, writeDuration_);
        if (ret < 0) {
            AudioStandard::RendererState rendererState = (audioRenderer_ != nullptr) ?
                audioRenderer_->GetStatus() : AudioStandard::RendererState::RENDERER_INVALID;
            if (rendererState == AudioStandard::RendererState::RENDERER_PAUSED ||
                rendererState == AudioStandard::RendererState::RENDERER_STOPPED) {
                MEDIA_LOG_W("WriteAudioBuffer error because audioRenderer_ paused or stopped, cache data.");
                shouldDrop = false;
            } else {
                MEDIA_LOG_W("WriteAudioBuffer error because audioRenderer_ error, drop data.");
                shouldDrop = true;
            }
            break;
        } else if (static_cast<size_t>(ret) < destLength) {
            std::unique_lock<std::mutex> lock(mutex_);
            auto waitStatus = writeCond_.wait_for(
                lock, std::chrono::milliseconds(WRITE_WAIT_TIME), [&] { return isInterruptNeeded_.load(); });
            if (waitStatus) {
                shouldDrop = true;
                break;
            }
        }
        if (static_cast<size_t>(ret) > destLength) {
            MEDIA_LOG_W("audioRenderer_ return ret " PUBLIC_LOG_D32 "> destLength " PUBLIC_LOG_U64,
                ret, destLength);
            ret = static_cast<int32_t>(destLength);
        }
        destBuffer += ret;
        destLength -= static_cast<size_t>(ret);
        MEDIA_LOG_DD("Written data size " PUBLIC_LOG_D32 ", bufferSize " PUBLIC_LOG_U64, ret, bufferSize);
    }
    return destLength;
}

Status AudioServerSinkPlugin::Write(const std::shared_ptr<OHOS::Media::AVBuffer> &inputBuffer)
{
    MEDIA_LOG_D_SHORT("Write buffer to audio framework");
    FALSE_RETURN_V_MSG_W(inputBuffer != nullptr && inputBuffer->memory_ != nullptr &&
        inputBuffer->memory_->GetSize() != 0, Status::OK, "Receive empty buffer."); // return ok
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::Write, bufferSize: "
        + std::to_string(inputBuffer->memory_->GetSize()));
    int32_t ret = 0;
    if (mimeType_ == MimeType::AUDIO_AVS3DA) {
        ret = WriteAudioVivid(inputBuffer);
        return ret >= 0 ? Status::OK : Status::ERROR_UNKNOWN;
    }
    auto mem = inputBuffer->memory_;
    auto srcBuffer = mem->GetAddr();
    auto destBuffer = const_cast<uint8_t *>(srcBuffer);
    auto srcLength = mem->GetSize();
    size_t destLength = static_cast<size_t>(srcLength);
    while (isForcePaused_ && seekable_ == Seekable::SEEKABLE && !isInterruptNeeded_.load()) {
        std::unique_lock<std::mutex> lock(mutex_);
        writeCond_.wait_for(
            lock, std::chrono::milliseconds(WRITE_WAIT_TIME), [&] { return isInterruptNeeded_.load(); });
    }
    FALSE_RETURN_V_MSG(!isInterruptNeeded_.load(), Status::OK, "Write isInterrupt");
    if (audioRenderer_ == nullptr) {
        DrainCacheData(false);
        return Status::ERROR_NULL_POINTER;
    }
    auto drainCacheRet = DrainCacheData(true);
    if (drainCacheRet != Status::OK) {
        if (drainCacheRet == Status::ERROR_AGAIN) {
            CacheData(destBuffer, destLength);
        }
        return Status::ERROR_UNKNOWN;
    }
    bool shouldDrop = false;
    size_t remained = WriteAudioBuffer(destBuffer, destLength, shouldDrop);
    if (remained == 0) {
        return Status::OK;
    }
    if (!shouldDrop) {
        CacheData(destBuffer + destLength - remained, remained);
    }
    return Status::ERROR_UNKNOWN;
}

int32_t AudioServerSinkPlugin::WriteAudioVivid(const std::shared_ptr<OHOS::Media::AVBuffer> &inputBuffer)
{
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::WriteAudioVivid");
    auto mem = inputBuffer->memory_;
    auto pcmBuffer = mem->GetAddr();
    auto pcmBufferSize = mem->GetSize();
    auto meta = inputBuffer->meta_;
    std::vector<uint8_t> metaData;
    meta->GetData(Tag::OH_MD_KEY_AUDIO_VIVID_METADATA, metaData);
    FALSE_RETURN_V(audioRenderer_ != nullptr, -1);
    return audioRenderer_->Write(pcmBuffer, pcmBufferSize, metaData.data(), metaData.size());
}

Status AudioServerSinkPlugin::Flush()
{
    MEDIA_LOG_D_SHORT("Flush entered.");
    DrainCacheData(false);
    if (audioRenderer_ == nullptr) {
        return Status::ERROR_WRONG_STATE;
    }
    if (audioRenderer_->Flush()) {
        MEDIA_LOG_D_T("flush renderer success");
        return Status::OK;
    }
    MEDIA_LOG_E_T("flush renderer fail");
    return Status::ERROR_UNKNOWN;
}

Status AudioServerSinkPlugin::Drain()
{
    MEDIA_LOG_I_T("Drain entered.");
    if (audioRenderer_ == nullptr) {
        DrainCacheData(false);
        return Status::ERROR_WRONG_STATE;
    }
    DrainCacheData(true); // try to drain
    cachedBuffers_.clear(); // force clear cached data, no matter drain success or not
    if (!audioRenderer_->Drain()) {
        uint64_t latency = 0;
        audioRenderer_->GetLatency(latency);
        latency /= 1000;    // 1000 cast into ms
        if (latency > 50) { // 50 latency too large
            MEDIA_LOG_W("Drain failed and latency is too large, will sleep " PUBLIC_LOG_U64 " ms, aka. latency.",
                        latency);
            OHOS::Media::SleepInJob(latency);
        }
    }
    MEDIA_LOG_I_T("drain renderer success");
    return Status::OK;
}

int64_t AudioServerSinkPlugin::GetPlayedOutDurationUs(int64_t nowUs)
{
    FALSE_RETURN_V(audioRenderer_ != nullptr && (rendererParams_.sampleRate != 0 || customSampleRate_ != 0), -1);
    int64_t numFramesPlayed = 0;
    AudioStandard::Timestamp ts;
    bool res = audioRenderer_->GetAudioTime(ts, AudioStandard::Timestamp::Timestampbase::MONOTONIC);
    if (res) {
        numFramesPlayed = ts.framePosition;
    }
    return numFramesPlayed;
}

Status AudioServerSinkPlugin::GetFramePosition(int32_t &framePosition)
{
    AudioStandard::Timestamp ts;
    if (audioRenderer_ == nullptr) {
        return Status::ERROR_WRONG_STATE;
    }
    bool res = audioRenderer_->GetAudioTime(ts, AudioStandard::Timestamp::Timestampbase::MONOTONIC);
    if (!res) {
        return Status::ERROR_UNKNOWN;
    }
    framePosition = static_cast<int32_t>(ts.framePosition);
    return Status::OK;
}

void AudioServerSinkPlugin::SetEventReceiver(const std::shared_ptr<Pipeline::EventReceiver>& receiver)
{
    FALSE_RETURN(receiver != nullptr);
    playerEventReceiver_ = receiver;
}

void AudioServerSinkPlugin::SetAudioDumpBySysParam()
{
    std::string dumpAllEnable;
    enableEntireDump_ = false;
    int32_t dumpAllRes = OHOS::system::GetStringParameter("sys.media.sink.entiredump.enable", dumpAllEnable, "");
    if (dumpAllRes == 0 && !dumpAllEnable.empty() && dumpAllEnable == "true") {
        enableEntireDump_ = true;
    }
    std::string dumpSliceEnable;
    enableDumpSlice_ = false;
    int32_t sliceDumpRes = OHOS::system::GetStringParameter("sys.media.sink.slicedump.enable", dumpSliceEnable, "");
    if (sliceDumpRes == 0 && !dumpSliceEnable.empty() && dumpSliceEnable == "true") {
        enableDumpSlice_ = true;
    }
    MEDIA_LOG_D_T("sys.media.sink.entiredump.enable: " PUBLIC_LOG_S ", sys.media.sink.slicedump.enable: "
        PUBLIC_LOG_S, dumpAllEnable.c_str(), dumpSliceEnable.c_str());
}

void AudioServerSinkPlugin::DumpEntireAudioBuffer(uint8_t* buffer, const size_t& bytesSingle)
{
    if (!enableEntireDump_) {
        return;
    }

    if (entireDumpFile_ == nullptr) {
        std::string path = "data/media/audio-sink-entire.pcm";
        entireDumpFile_ = fopen(path.c_str(), "wb+");
    }
    if (entireDumpFile_ == nullptr) {
        return;
    }
    (void)fwrite(buffer, bytesSingle, 1, entireDumpFile_);
    (void)fflush(entireDumpFile_);
}

void AudioServerSinkPlugin::DumpSliceAudioBuffer(uint8_t* buffer, const size_t& bytesSingle)
{
    if (!enableDumpSlice_) {
        return;
    }

    if (curCount_ != sliceCount_) {
        curCount_ = sliceCount_;
        if (sliceDumpFile_ != nullptr) {
            (void)fclose(sliceDumpFile_);
        }
        std::string path = "data/media/audio-sink-slice-" + std::to_string(sliceCount_) + ".pcm";
        sliceDumpFile_ = fopen(path.c_str(), "wb+");
    }
    if (sliceDumpFile_ == nullptr) {
        return;
    }
    (void)fwrite(buffer, bytesSingle, 1, sliceDumpFile_);
    (void)fflush(sliceDumpFile_);
}

Status AudioServerSinkPlugin::SetMuted(bool isMuted)
{
    FALSE_RETURN_V(audioRenderer_ != nullptr, Status::ERROR_NULL_POINTER);
    MEDIA_LOG_D("SetMuted in");
    audioRenderer_->SetSilentModeAndMixWithOthers(isMuted);
    MEDIA_LOG_I("SetMuted out");
    return Status::OK;
}

int64_t AudioServerSinkPlugin::GetWriteDurationMs()
{
    int64_t writeDuration = writeDuration_;
    writeDuration_ = 0;
    return writeDuration;
}

void AudioServerSinkPlugin::Freeze()
{
    FALSE_RETURN_NOLOG(audioRenderWriteCallback_ != nullptr);
    MEDIA_LOG_I("NotifyFreeze");
    audioRenderWriteCallback_->NotifyFreeze();
}

void AudioServerSinkPlugin::UnFreeze()
{
    FALSE_RETURN_NOLOG(audioRenderWriteCallback_ != nullptr);
    MEDIA_LOG_I("NotifyUnFreeze");
    audioRenderWriteCallback_->NotifyUnFreeze();
}

AudioServerSinkPlugin::AudioRendererWriteCallbackImpl::AudioRendererWriteCallbackImpl(
    const std::weak_ptr<AudioServerSinkPlugin> &plugin): plugin_(plugin)
{
}

void AudioServerSinkPlugin::AudioRendererWriteCallbackImpl::OnWriteData(size_t length)
{
    {
        std::unique_lock<std::mutex> lock(freezeMutex_);
        if (isFrozen_) {
            freezeCond_.wait(lock, [this] {
                return !isFrozen_ || isInterruptNeeded_;
            });
        }
    }
    auto plugin = plugin_.lock();
    FALSE_RETURN_MSG(plugin != nullptr, "AudioServerSinkPlugin OnWriteData plugin_ is nullptr");
    plugin->OnWriteData(length);
}

void AudioServerSinkPlugin::AudioRendererWriteCallbackImpl::NotifyFreeze()
{
    std::unique_lock<std::mutex> lock(freezeMutex_);
    isFrozen_ = true;
}

void AudioServerSinkPlugin::AudioRendererWriteCallbackImpl::NotifyUnFreeze()
{
    std::unique_lock<std::mutex> lock(freezeMutex_);
    MEDIA_LOG_I("NotifyUnFreeze");
    isFrozen_ = false;
    freezeCond_.notify_all();
}

void AudioServerSinkPlugin::AudioRendererWriteCallbackImpl::NotifyInterrupt(bool isInterruptNeeded)
{
    std::unique_lock<std::mutex> lock(freezeMutex_);
    MEDIA_LOG_I("NotifyInterrupt");
    isInterruptNeeded_ = isInterruptNeeded;
    freezeCond_.notify_all();
}

Status AudioServerSinkPlugin::MuteAudioBuffer(uint8_t *addr, size_t offset, size_t length)
{
    FALSE_RETURN_V_MSG(audioRenderer_ != nullptr, Status::ERROR_UNKNOWN, "audioRender_ is nullptr");
    MediaAVCodec::AVCodecTrace trace("AudioServerSinkPlugin::MuteAudioBuffer");
    FALSE_RETURN_V_MSG(addr != nullptr, Status::ERROR_UNKNOWN, "addr is nullptr");
    int32_t ret = audioRenderer_->MuteAudioBuffer(addr, offset, length, rendererOptions_.streamInfo.format);
    FALSE_RETURN_V_MSG(ret == AudioStandard::SUCCESS, Status::ERROR_UNKNOWN,
        "MuteAudioBuffer failed, ret=" PUBLIC_LOG_D32, ret);
    return Status::OK;
}

Status AudioServerSinkPlugin::EnqueueBufferDesc(const AudioStandard::BufferDesc &bufferDesc)
{
    FALSE_RETURN_V_MSG(audioRenderer_ != nullptr, Status::ERROR_UNKNOWN, "Enqueue audioRender_ is nullptr");
    int32_t ret = 0;
    if (bufferDesc.dataLength == 0) {
        if (enqueueNumber_++ < ON_WRITE_ZERO_COUNT && ((enqueueNumber_ & (LOG_PRINT_LIMIT - 1)) == 0)) {
            MEDIA_LOG_I("dataLength = 0, count:" PUBLIC_LOG_U64, enqueueNumber_);
        }
    } else {
        enqueueNumber_ = 0;
    }
    ret = audioRenderer_->Enqueue(bufferDesc);
    MEDIA_LOG_DD("EnqueueBufferDesc out");
    FALSE_RETURN_V_MSG(ret == AudioStandard::SUCCESS, Status::ERROR_UNKNOWN,
        "Enqueue BufferDesc failed, ret=" PUBLIC_LOG_D32, ret);
    return Status::OK;
}

Status AudioServerSinkPlugin::GetBufferDesc(AudioStandard::BufferDesc &bufferDesc)
{
    FALSE_RETURN_V_MSG(audioRenderer_ != nullptr, Status::ERROR_UNKNOWN, "GetBufferDesc audioRender_ is nullptr");
    int32_t ret = 0;
    ret = audioRenderer_->GetBufferDesc(bufferDesc);
    FALSE_RETURN_V_MSG(ret == AudioStandard::SUCCESS, Status::ERROR_UNKNOWN,
        "Get BufferDesc failed, ret=" PUBLIC_LOG_D32, ret);
    return Status::OK;
}

int32_t AudioServerSinkPlugin::GetCallbackBufferDuration()
{
    FALSE_RETURN_V(mimeType_ != MimeType::AUDIO_AVS3DA, -1);
    FALSE_RETURN_V_MSG(sampleRate_ > 0, -1, "Can not calculate callback buffer size because sampleRate <= 0.");
    return GetAvailableBufferDuration(customSampleRate_);
}

Status AudioServerSinkPlugin::SetRequestDataCallback(const std::shared_ptr<AudioSinkDataCallback> &callback)
{
    FALSE_RETURN_V_MSG(audioRenderWriteCallback_ == nullptr, Status::ERROR_UNKNOWN,
        "audiorender callback has been set.");
    FALSE_RETURN_V_MSG(callback != nullptr && audioRenderer_ != nullptr, Status::ERROR_UNKNOWN,
        "audiorender callback set failed");
    audioSinkDataCallback_ = callback;
    isAudioVivid_ = mimeType_ == MimeType::AUDIO_AVS3DA;
    audioRenderWriteCallback_ = std::make_shared<AudioRendererWriteCallbackImpl>(shared_from_this());
    int32_t ret = 0;
    ret = audioRenderer_->SetRenderMode(AudioStandard::RENDER_MODE_CALLBACK);
    FALSE_RETURN_V_MSG(ret == AudioStandard::SUCCESS, Status::ERROR_UNKNOWN, "audioRender_->SetRenderMode fail.");
    ret = audioRenderer_->SetRendererWriteCallback(audioRenderWriteCallback_);
    FALSE_RETURN_V_MSG(ret == AudioStandard::SUCCESS, Status::ERROR_UNKNOWN,
        "audioRender_->SetRenderWriteCallback fail.");
    int32_t callbackBufferDuration = GetCallbackBufferDuration();
    FALSE_RETURN_V_MSG_W(callbackBufferDuration > 0, Status::OK,
        "minetype is audioVivid");
    audioRenderer_->SetBufferDuration(callbackBufferDuration);
    MEDIA_LOG_I("Set Preferred duration is " PUBLIC_LOG_D32 " ms", callbackBufferDuration);
    return Status::OK;
}

int32_t AudioServerSinkPlugin::GetAvailableBufferDuration(uint32_t customSampleRate)
{
    FALSE_RETURN_V_MSG(customSampleRate != 0, CALLBACK_BUFFER_DURATION_IN_MILLISECONDS,
        "the mimType is not flac, set the default buffer duration");
    if (std::fmod(customSampleRate * CALLBACK_BUFFER_DURATION_IN_MILLISECONDS, MS_IN_SECOND) == 0) {
        return CALLBACK_BUFFER_DURATION_IN_MILLISECONDS;
    }
    return CALLBACK_BUFFER_DURATION_IN_MILLISECONDS_100;
}

bool AudioServerSinkPlugin::GetAudioPosition(timespec &time, uint32_t &framePosition)
{
    ScopedTimer timer("GetAudioPosition", GET_AUDIO_POSITION_WARNING_MS);
    FALSE_RETURN_V_MSG(audioRenderer_ != nullptr, false, "GetAudioPosition audioRender_ is nullptr");
    AudioStandard::Timestamp audioPositionTimestamp;
    bool ret = audioRenderer_->GetAudioPosition(audioPositionTimestamp,
        AudioStandard::Timestamp::Timestampbase::MONOTONIC);
    FALSE_RETURN_V_MSG(ret, false, "GetAudioPosition failed");
    time = audioPositionTimestamp.time;
    int64_t tempframeposition = audioPositionTimestamp.framePosition;
    FALSE_RETURN_V_MSG(tempframeposition >= 0 && tempframeposition <= static_cast<int64_t>(UINT32_MAX),
        false, "audioPositionTimestamp.framePosition is invalid");
    framePosition = static_cast<uint32_t>(audioPositionTimestamp.framePosition);
    return ret;
}

void AudioServerSinkPlugin::SetInterruptState(bool isInterruptNeeded)
{
    MEDIA_LOG_D("onInterrupted %{public}d", isInterruptNeeded);
    {
        std::unique_lock<std::mutex> lock(mutex_);
        isInterruptNeeded_ = isInterruptNeeded;
        writeCond_.notify_all();
    }
    FALSE_RETURN_NOLOG(audioRenderWriteCallback_ != nullptr);
    MEDIA_LOG_I("NotifyInterrupt");
    audioRenderWriteCallback_->NotifyInterrupt(isInterruptNeeded);
}

void AudioServerSinkPlugin::OnWriteData(size_t length)
{
    // First check if can get lock
    std::unique_lock<std::mutex> lock(releaseRenderMutex_, std::try_to_lock);
    FALSE_RETURN_MSG(lock.owns_lock(), "AudioServerSinkPlugin OnWriteData try to get lock failed");

    // Then check if callback untied
    FALSE_RETURN_MSG(!isReleasingRender_, "AudioServerSinkPlugin OnWriteData is releasing ");
    
    ScopedTimer timer("OnWriteData", ON_WRITE_WARNING_MS);
    auto cb = audioSinkDataCallback_.lock();
    FALSE_RETURN_MSG(cb != nullptr, "AudioServerSinkPlugin OnWriteData callback is nullptr");
    cb->OnWriteData(length, isAudioVivid_);
}

bool AudioServerSinkPlugin::IsOffloading()
{
    FALSE_RETURN_V(audioRenderer_ != nullptr, false);
    bool ret = audioRenderer_->IsOffloadEnable();
    MEDIA_LOG_I("IsOffloading %{public}d", ret);
    return ret;
}

Status AudioServerSinkPlugin::SetAudioHapticsSyncId(int32_t syncId)
{
    MEDIA_LOG_D("SetAHapSyncId " PUBLIC_LOG_D32, syncId);
    audioHapticsSyncId_ = syncId;
    return Status::OK;
}

void AudioServerSinkPlugin::ApplyAudioHapticsSyncId()
{
    FALSE_RETURN_W(audioRenderer_ != nullptr);
    MEDIA_LOG_D("ApplyAHapSyncId " PUBLIC_LOG_D32, audioHapticsSyncId_);
    audioRenderer_->SetAudioHapticsSyncId(audioHapticsSyncId_);
}

Status AudioServerSinkPlugin::SetLoudnessGain(float loudnessGain)
{
    FALSE_RETURN_V_MSG(audioRenderer_ != nullptr, Status::ERROR_UNKNOWN,
        "SetLoudnessGain audioRender_ is nullptr");
    int32_t ret = audioRenderer_->SetLoudnessGain(loudnessGain);
    FALSE_RETURN_V_MSG_E(ret == OHOS::AudioStandard::SUCCESS, Status::ERROR_UNKNOWN,
        "set loudnessGain failed with code " PUBLIC_LOG_D32, ret);
    MEDIA_LOG_I("SetLoudnessGain succ");
    return Status::OK;
}

void AudioServerSinkPlugin::OnFirstFrameWriting()
{
    auto cb = audioSinkDataCallback_.lock();
    FALSE_RETURN_MSG(cb != nullptr, "AudioServerSinkPlugin OnFirstFrameWriting callback is nullptr");
    cb->OnFirstFrameWriting();
}

void AudioServerSinkPlugin::SetResponseCallback(bool isNeedResponseCallback)
{
    MEDIA_LOG_D("isNeedResponseCallback %{public}d", isNeedResponseCallback);
    isNeedResponseCallback_ = isNeedResponseCallback;
    FALSE_RETURN_MSG(audioRendererCallback_ != nullptr, "audioRendererCallback_ is nullptr");
    audioRendererCallback_->SetResponseCallback(isNeedResponseCallback);
}
} // namespace Plugin
} // namespace Media
} // namespace OHOS
