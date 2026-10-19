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

#include <cinttypes>
#include "audio_sink.h"
#include "avcodec_trace.h"
#include "syspara/parameters.h"
#include "plugin/plugin_manager_v2.h"
#include "common/log.h"
#include "calc_max_amplitude.h"
#include "scoped_timer.h"
#include "avcodec_info.h"
#include "common/event.h"

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = { LOG_CORE, LOG_DOMAIN_SYSTEM_PLAYER, "AudioSink" };
constexpr int64_t MAX_BUFFER_DURATION_US = 200000; // Max buffer duration is 200 ms
constexpr int64_t US_TO_MS = 1000; // 1000 us per ms
constexpr int64_t ANCHOR_UPDATE_PERIOD_US = 200000; // Update time anchor every 200 ms
constexpr int64_t DRAIN_TIME_DIFF_WARN_MS = 40;
constexpr int64_t DRAIN_TIME_DIFF_INFO_MS = 20;
constexpr int64_t AUDIO_SAMPLE_8_BIT = 1;
constexpr int64_t AUDIO_SAMPLE_16_BIT = 2;
constexpr int64_t AUDIO_SAMPLE_24_BIT = 3;
constexpr int64_t AUDIO_SAMPLE_32_BIT = 4;
constexpr int64_t SEC_TO_US = 1000 * 1000;
constexpr int64_t EOS_CALLBACK_WAIT_MS = 500;
constexpr int32_t BOOT_APP_UID = 1003;
constexpr int64_t INIT_PLUGIN_WARNING_MS = 20;
constexpr int64_t OVERTIME_WARNING_MS = 50;
constexpr int64_t FORMAT_CHANGE_MS = 100;
constexpr int64_t BUFFER_CONSUME_MS = 50;
constexpr int64_t FIX_DELAY_MS_AUDIO_VIVID = 80;
constexpr int64_t PTS_DISCONTINUE_THRESHOLD_US = 1000000;
}

