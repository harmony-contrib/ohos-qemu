/* SPDX-License-Identifier: Apache-2.0 */
#include "qemu_wallpaper_renderer.h"
#include <atomic>
#include <mutex>
#include <vector>
#include "ability_connect_callback_stub.h"
#include "ability_manager_client.h"
#include "hilog_wrapper.h"
#include "iremote_object.h"
#include "os_account_manager.h"

namespace OHOS::WallpaperMgrService {
namespace {
constexpr int32_t TICKS = 150;
constexpr int32_t INTERVAL_MS = 200;
constexpr int32_t PENDING_TICKS = 50;
constexpr const char *BUNDLE = "com.ohos.wallpaper";
constexpr const char *ABILITY = "WallpaperExtAbility";
constexpr const char *TIMER = "qemu-wallpaper-renderer-tick";
constexpr const char *CALLBACK = "qemu-wallpaper-renderer-callback";
class Renderer;

class Connection final : public AAFwk::AbilityConnectionStub {
public:
    Connection(std::weak_ptr<Renderer> owner, std::weak_ptr<AppExecFwk::EventHandler> handler,
        uint64_t epoch, uint64_t attempt) : owner_(owner), handler_(handler), epoch_(epoch), attempt_(attempt) {}
    void OnAbilityConnectDone(const AppExecFwk::ElementName &element,
        const sptr<IRemoteObject> &remote, int32_t result) override;
    void OnAbilityDisconnectDone(const AppExecFwk::ElementName &element, int32_t result) override;
    bool WasDisconnected() const { return disconnected_.load(); }
private:
    std::weak_ptr<Renderer> owner_;
    std::weak_ptr<AppExecFwk::EventHandler> handler_;
    uint64_t epoch_;
    uint64_t attempt_;
    std::atomic<bool> disconnected_ { false };
};

class Death final : public IRemoteObject::DeathRecipient {
public:
    Death(std::weak_ptr<Renderer> owner, std::weak_ptr<AppExecFwk::EventHandler> handler,
        uint64_t epoch, uint64_t attempt) : owner_(owner), handler_(handler), epoch_(epoch), attempt_(attempt) {}
    void OnRemoteDied(const wptr<IRemoteObject> &remote) override;
private:
    std::weak_ptr<Renderer> owner_;
    std::weak_ptr<AppExecFwk::EventHandler> handler_;
    uint64_t epoch_;
    uint64_t attempt_;
};

class Renderer final : public QemuWallpaperRenderer, public std::enable_shared_from_this<Renderer> {
public:
    explicit Renderer(const std::shared_ptr<AppExecFwk::EventHandler> &handler) : handler_(handler) {}
    ~Renderer() override { Stop(); }
    bool Stopped() const { return stopped_.load(); }

    void Request(int32_t user) override
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopped_ || handler_ == nullptr || user < -1 || user == 0) { return; }
        // Do not extend a running budget on every wallpaper update or duplicate
        // USER_SWITCHED. A later public request can retry an exhausted epoch.
        if (user == user_ && (remaining_ > 0 || ConnectedLocked())) { return; }
        handler_->RemoveTask(TIMER);
        RetireLocked();
        ++epoch_;
        user_ = user;
        remaining_ = TICKS;
        PostTickLocked(0);
    }

