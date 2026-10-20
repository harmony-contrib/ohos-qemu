/*
 * Copyright (C) 2023-2025 Huawei Device Co., Ltd.
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

#ifndef HISTREAMER_AU_SERVER_SINK_PLUGIN_H
#define HISTREAMER_AU_SERVER_SINK_PLUGIN_H

#include <atomic>
#include <memory>
#include <unordered_map>

#include "audio_info.h"
#include "audio_renderer.h"
#include "osal/task/mutex.h"
#include "meta/audio_types.h"
#include "plugin/audio_sink_plugin.h"
#include "ffmpeg_utils.h"
#include "ffmpeg_convert.h"
#include "timestamp.h"

namespace OHOS {
namespace Media {
namespace Plugins {
class AudioServerSinkPlugin : public Plugins::AudioSinkPlugin,
    public std::enable_shared_from_this<AudioServerSinkPlugin> {
public:
    explicit AudioServerSinkPlugin(std::string name);

    ~AudioServerSinkPlugin() override;

    Status Init() override;

    __attribute__((no_sanitize("cfi"))) Status Deinit() override;

    Status Prepare() override;

    Status Reset() override;

    Status Start() override;

    Status Stop() override;

    Status GetParameter(std::shared_ptr<Meta> &meta) override;

    Status SetParameter(const std::shared_ptr<Meta> &meta) override;

    Status SetCallback(Callback *cb) override
    {
        callback_ = cb;
        return Status::OK;
    }

    Status GetMute(bool &mute) override
    {
        return Status::OK;
    }

    Status SetMute(bool mute) override
    {
        return Status::OK;
    }

    Status GetVolume(float &volume) override;

    Status SetVolume(float volume) override;

    Status SetVolumeMode(int32_t volume) override;

    Status GetSpeed(float &speed) override;

    Status SetSpeed(float speed) override;

    Status Pause() override;

    Status PauseTransitent() override;

    Status Resume() override;

    Status GetLatency(uint64_t &hstTime) override;

    Status GetFrameSize(size_t &size) override
    {
        return Status::OK;
    }

    Status GetFrameCount(uint32_t &count) override
    {
        return Status::OK;
    }

    Status Write(const std::shared_ptr<OHOS::Media::AVBuffer> &inputBuffer) override;

    int32_t WriteAudioVivid(const std::shared_ptr<OHOS::Media::AVBuffer> &inputBuffer);

    Status Flush() override;

    Status Drain() override;

    int64_t GetPlayedOutDurationUs(int64_t nowUs) override;

    Status GetFramePosition(int32_t &framePosition) override;

    void SetEventReceiver(const std::shared_ptr<Pipeline::EventReceiver>& receiver) override;

    int32_t SetVolumeWithRamp(float targetVolume, int32_t duration) override;

    Status GetAudioEffectMode(int32_t &effectMode) override;

    Status SetAudioEffectMode(int32_t effectMode) override;

    Status SetMuted(bool isMuted) override;

    AudioSampleFormat GetSampleFormat() override;

    int64_t GetWriteDurationMs() override;
 
    bool IsOffloading() override;

    Status SetRequestDataCallback(const std::shared_ptr<AudioSinkDataCallback> &callback) override;
 
    bool GetAudioPosition(timespec &time, uint32_t &framePosition) override;

    void Freeze() override;

    void UnFreeze() override;

    Status MuteAudioBuffer(uint8_t *addr, size_t offset, size_t length) override;

    Status EnqueueBufferDesc(const AudioStandard::BufferDesc &bufferDesc) override;
 
    Status GetBufferDesc(AudioStandard::BufferDesc &bufferDesc) override;

    void SetInterruptState(bool isInterruptNeeded) override;

    bool IsFormatSupported(const std::shared_ptr<Meta>& meta) override;

    void OnWriteData(size_t length);

    Status SetAudioHapticsSyncId(int32_t syncId) override;

    Status SetLoudnessGain(float loudnessGain) override;

    void OnFirstFrameWriting();

    void SetAudioPassFlag(bool isAudioPass) override;

    void SetResponseCallback(bool isNeedResponseCallback) override;

    bool IsNeedResponseCallback() override
    {
        return isNeedResponseCallback_;
    }
private:
    class AudioRendererCallbackImpl : public OHOS::AudioStandard::AudioRendererCallback,
        public OHOS::AudioStandard::AudioRendererOutputDeviceChangeCallback {
    public:
        AudioRendererCallbackImpl(const std::shared_ptr<Pipeline::EventReceiver> &receiver, const bool &isPaused);
        void OnInterrupt(const OHOS::AudioStandard::InterruptEvent &interruptEvent) override;
        void OnStateChange(const OHOS::AudioStandard::RendererState state,
                           const OHOS::AudioStandard::StateChangeCmdType cmdType) override;
        void OnOutputDeviceChange(const AudioStandard::AudioDeviceDescriptor &deviceInfo,
            const AudioStandard::AudioStreamDeviceChangeReason reason) override;
        void SetResponseCallback(bool isNeedResponseCallback);
    private:
        std::shared_ptr<Pipeline::EventReceiver> playerEventReceiver_;
        bool isPaused_{false};
        bool isNeedResponseCallback_ {true};
    };
    class AudioServiceDiedCallbackImpl : public OHOS::AudioStandard::AudioRendererPolicyServiceDiedCallback {
    public:
        explicit AudioServiceDiedCallbackImpl(std::shared_ptr<Pipeline::EventReceiver> &receiver);
        void OnAudioPolicyServiceDied() override;
    private:
        std::shared_ptr<Pipeline::EventReceiver> playerEventReceiver_;
    };
    class AudioFirstFrameCallbackImpl : public OHOS::AudioStandard::AudioRendererFirstFrameWritingCallback {
    public:
        explicit AudioFirstFrameCallbackImpl(std::shared_ptr<Pipeline::EventReceiver> &receiver,
            const std::weak_ptr<AudioServerSinkPlugin> &plugin);
        void OnFirstFrameWriting(uint64_t latency) override;

    private:
        std::shared_ptr<Pipeline::EventReceiver> playerEventReceiver_;
        std::weak_ptr<AudioServerSinkPlugin> plugin_;
    };
    class AudioRendererWriteCallbackImpl : public AudioStandard::AudioRendererWriteCallback {
    public:
        explicit AudioRendererWriteCallbackImpl(const std::weak_ptr<AudioServerSinkPlugin> &plugin);
        void OnWriteData(size_t length) override;
        void NotifyFreeze();
        void NotifyUnFreeze();
        void NotifyInterrupt(bool isInterruptNeeded);
    private:
        std::weak_ptr<AudioServerSinkPlugin> plugin_;
        std::mutex freezeMutex_;
        bool isFrozen_ {false};
        std::condition_variable freezeCond_;
        std::atomic<bool> isInterruptNeeded_ {false};
    };
    void ReleaseRender();
    __attribute__((no_sanitize("cfi"))) void ReleaseFile();
    bool StopRender();
    bool AssignSampleRateIfSupported(uint32_t sampleRate);
    bool AssignChannelNumIfSupported(uint32_t channelNum);
    bool AssignSampleFmtIfSupported(AudioSampleFormat sampleFormat);
    void SetInterruptMode(AudioStandard::InterruptMode interruptMode);

    void SetUpParamsSetterMap();
    void SetUpMimeTypeSetter();
    void SetUpSampleRateSetter();
    void SetUpAudioOutputChannelsSetter();
    void SetUpMediaBitRateSetter();
    void SetUpAudioSampleFormatSetter();
    void SetUpAudioOutputChannelLayoutSetter();
    void SetUpAudioSamplePerFrameSetter();
    void SetUpBitsPerCodedSampleSetter();
    void SetUpMediaSeekableSetter();
    void SetUpAppPidSetter();
    void SetUpAppUidSetter();
    void SetUpAudioRenderInfoSetter();
    void SetPrivacyType();
    void SetUpAudioInterruptModeSetter();
    void SetUpAudioRenderSetFlagSetter();
    void SetUpAudioRenderSourceDurationSetter();
    void SetAudioDumpBySysParam();
    void DumpEntireAudioBuffer(uint8_t* buffer, const size_t& bytesSingle);
    void DumpSliceAudioBuffer(uint8_t* buffer, const size_t& bytesSingle);
    void CacheData(uint8_t* inputBuffer, size_t bufferSize);
    Status DrainCacheData(bool render);
    //return value is the remained buffer size
    size_t WriteAudioBuffer(uint8_t* inputBuffer, size_t bufferSize, bool& shouldDrop);
    int32_t GetCallbackBufferDuration();
    int32_t ChooseVolumeMode();
    void ApplyAudioHapticsSyncId();
    int32_t GetAvailableBufferDuration(uint32_t customSampleRate);
    AudioStandard::AudioEncodingType GetEncodingType(std::string mime);

    OHOS::Media::Mutex renderMutex_{};
    Callback *callback_{};
    AudioRenderInfo audioRenderInfo_{};
    AudioStandard::AudioRendererOptions rendererOptions_{};
    AudioStandard::InterruptMode audioInterruptMode_{AudioStandard::InterruptMode::SHARE_MODE};
    std::unique_ptr<AudioStandard::AudioRenderer> audioRenderer_{nullptr};
    std::shared_ptr<AudioRendererCallbackImpl> audioRendererCallback_{nullptr};
    std::shared_ptr<OHOS::AudioStandard::AudioRendererFirstFrameWritingCallback> audioFirstFrameCallback_{nullptr};
    std::shared_ptr<OHOS::AudioStandard::AudioRendererPolicyServiceDiedCallback> audioServiceDiedCallback_{nullptr};
    AudioStandard::AudioRendererParams rendererParams_{};
    int64_t sourceDuraionMs_{-1};

    std::shared_ptr<Pipeline::EventReceiver> playerEventReceiver_;
    bool fmtSupported_{false};
    bool isForcePaused_{false};
    std::shared_ptr<Meta> meta_;
    AVSampleFormat reSrcFfFmt_{AV_SAMPLE_FMT_NONE};
    const AudioStandard::AudioSampleFormat reStdDestFmt_{AudioStandard::AudioSampleFormat::SAMPLE_S16LE};
    AudioChannelLayout channelLayout_{};
    std::string mimeType_;
    uint32_t channels_{};
    uint32_t samplesPerFrame_{};
    uint32_t bitsPerSample_{0};
    uint32_t sampleRate_{};
    int64_t bitRate_{0};
    int32_t appPid_{0};
    int32_t appUid_{0};
    int32_t volumeMode_{0};
    bool needReformat_{false};
    Plugins::Seekable seekable_{Plugins::Seekable::INVALID};
    std::shared_ptr<Ffmpeg::Resample> resample_{nullptr};

    std::unordered_map<TagType, std::function<Status(const ValueType &para)>> paramsSetterMap_;
    float audioRendererVolume_ = 1.0;

    FILE* entireDumpFile_ = nullptr;
    FILE* sliceDumpFile_ = nullptr;
    int32_t sliceCount_ {0};
    int32_t curCount_ {-1};
    bool enableEntireDump_ {false};
    bool enableDumpSlice_ {false};
    bool audioRenderSetFlag_ {false};
    std::list<std::vector<uint8_t>> cachedBuffers_;
    int64_t writeDuration_ = 0;
    std::shared_ptr<AudioRendererWriteCallbackImpl> audioRenderWriteCallback_ {nullptr};
    std::atomic<bool> isInterruptNeeded_{false};
    std::mutex mutex_;
    std::condition_variable writeCond_;
    std::mutex releaseRenderMutex_;
    bool isReleasingRender_ {false};
    std::weak_ptr<AudioSinkDataCallback> audioSinkDataCallback_;
    bool isAudioVivid_ {false};
    uint64_t enqueueNumber_ {0};
    int32_t audioHapticsSyncId_ {0};
    uint32_t customSampleRate_{0};
    int32_t privacyType_ {0};
    bool isAudioPass_ {false};
    bool isNeedResponseCallback_ {true};
};
} // namespace Plugin
} // namespace Media
} // namespace OHOS
#endif // HISTREAMER_AU_SERVER_SINK_PLUGIN_H
