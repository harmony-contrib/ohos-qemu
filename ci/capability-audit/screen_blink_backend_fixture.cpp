// Host doubles for lifecycle only. Never evidence of real WM/RS pixels or IPC.
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#include <poll.h>
#include <sys/syscall.h>
#include <unistd.h>
#define HILOG_ERROR(...) ((void)0)
#ifndef SYS_pidfd_open
#define SYS_pidfd_open 434
#endif
static int ownerPipe[2];
static std::atomic<bool> failPidfd {false};
static int FakeSyscall(long, int, int) { return failPidfd ? -1 : dup(ownerPipe[0]); }
#define syscall FakeSyscall

namespace OHOS {
template<class T> class sptr : public std::shared_ptr<T> {
public:
    using std::shared_ptr<T>::shared_ptr;
    using std::shared_ptr<T>::operator=;
    sptr() = default;
    sptr(T *value) : std::shared_ptr<T>(value) {}
    sptr &operator=(std::nullptr_t) { this->reset(); return *this; }
};
namespace Accessibility {
enum RetError { RET_OK = 0, RET_ERR_FAILED = -1, RET_ERR_INVALID_PARAM = -2, RET_ERR_TIME_OUT = -3 };
constexpr int SUCCESS = 0;
}
namespace AppExecFwk {
class EventRunner {
public:
    static std::shared_ptr<EventRunner> Create(const char *) { return std::make_shared<EventRunner>(); }
};
class EventHandler {
    struct Task { std::chrono::steady_clock::time_point at; std::string name; std::function<void()> fn; };
    std::mutex mutex_;
    std::condition_variable cv_;
    bool stop_ = false;
    std::vector<Task> tasks_;
    std::thread worker_;
    void Run() {
        std::unique_lock<std::mutex> lock(mutex_);
        while (!stop_) {
            if (tasks_.empty()) { cv_.wait(lock); continue; }
            auto found = std::min_element(tasks_.begin(), tasks_.end(), [](auto &a, auto &b) { return a.at < b.at; });
            auto at = found->at;
            if (at > std::chrono::steady_clock::now()) { cv_.wait_until(lock, at); continue; }
            auto fn = std::move(found->fn); tasks_.erase(found);
            lock.unlock(); fn(); lock.lock();
        }
    }
public:
    explicit EventHandler(std::shared_ptr<EventRunner>) : worker_([this] { Run(); }) {}
    ~EventHandler() {
        { std::lock_guard<std::mutex> lock(mutex_); stop_ = true; cv_.notify_all(); }
        worker_.join();
    }
    bool PostTask(std::function<void()> fn, const std::string &name, int64_t delay = 0) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stop_) return false;
        tasks_.push_back({std::chrono::steady_clock::now() + std::chrono::milliseconds(delay), name, std::move(fn)});
        cv_.notify_all(); return true;
    }
    bool PostSyncTask(std::function<void()> fn, const std::string &name) {
        auto done = std::make_shared<std::promise<void>>(); auto future = done->get_future();
        if (!PostTask([fn, done] { fn(); done->set_value(); }, name)) return false;
        future.get(); return true;
    }
    void RemoveTask(const std::string &name) {
        std::lock_guard<std::mutex> lock(mutex_);
        tasks_.erase(std::remove_if(tasks_.begin(), tasks_.end(), [&](auto &task) { return task.name == name; }), tasks_.end());
        cv_.notify_all();
    }
    void RemoveAllEvents() { std::lock_guard<std::mutex> lock(mutex_); tasks_.clear(); cv_.notify_all(); }
};
}
namespace Rosen {
static std::atomic<int> shown {0}, destroyed {0}, live {0}, displayWidth {1280};
static std::atomic<bool> failCreate {false}, failShow {false}, failDestroy {false};
static std::atomic<uint32_t> color {0};
class Display {
public:
    int GetWidth() { return displayWidth; }
    int GetHeight() { return 800; }
    uint64_t GetId() { return 1; }
};
class DisplayManager {
public:
    static DisplayManager &GetInstance() { static DisplayManager value; return value; }
    std::shared_ptr<Display> GetDefaultDisplay() { return std::make_shared<Display>(); }
};
class RSTransaction { public: void FlushImplicitTransaction() {} };
class RSUIContext { public: std::shared_ptr<RSTransaction> GetRSTransaction() { return std::make_shared<RSTransaction>(); } };
class RSCanvasNode {
public:
    static std::shared_ptr<RSCanvasNode> Create(bool, bool, std::shared_ptr<RSUIContext>) { return std::make_shared<RSCanvasNode>(); }
    void SetBounds(int, int, int, int) {}
    void SetFrame(int, int, int, int) {}
    void SetBackgroundColor(uint32_t value) { color = value; }
};
class RSSurfaceNode {
public:
    std::shared_ptr<RSUIContext> GetRSUIContext() { return std::make_shared<RSUIContext>(); }
    void AddChild(std::shared_ptr<RSCanvasNode>, int) {}
};
enum class WindowType { WINDOW_TYPE_SYSTEM_FLOAT };
enum class WindowMode { WINDOW_MODE_FLOATING };
enum class WMError { WM_OK, WM_ERROR };
struct Rect { int x, y; uint32_t width, height; };
class WindowOption {
public:
    void SetWindowType(WindowType) {}
    void SetWindowMode(WindowMode) {}
    void SetDisplayId(uint64_t) {}
    void SetWindowRect(Rect) {}
    void SetFocusable(bool value) { assert(!value); }
    void SetTouchable(bool value) { assert(!value); }
};
class Window {
    bool removed_ = false;
public:
    Window() { ++live; }
    ~Window() { --live; }
    static sptr<Window> Create(const char *, sptr<WindowOption>) { return failCreate ? nullptr : new Window(); }
    std::shared_ptr<RSSurfaceNode> GetSurfaceNode() { return std::make_shared<RSSurfaceNode>(); }
    WMError Show() { if (failShow) return WMError::WM_ERROR; ++shown; return WMError::WM_OK; }
    WMError Destroy() {
        if (failDestroy) return WMError::WM_ERROR;
        assert(!removed_); removed_ = true; ++destroyed; return WMError::WM_OK;
    }
};
}
}