namespace OHOS {
namespace Media {

const int32_t DEFAULT_BUFFER_QUEUE_SIZE = 8;
const int32_t APE_BUFFER_QUEUE_SIZE = 30;
const int64_t DEFAULT_PLAY_RANGE_VALUE = -1;
const int64_t MICROSECONDS_CONVERT_UNITS = 1000;

int64_t GetAudioLatencyFixDelay()
{
    constexpr int64_t defaultOffset = -1;
    const std::string audioLatencyOffsetKey = "const.multimedia.audio.latency_offset";
    static int64_t audioLatencyOffset = OHOS::system::GetIntParameter(audioLatencyOffsetKey, defaultOffset);
    MEDIA_LOG_I("audio.latency_offset, pid:%{public}d , offset: " PUBLIC_LOG_D64, getprocpid(), audioLatencyOffset);
    FALSE_RETURN_V_NOLOG(audioLatencyOffset < 0, audioLatencyOffset * HST_USECOND);

    constexpr uint64_t defaultValue = 120 * HST_USECOND;
    static uint64_t fixDelay = OHOS::system::GetUintParameter("debug.media_service.audio_sync_fix_delay", defaultValue);
    MEDIA_LOG_I("audio_sync_fix_delay, pid:%{public}d , fixdelay: %{public}" PRIu64, getprocpid(), fixDelay);
    return static_cast<int64_t>(fixDelay);
}

AudioSink::AudioSink()
{
    bool isRenderCallbackMode =
        OHOS::system::GetParameter("debug.media_service.audio.audiosink_callback", "1") == "1";
    bool isProcessInputMerged =
        OHOS::system::GetParameter("debug.media_service.audio.audiosink_processinput_merged", "1") == "1";
    MEDIA_LOG_I("AudioSink ctor isRenderCallbackMode: " PUBLIC_LOG_D32 ", isProcessInputMerged: " PUBLIC_LOG_D32,
        isRenderCallbackMode, isProcessInputMerged);
    isRenderCallbackMode_ = isRenderCallbackMode;
    isProcessInputMerged_ = isProcessInputMerged;
    syncerPriority_ = IMediaSynchronizer::AUDIO_SINK;
    fixDelay_ = GetAudioLatencyFixDelay();
    plugin_ = CreatePlugin();
}

AudioSink::AudioSink(bool isRenderCallbackMode, bool isProcessInputMerged)
    : isRenderCallbackMode_(isRenderCallbackMode), isProcessInputMerged_(isProcessInputMerged)
{
    MEDIA_LOG_I("AudioSink ctor default isRenderCallbackMode: " PUBLIC_LOG_D32
        ", isProcessInputMerged: " PUBLIC_LOG_D32, isRenderCallbackMode, isProcessInputMerged);
    syncerPriority_ = IMediaSynchronizer::AUDIO_SINK;
    fixDelay_ = GetAudioLatencyFixDelay();
    plugin_ = CreatePlugin();
}

AudioSink::~AudioSink()
{
    MEDIA_LOG_I("AudioSink dtor");
}

AudioSink::AudioSinkDataCallbackImpl::AudioSinkDataCallbackImpl(std::shared_ptr<AudioSink> sink): audioSink_(sink) {}

void AudioSink::AudioSinkDataCallbackImpl::OnWriteData(int32_t size, bool isAudioVivid)
{
    auto sink = audioSink_.lock();
    FALSE_RETURN_MSG(sink != nullptr, "audioSink_ is nullptr");
    FALSE_RETURN_MSG(!sink->isBuffering_ || !sink->isFirstFrameWrite_, "OnWriteData buffering");
    AudioStandard::BufferDesc bufferDesc;
    MediaAVCodec::AVCodecTrace trace("AudioSink::OnWriteData");
    MEDIA_LOG_DD("GetBufferDesc in");
    Status ret = sink->GetBufferDesc(bufferDesc);
    FALSE_RETURN_MSG(ret == Status::OK, "GetBufferDesc fail, ret=" PUBLIC_LOG_D32, ret);
    bufferDesc.dataLength = 0;

    if (sink->IsInputBufferDataEnough(size, isAudioVivid)) {
        bool isCopySucess = sink->HandleAudioRenderRequest(static_cast<size_t>(size),
            isAudioVivid, bufferDesc);
        bufferDesc.dataLength = isCopySucess ? bufferDesc.dataLength : 0;
    }
    ret = sink->EnqueueBufferDesc(bufferDesc);
    sink->HandleAudioRenderRequestPost();
    FALSE_RETURN_MSG(ret == Status::OK, "enqueue failed, ret=" PUBLIC_LOG_D32, ret);
}

void AudioSink::AudioSinkDataCallbackImpl::OnFirstFrameWriting()
{
    auto sink = audioSink_.lock();
    FALSE_RETURN_MSG(sink != nullptr, "audioSink_ is nullptr");
    sink->OnFirstFrameWriting();
}
 
void AudioSink::OnFirstFrameWriting()
{
    isFirstFrameWrite_ = true;
}
  
void AudioSink::SetBuffering(bool isBuffering)
{
    isBuffering_ = isBuffering;
}

void AudioSink::SetAudioPassFlag(bool isAudioPass)
{
    isAudioPass_ = isAudioPass;
}

bool AudioSink::HandleAudioRenderRequest(size_t size, bool isAudioVivid, AudioStandard::BufferDesc &bufferDesc)
{
    FALSE_RETURN_V(!eosDraining_, false);
    bool isCopySucess = CopyDataToBufferDesc(static_cast<size_t>(size), isAudioVivid, bufferDesc);
    FALSE_RETURN_V_MSG_D(isCopySucess, false, "CopyDataToBufferDesc failed");
    UpdateAudioWriteTimeMayWait();
    SyncWriteByRenderInfo();
    UpdateAmplitude();
    return true;
}

void AudioSink::HandleAudioRenderRequestPost()
{
    std::lock_guard<std::mutex> lock(availBufferMutex_);
    if (appUid_ == BOOT_APP_UID && isEosBuffer_ && availOutputBuffers_.empty()) {
        std::unique_lock<std::mutex> eosCbLock(eosCbMutex_);
        hangeOnEosCb_ = true;
        eosCbCond_.wait_for(eosCbLock, std::chrono::milliseconds(EOS_CALLBACK_WAIT_MS),
            [this] () { return !hangeOnEosCb_; });
    }
    FALSE_RETURN_NOLOG(isEosBuffer_);
    FALSE_RETURN_NOLOG(!availOutputBuffers_.empty());
    auto cacheBuffer = availOutputBuffers_.front();
    FALSE_RETURN(cacheBuffer != nullptr);
    FALSE_RETURN_NOLOG(IsEosBuffer(cacheBuffer));
    availOutputBuffers_.pop();
    ReleaseDecodedBuffer();
    HandleEosBuffer(cacheBuffer);
}

Status AudioSink::GetBufferDesc(AudioStandard::BufferDesc &bufferDesc)
{
    FALSE_RETURN_V_MSG(plugin_ != nullptr, Status::ERROR_UNKNOWN, "GetBufferDesc audioSinkPlugin is nullptr");
    MEDIA_TRACE_DEBUG("AudioSink::GetBufferDesc");
    return plugin_->GetBufferDesc(bufferDesc);
}

Status AudioSink::EnqueueBufferDesc(const AudioStandard::BufferDesc &bufferDesc)
{
    FALSE_RETURN_V_MSG(plugin_ != nullptr, Status::ERROR_UNKNOWN, "Enqueue audioSinkPlugin is nullptr");
    MEDIA_TRACE_DEBUG("AudioSink::EnqueueBufferDesc");
    return plugin_->EnqueueBufferDesc(bufferDesc);
}

bool AudioSink::IsInputBufferDataEnough(int32_t size, bool isAudioVivid)
{
    std::lock_guard<std::mutex> lock(availBufferMutex_);
    if (!isAudioVivid && !isAudioPass_) {
        maxCbDataSize_ = std::max(maxCbDataSize_, size);
    } else {
        // audioVivid use min(size, availDataSize) as maxDataSize to ensure that audioVivid dont use swapBuffers
        size_t availDataSize = availDataSize_.load();
        int32_t availDataSizeInt32 = availDataSize <= static_cast<size_t>(INT32_MAX) ?
            static_cast<int32_t>(availDataSize): INT32_MAX;
        maxCbDataSize_ = std::min(size, availDataSizeInt32);
    }
    DriveBufferCircle();
    std::unique_lock<std::mutex> formatLock(formatChangeMutex_);
    return availDataSize_.load() >= static_cast<size_t>(size) || isEosBuffer_ || formatChange_.load() || isAudioPass_;
}

Status AudioSink::Init(std::shared_ptr<Meta>& meta, const std::shared_ptr<Pipeline::EventReceiver>& receiver)
{
    state_ = Pipeline::FilterState::INITIALIZED;
    Status ret = InitAudioSinkPlugin(meta, receiver, plugin_);
    FALSE_RETURN_V(ret == Status::OK, ret);
    ret = InitAudioSinkInfo(meta);
    FALSE_RETURN_V(ret == Status::OK, ret);
    return Status::OK;
}

Status AudioSink::InitAudioSinkPlugin(const std::shared_ptr<Meta>& meta,
    const std::shared_ptr<Pipeline::EventReceiver>& receiver,
    const std::shared_ptr<Plugins::AudioSinkPlugin>& plugin)
{
    FALSE_RETURN_V(plugin != nullptr, Status::ERROR_NULL_POINTER);
    FALSE_RETURN_V(meta != nullptr, Status::ERROR_NULL_POINTER);
    meta->SetData(Tag::APP_PID, appPid_);
    meta->SetData(Tag::APP_UID, appUid_);
    plugin->SetEventReceiver(receiver);
    plugin->SetParameter(meta);
    plugin->SetAudioPassFlag(isAudioPass_);
    {
        ScopedTimer timer("InitAudioSinkPlugin", INIT_PLUGIN_WARNING_MS);
        plugin->Init();
    }
    if (isRenderCallbackMode_) {
        if (audioSinkDataCallback_ == nullptr) {
            audioSinkDataCallback_ = std::make_shared<AudioSinkDataCallbackImpl>(shared_from_this());
        }
        Status ret = plugin->SetRequestDataCallback(audioSinkDataCallback_);
        isRenderCallbackMode_ = ret == Status::OK ? true : false;
    }
    plugin->Prepare();
    plugin->SetMuted(isMuted_);
    return Status::OK;
}

Status AudioSink::InitAudioSinkInfo(std::shared_ptr<Meta>& meta)
{
    FALSE_RETURN_V(meta != nullptr, Status::ERROR_NULL_POINTER);
    meta->GetData(Tag::AUDIO_SAMPLE_RATE, sampleRate_);
    meta->GetData(Tag::AUDIO_SAMPLE_PER_FRAME, samplePerFrame_);
    meta->GetData(Tag::AUDIO_CHANNEL_COUNT, audioChannelCount_);
    if (samplePerFrame_ > 0 && sampleRate_ > 0) {
        playingBufferDurationUs_ = static_cast<int64_t>(samplePerFrame_) * SEC_TO_US / sampleRate_;
    }
    MEDIA_LOG_I("Audiosink playingBufferDurationUs_ = " PUBLIC_LOG_D64, playingBufferDurationUs_);
    std::string mime;
    if (!meta->Get<Tag::MIME_TYPE>(mime)) {
        return Status::OK;
    }
    if (mime == MediaAVCodec::CodecMimeType::AUDIO_APE) {
        isApe_ = true;
        MEDIA_LOG_I("AudioSink::Init is ape");
    } else if (mime == MediaAVCodec::CodecMimeType::AUDIO_FLAC) {
        isFlac_ = true;
        MEDIA_LOG_I("AudioSink::Init is flac");
    } else if (mime == MediaAVCodec::CodecMimeType::AUDIO_VIVID) {
        fixDelay_ = FIX_DELAY_MS_AUDIO_VIVID * HST_USECOND;
        MEDIA_LOG_I("Audio vivid update fix delay to" PUBLIC_LOG_D64, fixDelay_);
    }
    return Status::OK;
}

sptr<AVBufferQueueProducer> AudioSink::GetBufferQueueProducer()
{
    if (state_ != Pipeline::FilterState::READY) {
        return nullptr;
    }
    return inputBufferQueueProducer_;
}

sptr<AVBufferQueueConsumer> AudioSink::GetBufferQueueConsumer()
{
    if (state_ != Pipeline::FilterState::READY) {
        return nullptr;
    }
    return inputBufferQueueConsumer_;
}

Status AudioSink::SetParameter(const std::shared_ptr<Meta>& meta)
{
    globalMeta_ = meta;
    UpdateMediaTimeRange(meta);
    FALSE_RETURN_V(meta != nullptr, Status::ERROR_NULL_POINTER);
    meta->GetData(Tag::APP_PID, appPid_);
    meta->GetData(Tag::APP_UID, appUid_);
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    plugin_->SetParameter(meta);
    return Status::OK;
}

Status AudioSink::GetParameter(std::shared_ptr<Meta>& meta)
{
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    return plugin_->GetParameter(meta);
}

Status AudioSink::Prepare()
{
    state_ = Pipeline::FilterState::PREPARING;
    Status ret = PrepareInputBufferQueue();
    if (ret != Status::OK) {
        state_ = Pipeline::FilterState::INITIALIZED;
        return ret;
    }
    state_ = Pipeline::FilterState::READY;
    {
        AutoLock lock(eosMutex_);
        eosInterruptType_ = EosInterruptState::NONE;
        eosDraining_ = false;
    }
    return ret;
}

Status AudioSink::Start()
{
    Status ret = Status::OK;
    {
        ScopedTimer timer("AudioSinkPlugin Start", OVERTIME_WARNING_MS);
        FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
        ret = plugin_->Start();
    }
    if (ret != Status::OK) {
        MEDIA_LOG_I("AudioSink start error " PUBLIC_LOG_D32, ret);
        return ret;
    }
    isEos_ = false;
    state_ = Pipeline::FilterState::RUNNING;
    FALSE_RETURN_V_NOLOG(playerEventReceiver_ != nullptr, Status::OK);
    playerEventReceiver_->OnMemoryUsageEvent({"AUDIO_SINK_BQ",
        DfxEventType::DFX_INFO_MEMORY_USAGE, inputBufferQueue_->GetMemoryUsage()});
    return ret;
}

Status AudioSink::Stop()
{
    std::lock_guard<std::mutex> lockPlugin(pluginMutex_);
    playRangeStartTime_ = DEFAULT_PLAY_RANGE_VALUE;
    playRangeEndTime_ = DEFAULT_PLAY_RANGE_VALUE;
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    Status ret = plugin_->Stop();
    underrunDetector_.Reset();
    lagDetector_.Reset();
    ResetInfo();
    if (ret != Status::OK) {
        return ret;
    }
    state_ = Pipeline::FilterState::INITIALIZED;
    AutoLock lock(eosMutex_);
    if (eosInterruptType_ != EosInterruptState::NONE) {
        eosInterruptType_ = EosInterruptState::STOP;
    }
    return ret;
}

Status AudioSink::Pause()
{
    Status ret = Status::OK;
    underrunDetector_.Reset();
    lagDetector_.Reset();
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    if (appUid_ == BOOT_APP_UID) {
        if (eosTask_  != nullptr) {
            eosTask_->SubmitJobOnce([this] {
                ScopedTimer timer("AudioSinkPlugin Pause BOOT", OVERTIME_WARNING_MS);
                {
                    std::unique_lock<std::mutex> eosCbLock(eosCbMutex_);
                    hangeOnEosCb_ = false;
                    eosCbCond_.notify_all();
                }
                plugin_->PauseTransitent();
            });
        }
    } else if (isTransitent_ || (isEos_ && isLoop_)) {
        ScopedTimer timer("AudioSinkPlugin PauseTransitent", OVERTIME_WARNING_MS);
        ret = plugin_->PauseTransitent();
    } else {
        ScopedTimer timer("AudioSinkPlugin Pause", OVERTIME_WARNING_MS);
        ret = plugin_->Pause();
    }
    forceUpdateTimeAnchorNextTime_ = true;
    if (ret != Status::OK) {
        return ret;
    }
    state_ = Pipeline::FilterState::PAUSED;
    AutoLock lock(eosMutex_);
    if (eosInterruptType_ == EosInterruptState::INITIAL || eosInterruptType_ == EosInterruptState::RESUME) {
        eosInterruptType_ = EosInterruptState::PAUSE;
    }
    return ret;
}

Status AudioSink::Resume()
{
    lagDetector_.Reset();
    lastPtsForDiscontinuity_ = HST_TIME_NONE;
    seekFlag_.store(false);
    isFirstFrameAfterSeek_ = true;
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    Status ret = plugin_->Resume();
    if (ret != Status::OK) {
        MEDIA_LOG_I("AudioSink resume error " PUBLIC_LOG_D32, ret);
        return ret;
    }
    isEos_ = false;
    state_ = Pipeline::FilterState::RUNNING;
    AutoLock lock(eosMutex_);
    if (eosInterruptType_ == EosInterruptState::PAUSE) {
        eosInterruptType_ = EosInterruptState::RESUME;
        if (!eosDraining_ && eosTask_ != nullptr) {
            eosTask_->SubmitJobOnce([this] {
                HandleEosInner(false);
            });
        }
    }
    return ret;
}

Status AudioSink::Flush()
{
    std::lock_guard<std::mutex> lockPlugin(pluginMutex_);
    MEDIA_LOG_D("do audioSink flush");
    underrunDetector_.Reset();
    lagDetector_.Reset();
    {
        AutoLock lock(eosMutex_);
        eosInterruptType_ = EosInterruptState::NONE;
        eosDraining_ = false;
    }
    Status ret = Status::OK;
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    ret = plugin_->Flush();
    if (ret != Status::OK && state_.load() == Pipeline::FilterState::READY) {
        MEDIA_LOG_W("AudioSink Flush fail in prepare, reset info.");
        ResetInfo();
    }
    FALSE_RETURN_V_MSG_E(ret == Status::OK, ret, "plugin flush failed");
    ResetInfo();
    return Status::OK;
}

void AudioSink::FlushForChangeTrack()
{
    MEDIA_LOG_D("do audioSink flush for change track");
    underrunDetector_.Reset();
    lagDetector_.Reset();

    {
        AutoLock lock(eosMutex_);
        eosInterruptType_ = EosInterruptState::NONE;
        eosDraining_ = false;
    }
    ResetInfo();
}

Status AudioSink::Release()
{
    underrunDetector_.Reset();
    lagDetector_.Reset();
    ResetInfo();
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    return plugin_->Deinit();
}

Status AudioSink::SetPlayRange(int64_t start, int64_t end)
{
    MEDIA_LOG_I("SetPlayRange enter.");
    playRangeStartTime_ = start;
    playRangeEndTime_ = end;
    return Status::OK;
}

Status AudioSink::SetVolumeMode(int32_t mode)
{
    if (plugin_ == nullptr) {
        return Status::ERROR_NULL_POINTER;
    }
    return plugin_->SetVolumeMode(mode);
}

Status AudioSink::SetVolume(float volume)
{
    if (plugin_ == nullptr) {
        return Status::ERROR_NULL_POINTER;
    }
    if (volume < 0) {
        return Status::ERROR_INVALID_PARAMETER;
    }
    volume_ = volume;
    return plugin_->SetVolume(volume);
}

int32_t AudioSink::SetVolumeWithRamp(float targetVolume, int32_t duration)
{
    MEDIA_LOG_I("SetVolumeWithRamp");
    FALSE_RETURN_V(plugin_ != nullptr, static_cast<int32_t>(Status::ERROR_NULL_POINTER));
    return plugin_->SetVolumeWithRamp(targetVolume, duration);
}

Status AudioSink::SetIsTransitent(bool isTransitent)
{
    MEDIA_LOG_I("AudioSink::SetIsTransitent entered.");
    isTransitent_ = isTransitent;
    return Status::OK;
}

Status AudioSink::Freeze()
{
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    plugin_->Freeze();
    return Status::OK;
}

Status AudioSink::UnFreeze()
{
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    plugin_->UnFreeze();
    return Status::OK;
}

Status AudioSink::PrepareInputBufferQueue()
{
    if (inputBufferQueue_ != nullptr && inputBufferQueue_-> GetQueueSize() > 0) {
        MEDIA_LOG_I("InputBufferQueue already create");
        return Status::ERROR_INVALID_OPERATION;
    }
    int32_t inputBufferSize = isApe_ ? APE_BUFFER_QUEUE_SIZE : DEFAULT_BUFFER_QUEUE_SIZE;
    MemoryType memoryType = MemoryType::SHARED_MEMORY;
#ifndef MEDIA_OHOS
    memoryType = MemoryType::VIRTUAL_MEMORY;
#endif
    bufferMemoryType_ = memoryType;
    MEDIA_LOG_I("PrepareInputBufferQueue ");
    inputBufferQueue_ = AVBufferQueue::Create(inputBufferSize, memoryType, INPUT_BUFFER_QUEUE_NAME);
    inputBufferQueueProducer_ = inputBufferQueue_->GetProducer();
    inputBufferQueueConsumer_ = inputBufferQueue_->GetConsumer();
    return Status::OK;
}

std::shared_ptr<Plugins::AudioSinkPlugin> AudioSink::CreatePlugin()
{
    auto plugin = Plugins::PluginManagerV2::Instance().CreatePluginByMime(Plugins::PluginType::AUDIO_SINK, "audio/raw");
    if (plugin == nullptr) {
        return nullptr;
    }
    return std::reinterpret_pointer_cast<Plugins::AudioSinkPlugin>(plugin);
}

void AudioSink::UpdateAudioWriteTimeMayWait()
{
    if (latestBufferDuration_ <= 0) {
        return;
    }
    if (latestBufferDuration_ > MAX_BUFFER_DURATION_US) {
        latestBufferDuration_ = MAX_BUFFER_DURATION_US; // wait at most MAX_DURATION
    }
    int64_t timeNow = Plugins::HstTime2Us(SteadyClock::GetCurrentTimeNanoSec());
    if (!lastBufferWriteSuccess_) {
        int64_t writeSleepTime = latestBufferDuration_ - (timeNow - lastBufferWriteTime_);
        MEDIA_LOG_W("Last buffer write fail, sleep time is " PUBLIC_LOG_D64 "us", writeSleepTime);
        if (writeSleepTime > 0) {
            usleep(writeSleepTime);
            timeNow = Plugins::HstTime2Us(SteadyClock::GetCurrentTimeNanoSec());
        }
    }
    lastBufferWriteTime_ = timeNow;
}

void AudioSink::SetThreadGroupId(const std::string& groupId)
{
    eosTask_ = std::make_unique<Task>("OS_EOSa", groupId, TaskType::AUDIO, TaskPriority::HIGH, false);
    changeTrackTask_ = std::make_unique<Task>("CHANGE_TRACK", groupId, TaskType::GLOBAL, TaskPriority::HIGH, false);
    bypassTask_ = std::make_unique<Task>("AudioBypass", groupId, TaskType::SINGLETON, TaskPriority::HIGH, false);
}

void AudioSink::HandleEosInner(bool drain)
{
    AutoLock lock(eosMutex_);
    eosDraining_ = true; // start draining task
    switch (eosInterruptType_) {
        case EosInterruptState::INITIAL: // No user operation during EOS drain, complete drain normally
            break;
        case EosInterruptState::RESUME: // EOS drain is resumed after pause, do necessary changes
            if (drain) {
                // pause and resume happened before this task, audiosink latency should be updated
                drain = false;
            }
            eosInterruptType_ = EosInterruptState::INITIAL; // Reset EOS draining state
            break;
        default: // EOS drain is interrupted by pause or stop, and not resumed
            MEDIA_LOG_W("Drain audiosink interrupted");
            eosDraining_ = false; // abort draining task
            return;
    }
    FALSE_RETURN(plugin_ != nullptr);
    if (drain || !plugin_->IsOffloading()) {
        MEDIA_LOG_I("Drain audiosink and report EOS");
        DrainAndReportEosEvent();
        return;
    }
    uint64_t latency = 0;
    if (plugin_->GetLatency(latency) != Status::OK) {
        MEDIA_LOG_W("Failed to get latency, drain audiosink directly");
        DrainAndReportEosEvent();
        return;
    }
    if (eosTask_ == nullptr) {
        MEDIA_LOG_W("Drain audiosink, eosTask_ is nullptr");
        DrainAndReportEosEvent();
        return;
    }
    MEDIA_LOG_I("Drain audiosink wait latency = " PUBLIC_LOG_U64, latency);
    eosTask_->SubmitJobOnce([this] {
            HandleEosInner(true);
        }, latency, false);
}

void AudioSink::DrainAndReportEosEvent()
{
    FALSE_RETURN(plugin_ != nullptr);
    plugin_->Drain();
    eosInterruptType_ = EosInterruptState::NONE;
    eosDraining_ = false; // finish draining task
    isEos_ = true;
    auto syncCenter = syncCenter_.lock();
    if (syncCenter) {
        syncCenter->ReportEos(this);
    }
    Event event {
        .srcFilter = "AudioSink",
        .type = EventType::EVENT_COMPLETE,
    };
    FALSE_RETURN(playerEventReceiver_ != nullptr);
    playerEventReceiver_->OnEvent(event);
}

void AudioSink::CheckUpdateState(char *frame, uint64_t replyBytes, int32_t format)
{
    FALSE_RETURN(frame != nullptr && replyBytes != 0);
    auto currentMaxAmplitude = OHOS::Media::CalcMaxAmplitude::UpdateMaxAmplitude(frame, replyBytes, format);
    currentMaxAmplitude_ = currentMaxAmplitude_ > currentMaxAmplitude ? currentMaxAmplitude_ : currentMaxAmplitude;
}

void AudioSink::UpdateAmplitude()
{
    AutoLock amplitudeLock(amplitudeMutex_);
    maxAmplitude_ = currentMaxAmplitude_ > maxAmplitude_ ? currentMaxAmplitude_ : maxAmplitude_;
}

float AudioSink::GetMaxAmplitude()
{
    AutoLock amplitudeLock(amplitudeMutex_);
    auto ret = maxAmplitude_;
    maxAmplitude_ = 0;
    return ret;
}

void AudioSink::CalcMaxAmplitude(std::shared_ptr<AVBuffer> filledOutputBuffer)
{
    FALSE_RETURN(filledOutputBuffer != nullptr);
    auto mem = filledOutputBuffer->memory_;
    FALSE_RETURN(mem != nullptr);
    auto srcBuffer = mem->GetAddr();
    auto destBuffer = const_cast<uint8_t *>(srcBuffer);
    auto srcLength = mem->GetSize();
    size_t destLength = static_cast<size_t>(srcLength);
    int32_t format = plugin_->GetSampleFormat();
    CheckUpdateState(reinterpret_cast<char *>(destBuffer), destLength, format);
}

bool AudioSink::DropApeBuffer(std::shared_ptr<AVBuffer> filledOutputBuffer)
{
    if (!isApe_ || seekTimeUs_ == HST_TIME_NONE) {
        return false;
    }
    if (filledOutputBuffer->pts_ < seekTimeUs_) {
        MEDIA_LOG_D("Drop ape buffer pts = " PUBLIC_LOG_D64, filledOutputBuffer->pts_);
        inputBufferQueueConsumer_->ReleaseBuffer(filledOutputBuffer);
        return true;
    } else {
        seekTimeUs_ = HST_TIME_NONE;
    }
    return false;
}

void AudioSink::ClearInputBuffer()
{
    MEDIA_LOG_D("AudioSink::ClearInputBuffer enter");
    if (!inputBufferQueueConsumer_) {
        return;
    }
    std::shared_ptr<AVBuffer> filledInputBuffer;
    Status ret = Status::OK;
    while (ret == Status::OK) {
        ret = inputBufferQueueConsumer_->AcquireBuffer(filledInputBuffer);
        if (ret != Status::OK) {
            MEDIA_LOG_I("AudioSink::ClearInputBuffer clear input Buffer");
            return;
        }
        inputBufferQueueConsumer_->ReleaseBuffer(filledInputBuffer);
    }
}

int32_t AudioSink::GetSampleFormatBytes()
{
    int32_t format = 0;
    FALSE_RETURN_V(plugin_ != nullptr, static_cast<int32_t>(Status::ERROR_NULL_POINTER));
    switch (plugin_->GetSampleFormat()) {
        case AudioSampleFormat::SAMPLE_U8:
            format = AUDIO_SAMPLE_8_BIT;
            break;
        case AudioSampleFormat::SAMPLE_S16LE:
            format = AUDIO_SAMPLE_16_BIT;
            break;
        case AudioSampleFormat::SAMPLE_S24LE:
            format = AUDIO_SAMPLE_24_BIT;
            break;
        case AudioSampleFormat::SAMPLE_S32LE:
        case AudioSampleFormat::SAMPLE_F32LE:
            format = AUDIO_SAMPLE_32_BIT;
            break;
        default:
            break;
    }
    return format;
}

bool AudioSink::IsBufferAvailable(std::shared_ptr<AVBuffer> &buffer, size_t &cacheBufferSize)
{
    FALSE_RETURN_V_MSG_D(buffer != nullptr && buffer->memory_ != nullptr, false, "buffer is null.");
    int32_t bufferSize = buffer->memory_->GetSize();
    FALSE_RETURN_V_MSG_D(bufferSize >= currentQueuedBufferOffset_, false, "buffer is empty, skip this buffer.");
    cacheBufferSize = static_cast<size_t>(bufferSize - currentQueuedBufferOffset_);
    return true;
}

bool AudioSink::CopyBufferData(AudioStandard::BufferDesc &bufferDesc, std::shared_ptr<AVBuffer> &buffer,
    size_t &size, size_t &cacheBufferSize, int64_t &bufferPts)
{
    FALSE_RETURN_V_MSG(bufferDesc.buffer != nullptr, false, "Audio bufferDesc is nullptr");
    FALSE_RETURN_V_MSG(buffer != nullptr && buffer->memory_ != nullptr, false, "AVBuffer is nullptr");
    size_t availableSize = cacheBufferSize > size ? size : cacheBufferSize;
    auto ret = memcpy_s(bufferDesc.buffer + bufferDesc.dataLength, availableSize,
        buffer->memory_->GetAddr() + currentQueuedBufferOffset_, availableSize);
    FALSE_RETURN_V_MSG(ret == 0, false, "copy from cache buffer may fail.");
    bufferPts = (bufferPts == HST_TIME_NONE) ? buffer->pts_ : bufferPts;
    bufferDesc.dataLength += availableSize;
    availDataSize_.fetch_sub(availableSize);
    if (cacheBufferSize > size) {
        currentQueuedBufferOffset_ += static_cast<int32_t>(size);
        size = 0;
        return false;
    }
    currentQueuedBufferOffset_ = 0;
    size -= cacheBufferSize;
    return true;
}

bool AudioSink::CopyAudioVividBufferData(AudioStandard::BufferDesc &bufferDesc, std::shared_ptr<AVBuffer> &buffer,
    size_t &size, size_t &cacheBufferSize, int64_t &bufferPts)
{
    FALSE_RETURN_V_MSG(bufferDesc.buffer != nullptr, false, "Audio bufferDesc is nullptr");
    FALSE_RETURN_V_MSG(buffer != nullptr && buffer->memory_ != nullptr, false, "AVBuffer is nullptr");
    auto memory = buffer->memory_;
    auto source = memory->GetAddr();
    const int32_t capacity = memory->GetCapacity();
    const int32_t offset = memory->GetOffset();
    const int32_t used = memory->GetSize();
    FALSE_RETURN_V_MSG(source != nullptr && capacity >= 0 && offset >= 0 && used >= 0 &&
        offset <= capacity && used <= capacity - offset && currentQueuedBufferOffset_ >= 0 &&
        currentQueuedBufferOffset_ <= used, false, "Audio source memory range is invalid");
    FALSE_RETURN_V_MSG(cacheBufferSize > 0 && cacheBufferSize <= size &&
        cacheBufferSize == static_cast<size_t>(used - currentQueuedBufferOffset_) &&
        bufferDesc.dataLength <= bufferDesc.bufLength &&
        cacheBufferSize <= bufferDesc.bufLength - bufferDesc.dataLength &&
        availDataSize_.load() >= cacheBufferSize, false, "Audio copy exceeds available data or output range");

    // This helper also carries compressed pass-through frames, which do not
    // require AudioVivid metadata. Validate vivid metadata before consuming PCM.
    std::vector<uint8_t> metaData;
    if (!isAudioPass_) {
        FALSE_RETURN_V_MSG(buffer->meta_ != nullptr && bufferDesc.metaBuffer != nullptr &&
            bufferDesc.metaLength > 0 && buffer->meta_->GetData(Tag::OH_MD_KEY_AUDIO_VIVID_METADATA, metaData) &&
            metaData.size() == bufferDesc.metaLength, false, "AudioVivid metadata is missing or has the wrong size");
        const auto metaRet = memcpy_s(bufferDesc.metaBuffer, bufferDesc.metaLength,
            metaData.data(), metaData.size());
        FALSE_RETURN_V_MSG(metaRet == 0, false, "copy AudioVivid metadata failed");
    }
    const auto ret = memcpy_s(bufferDesc.buffer + bufferDesc.dataLength,
        bufferDesc.bufLength - bufferDesc.dataLength,
        source + offset + currentQueuedBufferOffset_, cacheBufferSize);
    FALSE_RETURN_V_MSG(ret == 0, false, "copy from cache buffer may fail.");

    // No length, PTS, queue counter or source cursor is published on failure.
    bufferPts = (bufferPts == HST_TIME_NONE) ? buffer->pts_ : bufferPts;
    if (isAudioPass_ && bufferPts >= 0) {
        bufferDesc.syncFramePts = static_cast<uint64_t>(bufferPts);
    }
    bufferDesc.dataLength += cacheBufferSize;
    size -= cacheBufferSize;
    availDataSize_.fetch_sub(cacheBufferSize);
    currentQueuedBufferOffset_ = 0;
    return true;
}

bool AudioSink::IsBufferDataDrained(AudioStandard::BufferDesc &bufferDesc, std::shared_ptr<AVBuffer> &buffer,
    size_t &size, size_t &cacheBufferSize, bool isAudioVivid, int64_t &bufferPts)
{
    FALSE_RETURN_V_MSG(cacheBufferSize <= size || !isAudioVivid || !isAudioPass_, false,
        "copy from cache buffer may fail.");
    MEDIA_TRACE_DEBUG("AudioSink::CopyBuffer");
    bool ret = isAudioVivid || isAudioPass_
        ? CopyAudioVividBufferData(bufferDesc, buffer, size, cacheBufferSize, bufferPts) :
        CopyBufferData(bufferDesc, buffer, size, cacheBufferSize, bufferPts);
    return ret;
}

bool AudioSink::CopyDataToBufferDesc(size_t size, bool isAudioVivid, AudioStandard::BufferDesc &bufferDesc)
{
    FALSE_RETURN_V_MSG(size != 0 && size == bufferDesc.bufLength, false,
        "bufferDesc or request size is unavailable");
    bufferDesc.dataLength = 0;
    std::lock_guard<std::mutex> lock(availBufferMutex_);
    MEDIA_TRACE_DEBUG("AudioSink::CopyDataToBufferDesc");
    int64_t bufferPts = HST_TIME_NONE;
    do {
        bool isSwapBuffer = false;
        FALSE_RETURN_V_MSG(!swapOutputBuffers_.empty() || !availOutputBuffers_.empty(), false, "buffer queue is empty");
        std::shared_ptr<AVBuffer> cacheBuffer;
        if (!swapOutputBuffers_.empty()) {
            cacheBuffer = swapOutputBuffers_.front();
            isSwapBuffer = true;
        } else {
            cacheBuffer = availOutputBuffers_.front();
        }
        if (MuteAudioBuffer(size, bufferDesc, IsEosBuffer(cacheBuffer)) != Status::OK) {
            break;
        }
        size_t cacheBufferSize = 0;
        if (IsBufferAvailable(cacheBuffer, cacheBufferSize)) {
            if (!IsBufferDataDrained(bufferDesc, cacheBuffer, size, cacheBufferSize, isAudioVivid, bufferPts)) {
                break;
            }
            ReportTrackRenderStart(cacheBuffer);
            HandleBypassOutput(cacheBuffer);
            CalcMaxAmplitude(cacheBuffer);
        }
        ReleaseCacheBuffer(isSwapBuffer);
    } while (size > 0 && !isAudioVivid && !isAudioPass_);
    if (bufferPts >= 0) {
        int64_t bufferDuration = CalculateBufferDuration(bufferDesc.dataLength);
        innerSynchroizer_->UpdateCurrentBufferInfo(bufferPts, bufferDuration);
        return true;
    }
    return false;
}

void AudioSink::ReportTrackRenderStart(const std::shared_ptr<AVBuffer>& cacheBuffer)
{
    uint64_t frameChangeSeq = 0;
    int32_t frameStreamType = -1;
    if (cacheBuffer != nullptr && cacheBuffer->meta_ != nullptr) {
        cacheBuffer->meta_->GetData(Tag::MEDIA_CHANGE_SEQ, frameChangeSeq);
        cacheBuffer->meta_->GetData(Tag::MEDIA_CHANGE_STREAM_TYPE, frameStreamType);
    }
    if (frameChangeSeq <= 0 || frameChangeSeq <= lastRenderedChangeSeqNum_.load()) {
        return;
    }
    lastRenderedChangeSeqNum_.store(frameChangeSeq);
    if (playerEventReceiver_ != nullptr && frameStreamType == MEDIA_STREAM_TYPE_AUDIO) {
        playerEventReceiver_->OnDfxEvent({"audio_sink",
            DfxEventType::DFX_EVENT_NEW_TRACK_RENDER_START, frameChangeSeq});
    }
}

Status AudioSink::MuteAudioBuffer(size_t size, AudioStandard::BufferDesc &bufferDesc, bool isEos)
{
    std::unique_lock<std::mutex> lock(formatChangeMutex_);
    FALSE_RETURN_V_NOLOG(formatChange_ || isEos, Status::OK);
    MEDIA_LOG_I("AudioSink mute audio buffer isEos %{public}d size %{public}zu dataLength %{public}zu"
        "bufferLength %{public}zu", isEos, size, bufferDesc.dataLength, bufferDesc.bufLength);
    FALSE_RETURN_V_NOLOG(plugin_ && size > 0, Status::ERROR_INVALID_STATE);
    (void)plugin_->MuteAudioBuffer(bufferDesc.buffer, bufferDesc.dataLength, size);
    return isEos ? Status::ERROR_INVALID_STATE : Status::OK;
}

int64_t AudioSink::CalculateBufferDuration(int64_t writeDataSize)
{
    int32_t format = GetSampleFormatBytes();
    FALSE_RETURN_V(format > 0 && audioChannelCount_ > 0, 0);
    int64_t sampleDataNums = writeDataSize / format / audioChannelCount_;
    FALSE_RETURN_V(sampleRate_ > 0, 0);
    int64_t sampleDataDuration = sampleDataNums * SEC_TO_US / sampleRate_;
    MEDIA_LOG_D("sampleDataDuration: " PUBLIC_LOG_D64, sampleDataDuration);
    return sampleDataDuration;
}

void AudioSink::AudioDataSynchroizer::UpdateCurrentBufferInfo(int64_t bufferPts, int64_t bufferDuration)
{
    bufferDuration_ = bufferDuration;
    startPTS_ = startPTS_ == HST_TIME_NONE ? bufferPts : startPTS_;
    lastBufferPTS_ = lastBufferPTS_ == HST_TIME_NONE ? bufferPts : lastBufferPTS_;
    curBufferPTS_ = bufferPts;
}

void AudioSink::AudioDataSynchroizer::UpdateLastBufferPTS(int64_t bufferOffset, float speed)
{
    MEDIA_LOG_DD("lastBuffer Info: lastBufferPTS_ is " PUBLIC_LOG_D64 " lastBufferOffset_ is " PUBLIC_LOG_D64
        " and compensateDuration_ is " PUBLIC_LOG_D64, lastBufferPTS_, lastBufferOffset_, compensateDuration_);
    curBufferPTS_ = curBufferPTS_ == HST_TIME_NONE ? 0 : curBufferPTS_;
    int64_t tempPTS = curBufferPTS_ + lastBufferOffset_ + bufferDuration_;
    if (tempPTS < lastBufferPTS_) {
        MEDIA_LOG_W("audio pts is not increasing, last pts: " PUBLIC_LOG_D64 ", current pts: " PUBLIC_LOG_D64,
            lastBufferPTS_, tempPTS);
    }
    lastBufferPTS_ = tempPTS;
    lastBufferOffset_ = bufferOffset;
    sumDuration_ += bufferDuration_;
    FALSE_RETURN_MSG(speed != 0, "speed is 0");
    compensateDuration_ += static_cast<int64_t>(bufferDuration_ - bufferDuration_ / speed);
}

void AudioSink::UpdateRenderInfo()
{
    timespec time;
    uint32_t position;
    MEDIA_TRACE_DEBUG("AudioSink::UpdateRenderInfo");
    FALSE_RETURN(plugin_ != nullptr);
    FALSE_RETURN_MSG(plugin_->GetAudioPosition(time, position), "GetAudioPosition from audioRender failed");
    int64_t currentRenderClockTime = time.tv_sec * SEC_TO_US + time.tv_nsec / US_TO_MS; // convert to us
    FALSE_RETURN(sampleRate_ > 0);
    int64_t currentRenderPTS = static_cast<int64_t>(position) * SEC_TO_US / sampleRate_;
    MEDIA_LOG_DD("currentRenderPTS is " PUBLIC_LOG_D64 " and currentRenderClockTime is " PUBLIC_LOG_D64,
        currentRenderPTS, currentRenderClockTime);
    innerSynchroizer_->OnRenderPositionUpdated(currentRenderPTS, currentRenderClockTime);
}

void AudioSink::AudioDataSynchroizer::OnRenderPositionUpdated(int64_t currentRenderPTS, int64_t currentRenderClockTime)
{
    currentRenderClockTime_ = currentRenderClockTime;
    currentRenderPTS_ = currentRenderPTS;
}

int64_t AudioSink::AudioDataSynchroizer::CalculateAudioLatency()
{
    int64_t latency = 0;
    if (lastBufferPTS_ == startPTS_) {
        return latency;
    }
    int64_t nowClockTime = Plugins::HstTime2Us(SteadyClock::GetCurrentTimeNanoSec());
    MEDIA_LOG_DD("PTS diff is " PUBLIC_LOG_D64, ((sumDuration_ - compensateDuration_) -
        currentRenderPTS_));
    latency = ((sumDuration_ - compensateDuration_) - currentRenderPTS_) -
        (nowClockTime - currentRenderClockTime_);
    FALSE_RETURN_V_MSG(latency >= 0, 0, "calculate latency failed");
    return latency;
}

int64_t AudioSink::AudioDataSynchroizer::GetLastBufferPTS() const
{
    return lastBufferPTS_;
}

int64_t AudioSink::AudioDataSynchroizer::GetLastReportedClockTime() const
{
    return lastReportedClockTime_;
}

int64_t AudioSink::AudioDataSynchroizer::GetBufferDuration() const
{
    return bufferDuration_;
}

int64_t AudioSink::AudioDataSynchroizer::GetCurrentRenderPTS() const
{
    return currentRenderPTS_;
}

int64_t AudioSink::AudioDataSynchroizer::GetCurrentRenderClockTime() const
{
    return currentRenderClockTime_;
}

void AudioSink::AudioDataSynchroizer::UpdateReportTime(int64_t nowClockTime)
{
    lastReportedClockTime_ = nowClockTime;
}

void AudioSink::AudioDataSynchroizer::Reset()
{
    lastBufferPTS_ = HST_TIME_NONE;
    bufferDuration_ = 0;
    currentRenderClockTime_ = 0;
    currentRenderPTS_ = 0;
    lastReportedClockTime_ = HST_TIME_NONE;
    startPTS_ = HST_TIME_NONE;
    curBufferPTS_ = HST_TIME_NONE;
    lastBufferOffset_ = 0;
    compensateDuration_ = 0;
    sumDuration_ = 0;
}

bool AudioSink::IsTimeAnchorNeedUpdate()
{
    auto syncCenter = syncCenter_.lock();
    FALSE_RETURN_V(syncCenter != nullptr, false);
    int64_t lastAnchorClockTime = innerSynchroizer_->GetLastReportedClockTime();
    int64_t nowCt = syncCenter->GetClockTimeNow();
    bool needUpdate = forceUpdateTimeAnchorNextTime_ ||
        (lastAnchorClockTime == HST_TIME_NONE) ||
        (nowCt - lastAnchorClockTime >= ANCHOR_UPDATE_PERIOD_US);
    FALSE_RETURN_V_MSG_D(needUpdate, false, "No need to update time anchor this time.");
    UpdateRenderInfo();
    int64_t latency = innerSynchroizer_->CalculateAudioLatency();
    MEDIA_LOG_DD("Calculate latency = " PUBLIC_LOG_U64, latency);
    int64_t lastBufferPTS = innerSynchroizer_->GetLastBufferPTS();
    int64_t lastBufferDuration = innerSynchroizer_->GetBufferDuration();
    if (isAudioPass_) {
        int64_t currentRenderPTS = innerSynchroizer_->GetCurrentRenderPTS();
        int64_t currentRenderClockTime = innerSynchroizer_->GetCurrentRenderClockTime();
        Pipeline::IMediaSyncCenter::IMediaTime iPassMediaTime = {currentRenderPTS,
            lastBufferPTS - firstPts_, lastBufferDuration};
        syncCenter->UpdateTimeAnchor(currentRenderClockTime, 0, iPassMediaTime, this);
        MEDIA_LOG_I("DolbyPassthrough AudioSink , pts-f: " PUBLIC_LOG_D64
            " us, currentRenderPTS: " PUBLIC_LOG_D64 " us"
            " us, currentRenderClockTime: " PUBLIC_LOG_D64 " us",
            lastBufferPTS - firstPts_, currentRenderPTS, currentRenderClockTime);
        forceUpdateTimeAnchorNextTime_ = false;
        innerSynchroizer_->UpdateReportTime(currentRenderClockTime);
        return true;
    }
    Pipeline::IMediaSyncCenter::IMediaTime iMediaTime = {lastBufferPTS - firstPts_, lastBufferPTS,
        lastBufferDuration};
    int64_t delayTime = latency == 0 ? fixDelay_ : latency;
    syncCenter->UpdateTimeAnchor(nowCt, delayTime, iMediaTime, this);
    MEDIA_LOG_I("AudioSink fixDelay_: " PUBLIC_LOG_D64
        " us, latency: " PUBLIC_LOG_D64
        " us, pts-f: " PUBLIC_LOG_D64
        " us, nowCt: " PUBLIC_LOG_D64 " us",
        fixDelay_, latency, lastBufferPTS - firstPts_, nowCt);
    forceUpdateTimeAnchorNextTime_ = false;
    innerSynchroizer_->UpdateReportTime(nowCt);
    return true;
}

void AudioSink::SyncWriteByRenderInfo()
{
    auto syncCenter = syncCenter_.lock();
    FALSE_RETURN(syncCenter != nullptr);
    if (firstPts_ == HST_TIME_NONE) {
        if (syncCenter && syncCenter->GetMediaStartPts() != HST_TIME_NONE) {
            firstPts_ = syncCenter->GetMediaStartPts();
        } else {
            firstPts_ = innerSynchroizer_->GetLastBufferPTS();
        }
    }
    bool anchorUpdated = IsTimeAnchorNeedUpdate();
    innerSynchroizer_->UpdateLastBufferPTS(CalculateBufferDuration(currentQueuedBufferOffset_), speed_);
    latestBufferDuration_ = innerSynchroizer_->GetBufferDuration() / speed_;
    if (anchorUpdated) {
        bufferDurationSinceLastAnchor_ = latestBufferDuration_;
    } else {
        bufferDurationSinceLastAnchor_ += latestBufferDuration_;
    }
    underrunDetector_.SetLastAudioBufferDuration(bufferDurationSinceLastAnchor_);
    if (syncCenter) {
        syncCenter->SetLastAudioBufferDuration(bufferDurationSinceLastAnchor_);
    }
}

void AudioSink::ReleaseCacheBuffer(bool isSwapBuffer)
{
    if (isSwapBuffer) {
        FALSE_RETURN_MSG(!swapOutputBuffers_.empty(), "swapOutputBuffers_ has no buffer");
        swapOutputBuffers_.pop();
        std::unique_lock<std::mutex> formatLock(formatChangeMutex_);
        FALSE_RETURN_NOLOG(formatChange_.load() && swapOutputBuffers_.empty() && availOutputBuffers_.empty());
        formatChange_ = false;
        formatChangeCond_.notify_all();
        return;
    }
    auto buffer = availOutputBuffers_.front();
    availOutputBuffers_.pop();
    FALSE_RETURN_MSG(buffer != nullptr, "release buffer, but buffer is null");
    MEDIA_LOG_DD("the pts is " PUBLIC_LOG_D64 " buffer is release", buffer->pts_);
    FALSE_RETURN_MSG(ReleaseDecodedBuffer() == Status::OK, "release avbuffer failed");
    std::unique_lock<std::mutex> formatLock(formatChangeMutex_);
    FALSE_RETURN_NOLOG(formatChange_.load() && swapOutputBuffers_.empty() && availOutputBuffers_.empty());
    formatChange_ = false;
    formatChangeCond_.notify_all();
    return;
}

void AudioSink::ResetInfo()
{
    if (appUid_ == BOOT_APP_UID) {
        std::unique_lock<std::mutex> eosCbLock(eosCbMutex_);
        hangeOnEosCb_ = false;
        eosCbCond_.notify_all();
    }
    innerSynchroizer_->Reset();
    maxAmplitude_ = 0;
    currentMaxAmplitude_ = 0;
    currentQueuedBufferOffset_ = 0;
    forceUpdateTimeAnchorNextTime_ = true;
    isEosBuffer_ = false;
    availDataSize_.store(0);
    ClearAvailableOutputBuffers();
    ClearInputBuffer();
}

void AudioSink::ClearAvailableOutputBuffers()
{
    FALSE_RETURN(inputBufferQueueConsumer_ != nullptr);
    std::lock_guard<std::mutex> lock(availBufferMutex_);
    while (!swapOutputBuffers_.empty()) {
        swapOutputBuffers_.pop();
    }
    while (!availOutputBuffers_.empty()) {
        ReleaseCacheBuffer();
    }
    std::unique_lock<std::mutex> formatLock(formatChangeMutex_);
    formatChange_ = false;
    formatChangeCond_.notify_all();
}

void AudioSink::GetAvailableOutputBuffers()
{
    FALSE_RETURN(inputBufferQueueConsumer_ != nullptr);
    std::lock_guard<std::mutex> lock(availBufferMutex_);
    std::shared_ptr<AVBuffer> filledInputBuffer;
    Status ret = Status::OK;
    MEDIA_TRACE_DEBUG("AudioSink::GetBufferFromUpstream");
    while (ret == Status::OK) {
        ret = inputBufferQueueConsumer_->AcquireBuffer(filledInputBuffer);
        if (ret != Status::OK || filledInputBuffer == nullptr) {
            break;
        }
        if (filledInputBuffer->memory_ == nullptr || filledInputBuffer->pts_ < 0 || isEosBuffer_) {
            inputBufferQueueConsumer_->ReleaseBuffer(filledInputBuffer);
            continue;
        }
        if (DropApeBuffer(filledInputBuffer)) {
            break;
        }
        if (IsEosBuffer(filledInputBuffer)) {
            MEDIA_LOG_I("AudioSink Recv EOS");
            isEosBuffer_ = true;
        }

        auto processedBuffer = HandlePostProcessingOutput(filledInputBuffer);
        if (filledInputBuffer->memory_->GetSize() <= 0 && !isEosBuffer_) {
            inputBufferQueueConsumer_->ReleaseBuffer(processedBuffer);
            continue;
        }
        UpdateSeekState(filledInputBuffer);
        decodedBuffers_.push(filledInputBuffer);
        availOutputBuffers_.push(processedBuffer);
        MEDIA_LOG_DD("the pts is " PUBLIC_LOG_D64 " buffer is push", processedBuffer->pts_);
        availDataSize_.fetch_add(processedBuffer->memory_->GetSize());
    }
    DriveBufferCircle();
    return;
}

void AudioSink::SetIsInPrePausing(bool isInPrePausing)
{
    MediaAVCodec::AVCodecTrace trace("AudioSink::SetIsInPrePausing" + std::to_string(isInPrePausing));
    isInPrePausing_.store(isInPrePausing, std::memory_order_relaxed);
    FALSE_RETURN_NOLOG(isInPrePausing && (isRenderCallbackMode_ && !isAudioDemuxDecodeAsync_));

    std::lock_guard<std::mutex> lock(availBufferMutex_);
    DriveBufferCircle();
}

void AudioSink::DriveBufferCircle()
{
    FALSE_RETURN_NOLOG(!availOutputBuffers_.empty() && inputBufferQueue_ != nullptr);
    FALSE_RETURN_NOLOG(availOutputBuffers_.size() >= inputBufferQueue_->GetQueueSize());
    size_t availDataSize = availDataSize_.load();
    int32_t availDataSizeInt32 = availDataSize <= static_cast<size_t>(INT32_MAX) ?
        static_cast<int32_t>(availDataSize): INT32_MAX;
    bool isInPrePausing = isInPrePausing_.load(std::memory_order_relaxed);
    FALSE_RETURN_NOLOG(isInPrePausing || availDataSizeInt32 < maxCbDataSize_);
    std::shared_ptr<AVBuffer> oldestBuffer = availOutputBuffers_.front();
    FALSE_RETURN_MSG(oldestBuffer != nullptr && oldestBuffer->memory_->GetSize() > 0, "buffer or memory is nullptr");
    std::shared_ptr<AVBuffer> swapBuffer = CopyBuffer(oldestBuffer);
    FALSE_RETURN_MSG(swapBuffer != nullptr, "CopyBuffer failed, swapBuffer is nullptr");
    availOutputBuffers_.pop();
    swapOutputBuffers_.push(swapBuffer);
    if (isInPrePausing) {
        MEDIA_LOG_I("DriveBufferCircle availOutputBuffers_ size:%{public}d, swapOutputBuffers_ size:%{public}d",
            static_cast<int>(availOutputBuffers_.size()), static_cast<int>(swapOutputBuffers_.size()));
    }
    FALSE_RETURN_MSG(ReleaseDecodedBuffer() == Status::OK, "bufferQueue consumer is nullptr");
}

std::shared_ptr<AVBuffer> AudioSink::CopyBuffer(const std::shared_ptr<AVBuffer> buffer)
{
    FALSE_RETURN_V_MSG_E(buffer != nullptr && buffer->memory_->GetSize() > 0, nullptr, "buffer or memory is nullptr");
    std::shared_ptr<Meta> meta = buffer->meta_;
    std::vector<uint8_t> metaData;
    FALSE_RETURN_V_MSG_W(meta == nullptr || !meta->GetData(Tag::OH_MD_KEY_AUDIO_VIVID_METADATA, metaData), nullptr,
        "copy buffer not support for audiovivid");
    AVBufferConfig avBufferConfig;
    avBufferConfig.capacity = static_cast<int32_t>(buffer->memory_->GetSize());
    avBufferConfig.memoryType = bufferMemoryType_;
    std::shared_ptr<AVBuffer> swapBuffer = AVBuffer::CreateAVBuffer(avBufferConfig);
    FALSE_RETURN_V_MSG_E(swapBuffer != nullptr && swapBuffer->memory_ != nullptr, nullptr, "create swapBuffer failed");
    swapBuffer->pts_ = buffer->pts_;
    swapBuffer->dts_ = buffer->dts_;
    swapBuffer->duration_ = buffer->duration_;
    swapBuffer->flag_ = buffer->flag_;
    FALSE_RETURN_V_MSG_E(swapBuffer->memory_->GetCapacity() >= buffer->memory_->GetSize(), nullptr, "no enough memory");
    errno_t res = memcpy_s(swapBuffer->memory_->GetAddr(),
        swapBuffer->memory_->GetCapacity(),
        buffer->memory_->GetAddr(),
        buffer->memory_->GetSize());
    FALSE_RETURN_V_MSG_E(res == EOK, nullptr, "copy data failed");
    swapBuffer->memory_->SetSize(buffer->memory_->GetSize());
    return swapBuffer;
}

void AudioSink::WriteDataToRender(std::shared_ptr<AVBuffer> &filledOutputBuffer)
{
    FALSE_RETURN(DropApeBuffer(filledOutputBuffer) == false);
    FALSE_RETURN(filledOutputBuffer != nullptr);
    if (IsEosBuffer(filledOutputBuffer)) {
        HandleEosBuffer(filledOutputBuffer);
        return;
    }
    FALSE_RETURN(plugin_ != nullptr);
    UpdateAudioWriteTimeMayWait();
    int64_t actionClock = 0;
    DoSyncWrite(filledOutputBuffer, actionClock);
    (void)actionClock;
    if (calMaxAmplitudeCbStatus_) {
        CalcMaxAmplitude(filledOutputBuffer);
        UpdateAmplitude();
    } else {
        maxAmplitude_ = 0.0f;
    }
    lastBufferWriteSuccess_ = (plugin_->Write(filledOutputBuffer) == Status::OK);
    int64_t nowClockTime = 0;
    GetSyncCenterClockTime(nowClockTime);
    auto audioWriteMs = plugin_->GetWriteDurationMs();
    lagDetector_.UpdateDrainTimeGroup(
        { lastAnchorClockTime_, bufferDurationSinceLastAnchor_, audioWriteMs, nowClockTime });
    PerfRecord(audioWriteMs);
    lagDetector_.CalcLag(filledOutputBuffer);
    MEDIA_LOG_DD("audio DrainOutputBuffer pts = " PUBLIC_LOG_D64, filledOutputBuffer->pts_);
    numFramesWritten_++;
    FALSE_RETURN(inputBufferQueueConsumer_ != nullptr);
    inputBufferQueueConsumer_->ReleaseBuffer(filledOutputBuffer);
}

bool AudioSink::IsEosBuffer(std::shared_ptr<AVBuffer> &filledOutputBuffer)
{
    FALSE_RETURN_V(filledOutputBuffer != nullptr, false);
    return (filledOutputBuffer->flag_ & BUFFER_FLAG_EOS) ||
        ((playRangeEndTime_ != DEFAULT_PLAY_RANGE_VALUE) &&
        (filledOutputBuffer->pts_ > playRangeEndTime_ * MICROSECONDS_CONVERT_UNITS));
}

void AudioSink::HandleEosBuffer(std::shared_ptr<AVBuffer> &filledOutputBuffer)
{
    FALSE_RETURN(inputBufferQueueConsumer_ != nullptr);
    inputBufferQueueConsumer_->ReleaseBuffer(filledOutputBuffer);
    AutoLock eosLock(eosMutex_);
    // avoid submit handle eos task multiple times
    FALSE_RETURN(!eosDraining_);
    eosInterruptType_ = EosInterruptState::INITIAL;
    if (eosTask_ == nullptr) {
        DrainAndReportEosEvent();
        return;
    }
    MEDIA_LOG_I("DrainOutputBuffer Recv EOS PTS");
    eosTask_->SubmitJobOnce([this] {
        HandleEosInner(false);
    });
    return;
}

void AudioSink::DrainOutputBuffer(bool flushed)
{
    std::lock_guard<std::mutex> lock(pluginMutex_);
    FALSE_RETURN(plugin_ != nullptr && inputBufferQueueConsumer_ != nullptr);

    if (isRenderCallbackMode_) {
        if (state_ != Pipeline::FilterState::RUNNING) {
            MEDIA_LOG_W("DrainOutputBuffer ignore temporarily for not RUNNINT state: " PUBLIC_LOG_D32
                ", isProcessInputMerged: " PUBLIC_LOG_D32, state_.load(), isProcessInputMerged_);

            /*
            * As the AudioRender START and PAUSE procedure may consume a long time about 200 ms,
            * if the consumption of inputbuffer queue is not excuted in AudioSinkFilter's task working thread,
            * this RETURN ACTION will cause the filled buffers not been consumed,
            * which cause the upstream filter RequesetBuffer failed and audio track playback stuck.
            */
            if (!isProcessInputMerged_) {
                return;
            }
        }
        GetAvailableOutputBuffers();
    } else {
        std::shared_ptr<AVBuffer> filledOutputBuffer = nullptr;
        Status ret = inputBufferQueueConsumer_->AcquireBuffer(filledOutputBuffer);
        FALSE_RETURN(ret == Status::OK && filledOutputBuffer != nullptr);
        if (state_ != Pipeline::FilterState::RUNNING || flushed) {
            MEDIA_LOG_W("DrainOutputBuffer, drop audio buffer pts = " PUBLIC_LOG_D64 ", state: " PUBLIC_LOG_D32
                ", flushed: " PUBLIC_LOG_D32, filledOutputBuffer->pts_, state_.load(), flushed);

            /*
             * As START and PAUSE procedure of AudioDecoderFilter and AudioSinkFilter run concurrently
             * in different working thread, AudioSinkFilter may change to RUNNING state after AudioDecoderFilter
             * or AudioSinkFilter may change to PAUSED state before AudioDecoderFilter.
             * This ReleaseBuffer ACTION will cause audio buffer droped, which may cause audio discontinuity.
             *
             * So, How to deal with this case?
             * 1. Try to cache buffers in non RUNNING state, prioritize consuming the cached buffers in RUNNING state?
             * 2. There may be some buffers that cannot be processed, i.e. do Pause/Resume repeatedly around the ending
             * and cause the EOS buffer being cached which may cause that the Audio Track can't end.
             */
            inputBufferQueueConsumer_->ReleaseBuffer(filledOutputBuffer);
            return;
        }
        WriteDataToRender(filledOutputBuffer);
    }
}

Status AudioSink::SetPerfRecEnabled(bool isPerfRecEnabled)
{
    isPerfRecEnabled_ = isPerfRecEnabled;
    return Status::OK;
}

void AudioSink::PerfRecord(int64_t audioWriteMs)
{
    FALSE_RETURN_NOLOG(isPerfRecEnabled_);
    FALSE_RETURN_MSG(playerEventReceiver_ != nullptr, "Report perf failed, event receiver is nullptr");
    FALSE_RETURN_NOLOG(perfRecorder_.Record(audioWriteMs) == PerfRecorder::FULL);
    playerEventReceiver_->OnDfxEvent(
        { "ASINK", DfxEventType::DFX_INFO_PERF_REPORT, perfRecorder_.GetMainPerfData() });
    perfRecorder_.Reset();
}

void AudioSink::ResetSyncInfo()
{
    lastAnchorClockTime_ = HST_TIME_NONE;
    forceUpdateTimeAnchorNextTime_ = true;
}

void AudioSink::UnderrunDetector::Reset()
{
    AutoLock lock(mutex_);
    lastClkTime_ = HST_TIME_NONE;
    lastLatency_ = HST_TIME_NONE;
    lastBufferDuration_ = HST_TIME_NONE;
}

void AudioSink::UnderrunDetector::SetEventReceiver(std::weak_ptr<Pipeline::EventReceiver> eventReceiver)
{
    eventReceiver_ = eventReceiver;
}

void AudioSink::UnderrunDetector::UpdateBufferTimeNoLock(int64_t clkTime, int64_t latency)
{
    lastClkTime_ = clkTime;
    lastLatency_ = latency;
}

void AudioSink::UnderrunDetector::SetLastAudioBufferDuration(int64_t durationUs)
{
    AutoLock lock(mutex_);
    lastBufferDuration_ = durationUs;
}

void AudioSink::UnderrunDetector::DetectAudioUnderrun(int64_t clkTime, int64_t latency)
{
    if (lastClkTime_ == HST_TIME_NONE) {
        AutoLock lock(mutex_);
        UpdateBufferTimeNoLock(clkTime, latency);
        return;
    }
    int64_t underrunTimeUs = 0;
    {
        AutoLock lock(mutex_);
        int64_t elapsedClk = clkTime - lastClkTime_;
        underrunTimeUs = elapsedClk - (lastLatency_ + lastBufferDuration_);
        UpdateBufferTimeNoLock(clkTime, latency);
    }
    if (underrunTimeUs > 0) {
        MEDIA_LOG_D("AudioSink maybe underrun, underrunTimeUs=" PUBLIC_LOG_D64, underrunTimeUs);
        auto eventReceiver = eventReceiver_.lock();
        FALSE_RETURN(eventReceiver != nullptr);
        eventReceiver->OnDfxEvent({"AudioSink", DfxEventType::DFX_INFO_PLAYER_AUDIO_LAG, underrunTimeUs / US_TO_MS});
    }
}

bool AudioSink::AudioLagDetector::CalcLag(std::shared_ptr<AVBuffer> buffer)
{
    (void)buffer;
    int64_t maxMediaTime = lastDrainTimeGroup_.anchorDuration + lastDrainTimeGroup_.lastAnchorPts + latency_;
    auto currentMediaTime = lastDrainTimeGroup_.nowClockTime;
    auto writeTimeMs = lastDrainTimeGroup_.writeDuration;

    MEDIA_LOG_DD("maxMediaTime " PUBLIC_LOG_D64 " currentMediaTime " PUBLIC_LOG_D64 " latency_ " PUBLIC_LOG_D64,
        maxMediaTime, currentMediaTime, latency_);

    if (maxMediaTime < currentMediaTime) {
        MEDIA_LOG_W("renderer write cost " PUBLIC_LOG_D64, writeTimeMs);
    }
    
    // Calc time delays except plugin write
    auto currentTimeMs = Plugins::GetCurrentMillisecond();
    auto totalTimeDiff = lastDrainTimeMs_ == 0 ? 0 : currentTimeMs - lastDrainTimeMs_;
    lastDrainTimeMs_ = currentTimeMs;
    auto drainTimeDiff = totalTimeDiff - writeTimeMs;
    if (drainTimeDiff > DRAIN_TIME_DIFF_WARN_MS) {
        MEDIA_LOG_W("Audio drain cost " PUBLIC_LOG_D64, drainTimeDiff);
    } else if (drainTimeDiff > DRAIN_TIME_DIFF_INFO_MS) {
        MEDIA_LOG_I("Audio drain cost " PUBLIC_LOG_D64, drainTimeDiff);
    } else {
        MEDIA_LOG_DD("Audio drain cost " PUBLIC_LOG_D64, drainTimeDiff);
    }

    return maxMediaTime < currentMediaTime;
}

void AudioSink::AudioLagDetector::Reset()
{
    latency_ = 0;
    lastDrainTimeMs_ = 0;
    lastDrainTimeGroup_.lastAnchorPts = 0;
    lastDrainTimeGroup_.anchorDuration = 0;
    lastDrainTimeGroup_.writeDuration = 0;
    lastDrainTimeGroup_.nowClockTime = 0;
}

bool AudioSink::GetSyncCenterClockTime(int64_t &clockTime)
{
    auto syncCenter = syncCenter_.lock();
    FALSE_RETURN_V(syncCenter != nullptr, false);
    clockTime = syncCenter->GetClockTimeNow();
    return true;
}

void AudioSink::AudioLagDetector::UpdateDrainTimeGroup(AudioDrainTimeGroup group)
{
    lastDrainTimeGroup_.lastAnchorPts = group.lastAnchorPts;
    lastDrainTimeGroup_.anchorDuration = group.anchorDuration;
    lastDrainTimeGroup_.writeDuration = group.writeDuration;
    lastDrainTimeGroup_.nowClockTime = group.nowClockTime;
}

bool AudioSink::UpdateTimeAnchorIfNeeded(const std::shared_ptr<OHOS::Media::AVBuffer>& buffer)
{
    auto syncCenter = syncCenter_.lock();
    FALSE_RETURN_V(syncCenter != nullptr, false);
    int64_t nowCt = syncCenter->GetClockTimeNow();
    bool needUpdate = forceUpdateTimeAnchorNextTime_ ||
        (lastAnchorClockTime_ == HST_TIME_NONE) ||
        (nowCt - lastAnchorClockTime_ >= ANCHOR_UPDATE_PERIOD_US);
    if (!needUpdate) {
        MEDIA_LOG_DD("No need to update time anchor this time.");
        return false;
    }
    uint64_t latency = 0;
    FALSE_LOG_MSG(plugin_->GetLatency(latency) == Status::OK, "failed to get latency");
    Pipeline::IMediaSyncCenter::IMediaTime iMediaTime = {buffer->pts_ - firstPts_, buffer->pts_, buffer->duration_};
    syncCenter->UpdateTimeAnchor(nowCt, latency + fixDelay_, iMediaTime, this);
    lagDetector_.SetLatency(latency + fixDelay_);
    MEDIA_LOG_I("AudioSink fixDelay_: " PUBLIC_LOG_D64
        " us, latency: " PUBLIC_LOG_D64
        " us, pts-f: " PUBLIC_LOG_D64
        " us, pts: " PUBLIC_LOG_D64
        " us, nowCt: " PUBLIC_LOG_D64 " us",
        fixDelay_, latency, buffer->pts_ - firstPts_, buffer->pts_, nowCt);
    forceUpdateTimeAnchorNextTime_ = false;
    lastAnchorClockTime_ = nowCt;
    return true;
}

int64_t AudioSink::DoSyncWrite(const std::shared_ptr<OHOS::Media::AVBuffer>& buffer, int64_t& actionClock)
{
    (void)actionClock;
    bool render = true; // audio sink always report time anchor and do not drop
    auto syncCenter = syncCenter_.lock();
    FALSE_RETURN_V(syncCenter != nullptr, 0);

    if (firstPts_ == HST_TIME_NONE) {
        if (syncCenter && syncCenter->GetMediaStartPts() != HST_TIME_NONE) {
            firstPts_ = syncCenter->GetMediaStartPts();
        } else {
            firstPts_ = buffer->pts_;
        }
        MEDIA_LOG_I("audio DoSyncWrite set firstPts = " PUBLIC_LOG_D64, firstPts_);
    }
    bool anchorUpdated = UpdateTimeAnchorIfNeeded(buffer);
    latestBufferDuration_ = CalcBufferDuration(buffer) / speed_;
    if (anchorUpdated) {
        bufferDurationSinceLastAnchor_ = latestBufferDuration_;
    } else {
        bufferDurationSinceLastAnchor_ += latestBufferDuration_;
    }
    underrunDetector_.SetLastAudioBufferDuration(bufferDurationSinceLastAnchor_);
    if (syncCenter) {
        syncCenter->SetLastAudioBufferDuration(bufferDurationSinceLastAnchor_);
    }
    return render ? 0 : -1;
}

int64_t AudioSink::CalcBufferDuration(const std::shared_ptr<OHOS::Media::AVBuffer>& buffer)
{
    FALSE_RETURN_V(buffer != nullptr && buffer->memory_ != nullptr && sampleRate_ != 0 && audioChannelCount_ != 0, 0);
    int64_t size = static_cast<int64_t>(buffer->memory_->GetSize());
    int32_t format = GetSampleFormatBytes();
    FALSE_RETURN_V(format > 0 && audioChannelCount_ > 0, 0);
    return SEC_TO_US * size / format / sampleRate_ / audioChannelCount_;
}

Status AudioSink::SetSpeed(float speed)
{
    if (plugin_ == nullptr) {
        return Status::ERROR_NULL_POINTER;
    }
    if (speed <= 0) {
        return Status::ERROR_INVALID_PARAMETER;
    }
    auto ret = plugin_->SetSpeed(speed);
    if (ret == Status::OK) {
        speed_ = speed;
    }
    forceUpdateTimeAnchorNextTime_ = true;
    return ret;
}

Status AudioSink::SetAudioEffectMode(int32_t effectMode)
{
    MEDIA_LOG_I("AudioSink::SetAudioEffectMode entered.");
    if (plugin_ == nullptr) {
        return Status::ERROR_NULL_POINTER;
    }
    effectMode_ = effectMode;
    return plugin_->SetAudioEffectMode(effectMode);
}

Status AudioSink::GetAudioEffectMode(int32_t &effectMode)
{
    MEDIA_LOG_I("AudioSink::GetAudioEffectMode entered.");
    if (plugin_ == nullptr) {
        return Status::ERROR_NULL_POINTER;
    }
    return plugin_->GetAudioEffectMode(effectMode);
}

bool AudioSink::OnNewAudioMediaTime(int64_t mediaTimeUs)
{
    bool render = true;
    if (firstAudioAnchorTimeMediaUs_ == Plugins::HST_TIME_NONE) {
        firstAudioAnchorTimeMediaUs_ = mediaTimeUs;
    }
    int64_t nowUs = 0;
    auto syncCenter = syncCenter_.lock();
    if (syncCenter) {
        nowUs = syncCenter->GetClockTimeNow();
    }
    int64_t pendingTimeUs = getPendingAudioPlayoutDurationUs(nowUs);
    render = syncCenter->UpdateTimeAnchor(nowUs, pendingTimeUs, {mediaTimeUs, mediaTimeUs, mediaTimeUs}, this);
    return render;
}

int64_t AudioSink::getPendingAudioPlayoutDurationUs(int64_t nowUs)
{
    int64_t writtenSamples = numFramesWritten_ * samplePerFrame_;
    const int64_t numFramesPlayed = plugin_->GetPlayedOutDurationUs(nowUs);
    FALSE_RETURN_V(sampleRate_ > 0, 0);
    int64_t pendingUs = (writtenSamples - numFramesPlayed) * HST_MSECOND / sampleRate_;
    MEDIA_LOG_DD("pendingUs: " PUBLIC_LOG_D64, pendingUs);
    if (pendingUs < 0) {
        pendingUs = 0;
    }
    return pendingUs;
}

int64_t AudioSink::getDurationUsPlayedAtSampleRate(uint32_t numFrames)
{
    std::shared_ptr<Meta> parameter;
    plugin_->GetParameter(parameter);
    int32_t sampleRate = 0;
    if (parameter) {
        parameter->GetData(Tag::AUDIO_SAMPLE_RATE, sampleRate);
    }
    if (sampleRate == 0) {
        MEDIA_LOG_W("cannot get sampleRate");
        return 0;
    }
    return (int64_t)(static_cast<int32_t>(numFrames) * HST_MSECOND / sampleRate);
}

void AudioSink::SetEventReceiver(const std::shared_ptr<Pipeline::EventReceiver>& receiver)
{
    FALSE_RETURN(receiver != nullptr);
    playerEventReceiver_ = receiver;
    FALSE_RETURN(plugin_ != nullptr);
    plugin_->SetEventReceiver(receiver);
}

void AudioSink::SetSyncCenter(std::shared_ptr<Pipeline::MediaSyncManager> syncCenter)
{
    syncCenter_ = syncCenter;
    MediaSynchronousSink::Init();
}

Status AudioSink::ChangeTrackForFormatChange()
{
    MEDIA_LOG_I("ChangeTrackForFormatChange.");
    std::lock_guard<std::mutex> lock(pluginMutex_);
    std::shared_ptr<Plugins::AudioSinkPlugin> plugin = std::move(plugin_);
    FALSE_RETURN_V(plugin != nullptr && changeTrackTask_ != nullptr, Status::ERROR_NULL_POINTER);
    plugin->SetResponseCallback(false);
    changeTrackTask_->SubmitJobOnce([plugin] {
        plugin->Stop();
        plugin->Deinit();
    });

    std::unique_lock<std::mutex> preCreateLock(preCreatePluginMutex_);
    preCreatePluginCond_.wait(preCreateLock,
        [this]() { return isInterruptNeeded_ || hasPluginCreateTaskFinished_.load(); });
    hasPluginCreateTaskFinished_ = false;
    FALSE_RETURN_V(newPlugin_ != nullptr, Status::ERROR_NULL_POINTER);
    plugin_ = std::move(newPlugin_);
    plugin_->SetParameter(globalMeta_);
    SetAudioSinkPluginParameters(plugin_);

    forceUpdateTimeAnchorNextTime_ = true;

    return Status::OK;
}

Status AudioSink::ChangeTrack(std::shared_ptr<Meta>& meta, const std::shared_ptr<Pipeline::EventReceiver>& receiver)
{
    MEDIA_LOG_I("AudioSink::GetAudioEffectMode ChangeTrack. ");
    std::lock_guard<std::mutex> lock(pluginMutex_);
    if (plugin_) {
        plugin_->Stop();
        plugin_->Deinit();
        plugin_ = nullptr;
    }
    plugin_ = CreatePlugin();
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    Status ret = Status::OK;
    ret = InitAudioSinkPlugin(meta, receiver, plugin_);
    FALSE_RETURN_V(ret == Status::OK, ret);

    ret = InitAudioSinkInfo(meta);
    FALSE_RETURN_V(ret == Status::OK, ret);

    ret = SetAudioSinkPluginParameters(plugin_);
    FALSE_RETURN_V(ret == Status::OK, ret);

    forceUpdateTimeAnchorNextTime_ = true;

    return Status::OK;
}

Status AudioSink::HandleFormatChange(std::shared_ptr<Meta>& meta,
    const std::shared_ptr<Pipeline::EventReceiver>& receiver)
{
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_INVALID_STATE);
    ScopedTimer timer("HandleFormatChange", FORMAT_CHANGE_MS);
    FALSE_RETURN_V_NOLOG(meta && plugin_ && plugin_->IsFormatSupported(meta), Status::ERROR_INVALID_PARAMETER);
    WaitForAllBufferConsumed();
    FALSE_RETURN_V_MSG(!isInterruptNeeded_, Status::OK, "Abandon format change operation becaused of interruption");
    FALSE_RETURN_V(changeTrackTask_ != nullptr, Status::ERROR_NULL_POINTER);
    std::weak_ptr<AudioSink> weakPtr(shared_from_this());
    changeTrackTask_->SubmitJobOnce([weakPtr, meta, receiver] {
        auto strongPtr = weakPtr.lock();
        FALSE_RETURN(strongPtr != nullptr);
        std::unique_lock<std::mutex> preCreateLock(strongPtr->preCreatePluginMutex_);
        strongPtr->newPlugin_ = strongPtr->PreCreateNewPlugin(meta, receiver);
        strongPtr->hasPluginCreateTaskFinished_ = true;
        strongPtr->preCreatePluginCond_.notify_one();
    });
    plugin_->Drain();
    FlushForChangeTrack();
    return ChangeTrackForFormatChange();
}

void AudioSink::WaitForAllBufferConsumed()
{
    ScopedTimer timer("WaitForAllBufferConsumed", BUFFER_CONSUME_MS);
    MediaAVCodec::AVCodecTrace trace("AudioSink::WaitForAllBufferConsumed");
    std::unique_lock<std::mutex> formatLock(formatChangeMutex_);
    formatChange_ = true;
    formatChangeCond_.wait(formatLock,
        [this]() { return isInterruptNeeded_ || (swapOutputBuffers_.empty() && availOutputBuffers_.empty()); });
}

Status AudioSink::SetAudioSinkPluginParameters(const std::shared_ptr<Plugins::AudioSinkPlugin>& plugin)
{
    FALSE_RETURN_V(plugin != nullptr, Status::ERROR_NULL_POINTER);
    Status ret = Status::OK;
    if (volume_ >= 0) {
        plugin->SetVolume(volume_);
    }
    if (speed_ >= 0) {
        plugin->SetSpeed(speed_);
    }
    if (effectMode_ >= 0) {
        plugin->SetAudioEffectMode(effectMode_);
    }
    if (state_ == Pipeline::FilterState::RUNNING) {
        ret = plugin->Start();
    }
    return ret;
}

Status AudioSink::SetMuted(bool isMuted)
{
    isMuted_ = isMuted;
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    return plugin_->SetMuted(isMuted);
}

Status AudioSink::SetSeekTime(int64_t seekTime)
{
    MEDIA_LOG_I("AudioSink SetSeekTime pts = " PUBLIC_LOG_D64, seekTime);
    seekTimeUs_ = seekTime;
    SetSeekFlag();
    return Status::OK;
}

int32_t AudioSink::SetMaxAmplitudeCbStatus(bool status)
{
    calMaxAmplitudeCbStatus_ = status;
    MEDIA_LOG_I("audio SetMaxAmplitudeCbStatus  = " PUBLIC_LOG_D32, calMaxAmplitudeCbStatus_);
    return 0;
}

void AudioSink::OnInterrupted(bool isInterruptNeeded)
{
    MEDIA_LOG_D("OnInterrupted %{public}d", isInterruptNeeded);
    {
        std::unique_lock<std::mutex> lock(formatChangeMutex_);
        isInterruptNeeded_ = isInterruptNeeded;
        formatChangeCond_.notify_all();
    }
    if (plugin_ != nullptr) {
        plugin_->SetInterruptState(isInterruptNeeded);
    }
}

Status AudioSink::SetIsCalledBySystemApp(bool isCalledBySystemApp)
{
    MEDIA_LOG_I("AudioSink isCalledBySystemApp = " PUBLIC_LOG_D32, isCalledBySystemApp);
    isCalledBySystemApp_ = isCalledBySystemApp;
    return Status::OK;
}

Status AudioSink::SetLooping(bool loop)
{
    isLoop_ = loop;
    MEDIA_LOG_I("AudioSink SetLooping isLoop_ = " PUBLIC_LOG_D32, isLoop_);
    return Status::OK;
}

Status AudioSink::SetAudioHapticsSyncId(int32_t syncId)
{
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    return plugin_->SetAudioHapticsSyncId(syncId);
}

Status AudioSink::SetLoudnessGain(float loudnessGain)
{
    FALSE_RETURN_V(plugin_ != nullptr, Status::ERROR_NULL_POINTER);
    return plugin_->SetLoudnessGain(loudnessGain);
}

std::shared_ptr<Plugins::AudioSinkPlugin> AudioSink::PreCreateNewPlugin(const std::shared_ptr<Meta>& meta,
    const std::shared_ptr<Pipeline::EventReceiver>& receiver)
{
    MEDIA_LOG_I("AudioSink PreCreateNewPlugin.");
    auto plugin = CreatePlugin();
    FALSE_RETURN_V(plugin != nullptr, nullptr);
    Status ret = Status::OK;
    ret = InitAudioSinkPlugin(meta, receiver, plugin);
    FALSE_RETURN_V(ret == Status::OK, nullptr);
    return plugin;
}

// empty availOutputBuffers_ stroe to swapOutputBuffers_
Status AudioSink::CacheBuffer()
{
    FALSE_RETURN_V(inputBufferQueue_ != nullptr, Status::OK);
    std::lock_guard<std::mutex> lock(availBufferMutex_);
    while (availOutputBuffers_.size() > 0) {
        std::shared_ptr<AVBuffer> buffer = availOutputBuffers_.front();
        FALSE_RETURN_V(buffer != nullptr && buffer->memory_->GetSize() > 0, Status::OK);

        std::shared_ptr<Meta> meta = buffer->meta_;
        std::vector<uint8_t> metaData;
        FALSE_RETURN_V_MSG_W(meta != nullptr && meta->GetData(Tag::OH_MD_KEY_AUDIO_VIVID_METADATA, metaData),
            Status::OK, "except audiovivid not need cacheBuffer");
        AVBufferConfig avBufferConfig;
        avBufferConfig.capacity = static_cast<int32_t>(buffer->memory_->GetSize());
        avBufferConfig.memoryType = bufferMemoryType_;
        std::shared_ptr<AVBuffer> swapBuffer = AVBuffer::CreateAVBuffer(avBufferConfig);
        FALSE_RETURN_V(swapBuffer != nullptr && swapBuffer->memory_ != nullptr, Status::ERROR_NO_MEMORY);
        if (metaData.size() > 0) {
            std::vector<uint8_t> swapMetaData;
            swapMetaData = metaData;
            swapBuffer->meta_->Set<Tag::OH_MD_KEY_AUDIO_VIVID_METADATA>(swapMetaData);
        }
        swapBuffer->pts_ = buffer->pts_;
        swapBuffer->dts_ = buffer->dts_;
        swapBuffer->duration_ = buffer->duration_;
        swapBuffer->flag_ = buffer->flag_;
        FALSE_RETURN_V(swapBuffer->memory_->GetCapacity() >= buffer->memory_->GetSize(), Status::ERROR_NO_MEMORY);
        errno_t res = memcpy_s(swapBuffer->memory_->GetAddr(),
            swapBuffer->memory_->GetCapacity(),
            buffer->memory_->GetAddr(),
            buffer->memory_->GetSize());
        FALSE_RETURN_V(res == EOK, Status::ERROR_NO_MEMORY);
        swapBuffer->memory_->SetSize(buffer->memory_->GetSize());

        availOutputBuffers_.pop();
        swapOutputBuffers_.push(swapBuffer);
        FALSE_RETURN_V(ReleaseDecodedBuffer() == Status::OK, Status::ERROR_UNKNOWN);
    }
    MEDIA_LOG_I("cacheBuffer availOutputBuffers_ size:%{public}d, swapOutputBuffers_ size:%{public}d",
        static_cast<int>(availOutputBuffers_.size()), static_cast<int>(swapOutputBuffers_.size()));
    return Status::OK;
}

void AudioSink::SetPCMCallback(const std::shared_ptr<IPCMCallback> &callback)
{
    MEDIA_LOG_I("SetPCMCallback");
    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);
    pcmCallback_ = callback;
}