    void Stop() override
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopped_) { return; }
        stopped_ = true;
        ++epoch_;
        remaining_ = 0;
        if (handler_ != nullptr) {
            handler_->RemoveTask(TIMER);
            handler_->RemoveTask(CALLBACK);
        }
        // The same lock covers every Connect IPC, so no queued/in-flight epoch
        // can issue another Connect after Stop returns. Late callback cleanup
        // may only Disconnect its own retired attempt; it cannot restart work.
        RetireLocked();
        handler_.reset();
    }

    void Tick(uint64_t epoch)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopped_ || epoch != epoch_ || remaining_ <= 0) { return; }
        --remaining_;
        int32_t active = -1;
        std::vector<int32_t> users;
        const auto status = AccountSA::OsAccountManager::QueryActiveOsAccountIds(users);
        if (status == ERR_OK && users.size() == 1 && users[0] > 0) { active = users[0]; }
        if (user_ < 0 && active > 0) { user_ = active; }
        if (active <= 0 || active != user_) {
            RetireLocked();
            HILOG_INFO("QEMU renderer waiting for exact foreground user %{public}d", user_);
        } else if (ConnectedLocked()) {
            remaining_ = 0;
            return;
        } else {
            if (pending_ && ++pendingTicks_ >= PENDING_TICKS) { RetireLocked(); }
            if (!pending_) { ConnectLocked(); }
        }
        if (remaining_ > 0) {
            PostTickLocked(INTERVAL_MS);
        } else {
            HILOG_ERROR("QEMU renderer connection budget exhausted user=%{public}d", user_);
            RetireLocked();
        }
    }

    void Connected(uint64_t epoch, uint64_t attempt, const sptr<Connection> &connection,
        const AppExecFwk::ElementName &element, const sptr<IRemoteObject> &remote, int32_t result)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopped_ || epoch != epoch_ || attempt != attempt_ || connection != connection_) {
            Disconnect(connection);
            return;
        }
        if (remote_ != nullptr) {
            HILOG_ERROR("QEMU renderer duplicate callback; preserving no success claim");
            remaining_ = 0;
            handler_->RemoveTask(TIMER);
            RetireLocked();
            return;
        }
        std::vector<int32_t> users;
        const auto account = AccountSA::OsAccountManager::QueryActiveOsAccountIds(users);
        if (account != ERR_OK || users.size() != 1 || users[0] != user_ || connection->WasDisconnected() ||
            result != ERR_OK || element.GetBundleName() != BUNDLE || element.GetAbilityName() != ABILITY ||
            remote == nullptr || remote->IsObjectDead()) {
            HILOG_ERROR("QEMU renderer rejected actual callback result=%{public}d", result);
            RetireLocked();
            return;
        }
        auto recipient = sptr<Death>(new Death(weak_from_this(), handler_, epoch_, attempt_));
        if (!remote->AddDeathRecipient(recipient)) {
            HILOG_ERROR("QEMU renderer death registration failed");
            RetireLocked();
            return;
        }
        remote_ = remote;
        death_ = recipient;
        pending_ = false;
        remaining_ = 0;
        handler_->RemoveTask(TIMER);
        HILOG_INFO("QEMU renderer real callback connected user=%{public}d", user_);
    }

    void Gone(uint64_t epoch, uint64_t attempt)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopped_ || epoch != epoch_ || attempt != attempt_) { return; }
        bool wasConnected = ConnectedLocked() || remote_ != nullptr;
        RetireLocked();
        if (wasConnected) {
            ++epoch_;
            remaining_ = TICKS;
            PostTickLocked(0);
        }
        // A failed pending attempt uses the existing epoch's remaining ticks.
        // It never creates a fresh budget by receiving another error callback.
    }

    static void Disconnect(const sptr<Connection> &connection)
    {
        if (connection == nullptr) { return; }
        auto client = AAFwk::AbilityManagerClient::GetInstance();
        if (client != nullptr) {
            const auto result = client->DisconnectAbility(connection);
            if (result != ERR_OK) { HILOG_INFO("QEMU renderer Disconnect result=%{public}d", result); }
        }
    }

