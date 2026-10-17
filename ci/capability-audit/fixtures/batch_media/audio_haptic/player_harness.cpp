// Actual AudioHaptic lifecycle functions with controlled sound/vibrator dependencies.
// This proves thread/state behavior only, never physical haptics or PCM output.
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

#define MEDIA_LOGI(...) ((void)0)
#define MEDIA_LOGE(...) ((void)0)
#define MEDIA_LOGW(...) ((void)0)
#define CHECK_AND_RETURN_RET_LOG(condition, result, ...) do { if (!(condition)) return (result); } while (0)
#define CHECK_AND_RETURN_LOG(condition, ...) do { if (!(condition)) return; } while (0)
constexpr int32_t MSERR_OK = 0;
constexpr int32_t MSERR_INVALID_OPERATION = -10;
constexpr int32_t LOAD_WAIT_SECONDS = 1;
constexpr int32_t LOAD_WAIT_SECONDS_FOR_LOOP = 1;
constexpr int32_t NORMAL_LOOP_FOLLOW_WAIT_MS = 40;
constexpr int32_t NORMAL_LOOP_FIRST_WAIT_MS = 80;
constexpr int32_t AUDIO_LATENCY_MODE_NORMAL = 0;
enum class AudioHapticPlayerState { STATE_PREPARED, STATE_RUNNING };
enum class HapticsMode { HAPTICS_MODE_NON_SYNC_ONCE, HAPTICS_MODE_NON_SYNC, HAPTICS_MODE_SYNC };
static int32_t GenerateSyncId() { return 1; }

class ControlledSound {
public:
    int32_t result = 0;
    int32_t StartSound(int32_t) { return result; }
};
class ControlledVibrator {
public:
    int32_t GetDelayTime() { return 0; }
    void SetAudioHapticSyncId(int32_t) {}
    void ResetStopState() {}
    void StopVibrate() {}
    void StartVibrate(int32_t)
    {
        std::lock_guard<std::mutex> lock(mutex);
        ++starts;
        cv.notify_all();
    }
    bool WaitForStarts(int expected)
    {
        std::unique_lock<std::mutex> lock(mutex);
        return cv.wait_for(lock, std::chrono::seconds(2), [&] { return starts == expected; });
    }
    std::mutex mutex;
    std::condition_variable cv;
    int starts = 0;
};
class AudioHapticPlayerImpl {
public:
    ~AudioHapticPlayerImpl()
    {
        if (vibrateThread_ != nullptr && vibrateThread_->joinable()) {
            StopVibrate();
        }
    }
    int32_t Start();
    int32_t StartVibrate();
    void StopVibrate();
    void ResetVibrateState();
    int32_t GetDelayTime(int32_t);
    void NotifyStartVibrate(const uint64_t &);
    void SendHapticPlayerEvent(const int32_t &error, const std::string &event)
    {
        std::lock_guard<std::mutex> lock(eventsMutex);
        events.emplace_back(error, event);
    }
    int32_t StartEventResult()
    {
        std::lock_guard<std::mutex> lock(eventsMutex);
        for (const auto &entry : events) {
            if (entry.second == "START_HAPTIC_PLAYER") return entry.first;
        }
        return -999;
    }
    std::mutex eventsMutex;
    std::vector<std::pair<int32_t, std::string>> events;
    std::mutex audioHapticPlayerLock_;
    std::shared_ptr<ControlledSound> audioHapticSound_ = std::make_shared<ControlledSound>();
    std::shared_ptr<ControlledVibrator> audioHapticVibrator_ = std::make_shared<ControlledVibrator>();
    AudioHapticPlayerState playerState_ = AudioHapticPlayerState::STATE_PREPARED;
    bool isSupportDSPSync_ = false;
    std::atomic<int32_t> audioHapticSyncId_ = 0;
    std::shared_ptr<std::thread> vibrateThread_;
    std::atomic<bool> isVibrationStopped_ = true;
    std::atomic<bool> isVibrationRunning_ = false;
    std::atomic<bool> loop_ = false;
    bool muteHaptic_ = false;
    std::mutex waitStartVibrateMutex_;
    std::condition_variable condStartVibrate_;
    bool canStartVibrate_ = false;
    uint64_t audioLatency_ = 0;
    int32_t latencyMode_ = AUDIO_LATENCY_MODE_NORMAL;
    HapticsMode hapticsMode_ = HapticsMode::HAPTICS_MODE_SYNC;
};

// ACTUAL_FUNCTIONS

int main()
{
    {
        AudioHapticPlayerImpl player;
        player.audioHapticSound_->result = -42;
        assert(player.Start() == -42);
#ifdef EXPECT_OLD
        assert(player.vibrateThread_ != nullptr);
        assert(!player.isVibrationStopped_.load());
        assert(player.StartEventResult() == 0);
#else
        assert(player.vibrateThread_ == nullptr);
        assert(player.isVibrationStopped_.load());
        assert(player.StartEventResult() == -42);
#endif
        assert(player.playerState_ == AudioHapticPlayerState::STATE_PREPARED);
        player.StopVibrate();
        player.audioHapticSound_->result = 0;
        assert(player.Start() == 0);
        player.NotifyStartVibrate(0);
        assert(player.audioHapticVibrator_->WaitForStarts(1));
        player.StopVibrate();
        assert(player.vibrateThread_ == nullptr);
    }
    {
        AudioHapticPlayerImpl player;
        player.NotifyStartVibrate(999);
#ifdef EXPECT_OLD
        assert(player.canStartVibrate_);
        assert(player.audioLatency_ == 999);
#else
        assert(!player.canStartVibrate_);
        assert(player.audioLatency_ == 0);
#endif
        // Also reproduce a callback queued just before a stop/restart boundary.
        player.canStartVibrate_ = true;
        player.audioLatency_ = 888;
        player.ResetVibrateState();
#ifdef EXPECT_OLD
        assert(player.canStartVibrate_);
        assert(player.audioLatency_ == 888);
#else
        assert(!player.canStartVibrate_);
        assert(player.audioLatency_ == 0);
#endif
        assert(!player.isVibrationStopped_.load());
        player.NotifyStartVibrate(7);
        assert(player.canStartVibrate_);
        assert(player.audioLatency_ == 7);
    }
    std::cout << "actual player functions: failure cleanup, retry, callback, stop and rearm passed\n";
}