void AudioSink::SetPCMOutputStatus(bool isEnable)
{
    MEDIA_LOG_I("SetPCMOutputStatus isEnable: %{public}d", isEnable);
    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);
    isPcmOutputEnable_ = isEnable;
}

void AudioSink::SetPCMProcessorStatus(bool isEnable)
{
    MEDIA_LOG_I("SetPCMProcessorStatus isEnable: %{public}d", isEnable);
    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);
    isPcmProcessorEnable_ = isEnable;
}

void AudioSink::SetPCMProcessorMaxLen(int32_t maxProcessedPcmLen)
{
    MEDIA_LOG_I("SetPCMProcessorMaxLen: %{public}d", maxProcessedPcmLen);
    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);
    maxProcessedPcmLen_ = maxProcessedPcmLen;
}

void AudioSink::HandleBypassOutput(const std::shared_ptr<AVBuffer> &buffer)
{
    {
        std::lock_guard<std::mutex> pcmLock(pcmCallbackMutex_);
        FALSE_RETURN_NOLOG(pcmCallback_ != nullptr && isPcmOutputEnable_);
    }
    FALSE_RETURN_MSG(buffer != nullptr && buffer->memory_ != nullptr, "buffer is null.");
    FALSE_RETURN_MSG(bypassTask_ != nullptr, "bypassTask_ is null.");

    auto pcmBypassBuffer = CopyPcmBuffer(buffer);
    FALSE_RETURN(pcmBypassBuffer != nullptr);

    std::weak_ptr<AudioSink> weakPtr(shared_from_this());
    bypassTask_->SubmitJobOnce([weakPtr, pcmBypassBuffer] {
        auto strongPtr = weakPtr.lock();
        FALSE_RETURN(strongPtr != nullptr);
        FALSE_RETURN(strongPtr->state_.load() == Pipeline::FilterState::RUNNING);

        std::shared_ptr<IPCMCallback> callback;
        {
            std::lock_guard<std::mutex> pcmLock(strongPtr->pcmCallbackMutex_);
            FALSE_RETURN(strongPtr->pcmCallback_ != nullptr);
            callback = strongPtr->pcmCallback_;
        }

        std::shared_ptr<Meta> meta = std::make_shared<Meta>();
        {
            std::lock_guard<std::mutex> pluginLock(strongPtr->pluginMutex_);
            FALSE_RETURN(strongPtr->plugin_ != nullptr);
            strongPtr->plugin_->GetParameter(meta);
        }

        pcmBypassBuffer->meta_ = std::move(meta);
        callback->OnPCMOutput(pcmBypassBuffer);
    });
}