private:
    bool ConnectedLocked() const { return connection_ != nullptr && !connection_->WasDisconnected() &&
        remote_ != nullptr && !remote_->IsObjectDead(); }

    void RetireLocked()
    {
        auto connection = connection_;
        connection_ = nullptr;
        ++attempt_;
        pending_ = false;
        pendingTicks_ = 0;
        if (remote_ != nullptr && death_ != nullptr) { remote_->RemoveDeathRecipient(death_); }
        death_ = nullptr;
        remote_ = nullptr;
        // Invalidate the attempt BEFORE Disconnect can synchronously deliver a
        // callback. Callback methods only queue observations and never wait for
        // this mutex or directly re-enter the owner.
        Disconnect(connection);
    }

    void PostTickLocked(int32_t delay)
    {
        auto weak = weak_from_this();
        auto epoch = epoch_;
        if (!handler_->PostTask([weak, epoch]() {
            if (auto owner = weak.lock()) { owner->Tick(epoch); }
        }, TIMER, delay)) {
            remaining_ = 0;
            RetireLocked();
            HILOG_ERROR("QEMU renderer retry task rejected");
        }
    }

    void ConnectLocked()
    {
        auto client = AAFwk::AbilityManagerClient::GetInstance();
        if (client == nullptr || client->Connect() != ERR_OK) { return; }
        AAFwk::Want want;
        want.SetElementName(BUNDLE, ABILITY);
        connection_ = new Connection(weak_from_this(), handler_, epoch_, ++attempt_);
        pending_ = true;
        pendingTicks_ = 0;
        // Pin the observed foreground account explicitly. Never let -1 resolve
        // a delayed attempt into a different foreground user's renderer.
        const auto result = client->ConnectExtensionAbility(want, connection_, user_);
        if (result != ERR_OK) { RetireLocked(); }
    }

    std::mutex mutex_;
    std::shared_ptr<AppExecFwk::EventHandler> handler_;
    std::atomic<bool> stopped_ { false };
    int32_t user_ = -1;
    int32_t remaining_ = 0;
    int32_t pendingTicks_ = 0;
    bool pending_ = false;
    uint64_t epoch_ = 0;
    uint64_t attempt_ = 0;
    sptr<Connection> connection_;
    sptr<IRemoteObject> remote_;
    sptr<Death> death_;
};

void Connection::OnAbilityConnectDone(const AppExecFwk::ElementName &element,
    const sptr<IRemoteObject> &remote, int32_t result)
{
    auto owner = owner_;
    auto epoch = epoch_;
    auto attempt = attempt_;
    sptr<Connection> self = this;
    auto live = owner.lock();
    // After Stop, do not enqueue cleanup on a handler whose last reference may
    // be disappearing. Disconnect this retired attempt directly instead.
    if (live == nullptr || live->Stopped()) { Renderer::Disconnect(self); return; }
    auto handler = handler_.lock();
    if (handler == nullptr || !handler->PostTask([owner, epoch, attempt, self, element, remote, result]() {
        if (auto state = owner.lock()) { state->Connected(epoch, attempt, self, element, remote, result); }
        else { Renderer::Disconnect(self); }
    }, CALLBACK)) { Renderer::Disconnect(self); }
}

void Connection::OnAbilityDisconnectDone(const AppExecFwk::ElementName &element, int32_t result)
{
    disconnected_.store(true);
    (void)element;
    (void)result;
    auto owner = owner_;
    auto epoch = epoch_;
    auto attempt = attempt_;
    auto live = owner.lock();
    if (live == nullptr || live->Stopped()) { return; }
    if (auto handler = handler_.lock()) {
        handler->PostTask([owner, epoch, attempt]() {
            if (auto state = owner.lock()) { state->Gone(epoch, attempt); }
        }, CALLBACK);
    }
}

void Death::OnRemoteDied(const wptr<IRemoteObject> &remote)
{
    (void)remote;
    auto owner = owner_;
    auto epoch = epoch_;
    auto attempt = attempt_;
    auto live = owner.lock();
    if (live == nullptr || live->Stopped()) { return; }
    if (auto handler = handler_.lock()) {
        handler->PostTask([owner, epoch, attempt]() {
            if (auto state = owner.lock()) { state->Gone(epoch, attempt); }
        }, CALLBACK);
    }
}
}

std::shared_ptr<QemuWallpaperRenderer> QemuWallpaperRenderer::Create(
    const std::shared_ptr<AppExecFwk::EventHandler> &handler)
{
    return std::make_shared<Renderer>(handler);
}
}
