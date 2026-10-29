/*
 * Copyright (c) 2023-2023 Huawei Device Co., Ltd.
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

#include "audio_capture_filter.h"
#include "common/log.h"
#include "filter/filter_factory.h"
#include "source/audio_capture/audio_capture_module.h"
#include "avcodec_trace.h"

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = { LOG_CORE, LOG_DOMAIN_RECORDER, "AudioCaptureFilter" };
static constexpr uint64_t AUDIO_NS_PER_SECOND = 1000000000;
static constexpr int64_t AUDIO_UNREGULAR_DELTA_TIME = 100000000;
static constexpr int64_t AUDIO_CAPTURE_READ_FAILED_WAIT_TIME = 20000000; // 20000000 us 20ms
static constexpr int64_t AUDIO_CAPTURE_READ_FRAME_TIME = 20000000; // 20000000 ns 20ms
static constexpr int64_t AUDIO_CAPTURE_READ_FRAME_TIME_HALF = 10000000;
static constexpr int32_t AUDIO_CAPTURE_MAX_CACHED_FRAMES = 256;
static constexpr int32_t AUDIO_RECORDER_FRAME_NUM = 5;
static constexpr uint64_t MAX_CAPTURE_BUFFER_SIZE = 100000;
}

namespace OHOS {
namespace Media {
namespace Pipeline {
constexpr uint32_t TIME_OUT_MS = 0;
static AutoRegisterFilter<AudioCaptureFilter> g_registerAudioCaptureFilter("builtin.recorder.audiocapture",
    FilterType::AUDIO_CAPTURE,
    [](const std::string& name, const FilterType type) {
        return std::make_shared<AudioCaptureFilter>(name, FilterType::AUDIO_CAPTURE);
    });

/// End of Stream Buffer Flag
constexpr uint32_t BUFFER_FLAG_EOS = 0x00000001;
class AudioCaptureFilterLinkCallback : public FilterLinkCallback {
public:
    explicit AudioCaptureFilterLinkCallback(std::shared_ptr<AudioCaptureFilter> audioCaptureFilter)
        : audioCaptureFilter_(std::move(audioCaptureFilter))
    {
    }

    void OnLinkedResult(const sptr<AVBufferQueueProducer> &queue, std::shared_ptr<Meta> &meta) override
    {
        if (auto captureFilter = audioCaptureFilter_.lock()) {
            captureFilter->OnLinkedResult(queue, meta);
        } else {
            MEDIA_LOG_I("invalid captureFilter");
        }
    }

    void OnUnlinkedResult(std::shared_ptr<Meta> &meta) override
    {
        if (auto captureFilter = audioCaptureFilter_.lock()) {
            captureFilter->OnUnlinkedResult(meta);
        } else {
            MEDIA_LOG_I("invalid captureFilter");
        }
    }

    void OnUpdatedResult(std::shared_ptr<Meta> &meta) override
    {
        if (auto captureFilter = audioCaptureFilter_.lock()) {
            captureFilter->OnUpdatedResult(meta);
        } else {
            MEDIA_LOG_I("invalid captureFilter");
        }
    }

private:
    std::weak_ptr<AudioCaptureFilter> audioCaptureFilter_;
};

class AudioCaptureModuleCallbackImpl : public AudioCaptureModule::AudioCaptureModuleCallback {
public:
    explicit AudioCaptureModuleCallbackImpl(std::shared_ptr<EventReceiver> receiver)
        : receiver_(receiver)
    {
    }
    void OnInterrupt(const std::string &interruptInfo) override
    {
        MEDIA_LOG_I("AudioCaptureModuleCallback interrupt: " PUBLIC_LOG_S, interruptInfo.c_str());
        receiver_->OnEvent({"audio_capture_filter", EventType::EVENT_ERROR,
            static_cast<int32_t>(Status::ERROR_AUDIO_INTERRUPT)});
    }
private:
    std::shared_ptr<EventReceiver> receiver_;
};

AudioCaptureFilter::AudioCaptureFilter(std::string name, FilterType type): Filter(name, type)
{
    MEDIA_LOG_I("audio capture filter create");
}

AudioCaptureFilter::~AudioCaptureFilter()
{
    MEDIA_LOG_I("audio capture filter destroy");
}

void AudioCaptureFilter::Init(const std::shared_ptr<EventReceiver> &receiver,
    const std::shared_ptr<FilterCallback> &callback)
{
    MEDIA_LOG_I("Init");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::Init");
    receiver_ = receiver;
    callback_ = callback;
    audioCaptureModule_ = std::make_shared<AudioCaptureModule::AudioCaptureModule>();
    std::shared_ptr<AudioCaptureModule::AudioCaptureModuleCallback> cb =
        std::make_shared<AudioCaptureModuleCallbackImpl>(receiver_);
    FALSE_RETURN_MSG(audioCaptureModule_ != nullptr, "AudioCaptureFilter audioCaptureModule_ is nullptr, Init fail.");
    Status cbError = audioCaptureModule_->SetAudioInterruptListener(cb);
    if (cbError != Status::OK) {
        MEDIA_LOG_E("audioCaptureModule_ SetAudioInterruptListener failed.");
    }
    audioCaptureModule_->SetAudioSource(sourceType_);
    audioCaptureModule_->SetParameter(audioCaptureConfig_);
    audioCaptureModule_->SetCallingInfo(appUid_, appPid_, bundleName_, instanceId_);
    Status err = audioCaptureModule_->Init();
    if (err != Status::OK) {
        MEDIA_LOG_E("Init audioCaptureModule fail");
    }
}

Status AudioCaptureFilter::PrepareAudioCapture()
{
    MEDIA_LOG_I("PrepareAudioCapture");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::PrepareAudioCapture");
    if (!taskPtr_) {
        taskPtr_ = std::make_shared<Task>("DataReader", groupId_, TaskType::AUDIO);
        taskPtr_->RegisterJob([this] {
            ReadLoop();
            return 0;
        });
    }
    if (audioCaptureModule_ == nullptr) {
        MEDIA_LOG_E("audioCaptureModule_ is nullptr, cannot Prepare");
        return Status::ERROR_NULL_POINTER;
    }
    Status err = audioCaptureModule_->Prepare();
    if (err != Status::OK) {
        MEDIA_LOG_E("audioCaptureModule prepare fail");
    }
    return err;
}

Status AudioCaptureFilter::SetAudioCaptureChangeCallback(
    const std::shared_ptr<AudioStandard::AudioCapturerInfoChangeCallback> &callback)
{
    if (audioCaptureModule_ == nullptr) {
        return Status::ERROR_WRONG_STATE;
    }
    return audioCaptureModule_->SetAudioCapturerInfoChangeCallback(callback);
}

Status AudioCaptureFilter::DoPrepare()
{
    MEDIA_LOG_I("Prepare");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::Prepare");
    if (callback_ == nullptr) {
        MEDIA_LOG_E("callback is nullptr");
        return Status::ERROR_NULL_POINTER;
    }
    return callback_->OnCallback(shared_from_this(), FilterCallBackCommand::NEXT_FILTER_NEEDED,
        StreamType::STREAMTYPE_RAW_AUDIO);
}

Status AudioCaptureFilter::DoStart()
{
    std::lock_guard<std::mutex> lifecycleLock(lifecycleMutex_);
    MEDIA_LOG_I("Start");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::Start");
    FALSE_RETURN_V_MSG_E(taskPtr_ != nullptr, Status::ERROR_INVALID_OPERATION, "audio reader task is null");
    eos_ = false;
    currentTime_ = 0;
    recordAudioFrameCount_ = 0;
    firstAudioFramePts_.store(-1);
    firstVideoFramePts_.store(-1);
    hasCalculateAVTime_ = false;
    GetCurrentTime(startTime_);
    MEDIA_LOG_I("[audio] startTime_: " PUBLIC_LOG_D64, startTime_);
    auto res = Status::ERROR_INVALID_OPERATION;
    // start audioCaptureModule firstly
    if (audioCaptureModule_) {
        res = audioCaptureModule_->Start();
    }
    FALSE_RETURN_V_MSG_E(res == Status::OK, res, "audioCaptureModule start failed");
    // start task secondly
    taskPtr_->Start();
    if (!taskPtr_->IsTaskRunning()) {
        audioCaptureModule_->Stop();
        return Status::ERROR_AUD_START_FAILED;
    }
    return res;
}

Status AudioCaptureFilter::DoPause()
{
    std::lock_guard<std::mutex> lifecycleLock(lifecycleMutex_);
    MEDIA_LOG_I("Pause");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::Pause");
    Status ret = Status::ERROR_INVALID_OPERATION;
    if (audioCaptureModule_) {
        ret = audioCaptureModule_->Stop();
    }
    if (ret != Status::OK) {
        MEDIA_LOG_E("audioCaptureModule stop fail");
        return Status::ERROR_AUD_STOP_FAILED;
    }
    // Stop wakes a blocking Read before Pause waits for its job to finish.
    if (taskPtr_) {
        taskPtr_->Pause();
    }

    GetCurrentTime(pauseTime_);
    MEDIA_LOG_I("[audio] pauseTime: " PUBLIC_LOG_D64, pauseTime_);
    if (withVideo_) {
        int32_t lostCount = 0;
        if (currentTime_ != 0 && currentTime_ < pauseTime_) {
            lostCount = ((pauseTime_ - currentTime_) + AUDIO_CAPTURE_READ_FRAME_TIME_HALF)
                / AUDIO_CAPTURE_READ_FRAME_TIME;
        } else if (currentTime_ == 0) {
            lostCount = ((pauseTime_ - startTime_ + AUDIO_CAPTURE_READ_FRAME_TIME_HALF)
                / AUDIO_CAPTURE_READ_FRAME_TIME) - static_cast<int64_t>(cachedAudioDataDeque_.size());
            MEDIA_LOG_I("[audio] no video frame return, fill audio frame by startTime");
        }
        if (lostCount > AUDIO_CAPTURE_MAX_CACHED_FRAMES) {
            // time diff is abnormal, do not fill data frame.
            MEDIA_LOG_W("[audio] abnormal time diff, please check");
        } else {
            FillLostFrame(lostCount);
        }
        if (!cachedAudioDataDeque_.empty()) {
            RecordCachedData(cachedAudioDataDeque_.size());
        }
    }
    MEDIA_LOG_I("Pause recordAudioFrameCount_: " PUBLIC_LOG_D64, recordAudioFrameCount_);
    return ret;
}

Status AudioCaptureFilter::DoResume()
{
    std::lock_guard<std::mutex> lifecycleLock(lifecycleMutex_);
    MEDIA_LOG_I("Resume");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::Resume");
    FALSE_RETURN_V_MSG_E(taskPtr_ != nullptr, Status::ERROR_INVALID_OPERATION, "audio reader task is null");
    currentTime_ = 0;
    firstAudioFramePts_.store(-1);
    firstVideoFramePts_.store(-1);
    hasCalculateAVTime_ = false;
    GetCurrentTime(startTime_);
    MEDIA_LOG_I("[audio] resumeTime: " PUBLIC_LOG_D64, startTime_);
    Status ret = Status::ERROR_INVALID_OPERATION;
    if (audioCaptureModule_) {
        ret = audioCaptureModule_->Start();
    }
    if (ret != Status::OK) {
        MEDIA_LOG_E("audioCapturer start failed");
        return Status::ERROR_AUD_START_FAILED;
    }
    taskPtr_->Start();
    if (!taskPtr_->IsTaskRunning()) {
        audioCaptureModule_->Stop();
        return Status::ERROR_AUD_START_FAILED;
    }
    return ret;
}

Status AudioCaptureFilter::DoStop()
{
    std::lock_guard<std::mutex> lifecycleLock(lifecycleMutex_);
    MEDIA_LOG_I("Stop");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::Stop");
    // stop task firstly
    if (taskPtr_) {
        taskPtr_->StopAsync();
    }
    // stop audioCaptureModule secondly
    Status ret = Status::OK;
    if (audioCaptureModule_) {
        ret = audioCaptureModule_->Stop();
    }
    if (ret != Status::OK) {
        MEDIA_LOG_E("audioCaptureModule stop fail");
        return ret;
    }
    if (taskPtr_) {
        taskPtr_->Stop();
    }
    firstAudioFramePts_.store(-1);
    firstVideoFramePts_.store(-1);
    currentTime_ = 0;
    startTime_ = 0;
    if (!cachedAudioDataDeque_.empty()) {
        RecordCachedData(cachedAudioDataDeque_.size());
    }
    MEDIA_LOG_I("Stop recordAudioFrameCount_: " PUBLIC_LOG_D64, recordAudioFrameCount_);
    return ret;
}

Status AudioCaptureFilter::DoFlush()
{
    MEDIA_LOG_I("Flush");
    return Status::OK;
}

Status AudioCaptureFilter::DoRelease()
{
    std::lock_guard<std::mutex> lifecycleLock(lifecycleMutex_);
    MEDIA_LOG_I("Release");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::Release");
    if (audioCaptureModule_) {
        auto ret = audioCaptureModule_->Stop();
        if (ret != Status::OK) {
            return ret;
        }
    }
    if (taskPtr_) {
        taskPtr_->Stop();
    }
    if (audioCaptureModule_) {
        auto ret = audioCaptureModule_->Deinit();
        if (ret != Status::OK) {
            return ret;
        }
    }
    audioCaptureModule_ = nullptr;
    taskPtr_ = nullptr;
    return Status::OK;
}

void AudioCaptureFilter::SetParameter(const std::shared_ptr<Meta> &meta)
{
    MEDIA_LOG_I("SetParameter");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::SetParameter");
    audioCaptureConfig_ = meta;
}

void AudioCaptureFilter::GetParameter(std::shared_ptr<Meta> &meta)
{
    MEDIA_LOG_I("GetParameter");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::GetParameter");
    if (audioCaptureModule_) {
        audioCaptureModule_->GetParameter(meta);
    }
}

Status AudioCaptureFilter::LinkNext(const std::shared_ptr<Filter> &nextFilter, StreamType outType)
{
    MEDIA_LOG_I("LinkNext");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::LinkNext");
    auto meta = std::make_shared<Meta>();
    GetParameter(meta);
    nextFilter_ = nextFilter;
    nextFiltersMap_[outType].push_back(nextFilter_);
    std::shared_ptr<FilterLinkCallback> filterLinkCallback =
        std::make_shared<AudioCaptureFilterLinkCallback>(shared_from_this());
    nextFilter->OnLinked(outType, meta, filterLinkCallback);
    return Status::OK;
}

FilterType AudioCaptureFilter::GetFilterType()
{
    MEDIA_LOG_I("GetFilterType");
    return FilterType::AUDIO_CAPTURE;
}

void AudioCaptureFilter::SetAudioSource(int32_t source)
{
    if (source == 1) {
        sourceType_ = AudioStandard::SourceType::SOURCE_TYPE_MIC;
    } else {
        sourceType_ = static_cast<AudioStandard::SourceType>(source);
    }
}

Status AudioCaptureFilter::SendEos()
{
    MEDIA_LOG_I("SendEos");
    Status ret = Status::OK;
    eos_ = true;
    GetCurrentTime(stopTime_);
    MEDIA_LOG_I("[audio] stopTime: " PUBLIC_LOG_D64, stopTime_);
    if (outputBufferQueue_) {
        if (!cachedAudioDataDeque_.empty()) {
            RecordCachedData(cachedAudioDataDeque_.size());
        }

        std::shared_ptr<AVBuffer> buffer;
        AVBufferConfig avBufferConfig;
        ret = outputBufferQueue_->RequestBuffer(buffer, avBufferConfig, TIME_OUT_MS);
        if (ret != Status::OK) {
            MEDIA_LOG_I("RequestBuffer fail, ret" PUBLIC_LOG_D32, ret);
            return ret;
        }
        buffer->flag_ |= BUFFER_FLAG_EOS;
        outputBufferQueue_->PushBuffer(buffer, false);
    }
    return ret;
}

void AudioCaptureFilter::ReadLoop()
{
    MEDIA_LOG_D("ReadLoop");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::ReadLoop");
    if (eos_.load()) {
        return;
    }
    uint64_t bufferSize = 0;
    auto ret = audioCaptureModule_->GetSize(bufferSize);
    if (ret != Status::OK) {
        MEDIA_LOG_E("Get audioCaptureModule buffer size fail");
        RelativeSleep(AUDIO_CAPTURE_READ_FAILED_WAIT_TIME);
        return;
    }

    if ((firstVideoFramePts_.load() < 0 || firstAudioFramePts_.load() < 0) && withVideo_) {
        if (cachedAudioDataDeque_.size() > AUDIO_CAPTURE_MAX_CACHED_FRAMES) {
            MEDIA_LOG_E("audioCapture cached frame over maxnum");
            firstVideoFramePts_.store(0);
            return;
        }
        auto cachedAudioData = AllocateAudioDataBuffer(bufferSize);
        if (!cachedAudioData) {
            return;
        }
        ret = audioCaptureModule_->Read(cachedAudioData.get(), bufferSize);
        if (ret != Status::OK) {
            MEDIA_LOG_E("audioCaptureModule read return again");
            RelativeSleep(AUDIO_CAPTURE_READ_FAILED_WAIT_TIME);
            return;
        }
        if (firstAudioFramePts_.load() < 0) {
            int64_t audioDataTime = 0;
            audioCaptureModule_->GetAudioTime(audioDataTime, true);
            if (audioDataTime == 0) {
                GetCurrentTime(audioDataTime);
            }
            firstAudioFramePts_.store(audioDataTime);
            MEDIA_LOG_I("firstAudioFramePts: " PUBLIC_LOG_D64, firstAudioFramePts_.load());
        }
        std::lock_guard<std::mutex> lock(cachedAudioDataMutex_);
        cachedAudioDataDeque_.push_back(cachedAudioData);
    } else {
        if (!hasCalculateAVTime_ && withVideo_) {
            CalculateAVTime();
        } else {
            RecordAudioFrame();
        }
    }
}

void AudioCaptureFilter::CalculateAVTime()
{
    if (audioCaptureModule_ == nullptr) {
        MEDIA_LOG_E("audioCaptureModule_ is nullptr, cannot CalculateAVTime");
        return;
    }
    uint64_t bufferSize = 0;
    audioCaptureModule_->GetSize(bufferSize);

    if (firstAudioFramePts_.load() > firstVideoFramePts_.load()) {
        // audio frame is later than video frame, add zeros to the front of the cache queue.
        int32_t diffCount = static_cast<int32_t>((firstAudioFramePts_.load() - firstVideoFramePts_.load()
            + AUDIO_CAPTURE_READ_FRAME_TIME_HALF) / AUDIO_CAPTURE_READ_FRAME_TIME);
        if (diffCount > AUDIO_CAPTURE_MAX_CACHED_FRAMES) {
            // video time is abnormal, do not fill data frame.
            currentTime_ = firstAudioFramePts_.load();
        } else {
            currentTime_ = firstAudioFramePts_.load() - diffCount * AUDIO_CAPTURE_READ_FRAME_TIME;
            MEDIA_LOG_I("Audio late, diffCount: " PUBLIC_LOG_D32, diffCount);
            FillLostFrame(diffCount);
        }
    } else {
        // audio frame is faster than video frame, crop frames of the cache queue.
        int32_t diffCount = static_cast<int32_t>((firstVideoFramePts_.load() - firstAudioFramePts_.load()
            + AUDIO_CAPTURE_READ_FRAME_TIME_HALF) / AUDIO_CAPTURE_READ_FRAME_TIME);
        if (diffCount > AUDIO_CAPTURE_MAX_CACHED_FRAMES) {
            // video time is abnormal, do not crop data frame.
            currentTime_ = firstAudioFramePts_.load();
        } else {
            currentTime_ = firstAudioFramePts_.load() + diffCount * AUDIO_CAPTURE_READ_FRAME_TIME;
            MEDIA_LOG_I("Video late, diffCount: " PUBLIC_LOG_D32, diffCount);
            std::lock_guard<std::mutex> lock(cachedAudioDataMutex_);
            while (diffCount > 0 && !cachedAudioDataDeque_.empty()) {
                cachedAudioDataDeque_.pop_front();
                --diffCount;
            }
        }
    }
    hasCalculateAVTime_ = true;
}

void AudioCaptureFilter::FillLostFrame(int32_t lostCount)
{
    if (audioCaptureModule_ == nullptr) {
        MEDIA_LOG_E("audioCaptureModule_ is nullptr, cannot FillLostFrame");
        return;
    }
    uint64_t bufferSize = 0;
    audioCaptureModule_->GetSize(bufferSize);
    auto cachedAudioData = AllocateAudioDataBuffer(bufferSize);
    if (!cachedAudioData) {
        return;
    }
    std::lock_guard<std::mutex> lock(cachedAudioDataMutex_);
    while (lostCount > 0) {
        cachedAudioDataDeque_.push_front(cachedAudioData);
        --lostCount;
    }
}

void AudioCaptureFilter::RecordAudioFrame()
{
    if (audioCaptureModule_ == nullptr) {
        MEDIA_LOG_E("audioCaptureModule_ is nullptr, cannot RecordAudioFrame");
        return;
    }
    uint64_t bufferSize = 0;
    audioCaptureModule_->GetSize(bufferSize);

    if (!cachedAudioDataDeque_.empty()) {
        auto cachedAudioData = AllocateAudioDataBuffer(bufferSize);
        if (!cachedAudioData) {
            return;
        }
        auto ret = audioCaptureModule_->Read(cachedAudioData.get(), bufferSize);
        if (ret != Status::OK) {
            MEDIA_LOG_E("audioCaptureModule read return fail");
            RelativeSleep(AUDIO_CAPTURE_READ_FAILED_WAIT_TIME);
            return;
        }
        int32_t lostCount = FillLostFrameNum();
        if (lostCount <= AUDIO_CAPTURE_MAX_CACHED_FRAMES && lostCount > 0) {
            FillLostFrame(lostCount);
        }
        {
            std::lock_guard<std::mutex> lock(cachedAudioDataMutex_);
            cachedAudioDataDeque_.push_back(cachedAudioData);
        }
        RecordCachedData(AUDIO_RECORDER_FRAME_NUM);
    } else {
        RecordOneAudioFrame(bufferSize);
    }
}

std::shared_ptr<uint8_t> AudioCaptureFilter::AllocateAudioDataBuffer(uint64_t bufferSize)
{
    if (bufferSize >= MAX_CAPTURE_BUFFER_SIZE) {
        MEDIA_LOG_E("bufferSize is too big, bufferSize: " PUBLIC_LOG_D64, bufferSize);
        return nullptr;
    }
    auto buffer = std::shared_ptr<uint8_t>(new (std::nothrow) uint8_t[bufferSize]{0},
        std::default_delete<uint8_t[]>());
    if (buffer.get() == nullptr) {
        MEDIA_LOG_W("create buffer fail");
    }
    return buffer;
}

int32_t AudioCaptureFilter::FillLostFrameNum()
{
    int64_t audioDataTime = 0;
    int32_t lostCount = 0;
    int64_t cachedAudioDateTime = static_cast<int64_t>(cachedAudioDataDeque_.size()) * AUDIO_CAPTURE_READ_FRAME_TIME;
    audioCaptureModule_->GetAudioTime(audioDataTime, false);
    if (audioDataTime > currentTime_ + cachedAudioDateTime
        && (audioDataTime - currentTime_ - cachedAudioDateTime) > static_cast<int64_t>(AUDIO_UNREGULAR_DELTA_TIME)
        && withVideo_) {
        MEDIA_LOG_I("[audio] audioDataTime: " PUBLIC_LOG_D64, audioDataTime);
        lostCount = (audioDataTime - AUDIO_CAPTURE_READ_FRAME_TIME - currentTime_
            - cachedAudioDateTime + AUDIO_CAPTURE_READ_FRAME_TIME_HALF) / AUDIO_CAPTURE_READ_FRAME_TIME;
        if (lostCount > AUDIO_CAPTURE_MAX_CACHED_FRAMES) {
            // time diff is abnormal, please check
            MEDIA_LOG_W("[audio] abnormal time diff, please check");
        }
    }
    return lostCount;
}

void AudioCaptureFilter::RecordOneAudioFrame(uint64_t bufferSize)
{
    FALSE_RETURN_MSG(audioCaptureModule_ != nullptr && outputBufferQueue_ != nullptr,
        "audioCaptureModule_ or outputBufferQueue_ is nullptr, cannot RecordOneAudioFrame");
    FALSE_RETURN_MSG(bufferSize > 0 && bufferSize < MAX_CAPTURE_BUFFER_SIZE, "invalid audio buffer size");
    std::shared_ptr<AVBuffer> buffer;
    AVBufferConfig avBufferConfig;
    avBufferConfig.size = static_cast<int32_t>(bufferSize);
    avBufferConfig.memoryFlag = MemoryFlag::MEMORY_READ_WRITE;
    auto ret = outputBufferQueue_->RequestBuffer(buffer, avBufferConfig, TIME_OUT_MS);
    if (ret != Status::OK || buffer == nullptr
        || buffer->memory_ == nullptr || buffer->memory_->GetCapacity() <= 0) {
        MEDIA_LOG_E("AudioCaptureFilter RequestBuffer fail");
        if (buffer != nullptr) {
            outputBufferQueue_->PushBuffer(buffer, false);
        }
        RelativeSleep(AUDIO_CAPTURE_READ_FAILED_WAIT_TIME);
        return;
    }
    ret = audioCaptureModule_->Read(buffer, static_cast<size_t>(bufferSize));
    if (ret != Status::OK) {
        MEDIA_LOG_E("audioCaptureModule read return fail");
        outputBufferQueue_->PushBuffer(buffer, false);
        RelativeSleep(AUDIO_CAPTURE_READ_FAILED_WAIT_TIME);
        return;
    }
    int32_t lostCount = FillLostFrameNum();
    if (lostCount <= AUDIO_CAPTURE_MAX_CACHED_FRAMES && lostCount > 0) {
        FillLostFrame(lostCount);
        RecordCachedData(lostCount);
    }
    ret = outputBufferQueue_->PushBuffer(buffer, true);
    if (ret != Status::OK) {
        MEDIA_LOG_E("PushBuffer fail");
        RelativeSleep(AUDIO_CAPTURE_READ_FAILED_WAIT_TIME);
        return;
    }
    currentTime_ += AUDIO_CAPTURE_READ_FRAME_TIME;
    recordAudioFrameCount_++;
    MEDIA_LOG_D("[audio] currentTime_: " PUBLIC_LOG_D64, currentTime_);
}

void AudioCaptureFilter::RecordCachedData(int32_t recordFrameNum)
{
    if (audioCaptureModule_ == nullptr) {
        MEDIA_LOG_E("audioCaptureModule_ is nullptr, cannot RecordCachedData");
        return;
    }
    uint64_t bufferSize = 0;
    if (audioCaptureModule_->GetSize(bufferSize) != Status::OK || bufferSize == 0 ||
        bufferSize >= MAX_CAPTURE_BUFFER_SIZE || recordFrameNum <= 0) {
        return;
    }

    std::deque<std::shared_ptr<uint8_t>> tempDataDeque;
    {
        std::lock_guard<std::mutex> lock(cachedAudioDataMutex_);
        MEDIA_LOG_I("cachedAudioDataList count: " PUBLIC_LOG_D32, static_cast<int32_t>(cachedAudioDataDeque_.size()));
        auto endIt = cachedAudioDataDeque_.begin()
            + std::min(recordFrameNum, static_cast<int32_t>(cachedAudioDataDeque_.size()));
        tempDataDeque.assign(cachedAudioDataDeque_.begin(), endIt);
        cachedAudioDataDeque_.erase(cachedAudioDataDeque_.begin(), endIt);
    }
    while (!tempDataDeque.empty() && outputBufferQueue_ && recordFrameNum > 0) {
        auto tmpData = tempDataDeque.front();
        tempDataDeque.pop_front();

        std::shared_ptr<AVBuffer> buffer;
        AVBufferConfig avBufferConfig;
        avBufferConfig.size = static_cast<int32_t>(bufferSize);
        avBufferConfig.memoryFlag = MemoryFlag::MEMORY_READ_WRITE;
        auto ret = outputBufferQueue_->RequestBuffer(buffer, avBufferConfig, TIME_OUT_MS);
        if (ret != Status::OK || buffer == nullptr
            || buffer->memory_ == nullptr || buffer->memory_->GetCapacity() <= 0) {
            MEDIA_LOG_E("AudioCaptureFilter RequestBuffer fail");
            if (buffer != nullptr) {
                outputBufferQueue_->PushBuffer(buffer, false);
            }
            RelativeSleep(AUDIO_CAPTURE_READ_FAILED_WAIT_TIME);
            continue;
        }
        auto memory = buffer->memory_;
        const int32_t offset = memory->GetOffset();
        const int32_t capacity = memory->GetCapacity();
        if (tmpData == nullptr || offset < 0 || offset > capacity ||
            bufferSize > static_cast<uint64_t>(capacity - offset) ||
            memory->Write(tmpData.get(), static_cast<int32_t>(bufferSize), offset) != static_cast<int32_t>(bufferSize) ||
            memory->SetSize(static_cast<int32_t>(bufferSize)) != Status::OK) {
            outputBufferQueue_->PushBuffer(buffer, false);
            continue;
        }
        ret = outputBufferQueue_->PushBuffer(buffer, true);
        if (ret != Status::OK) {
            MEDIA_LOG_E("PushBuffer fail");
            RelativeSleep(AUDIO_CAPTURE_READ_FAILED_WAIT_TIME);
            continue;
        }
        currentTime_ += AUDIO_CAPTURE_READ_FRAME_TIME;
        recordFrameNum--;
        recordAudioFrameCount_++;
        MEDIA_LOG_D("[audio] currentTime_: " PUBLIC_LOG_D64, currentTime_);
    }
}

void AudioCaptureFilter::GetCurrentTime(int64_t &currentTime)
{
    struct timespec timestamp = {0, 0};
    clock_gettime(CLOCK_MONOTONIC, &timestamp);
    currentTime = static_cast<int64_t>(timestamp.tv_sec) * static_cast<int64_t>(AUDIO_NS_PER_SECOND)
        + static_cast<int64_t>(timestamp.tv_nsec);
}

void AudioCaptureFilter::SetVideoFirstFramePts(int64_t firstFramePts)
{
    if (firstFramePts > startTime_ || !hasCalculateAVTime_) {
        firstVideoFramePts_.store(firstFramePts);
        MEDIA_LOG_I("set firstVideoFramePts: " PUBLIC_LOG_D64, firstVideoFramePts_.load());
    }
}

void AudioCaptureFilter::SetWithVideo(bool withVideo)
{
    withVideo_ = withVideo;
    MEDIA_LOG_I("set withVideo: " PUBLIC_LOG_D32, withVideo_);
}

Status AudioCaptureFilter::GetCurrentCapturerChangeInfo(AudioStandard::AudioCapturerChangeInfo &changeInfo)
{
    MEDIA_LOG_I("GetCurrentCapturerChangeInfo");
    if (audioCaptureModule_ == nullptr) {
        MEDIA_LOG_E("audioCaptureModule_ is nullptr, cannot get audio capturer change info");
        return Status::ERROR_INVALID_OPERATION;
    }
    audioCaptureModule_->GetCurrentCapturerChangeInfo(changeInfo);
    return Status::OK;
}

Status AudioCaptureFilter::GetMaxAmplitude(int32_t &amplitude)
{
    MEDIA_LOG_I("GetMaxAmplitude");
    if (audioCaptureModule_ == nullptr) {
        MEDIA_LOG_E("audioCaptureModule_ is nullptr, cannot get audio capturer change info");
        return Status::ERROR_INVALID_OPERATION;
    }
    amplitude = audioCaptureModule_->GetMaxAmplitude();
    return Status::OK;
}

Status AudioCaptureFilter::SetWillMuteWhenInterrupted(bool muteWhenInterrupted)
{
    MEDIA_LOG_I("SetWillMuteWhenInterrupted");
    if (audioCaptureModule_ == nullptr) {
        MEDIA_LOG_E("audioCaptureModule_ is nullptr, cannot SetWillMuteWhenInterrupted");
        return Status::ERROR_INVALID_OPERATION;
    }
    return audioCaptureModule_->SetWillMuteWhenInterrupted(muteWhenInterrupted);
}

void AudioCaptureFilter::OnLinkedResult(const sptr<AVBufferQueueProducer> &queue, std::shared_ptr<Meta> &meta)
{
    MEDIA_LOG_I("OnLinkedResult");
    MediaAVCodec::AVCodecTrace trace("AudioCaptureFilter::OnLinkedResult");
    outputBufferQueue_ = queue;
    PrepareAudioCapture();
}

Status AudioCaptureFilter::UpdateNext(const std::shared_ptr<Filter> &nextFilter, StreamType outType)
{
    MEDIA_LOG_I("UpdateNext");
    return Status::OK;
}

Status AudioCaptureFilter::UnLinkNext(const std::shared_ptr<Filter> &nextFilter, StreamType outType)
{
    MEDIA_LOG_I("UnLinkNext");
    return Status::OK;
}

Status AudioCaptureFilter::OnLinked(StreamType inType, const std::shared_ptr<Meta> &meta,
    const std::shared_ptr<FilterLinkCallback> &callback)
{
    MEDIA_LOG_I("OnLinked");
    return Status::OK;
}

Status AudioCaptureFilter::OnUpdated(StreamType inType, const std::shared_ptr<Meta> &meta,
    const std::shared_ptr<FilterLinkCallback> &callback)
{
    MEDIA_LOG_I("OnUpdated");
    return Status::OK;
}

Status AudioCaptureFilter::OnUnLinked(StreamType inType, const std::shared_ptr<FilterLinkCallback> &callback)
{
    MEDIA_LOG_I("OnUnLinked");
    return Status::OK;
}

void AudioCaptureFilter::OnUnlinkedResult(const std::shared_ptr<Meta> &meta)
{
    MEDIA_LOG_I("OnUnlinkedResult");
    (void) meta;
}

void AudioCaptureFilter::OnUpdatedResult(const std::shared_ptr<Meta> &meta)
{
    MEDIA_LOG_I("OnUpdatedResult");
    (void) meta;
}

void AudioCaptureFilter::SetCallingInfo(int32_t appUid, int32_t appPid,
    const std::string &bundleName, uint64_t instanceId)
{
    appUid_ = appUid;
    appPid_ = appPid;
    bundleName_ = bundleName;
    instanceId_ = instanceId;
    if (audioCaptureModule_) {
        audioCaptureModule_->SetCallingInfo(appUid, appPid, bundleName, instanceId);
    }
}

int32_t AudioCaptureFilter::RelativeSleep(int64_t nanoTime)
{
    int32_t ret = -1; // -1 for bad result.
    if (nanoTime <= 0) {
        MEDIA_LOG_E("RelativeSleep nanoTime <= 0");
        return ret;
    }
    struct timespec time;
    time.tv_sec = nanoTime / static_cast<int64_t>(AUDIO_NS_PER_SECOND);
    // Avoids % operation.
    time.tv_nsec = nanoTime - (static_cast<int64_t>(time.tv_sec) * static_cast<int64_t>(AUDIO_NS_PER_SECOND));
    clockid_t clockId = CLOCK_MONOTONIC;
    const int relativeFlag = 0; // flag of relative sleep.
    ret = clock_nanosleep(clockId, relativeFlag, &time, nullptr);
    if (ret != 0) {
        MEDIA_LOG_I("RelativeSleep may failed, ret is :%{public}d", ret);
    }
    return ret;
}

} // namespace Pipeline
} // namespace Media
} // namespace OHOS