std::shared_ptr<AVBuffer> AudioSink::HandlePostProcessingOutput(const std::shared_ptr<AVBuffer> &buffer)
{
    std::shared_ptr<IPCMCallback> callback;
    {
        std::lock_guard<std::mutex> pcmLock(pcmCallbackMutex_);
        FALSE_RETURN_V_NOLOG(pcmCallback_ != nullptr && isPcmProcessorEnable_, buffer);
        callback = pcmCallback_;
    }

    FALSE_RETURN_V_MSG(buffer != nullptr && buffer->memory_ != nullptr, buffer, "buffer is null.");
    bool needExpand = maxProcessedPcmLen_ > buffer->memory_->GetCapacity();
    auto pcmBuffer = needExpand ? CopyPcmBuffer(buffer, maxProcessedPcmLen_) : buffer;
    FALSE_RETURN_V(pcmBuffer != nullptr, buffer);

    FALSE_RETURN_V(plugin_ != nullptr, buffer);
    std::shared_ptr<Meta> meta = std::make_shared<Meta>();
    plugin_->GetParameter(meta);

    pcmBuffer->meta_ = std::move(meta);
    callback->OnPCMProcessor(pcmBuffer);

    FALSE_RETURN_V_NOLOG(needExpand, buffer);
    if (pcmBuffer->memory_ != nullptr && pcmBuffer->memory_->GetSize() <= 0) {
        buffer->memory_->SetSize(0);
        return buffer;
    }
    auto processedBuffer = CopyPcmBuffer(pcmBuffer);
    FALSE_RETURN_V(processedBuffer != nullptr, buffer); // Copy buffer failed, use unprocessed buffer

    return processedBuffer;
}

