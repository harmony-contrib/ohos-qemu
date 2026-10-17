// Actual normal-sound functions; controlled AVPlayer is never product/runtime proof.
#include <cassert>
#include <chrono>
#include <cinttypes>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>

#define MEDIA_LOGI(...) ((void)0)
#define MEDIA_LOGE(...) ((void)0)
#define CHECK_AND_RETURN_RET_LOG(condition, result, ...) do { if (!(condition)) return (result); } while (0)
#define CHECK_AND_RETURN_LOG(condition, ...) do { if (!(condition)) return; } while (0)
constexpr int32_t MSERR_OK = 0;
constexpr int32_t MSERR_INVALID_OPERATION = -1;
constexpr int32_t MSERR_UNSUPPORT_FILE = -2;
constexpr int32_t MSERR_OPEN_FILE_FAILED = -3;
// An immediate deadline makes a missing new callback deterministic in host tests.
constexpr int32_t LOAD_WAIT_SECONDS = 0;
enum class AudioHapticPlayerState { STATE_NEW, STATE_PREPARED };
namespace AudioStandard { constexpr int CONTENT_TYPE_UNKNOWN = 0; }
struct PlayerKeys {
    static constexpr int CONTENT_TYPE = 1;
    static constexpr int STREAM_USAGE = 2;
    static constexpr int RENDERER_FLAG = 3;
    static constexpr int AUDIO_FIRST_FRAME = 4;
};
class Format {
public:
    void PutIntValue(int, int) {}
    bool GetLongValue(int, int64_t &out) const { out = value; return present; }
    bool present = true;
    int64_t value = 0;
};
class ControlledPlayer {
public:
    int Reset() { return resetResult; }
    int SetSource(int, int, int) { ++sourceCalls; return sourceResult; }
    int SetParameter(const Format &) { return parameterResult; }
    int PrepareAsync() { if (onPrepare) onPrepare(); return prepareResult; }
    int SetVolume(float, float) { ++volumeCalls; return 0; }
    int SetLooping(bool) { return 0; }
    int resetResult = 0;
    int sourceResult = 0;
    int parameterResult = 0;
    int prepareResult = 0;
    int sourceCalls = 0;
    int volumeCalls = 0;
    std::function<void()> onPrepare;
};
class AudioHapticSoundNormalImpl {
public:
    int32_t ResetAVPlayer();
    void NotifyPreparedEvent();
    void NotifyFirstFrameEvent(uint64_t value) { ++firstFrameCalls; latency = value; }
    int32_t OpenAudioSource() { return openResult; }
    std::shared_ptr<ControlledPlayer> avPlayer_ = std::make_shared<ControlledPlayer>();
    std::mutex prepareMutex_;
    std::condition_variable prepareCond_;
    bool isPrepared_ = false;
    bool isUnsupportedFile_ = false;
    bool isReleased_ = false;
    int openResult = 0;
    int fileDes_ = 1;
    struct Source { int offset = 0; int length = 64; } audioSource_, configuredAudioSource_;
    float volume_ = 1;
    bool muteAudio_ = false;
    bool loop_ = false;
    int streamUsage_ = 0;
    int rendererFlags_ = 0;
    AudioHapticPlayerState playerState_ = AudioHapticPlayerState::STATE_NEW;
    int firstFrameCalls = 0;
    uint64_t latency = 0;
};
class AHSoundNormalCallback {
public:
    void HandleAudioFirstFrameEvent(int32_t extra, const Format &infoBody);
    std::weak_ptr<AudioHapticSoundNormalImpl> soundNormalImpl_;
};

// ACTUAL_FUNCTIONS

int main()
{
    {
        AudioHapticSoundNormalImpl sound;
        sound.isPrepared_ = true;
#ifdef EXPECT_OLD
        assert(sound.ResetAVPlayer() == MSERR_OK);
        assert(sound.avPlayer_->volumeCalls == 1);
#else
        assert(sound.ResetAVPlayer() == MSERR_OPEN_FILE_FAILED);
        assert(sound.avPlayer_->volumeCalls == 0);
#endif
    }
    {
        AudioHapticSoundNormalImpl sound;
        sound.isUnsupportedFile_ = true;
        sound.avPlayer_->onPrepare = [&] { sound.NotifyPreparedEvent(); };
#ifdef EXPECT_OLD
        assert(sound.ResetAVPlayer() == MSERR_UNSUPPORT_FILE);
#else
        assert(sound.ResetAVPlayer() == MSERR_OK);
        assert(sound.playerState_ == AudioHapticPlayerState::STATE_PREPARED);
        assert(sound.avPlayer_->volumeCalls == 1);
#endif
    }
    {
        AudioHapticSoundNormalImpl sound;
        sound.avPlayer_->resetResult = -123;
        sound.avPlayer_->onPrepare = [&] { sound.NotifyPreparedEvent(); };
#ifdef EXPECT_OLD
        assert(sound.ResetAVPlayer() == MSERR_OK);
        assert(sound.avPlayer_->sourceCalls == 1);
#else
        assert(sound.ResetAVPlayer() == -123);
        assert(sound.avPlayer_->sourceCalls == 0);
#endif
    }
    for (int scenario = 0; scenario < 5; ++scenario) {
        AudioHapticSoundNormalImpl sound;
        sound.avPlayer_->onPrepare = [&] { sound.NotifyPreparedEvent(); };
        if (scenario == 0) sound.isReleased_ = true;
        if (scenario == 1) sound.openResult = -101;
        if (scenario == 2) sound.avPlayer_->sourceResult = -102;
        if (scenario == 3) sound.avPlayer_->parameterResult = -103;
        if (scenario == 4) sound.avPlayer_->prepareResult = -104;
        const int expected[] = {MSERR_INVALID_OPERATION, -101, MSERR_OPEN_FILE_FAILED, -103, -104};
        assert(sound.ResetAVPlayer() == expected[scenario]);
    }
    {
        auto sound = std::make_shared<AudioHapticSoundNormalImpl>();
        AHSoundNormalCallback callback;
        callback.soundNormalImpl_ = sound;
        Format missing;
        missing.present = false;
        callback.HandleAudioFirstFrameEvent(0, missing);
        Format negative;
        negative.value = -1;
        callback.HandleAudioFirstFrameEvent(0, negative);
#ifdef EXPECT_OLD
        assert(sound->firstFrameCalls == 2);
        assert(sound->latency == UINT64_MAX);
#else
        assert(sound->firstFrameCalls == 0);
#endif
        Format valid;
        valid.value = 42;
        callback.HandleAudioFirstFrameEvent(0, valid);
        assert(sound->latency == 42);
        valid.value = 0;
        callback.HandleAudioFirstFrameEvent(0, valid);
        assert(sound->latency == 0);
        sound.reset();
        callback.HandleAudioFirstFrameEvent(0, valid);
    }
    std::cout << "actual normal functions: fresh prepare, reset errors and first-frame payloads passed\n";
}
