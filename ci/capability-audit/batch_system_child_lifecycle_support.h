// Host ABI shims for executing fixed upstream callback/retention code.
// No service backend, process creation, identity or package result is simulated.
#pragma once
#include <algorithm>
#include <atomic>
#include <cstddef>
#include <functional>
#include <list>
#include <mutex>
#include <set>
#include <string>
#include <utility>

#define TAG_LOGE(...) ((void)0)
#define TAG_LOGI(...) ((void)0)
#define DISALLOW_COPY_AND_MOVE(T) T(const T&) = delete; T& operator=(const T&) = delete

namespace OHOS {
class IRemoteObject {
public:
    inline static std::atomic<int> live{0};
    IRemoteObject() { ++live; }
    virtual ~IRemoteObject() { --live; }
    void IncStrong() const { ++refs_; }
    void DecStrong() const { if (--refs_ == 0) delete this; }
    int StrongCount() const { return refs_; }
private:
    mutable std::atomic<int> refs_{0};
};

template<class T> class sptr {
public:
    sptr(std::nullptr_t = nullptr) {}
    sptr(T* ptr) : ptr_(ptr) { if (ptr_) ptr_->IncStrong(); }
    sptr(const sptr& other) : sptr(other.ptr_) {}
    template<class U> sptr(const sptr<U>& other) : sptr(other.GetRefPtr()) {}
    sptr(sptr&& other) noexcept : ptr_(other.ptr_) { other.ptr_ = nullptr; }
    ~sptr() { if (ptr_) ptr_->DecStrong(); }
    sptr& operator=(sptr other) { std::swap(ptr_, other.ptr_); return *this; }
    T* GetRefPtr() const { return ptr_; }
    T* operator->() const { return ptr_; }
    explicit operator bool() const { return ptr_ != nullptr; }
    bool operator<(const sptr& other) const { return std::less<T*>{}(ptr_, other.ptr_); }
private:
    T* ptr_ = nullptr;
};
}

struct OHIPCRemoteProxy { OHOS::sptr<OHOS::IRemoteObject> remote; };
using OH_Ability_OnNativeChildProcessStarted = void (*)(int, OHIPCRemoteProxy*);
using OH_Ability_OnNativeChildProcessExit = void (*)(int, int);
enum Ability_NativeChildProcess_ErrCode {
    NCP_NO_ERROR = 0, NCP_ERR_INVALID_PARAM = 401, NCP_ERR_INTERNAL = 16000050,
    NCP_ERR_CALLBACK_NOT_EXIST = 16000051
};
enum NativeChildProcess_IsolationMode {
    NCP_ISOLATION_MODE_NORMAL = 0, NCP_ISOLATION_MODE_ISOLATED = 1
};
struct Ability_ChildProcessConfigs {
    NativeChildProcess_IsolationMode isolationMode = NCP_ISOLATION_MODE_NORMAL;
    std::string processName;
    bool isIsolationUid = false;
};
OHIPCRemoteProxy* CreateIPCRemoteProxy(OHOS::sptr<OHOS::IRemoteObject> remote);

namespace OHOS::AppExecFwk {
class NativeChildNotifyStub : public IRemoteObject {
public:
    virtual void OnNativeChildStarted(const sptr<IRemoteObject>&) = 0;
    virtual void OnError(int32_t) = 0;
    virtual int32_t OnNativeChildExit(int32_t, int32_t) = 0;
};
}

namespace OHOS::AbilityRuntime {
enum class ChildProcessManagerErrorCode { ERR_OK = 0, ERR_INTERNAL = 1 };
class ChildProcessManagerErrorUtil {
public:
    static Ability_NativeChildProcess_ErrCode CvtChildProcessManagerErrCode(ChildProcessManagerErrorCode)
    { return NCP_ERR_INTERNAL; }
};
class ChildProcessManager {
public:
    static ChildProcessManager& GetInstance() { static ChildProcessManager manager; return manager; }
    ChildProcessManagerErrorCode CreateNativeChildProcessByAppSpawnFork(
        const std::string&, const sptr<IRemoteObject>&, const std::string& = "", bool = false, bool = false);
};
}

int OH_Ability_CreateNativeChildProcess(const char*, OH_Ability_OnNativeChildProcessStarted);
Ability_NativeChildProcess_ErrCode OH_Ability_CreateNativeChildProcessWithConfigs(
    const char*, Ability_ChildProcessConfigs*, OH_Ability_OnNativeChildProcessStarted);