std::shared_ptr<AVBuffer> AudioSink::CopyPcmBuffer(const std::shared_ptr<AVBuffer> buffer, int32_t minCapacity)
{
    FALSE_RETURN_V_MSG_E(buffer != nullptr && buffer->memory_ != nullptr && buffer->memory_->GetSize() > 0, nullptr,
        "buffer or memory is nullptr");
    AVBufferConfig avBufferConfig;

    // If minCapacity is default value or less than buffer size, use buffer size
    avBufferConfig.capacity = std::max(minCapacity, static_cast<int32_t>(buffer->memory_->GetSize()));
    avBufferConfig.memoryType = bufferMemoryType_;
    std::shared_ptr<AVBuffer> swapBuffer = AVBuffer::CreateAVBuffer(avBufferConfig);
    FALSE_RETURN_V_MSG_E(swapBuffer != nullptr && swapBuffer->memory_ != nullptr, nullptr, "create swapBuffer failed");
    swapBuffer->pts_ = buffer->pts_;
    swapBuffer->dts_ = buffer->dts_;
    swapBuffer->duration_ = buffer->duration_;
    swapBuffer->flag_ = buffer->flag_;
    FALSE_RETURN_V_MSG_E(swapBuffer->memory_->GetCapacity() >= buffer->memory_->GetSize(), nullptr, "no enough memory");
    errno_t res = memcpy_s(swapBuffer->memory_->GetAddr(),
        swapBuffer->memory_->GetCapacity(),
        buffer->memory_->GetAddr(),
        buffer->memory_->GetSize());
    FALSE_RETURN_V_MSG_E(res == EOK, nullptr, "copy data failed");
    swapBuffer->memory_->SetSize(buffer->memory_->GetSize());
    return swapBuffer;
}

