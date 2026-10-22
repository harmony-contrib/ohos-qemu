// Copyright 2026. Apache-2.0. Product CPU provider; no synthetic recognition.
#ifndef QEMU_CPU_VOICE_ENGINE_H
#define QEMU_CPU_VOICE_ENGINE_H
#include "engine_base.h"
#include "sherpa-onnx/c-api/c-api.h"
#include <mutex>
#include <string>
#include <vector>
namespace OHOS::IntelligentVoice::Engine {
class CpuVoiceEngine final : public EngineBase {
public:
    explicit CpuVoiceEngine(bool enroll) : enroll_(enroll) {}
    ~CpuVoiceEngine() override { Release(); }
    IntellVoiceStatus SetListener(std::shared_ptr<IEngineCallback> listener) override;
    IntellVoiceStatus Init(const IntellVoiceEngineAdapterInfo &info) override;
    IntellVoiceStatus Start(const StartInfo &info) override;
    IntellVoiceStatus Write(const uint8_t *buffer, uint32_t size) override;
    IntellVoiceStatus Stop() override;
    IntellVoiceStatus Cancel() override;
    IntellVoiceStatus Release() override;
    IntellVoiceStatus SetParameter(const std::string &value) override;
    IntellVoiceStatus GetParameter(const std::string &key, getParameterCb cb) override;
    IntellVoiceStatus GetWakeupPcm(std::vector<uint8_t> &data) override;
    IntellVoiceStatus ReadFileData(ContentType type, getFileDataCb cb) override;
    IntellVoiceStatus Evaluate(const std::string &word, EvaluationResultInfo &info) override;
    static int32_t ClearEnrollment(const std::string &phrase);
private:
    void DestroyLocked();
    void ResetStreamLocked();
    bool MakeEmbeddingLocked(std::vector<float> &embedding);
    bool LoadEnrollmentLocked();
    bool CommitLocked();
    void JournalLocked(const std::string &event, int result, const std::string &detail = "");
    std::mutex mutex_;
    bool enroll_, initialized_ = false, active_ = false, enrolled_ = false, phraseHeard_ = false;
    std::string phrase_, keywords_;
    uint64_t speechBegin_ = 0, speechEnd_ = 0;
    uint64_t frames_ = 0, generation_ = 0, seq_ = 0, segment_ = 0;
    std::string tracePath_;
    std::vector<uint8_t> pcm_;
    std::vector<float> candidate_, committed_;
    const SherpaOnnxKeywordSpotter *kws_ = nullptr;
    const SherpaOnnxSpeakerEmbeddingExtractor *speaker_ = nullptr;
    const SherpaOnnxOnlineStream *stream_ = nullptr;
};
}
#endif
