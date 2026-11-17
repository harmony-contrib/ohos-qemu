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
#ifndef FILTERS_AUDIO_CAPTURE_FILTER_H
#define FILTERS_AUDIO_CAPTURE_FILTER_H

#include <deque>
#include <mutex>
#include "filter/filter.h"
#include "common/status.h"
#include "osal/task/task.h"
#include "audio_capturer.h"

namespace OHOS {
namespace Media {
namespace AudioCaptureModule {
class AudioCaptureModule;
}
namespace Pipeline {

class AudioCaptureFilter : public Filter, public std::enable_shared_from_this<AudioCaptureFilter> {
public:
    explicit AudioCaptureFilter(std::string name, FilterType type);
    ~AudioCaptureFilter() override;
    void Init(const std::shared_ptr<EventReceiver> &receiver,
        const std::shared_ptr<FilterCallback> &callback) override;
    Status DoPrepare() override;
    Status DoStart() override;
    Status DoPause() override;
    Status DoResume() override;
    Status DoStop() override;
    Status DoFlush() override;
    Status DoRelease() override;
    void SetParameter(const std::shared_ptr<Meta> &meta) override;
    void GetParameter(std::shared_ptr<Meta> &meta) override;
    Status LinkNext(const std::shared_ptr<Filter> &nextFilter, StreamType outType) override;
    Status UpdateNext(const std::shared_ptr<Filter> &nextFilter, StreamType outType) override;
    Status UnLinkNext(const std::shared_ptr<Filter> &nextFilter, StreamType outType) override;
    Status SendEos();
    FilterType GetFilterType();
    void SetAudioSource(int32_t source);
    void OnLinkedResult(const sptr<AVBufferQueueProducer> &queue, std::shared_ptr<Meta> &meta);
    Status OnLinked(StreamType inType, const std::shared_ptr<Meta> &meta,
        const std::shared_ptr<FilterLinkCallback> &callback) override;
    Status OnUpdated(StreamType inType, const std::shared_ptr<Meta> &meta,
        const std::shared_ptr<FilterLinkCallback> &callback) override;
    Status OnUnLinked(StreamType inType, const std::shared_ptr<FilterLinkCallback> &callback) override;
    void OnUnlinkedResult(const std::shared_ptr<Meta> &meta);
    void OnUpdatedResult(const std::shared_ptr<Meta> &meta);
    Status SetAudioCaptureChangeCallback(
        const std::shared_ptr<AudioStandard::AudioCapturerInfoChangeCallback> &callback);
    Status GetCurrentCapturerChangeInfo(AudioStandard::AudioCapturerChangeInfo &changeInfo);
    Status SetWillMuteWhenInterrupted(bool muteWhenInterrupted);
    Status GetMaxAmplitude(int32_t &amplitude);
    void SetVideoFirstFramePts(int64_t firstFramePts);
    void SetWithVideo(bool withVideo);
    void SetCallingInfo(int32_t appUid, int32_t appPid, const std::string &bundleName, uint64_t instanceId);
private:
    void ReadLoop();
    Status PrepareAudioCapture();
    // Worker jobs do not acquire this control-operation lock.
    std::mutex lifecycleMutex_;
    std::shared_ptr<Task> taskPtr_{nullptr};
    int32_t RelativeSleep(int64_t nanoTime);
    void GetCurrentTime(int64_t &currentTime);
    void CalculateAVTime();
    void FillLostFrame(int32_t lostCount);
    void RecordCachedData(int32_t recordFrameNum);
    void RecordAudioFrame();
    int32_t FillLostFrameNum();
    void RecordOneAudioFrame(uint64_t bufferSize);
    std::shared_ptr<uint8_t> AllocateAudioDataBuffer(uint64_t bufferSize);
    std::shared_ptr<AudioCaptureModule::AudioCaptureModule> audioCaptureModule_{nullptr};
    sptr<AVBufferQueueProducer> outputBufferQueue_;
    AudioStandard::SourceType sourceType_ = AudioStandard::SourceType::SOURCE_TYPE_INVALID;
    std::shared_ptr<Meta> audioCaptureConfig_;

    std::shared_ptr<EventReceiver> receiver_;
    std::shared_ptr<FilterCallback> callback_;

    std::shared_ptr<Filter> nextFilter_;
    std::atomic<bool> eos_{false};
    std::string bundleName_;
    uint64_t instanceId_{0};
    int32_t appUid_ {0};
    int32_t appPid_ {0};
    bool withVideo_ {true};
    bool hasCalculateAVTime_ {false};
    int64_t startTime_ {0};
    int64_t pauseTime_ {0};
    int64_t stopTime_ {0};
    int64_t currentTime_ {0};
    int64_t recordAudioFrameCount_{0};
    std::atomic<int64_t> firstAudioFramePts_{-1};
    std::atomic<int64_t> firstVideoFramePts_{-1};
    std::deque<std::shared_ptr<uint8_t>> cachedAudioDataDeque_;
    std::mutex cachedAudioDataMutex_;
};
} // namespace Pipeline
} // namespace Media
} // namespace OHOS
#endif // FILTERS_AUDIO_CAPTURE_FILTER_H