Status AudioSink::ReleaseDecodedBuffer()
{
    FALSE_RETURN_V(inputBufferQueueConsumer_ != nullptr, Status::ERROR_UNKNOWN);
    FALSE_RETURN_V(!decodedBuffers_.empty(), Status::OK);
    auto decodedBuffer = std::move(decodedBuffers_.front());
    decodedBuffers_.pop();
    inputBufferQueueConsumer_->ReleaseBuffer(decodedBuffer);
    return Status::OK;
}

void AudioSink::UpdateSeekState(const std::shared_ptr<OHOS::Media::AVBuffer>& buffer)
{
    if (seekFlag_.load()) {
        isFirstFrameAfterSeek_ = true;
    } else if (isFirstFrameAfterSeek_) {
        isFirstFrameAfterSeek_ = false;
    } else {
        CheckPtsDiscontinuity(buffer);
    }
}

void AudioSink::CheckPtsDiscontinuity(const std::shared_ptr<OHOS::Media::AVBuffer>& buffer)
{
    FALSE_RETURN_NOLOG(playerEventReceiver_ != nullptr);
    FALSE_RETURN_NOLOG(buffer != nullptr);
    FALSE_RETURN_NOLOG(!(buffer->flag_ & static_cast<uint32_t>(AVBufferFlag::EOS)));
    
    int64_t curPts = buffer->pts_;
    int64_t lastPts = lastPtsForDiscontinuity_;
    lastPtsForDiscontinuity_ = curPts;
    
    int64_t ptsDiff = curPts > lastPts ? (curPts - lastPts) : (lastPts - curPts);
    if (ptsDiff > PTS_DISCONTINUE_THRESHOLD_US && lastPts != HST_TIME_NONE) {
        MEDIA_LOG_I("Audio PTS discontinuity detected, lastPts " PUBLIC_LOG_D64
            ", curPts " PUBLIC_LOG_D64, lastPts, curPts);
        MediaDiscontinueInfo discontinueInfo {
            .streamType = 1,
            .discontinueType = 2,
            .ptsBefore = lastPts,
            .ptsAfter = curPts
        };
        playerEventReceiver_->OnDfxEvent({"AudioSink", DfxEventType::DFX_EVENT_MEDIA_DISCONTINUE, discontinueInfo});
    }
}

void AudioSink::SetSeekFlag()
{
    seekFlag_.store(true);
    lastPtsForDiscontinuity_ = HST_TIME_NONE;
}
} // namespace MEDIA
} // namespace OHOS
