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
#include "audio_capture_module.h"
#include <cstring>
#include "common/log.h"
#include "osal/task/autolock.h"
#include "common/status.h"
#include "audio_type_translate.h"
#include "audio_capturer.h"
#include "avcodec_sysevent.h"

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = { LOG_CORE, LOG_DOMAIN_RECORDER, "AudioCaptureModule" };
static constexpr uint64_t AUDIO_NS_PER_SECOND = 1000000000;
static constexpr uint64_t AUDIO_CAPTURE_READ_FRAME_TIME = 20000000; // 20000000 ns 20ms
}

namespace OHOS {
namespace Media {
namespace AudioCaptureModule {
using namespace OHOS::MediaAVCodec;
#define FAIL_LOG_RETURN(exec, msg) \
do { \
    auto ret = (exec); \
    if (ret != 0) { \
        MEDIA_LOG_E(msg " failed return " PUBLIC_LOG_D32, ret); \
        return Error2Status(ret); \
    } \
} while (0)

constexpr size_t MAX_CAPTURE_BUFFER_SIZE = 100000;

class AudioCapturerCallbackImpl : public AudioStandard::AudioCapturerCallback {
public:
    explicit AudioCapturerCallbackImpl(std::shared_ptr<AudioCaptureModuleCallback> audioCaptureModuleCallback)
        : audioCaptureModuleCallback_(audioCaptureModuleCallback)
    {
    }

    void OnInterrupt(const AudioStandard::InterruptEvent &interruptEvent) override
    {
        MEDIA_LOG_E("AudioCapture OnInterrupt Hint: " PUBLIC_LOG_D32 ", EventType: " PUBLIC_LOG_D32 ", forceType: "
            PUBLIC_LOG_D32, interruptEvent.hintType, interruptEvent.eventType, interruptEvent.forceType);

        if (interruptEvent.hintType == AudioStandard::InterruptHint::INTERRUPT_HINT_MUTE ||
            interruptEvent.hintType == AudioStandard::InterruptHint::INTERRUPT_HINT_UNMUTE) {
            MEDIA_LOG_I("AudioCapture OnInterrupt recv mute state change event, ignore...");
            return;
        }
        if (audioCaptureModuleCallback_ != nullptr) {
            MEDIA_LOG_I("audioCaptureModuleCallback_ send info to audioCaptureFilter");
            audioCaptureModuleCallback_->OnInterrupt("AudioCapture OnInterrupt");
        }
    }

