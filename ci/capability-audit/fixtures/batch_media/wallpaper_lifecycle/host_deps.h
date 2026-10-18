/* Explicit host doubles. Never product headers or a guest/runtime receipt. */
#ifndef QEMU_WALLPAPER_LIFECYCLE_HOST_DEPS_H
#define QEMU_WALLPAPER_LIFECYCLE_HOST_DEPS_H
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <functional>
#include <memory>
#include <string>
#include <utility>
#include <vector>
#define HILOG_INFO(...) do {} while (0)
#define HILOG_ERROR(...) do {} while (0)
namespace OHOS {
constexpr int ERR_OK = 0;
class RefBase {
public:
    void Inc() const { ++refs_; }
    void Dec() const { if (--refs_ == 0) delete this; }
protected:
    virtual ~RefBase() = default;
private:
    mutable std::atomic<int> refs_ { 0 };
};
template<class T> class sptr {
public:
    sptr() = default;
    sptr(std::nullptr_t) {}
    sptr(T *value) : p_(value) { if (p_) p_->Inc(); }
    sptr(const sptr &value) : sptr(value.p_) {}
    template<class U> sptr(const sptr<U> &value) : sptr(value.GetRefPtr()) {}
    ~sptr() { if (p_) p_->Dec(); }
    sptr &operator=(sptr other) { std::swap(p_, other.p_); return *this; }
    T *GetRefPtr() const { return p_; }
    T *operator->() const { return p_; }
    bool operator==(const sptr &other) const { return p_ == other.p_; }
    bool operator!=(const sptr &other) const { return p_ != other.p_; }
    bool operator==(std::nullptr_t) const { return !p_; }
    bool operator!=(std::nullptr_t) const { return p_ != nullptr; }
private:
    T *p_ = nullptr;
};
template<class T> class wptr {};
class IRemoteObject : public RefBase {
public:
    class DeathRecipient : public RefBase {
    public:
        virtual void OnRemoteDied(const wptr<IRemoteObject>&) = 0;
    };
    bool IsObjectDead() const { return dead; }
    bool AddDeathRecipient(const sptr<DeathRecipient> &value) {
        if (!allowDeath) return false;
        deaths.push_back(value); return true;
    }
    bool RemoveDeathRecipient(const sptr<DeathRecipient> &value) {
        deaths.erase(std::remove(deaths.begin(), deaths.end(), value), deaths.end()); return true;
    }
    void Kill() { dead = true; auto callbacks = deaths; for (auto &callback : callbacks) callback->OnRemoteDied({}); }
    bool dead = false, allowDeath = true;
    std::vector<sptr<DeathRecipient>> deaths;
};
namespace AppExecFwk {
class ElementName {
public:
    ElementName(std::string bundle = "com.ohos.wallpaper", std::string ability = "WallpaperExtAbility")
        : bundle_(std::move(bundle)), ability_(std::move(ability)) {}
    std::string GetBundleName() const { return bundle_; }
    std::string GetAbilityName() const { return ability_; }
private:
    std::string bundle_, ability_;
};
class EventHandler {
public:
    struct Item { int due; int serial; std::string name; std::function<void()> task; };
    bool PostTask(const std::function<void()> &task, const std::string &name = "", int64_t delay = 0) {
        if (reject) return false;
        queue.push_back({now + static_cast<int>(delay), ++serial, name, task}); return true;
    }
    void RemoveTask(const std::string &name) {
        queue.erase(std::remove_if(queue.begin(), queue.end(), [&](const Item &i) { return i.name == name; }), queue.end());
    }
    bool Next() {
        if (queue.empty()) return false;
        const auto where = std::min_element(queue.begin(), queue.end(), [](const Item &a, const Item &b) {
            return a.due != b.due ? a.due < b.due : a.serial < b.serial;
        });
        auto item = *where; queue.erase(where); now = item.due; item.task(); return true;
    }
    void Drain() { int count = 0; while (Next()) assert(++count < 1000); }
    int now = 0, serial = 0;
    bool reject = false;
    std::vector<Item> queue;
};
}
namespace AAFwk {
class Want {
public:
    void SetElementName(const char *bundle, const char *ability) { element = {bundle, ability}; }
    AppExecFwk::ElementName element;
};
class AbilityConnectionStub : public RefBase {
public:
    virtual void OnAbilityConnectDone(const AppExecFwk::ElementName&, const sptr<IRemoteObject>&, int32_t) = 0;
    virtual void OnAbilityDisconnectDone(const AppExecFwk::ElementName&, int32_t) = 0;
};
class AbilityManagerClient {
public:
    struct Call { sptr<AbilityConnectionStub> connection; int user; };
    static std::shared_ptr<AbilityManagerClient> GetInstance() { static auto value = std::make_shared<AbilityManagerClient>(); return value; }
    int Connect() { ++brokerCalls; return brokerResult; }
    int ConnectExtensionAbility(const Want &want, const sptr<AbilityConnectionStub> &connection, int user) {
        assert(want.element.GetBundleName() == "com.ohos.wallpaper");
        assert(want.element.GetAbilityName() == "WallpaperExtAbility"); assert(user > 0);
        if (beforeConnect) beforeConnect();
        calls.push_back({connection, user});
        if (synchronous) connection->OnAbilityConnectDone(want.element, new IRemoteObject, 0);
        return result;
    }
    int DisconnectAbility(const sptr<AbilityConnectionStub> &connection) {
        disconnects.push_back(connection);
        // A synchronous callback must only enqueue; no owner mutex re-entry.
        connection->OnAbilityDisconnectDone({}, 0); return 0;
    }
    void Reset() { beforeConnect = {}; brokerCalls = brokerResult = result = 0; synchronous = false; calls.clear(); disconnects.clear(); }
    int brokerCalls = 0, brokerResult = 0, result = 0;
    bool synchronous = false;
    std::function<void()> beforeConnect;
    std::vector<Call> calls;
    std::vector<sptr<AbilityConnectionStub>> disconnects;
};
}
namespace AccountSA {
class OsAccountManager {
public:
    static int QueryActiveOsAccountIds(std::vector<int32_t> &result) { result = users; return error; }
    inline static std::vector<int32_t> users { 100 };
    inline static int error = 0;
};
}
}

#endif // QEMU_WALLPAPER_LIFECYCLE_HOST_DEPS_H