// __ACTUAL_HEADER_AND_IMPLEMENTATION__

int main() {
    using namespace OHOS::Accessibility;
    using namespace OHOS::Rosen;
    assert(pipe(ownerPipe) == 0);
    std::atomic<bool> enabled {false};
    std::atomic<bool> providerFailure {false};
    AccessibilityBlinkController controller([&](bool &value) {
        value = enabled.load(); return providerFailure ? RET_ERR_FAILED : RET_OK;
    });
    int32_t result = -1;
    auto call = [&](bool start, int mode = 2, int scenario = 4, int pid = 100, uint32_t token = 200) {
        return controller.Control(start, mode, scenario, pid, token, result);
    };
    assert(call(true) == RET_OK && result == 5 && shown == 0);
    enabled = true;
    for (int mode : {0, 3, -1}) assert(call(true, mode) == RET_ERR_INVALID_PARAM);
    assert(call(true, 2, 0) == RET_ERR_INVALID_PARAM);
    assert(call(true, 2, 5) == RET_ERR_INVALID_PARAM);
    failPidfd = true; assert(call(true) == RET_ERR_FAILED && live == 0); failPidfd = false;
    failCreate = true; assert(call(true) == RET_ERR_FAILED && live == 0); failCreate = false;
    failShow = true; assert(call(true) == RET_ERR_FAILED && live == 0); failShow = false;
    assert(call(true) == RET_OK && result == 0 && shown == 1 && color != 0);
    assert(call(true) == RET_OK && result == 1 && shown == 1);
    assert(call(true, 2, 4, 101) == RET_OK && result == 2);
    assert(call(false, 2, 4, 100, 201) == RET_OK && result == 2 && live == 1);
    assert(call(false, 2, 3) == RET_OK && result == 2 && live == 1);
    assert(call(false) == RET_OK && result == 0 && live == 0 && color == 0);
    assert(call(false) == RET_OK && result == 0);
    assert(call(true, 1) == RET_OK && result == 0);
    std::this_thread::sleep_for(std::chrono::milliseconds(850));
    assert(live == 0 && color == 0);
    assert(call(true) == RET_OK); enabled = false;
    std::this_thread::sleep_for(std::chrono::milliseconds(850));
    assert(live == 0 && color == 0); enabled = true;
    assert(call(true) == RET_OK); controller.CancelForAccountChange();
    assert(call(false) == RET_OK && live == 0);
    assert(call(true) == RET_OK); displayWidth = 800;
    std::this_thread::sleep_for(std::chrono::milliseconds(850));
    assert(live == 0 && color == 0); displayWidth = 1280;
    providerFailure = true; assert(call(true) == RET_ERR_FAILED && live == 0); providerFailure = false;
    assert(call(true) == RET_OK); close(ownerPipe[1]);
    std::this_thread::sleep_for(std::chrono::milliseconds(850));
    assert(live == 0 && color == 0);
    close(ownerPipe[0]); assert(pipe(ownerPipe) == 0);
    assert(call(true) == RET_OK); failDestroy = true;
    assert(call(false) == RET_ERR_FAILED && color == 0 && live == 1);
    failDestroy = false; assert(call(false) == RET_OK && live == 0);
    assert(call(true) == RET_OK); controller.Shutdown();
    assert(live == 0 && color == 0 && call(true) == RET_ERR_FAILED);
    controller.Shutdown();
    std::atomic<bool> hold {true};
    AccessibilityBlinkController slow([&](bool &value) {
        while (hold) std::this_thread::sleep_for(std::chrono::milliseconds(1));
        value = true; return RET_OK;
    });
    int beforeTimeout = shown;
    assert(slow.Control(true, 2, 4, 100, 200, result) == RET_ERR_TIME_OUT);
    hold = false;
    assert(slow.Control(false, 2, 4, 100, 200, result) == RET_OK);
    assert(shown == beforeTimeout && live == 0 && color == 0);
    slow.Shutdown();
    close(ownerPipe[0]); close(ownerPipe[1]);
}