    void OnStateChange(const AudioStandard::CapturerState state) override
    {
    }

private:
    std::shared_ptr<AudioCaptureModuleCallback> audioCaptureModuleCallback_;
};

AudioCaptureModule::AudioCaptureModule()
{
}

AudioCaptureModule::~AudioCaptureModule()
{
    DoDeinit();
}

Status AudioCaptureModule::Init()
{
    std::lock_guard<std::mutex> controlLock(controlMutex_);
    AutoLock lock(captureMutex_);
    if (audioCapturer_ == nullptr) {
        AudioStandard::AppInfo appInfo;
        appInfo.appTokenId = static_cast<uint32_t>(appTokenId_);
        appInfo.appUid = appUid_;
        appInfo.appPid = appPid_;
        appInfo.appFullTokenId = static_cast<uint64_t>(appFullTokenId_);
        options_.capturerInfo.recorderType = AudioStandard::RecorderType::RECORDER_TYPE_AV_RECORDER;
        audioCapturer_ = AudioStandard::AudioCapturer::Create(options_, appInfo);
        if (audioCapturer_ == nullptr) {
            MEDIA_LOG_E("Create audioCapturer fail");
            SetFaultEvent("AudioCaptureModule::Init, create audioCapturer fail");
            return Status::ERROR_AUD_INIT_FAILED;
        }
        audioInterruptCallback_ = std::make_shared<AudioCapturerCallbackImpl>(audioCaptureModuleCallback_);
        audioCapturer_->SetCapturerCallback(audioInterruptCallback_);
    }
    return Status::OK;
}

Status AudioCaptureModule::DoDeinit()
{
    std::lock_guard<std::mutex> controlLock(controlMutex_);
    std::shared_ptr<AudioStandard::AudioCapturer> capturer;
    {
        AutoLock lock(captureMutex_);
        ++readGeneration_;
        capturer = audioCapturer_;
        if (capturer == nullptr) {
            return Status::OK;
        }
        if (capturer->GetStatus() == AudioStandard::CAPTURER_RUNNING && !capturer->Stop()) {
            return Status::ERROR_AUD_STOP_FAILED;
        }
        // Reject new reads before waiting for the stopped generation to leave Read().
        audioCapturer_ = nullptr;
    }
    std::lock_guard<std::mutex> readLock(readMutex_);
    if (!capturer->Release()) {
        AutoLock lock(captureMutex_);
        audioCapturer_ = capturer;
        return Status::ERROR_INVALID_OPERATION;
    }
    capturer->RemoveAudioCapturerInfoChangeCallback(audioCapturerInfoChangeCallback_);
    return Status::OK;
}

Status AudioCaptureModule::Deinit()
{
    MEDIA_LOG_I("Deinit");
    return DoDeinit();
}

Status AudioCaptureModule::Prepare()
{
    MEDIA_LOG_I("Prepare enter.");
    size_t size;
    {
        AutoLock lock (captureMutex_);
        FALSE_RETURN_V_MSG_E(audioCapturer_ != nullptr, Status::ERROR_AUD_INIT_FAILED, "no available audio capture");
        FAIL_LOG_RETURN(audioCapturer_->GetBufferSize(size), "audioCapturer GetBufferSize");
    }
    FALSE_RETURN_V_MSG_E(size < MAX_CAPTURE_BUFFER_SIZE, Status::ERROR_INVALID_PARAMETER,
        "bufferSize is too big: " PUBLIC_LOG_ZU, size);
    bufferSize_ = size;
    MEDIA_LOG_E("bufferSize is: " PUBLIC_LOG_ZU, bufferSize_);
    return Status::OK;
}

Status AudioCaptureModule::Reset()
{
    std::lock_guard<std::mutex> controlLock(controlMutex_);
    MEDIA_LOG_I("Reset enter.");
    {
        AutoLock lock (captureMutex_);
        FALSE_RETURN_V_MSG_E(audioCapturer_ != nullptr, Status::ERROR_AUD_INIT_FAILED, "no available audio capture");
        ++readGeneration_;
        if (audioCapturer_->GetStatus() == AudioStandard::CapturerState::CAPTURER_RUNNING &&
            !audioCapturer_->Stop()) {
            return Status::ERROR_AUD_STOP_FAILED;
        }
    }
    bufferSize_ = 0;
    bitRate_ = 0;
    options_ = AudioStandard::AudioCapturerOptions();
    return Status::OK;
}

Status AudioCaptureModule::Start()
{
    std::lock_guard<std::mutex> controlLock(controlMutex_);
    MEDIA_LOG_I("start enter.");
    AutoLock lock (captureMutex_);
    FALSE_RETURN_V_MSG_E(audioCapturer_ != nullptr, Status::ERROR_AUD_INIT_FAILED, "no available audio capture");
    if (audioCapturer_->GetStatus() != AudioStandard::CapturerState::CAPTURER_RUNNING) {
        if (!audioCapturer_->Start()) {
            MEDIA_LOG_E("audioCapturer start failed");
            SetFaultEvent("AudioCaptureModule::Start error");
            return Status::ERROR_AUD_START_FAILED;
        }
    }
    isTrackMaxAmplitude = false;
    return Status::OK;
}

Status AudioCaptureModule::Stop()
{
    std::lock_guard<std::mutex> controlLock(controlMutex_);
    MEDIA_LOG_I("stop enter.");
    AutoLock lock (captureMutex_);
    ++readGeneration_;
    if (audioCapturer_ && audioCapturer_->GetStatus() == AudioStandard::CAPTURER_RUNNING) {
        if (!audioCapturer_->Stop()) {
            MEDIA_LOG_E("Stop audioCapturer fail");
            SetFaultEvent("audioCapturer stop fail");
            return Status::ERROR_AUD_STOP_FAILED;
        }
    }
    return Status::OK;
}

Status AudioCaptureModule::GetParameter(std::shared_ptr<Meta> &meta)
{
    MEDIA_LOG_I("GetParameter enter.");
    AudioStandard::AudioCapturerParams params;
    {
        AutoLock lock (captureMutex_);
        if (!audioCapturer_) {
            return Status::ERROR_AUD_INIT_FAILED;
        }
        FAIL_LOG_RETURN(audioCapturer_->GetParams(params), "audioCapturer GetParams");
    }

    if (params.samplingRate != options_.streamInfo.samplingRate) {
        MEDIA_LOG_W("samplingRate has changed from " PUBLIC_LOG_U32 " to " PUBLIC_LOG_U32,
            options_.streamInfo.samplingRate, params.samplingRate);
    }
    FALSE_RETURN_V_MSG_E(meta != nullptr, Status::ERROR_NULL_POINTER, "meta is null, set audio sample rate");
    FALSE_LOG(meta->Set<Tag::AUDIO_SAMPLE_RATE>(params.samplingRate));

    if (params.audioChannel != options_.streamInfo.channels) {
        MEDIA_LOG_W("audioChannel has changed from " PUBLIC_LOG_U32 " to " PUBLIC_LOG_U32,
            options_.streamInfo.channels, params.audioChannel);
    }
    FALSE_RETURN_V_MSG_E(meta != nullptr, Status::ERROR_NULL_POINTER, "meta is null, set audio channel");
    FALSE_LOG(meta->Set<Tag::AUDIO_CHANNEL_COUNT>(params.audioChannel));

    if (params.audioSampleFormat != options_.streamInfo.format) {
        MEDIA_LOG_W("audioSampleFormat has changed from " PUBLIC_LOG_U32 " to " PUBLIC_LOG_U32,
            options_.streamInfo.format, params.audioSampleFormat);
    }
    FALSE_RETURN_V_MSG_E(meta != nullptr, Status::ERROR_NULL_POINTER, "meta is null, set audio sample format");
    FALSE_LOG(meta->Set<Tag::AUDIO_SAMPLE_FORMAT>(static_cast<Plugins::AudioSampleFormat>(params.audioSampleFormat)));

    FALSE_RETURN_V_MSG_E(meta != nullptr, Status::ERROR_NULL_POINTER, "meta is null, set audio bitrate");
    meta->Set<Tag::MEDIA_BITRATE>(bitRate_);
    return Status::OK;
}

Status AudioCaptureModule::SetParameter(const std::shared_ptr<Meta> &meta)
{
    FALSE_LOG_MSG(meta->Get<Tag::APP_TOKEN_ID>(appTokenId_), "Unknown APP_TOKEN_ID");
    FALSE_LOG_MSG(meta->Get<Tag::APP_UID>(appUid_), "Unknown APP_UID");
    FALSE_LOG_MSG(meta->Get<Tag::APP_PID>(appPid_), "Unknown APP_PID");
    FALSE_LOG_MSG(meta->Get<Tag::APP_FULL_TOKEN_ID>(appFullTokenId_), "Unknown appFullTokenId_");
    FALSE_LOG_MSG(meta->Get<Tag::MEDIA_BITRATE>(bitRate_), "Unknown MEDIA_BITRATE");

    int32_t sampleRate = 0;
    if (meta->Get<Tag::AUDIO_SAMPLE_RATE>(sampleRate)) {
        FALSE_RETURN_V_MSG_E(AssignSampleRateIfSupported(sampleRate), Status::ERROR_INVALID_PARAMETER,
            "SampleRate is unsupported by audiocapturer");
    }

    int32_t channelCount = 0;
    if (meta->Get<Tag::AUDIO_CHANNEL_COUNT>(channelCount)) {
        FALSE_RETURN_V_MSG_E(AssignChannelNumIfSupported(channelCount), Status::ERROR_INVALID_PARAMETER,
            "ChannelNum is unsupported by audiocapturer");
    }

    Plugins::AudioSampleFormat sampleFormat;
    if (meta->Get<Tag::AUDIO_SAMPLE_FORMAT>(sampleFormat)) {
        FALSE_RETURN_V_MSG_E(AssignSampleFmtIfSupported(static_cast<Plugins::AudioSampleFormat>(sampleFormat)),
            Status::ERROR_INVALID_PARAMETER, "SampleFormat is unsupported by audiocapturer");
    }

    AudioStandard::AudioEncodingType audioEncoding = AudioStandard::ENCODING_INVALID;
    auto supportedEncodingTypes = OHOS::AudioStandard::AudioCapturer::GetSupportedEncodingTypes();
    for (auto& supportedEncodingType : supportedEncodingTypes) {
        if (supportedEncodingType == AudioStandard::ENCODING_PCM) {
            audioEncoding = AudioStandard::ENCODING_PCM;
            break;
        }
    }

    if (audioEncoding != AudioStandard::ENCODING_PCM) {
        MEDIA_LOG_E("audioCapturer do not support pcm encoding");
        SetFaultEvent("AudioCaptureModule::Prepare, audioCapturer do not support pcm encoding");
        return Status::ERROR_UNKNOWN;
    }
    options_.streamInfo.encoding = AudioStandard::ENCODING_PCM;
    return Status::OK;
}

bool AudioCaptureModule::AssignSampleRateIfSupported(const int32_t value)
{
    uint32_t sampleRate = static_cast<uint32_t>(value);
    AudioStandard::AudioSamplingRate aRate = AudioStandard::SAMPLE_RATE_8000;
    FALSE_RETURN_V_MSG_E(SampleRateNum2Enum(sampleRate, aRate), false, "sample rate " PUBLIC_LOG_U32
        "not supported", sampleRate);
    for (const auto& rate : AudioStandard::AudioCapturer::GetSupportedSamplingRates()) {
        if (rate == sampleRate) {
            options_.streamInfo.samplingRate = rate;
            return true;
        }
    }
    return false;
}

bool AudioCaptureModule::AssignChannelNumIfSupported(const int32_t value)
{
    uint32_t channelNum = static_cast<uint32_t>(value);
    constexpr uint32_t maxSupportChannelNum = 2;
    if (channelNum > maxSupportChannelNum) {
        MEDIA_LOG_E("Unsupported channelNum: " PUBLIC_LOG_U32, channelNum);
        return false;
    }
    AudioStandard::AudioChannel aChannel = AudioStandard::MONO;
    FALSE_RETURN_V_MSG_E(ChannelNumNum2Enum(channelNum, aChannel), false, "Channel num "
        PUBLIC_LOG_U32 "not supported", channelNum);
    for (const auto& channel : AudioStandard::AudioCapturer::GetSupportedChannels()) {
        if (channel == channelNum) {
            options_.streamInfo.channels = channel;
            return true;
        }
    }
    return false;
}

bool AudioCaptureModule::AssignSampleFmtIfSupported(const Plugins::AudioSampleFormat value)
{
    Plugins::AudioSampleFormat sampleFormat = value;
    AudioStandard::AudioSampleFormat aFmt = AudioStandard::AudioSampleFormat::INVALID_WIDTH;
    FALSE_RETURN_V_MSG_E(ModuleFmt2SampleFmt(sampleFormat, aFmt), false,
        "sample format " PUBLIC_LOG_U8 " not supported", static_cast<uint8_t>(sampleFormat));
    for (const auto& fmt : AudioStandard::AudioCapturer::GetSupportedFormats()) {
        if (fmt == aFmt) {
            options_.streamInfo.format = fmt;
            return true;
        }
    }
    return false;
}

Status AudioCaptureModule::Read(std::shared_ptr<AVBuffer> &buffer, size_t expectedLen)
{
    if (buffer == nullptr || buffer->meta_ == nullptr || buffer->memory_ == nullptr ||
        expectedLen == 0 || expectedLen >= MAX_CAPTURE_BUFFER_SIZE) {
        return Status::ERROR_INVALID_PARAMETER;
    }
    auto memory = buffer->memory_;
    const int32_t capacity = memory->GetCapacity();
    const int32_t offset = memory->GetOffset();
    if (capacity <= 0 || offset < 0 || offset > capacity ||
        expectedLen > static_cast<size_t>(capacity - offset) || memory->GetAddr() == nullptr ||
        (memory->GetMemoryFlag() & MemoryFlag::MEMORY_WRITE_ONLY) == 0) {
        return Status::ERROR_INVALID_PARAMETER;
    }
    auto ret = memory->SetSize(0);
    if (ret != Status::OK) {
        return ret;
    }
    ret = Read(memory->GetAddr() + offset, expectedLen);
    if (ret != Status::OK) {
        return ret;
    }
    return memory->SetSize(static_cast<int32_t>(expectedLen));
}

Status AudioCaptureModule::Read(uint8_t *cacheAudioData, size_t expectedLen)
{
    if (cacheAudioData == nullptr || expectedLen == 0 || expectedLen >= MAX_CAPTURE_BUFFER_SIZE) {
        return Status::ERROR_INVALID_PARAMETER;
    }
    // Serialize readers, but never hold captureMutex_ across a blocking Capturer::Read.
    std::lock_guard<std::mutex> readLock(readMutex_);
    std::shared_ptr<AudioStandard::AudioCapturer> capturer;
    uint64_t generation;
    {
        AutoLock lock(captureMutex_);
        capturer = audioCapturer_;
        generation = readGeneration_;
    }
    if (capturer == nullptr) {
        return Status::ERROR_AUD_INIT_FAILED;
    }
    size_t filled = 0;
    while (filled < expectedLen) {
        {
            AutoLock lock(captureMutex_);
            if (generation != readGeneration_ || capturer != audioCapturer_ ||
                capturer->GetStatus() != AudioStandard::CAPTURER_RUNNING) {
                return Status::ERROR_AGAIN;
            }
        }
        const size_t remaining = expectedLen - filled;
        const int32_t readSize = capturer->Read(cacheAudioData[filled], remaining, true);
        if (readSize <= 0 || static_cast<size_t>(readSize) > remaining) {
            return Status::ERROR_NOT_ENOUGH_DATA;
        }
        filled += static_cast<size_t>(readSize);
    }
    AutoLock lock(captureMutex_);
    // Stop/Resume may have completed while the last blocking read was returning.
    if (generation != readGeneration_ || capturer != audioCapturer_ ||
        capturer->GetStatus() != AudioStandard::CAPTURER_RUNNING) {
        return Status::ERROR_AGAIN;
    }
    if (isTrackMaxAmplitude) {
        TrackMaxAmplitude(cacheAudioData, static_cast<int32_t>(filled / sizeof(int16_t)));
    }
    return Status::OK;
}

void AudioCaptureModule::GetAudioTime(int64_t &audioDataTime, bool isFirstFrame)
{
    MEDIA_LOG_D("AudioCaptureModule GetAudioTime");
    bool ret = true;
    {
        AutoLock lock(captureMutex_);
        FALSE_RETURN_MSG(audioCapturer_ != nullptr, "Audio capture is null");
        FALSE_RETURN_MSG(audioCapturer_->GetStatus() == AudioStandard::CAPTURER_RUNNING,
            "Audio capture Status error");
        AudioStandard::Timestamp timestamp{};
        ret = audioCapturer_->GetTimeStampInfo(timestamp, AudioStandard::Timestamp::Timestampbase::MONOTONIC);
        FALSE_RETURN_MSG(ret, "audioCapturer GetAudioTime fail");

        audioDataTime = static_cast<int64_t>(timestamp.time.tv_sec) * AUDIO_NS_PER_SECOND
            + static_cast<int64_t>(timestamp.time.tv_nsec);
        MEDIA_LOG_D("GetTimeStampInfo audioDataTime: " PUBLIC_LOG_D64, audioDataTime);

        if (isFirstFrame) {
            audioDataTime -= AUDIO_CAPTURE_READ_FRAME_TIME;
        }
    }
}

Status AudioCaptureModule::GetSize(uint64_t& size)
{
    if (bufferSize_ == 0) {
        return Status::ERROR_INVALID_PARAMETER;
    }
    size = bufferSize_;
    return Status::OK;
}

Status AudioCaptureModule::SetAudioInterruptListener(const std::shared_ptr<AudioCaptureModuleCallback> &callback)
{
    if (callback == nullptr) {
        MEDIA_LOG_E("SetAudioInterruptListener callback input param is nullptr");
        return Status::ERROR_INVALID_PARAMETER;
    }
    audioCaptureModuleCallback_ = callback;
    return Status::OK;
}

Status AudioCaptureModule::SetAudioCapturerInfoChangeCallback(
    const std::shared_ptr<AudioStandard::AudioCapturerInfoChangeCallback> &callback)
{
    if (audioCapturer_ == nullptr) {
        return Status::ERROR_AUD_INIT_FAILED;
    }
    audioCapturerInfoChangeCallback_ = callback;
    int32_t ret = audioCapturer_->SetAudioCapturerInfoChangeCallback(audioCapturerInfoChangeCallback_);
    if (ret != (int32_t)Status::OK) {
        MEDIA_LOG_E("SetAudioCapturerInfoChangeCallback fail error code: %{public}d", ret);
        SetFaultEvent("SetAudioCapturerInfoChangeCallback error", ret);
        return Status::ERROR_UNKNOWN;
    }
    return Status::OK;
}

Status AudioCaptureModule::SetWillMuteWhenInterrupted(bool muteWhenInterrupted)
{
    FALSE_RETURN_V_MSG_E(audioCapturer_ != nullptr, Status::ERROR_INVALID_OPERATION,
        "audioCapturer is nullptr, cannot SetWillMuteWhenInterrupted");
    int32_t ret = audioCapturer_->SetInterruptStrategy(muteWhenInterrupted ?
            AudioStandard::InterruptStrategy::MUTE : AudioStandard::InterruptStrategy::DEFAULT);
    if (ret != static_cast<int32_t>(Status::OK)) {
        MEDIA_LOG_E("fail error code: %{public}d", ret);
        return Status::ERROR_UNKNOWN;
    }
    return Status::OK;
}

Status AudioCaptureModule::GetCurrentCapturerChangeInfo(AudioStandard::AudioCapturerChangeInfo &changeInfo)
{
    FALSE_RETURN_V_MSG_E(audioCapturer_ != nullptr, Status::ERROR_INVALID_OPERATION,
        "audioCapturer is nullptr, cannot get audio capturer change info");
    audioCapturer_->GetCurrentCapturerChangeInfo(changeInfo);
    return Status::OK;
}

int32_t AudioCaptureModule::GetMaxAmplitude()
{
    AutoLock lock(captureMutex_);
    if (!isTrackMaxAmplitude) {
        isTrackMaxAmplitude = true;
    }
    int32_t value = maxAmplitude_;
    maxAmplitude_ = 0;
    return value;
}

void AudioCaptureModule::SetAudioSource(AudioStandard::SourceType source)
{
    options_.capturerInfo.sourceType = source;
}

void AudioCaptureModule::TrackMaxAmplitude(const uint8_t *data, int32_t size)
{
    for (int32_t i = 0; i < size; i++) {
        int16_t sample;
        std::memcpy(&sample, data + static_cast<size_t>(i) * sizeof(sample), sizeof(sample));
        int32_t value = sample;
        if (value < 0) {
            value = -value;
        }
        if (maxAmplitude_ < value) {
            maxAmplitude_ = value;
        }
    }
}

void AudioCaptureModule::SetFaultEvent(const std::string &errMsg, int32_t ret)
{
    SetFaultEvent(errMsg + ", ret = " + std::to_string(ret));
}

void AudioCaptureModule::SetFaultEvent(const std::string &errMsg)
{
    AudioSourceFaultInfo audioSourceFaultInfo;
    audioSourceFaultInfo.appName = bundleName_;
    audioSourceFaultInfo.instanceId = std::to_string(instanceId_);
    audioSourceFaultInfo.audioSourceType = options_.capturerInfo.sourceType;
    audioSourceFaultInfo.errMsg = errMsg;
    FaultRecordAudioEventWrite(audioSourceFaultInfo);
}

void AudioCaptureModule::SetCallingInfo(int32_t appUid, int32_t appPid,
    const std::string &bundleName, uint64_t instanceId)
{
    appUid_ = appUid;
    appPid_ = appPid;
    bundleName_ = bundleName;
    instanceId_ = instanceId;
}
} // namespace AudioCaptureModule
} // namespace Media
} // namespace OHOS
