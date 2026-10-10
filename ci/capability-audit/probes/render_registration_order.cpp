// Scheduling doubles around extracted production critical sections. Not an
// FFRT, Binder, AppMgr-service or guest end-to-end substitute.
#include <atomic>
#include <cassert>
#include <chrono>
#include <future>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
using namespace std::chrono_literals;
#define TAG_LOGE(...) ((void)0)
#define TAG_LOGI(...) ((void)0)
#define FAILED(value) ((value) != 0)
using ErrCode = int;
constexpr int ERR_INVALID_VALUE = -1;
enum class ProcessType { RENDER, GPU };
enum class ProcessStartFailedReason { APPSPAWN_FAILED };
struct AMSEventHandler { static constexpr int RENDER_ATTACH_TIMEOUT_MSG = 1; };
struct AppMgrEventUtil {
    template<class... Args> static void SendRenderProcessStartFailedEvent(Args&&...) {}
};
namespace ffrt {
struct mutex {
    inline static thread_local const mutex* owned = nullptr;
    std::mutex value;
    std::promise<void>* contended = nullptr;
    std::atomic<bool> held{false};
    void lock() {
        if (!value.try_lock()) {
            if (contended) contended->set_value();
            value.lock();
        }
        held = true;
        owned = this;
    }
    void unlock() { owned = nullptr; held = false; value.unlock(); }
    bool OwnedByThisThread() const { return owned == this; }
};
}
struct RenderRecord {
    int pid = 0, uid = 0;
    ProcessType type = ProcessType::RENDER;
    std::string name;
    void SetPid(int n) { pid = n; }
    void SetUid(int n) { uid = n; }
    void SetProcessName(const std::string& n) { name = n; }
    void SetProcessType(ProcessType n) { type = n; }
};
struct AppRunningRecord {
    std::shared_ptr<RenderRecord> record;
    int gpuPid = 0;
    bool IsNWebPreload() const { return false; }
    void SetGPUPid(int n) { gpuPid = n; }
    void AddRenderRecord(std::shared_ptr<RenderRecord> value) { record = value; }
    std::shared_ptr<RenderRecord> GetRenderRecordByPid(int pid) {
        return record && record->pid == pid ? record : nullptr;
    }
};
struct AppStateObserverManager {
    void OnRenderProcessCreated(std::shared_ptr<RenderRecord>, bool) {
        assert(ffrt::mutex::owned == nullptr);
    }
};
template<class T> struct DelayedSingleton {
    static T* GetInstance() { static T value; return &value; }
};
struct RunningManager {
    std::shared_ptr<AppRunningRecord> app;
    bool missingApp = false, missingRender = false;
    std::shared_ptr<AppRunningRecord> GetAppRunningRecordByRenderPid(int pid) {
        if (missingApp || !app || !app->record || app->record->pid != pid) return nullptr;
        if (missingRender) return std::make_shared<AppRunningRecord>();
        return app;
    }
};
struct Events {
    std::atomic<bool> pending{false};
    void RemoveEvent(int, int) { pending = false; }
};
struct SpawnMessage { std::string procName = "browser:render"; };
struct SpawnClient {
    std::promise<void> entered;
    std::shared_future<void> released;
    int result = 0;
    int StartProcess(const SpawnMessage&, int& pid) {
        entered.set_value();
        assert(released.wait_for(5s) == std::future_status::ready);
        pid = 1234;
        return result;
    }
};
struct Harness {
    ffrt::mutex renderProcessRegistrationLock_;
    std::shared_ptr<RunningManager> appRunningManager_ = std::make_shared<RunningManager>();
    std::shared_ptr<Events> eventHandler_ = std::make_shared<Events>();
    bool uidRemoved = false;
    std::atomic<int> attached{0};
    void RemoveRenderProcessIsolationUid(int) {
        assert(!renderProcessRegistrationLock_.OwnedByThisThread());
        uidRemoved = true;
    }
    void PostRenderAttachTimeoutTask(std::shared_ptr<RenderRecord>) {
        assert(renderProcessRegistrationLock_.OwnedByThisThread() == bool(EXPECT_FIXED));
        eventHandler_->pending = true;
    }
    int Start(std::shared_ptr<SpawnClient> nwebSpawnClient,
        std::shared_ptr<RenderRecord> renderRecord,
        std::shared_ptr<AppRunningRecord> appRecord, int& renderPid, bool isGPU) {
        int renderUid = 991;
        SpawnMessage startMsg;
/* ACTUAL_SPAWN_SECTION */
        // The original and repaired tails both include actual observer enqueue
        // and timeout ordering; the observer double checks no lock is owned.
        assert(!renderProcessRegistrationLock_.OwnedByThisThread());
        return 0;
    }
    void Attach(int pid, bool scheduler) {
/* ACTUAL_ATTACH_SECTION */
        // Production then registers death recipient / calls renderer scheduler.
        assert(!renderProcessRegistrationLock_.OwnedByThisThread());
        ++attached;
    }
};
void CheckRace(bool failure, bool gpu) {
    Harness h;
    auto app = std::make_shared<AppRunningRecord>();
    auto record = std::make_shared<RenderRecord>();
    auto spawn = std::make_shared<SpawnClient>();
    h.appRunningManager_->app = app;
    std::promise<void> release, contention;
    auto contended = contention.get_future();
    h.renderProcessRegistrationLock_.contended = &contention;
    spawn->released = release.get_future().share();
    spawn->result = failure ? 9 : 0;
    auto entered = spawn->entered.get_future();
    int result = 42, pid = 0;
    std::thread producer([&] { result = h.Start(spawn, record, app, pid, gpu); });
    assert(entered.wait_for(5s) == std::future_status::ready);
    std::promise<void> attached;
    auto completed = attached.get_future();
    std::thread consumer([&] { h.Attach(1234, true); attached.set_value(); });
#if EXPECT_FIXED
    assert(contended.wait_for(5s) == std::future_status::ready);
    assert(completed.wait_for(0s) == std::future_status::timeout);
#else
    // Exact original code loses attachment before publication, deterministically.
    assert(completed.wait_for(5s) == std::future_status::ready);
    assert(h.attached == 0);
#endif
    release.set_value();
    producer.join(); consumer.join();
    assert(result == (failure ? ERR_INVALID_VALUE : 0));
    assert(h.uidRemoved == failure);
    assert(h.attached == (EXPECT_FIXED && !failure ? 1 : 0));
    assert(!h.renderProcessRegistrationLock_.held);
    if (failure) { assert(!app->record && pid == 0); return; }
    assert(app->record == record && pid == 1234 && record->uid == 991);
    assert(record->name == "browser:render");
    assert(record->type == (gpu ? ProcessType::GPU : ProcessType::RENDER));
    assert(app->gpuPid == (gpu ? 1234 : 0));
    assert(h.eventHandler_->pending == !bool(EXPECT_FIXED));
    h.renderProcessRegistrationLock_.contended = nullptr;
    // All early returns must release the RAII lock, allowing the next attach.
    int before = h.attached;
    h.Attach(0, true); h.Attach(-1, true); h.Attach(1234, false);
    auto manager = h.appRunningManager_;
    h.appRunningManager_.reset(); h.Attach(1234, true); h.appRunningManager_ = manager;
    manager->missingApp = true; h.Attach(1234, true); manager->missingApp = false;
    manager->missingRender = true; h.Attach(1234, true); manager->missingRender = false;
    assert(h.attached == before);
    assert(!h.renderProcessRegistrationLock_.held);
    h.eventHandler_.reset(); h.Attach(1234, true);
    assert(h.attached == before + 1);
}
int main() {
    for (int iteration = 0; iteration < 100; ++iteration)
        for (bool failure : {false, true})
            for (bool gpu : {false, true}) CheckRace(failure, gpu);
}
