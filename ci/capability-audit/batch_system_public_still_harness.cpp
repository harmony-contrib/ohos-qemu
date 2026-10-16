// Host-only native lifecycle regression. Actual fixed IMsdp/SensorAgent headers
// and algorithm TUs are used. SensorAgent calls below are fault-injection seams;
// none of this executable is a guest capability test or a virtual provider.
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits.h>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include "sensor_agent.h"
#include "devicestatus_msdp_interface.h"
#include "devicestatus_data_define.h"
#include "devicestatus_define.h"

#ifdef BATCH_PLUGIN_HELPERS
#include "algo_absolute_still.h"
extern "C" bool batch_stack_owner_init()
{
    OHOS::Msdp::DeviceStatus::AlgoAbsoluteStill stack;
    return stack.Init(OHOS::Msdp::DeviceStatus::TYPE_STILL);
}
#else
#include "devicestatus_msdp_client_impl.h"
using namespace OHOS;
using namespace OHOS::Msdp::DeviceStatus;
namespace {
std::mutex sensorLock;
const SensorUser* sensorUser = nullptr;
std::atomic<int> subscriptions{0}, unsubscriptions{0}, activations{0}, deactivations{0};
std::atomic<int> batchFailure{0}, deactivateFailure{0};
void Check(bool value, const char* message) { if (!value) { std::cerr << message << '\n'; std::exit(3); } }
bool Wait(const std::function<bool()>& predicate)
{
    auto end = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    do {
        if (predicate()) { return true; }
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    } while (std::chrono::steady_clock::now() < end);
    return predicate();
}
bool Mapped(const std::string& path)
{
    std::ifstream stream("/proc/self/maps");
    Check(stream.good(), "Linux /proc/self/maps required; never infer unload from a return code");
    std::stringstream text; text << stream.rdbuf();
    return text.str().find(path) != std::string::npos;
}
void Emit(float x, float y, float z)
{
    AccelData data{x, y, z};
    SensorEvent event{}; event.sensorTypeId = SENSOR_TYPE_ID_ACCELEROMETER;
    event.data = reinterpret_cast<uint8_t*>(&data); event.dataLen = sizeof(data);
    std::lock_guard lock(sensorLock);
    if (sensorUser != nullptr && sensorUser->callback != nullptr) { sensorUser->callback(&event); }
}
void Five()
{
    for (int i = 0; i < 6; ++i) { Emit(1.0F, 1.5F, 9.5F); std::this_thread::sleep_for(std::chrono::milliseconds(2)); }
}
struct Recorded {
    std::mutex mutex; std::vector<Data> values;
    int Add(const Data& data) { std::lock_guard lock(mutex); values.push_back(data); return RET_OK; }
    bool Saw(Type type, OnChangedValue value) {
        std::lock_guard lock(mutex);
        return std::any_of(values.begin(), values.end(), [&](const Data& d) { return d.type == type && d.value == value; });
    }
};
}
extern "C" int32_t GetAllSensors(SensorInfo** info, int32_t* count)
{
    static SensorInfo acceleration; acceleration.sensorTypeId = SENSOR_TYPE_ID_ACCELEROMETER;
    acceleration.sensorId = SENSOR_TYPE_ID_ACCELEROMETER; *info = &acceleration; *count = 1; return 0;
}
extern "C" int32_t SubscribeSensor(int32_t type, const SensorUser* user)
{
    Check(type == SENSOR_TYPE_ID_ACCELEROMETER && user != nullptr && user->callback != nullptr, "actual SensorAgent subscription arguments");
    std::lock_guard lock(sensorLock); sensorUser = user; ++subscriptions; return 0;
}
extern "C" int32_t UnsubscribeSensor(int32_t type, const SensorUser* user)
{
    Check(type == SENSOR_TYPE_ID_ACCELEROMETER && user != nullptr, "actual SensorAgent unsubscribe arguments");
    std::lock_guard lock(sensorLock); sensorUser = nullptr; ++unsubscriptions; return 0;
}
extern "C" int32_t SetBatch(int32_t, const SensorUser*, int64_t, int64_t)
{
    return batchFailure.exchange(0) != 0 ? -1 : 0;
}
extern "C" int32_t ActivateSensor(int32_t, const SensorUser*) { ++activations; return 0; }
extern "C" int32_t DeactivateSensor(int32_t, const SensorUser*)
{
    ++deactivations; return deactivateFailure.exchange(0) != 0 ? -1 : 0;
}
namespace OHOS { namespace Msdp { namespace DeviceStatus {
std::string DEVICESTATUS_ALGO_LIB_PATH;
struct HostDumper { void PushDeviceStatus(const Data&) {} };
HostDumper hostDumper;
#define DS_DUMPER (&hostDumper)
#include "actual_client.inc"
#undef DS_DUMPER
}}}

// Real manager method bodies are compiled below with a minimal Binder lifecycle
// test scaffold. The scaffold is not substituted in product or normal-HAP code.
namespace OHOS { namespace Msdp { namespace DeviceStatus {
template<class T> using sptr = std::shared_ptr<T>;
template<class T> struct wptr : std::weak_ptr<T> {
    wptr(const sptr<T>& p) : std::weak_ptr<T>(p) {}
    sptr<T> promote() const { return this->lock(); }
};
struct IRemoteObject : std::enable_shared_from_this<IRemoteObject> {
    struct DeathRecipient { virtual ~DeathRecipient() = default; virtual void OnRemoteDied(const wptr<IRemoteObject>&) = 0; };
    bool fail = false; std::vector<sptr<DeathRecipient>> deaths;
    bool AddDeathRecipient(sptr<DeathRecipient> p) { if (fail) { return false; } deaths.push_back(p); return true; }
    void RemoveDeathRecipient(sptr<DeathRecipient> p) { deaths.erase(std::remove(deaths.begin(), deaths.end(), p), deaths.end()); }
    void Die() { auto copy = deaths; for (const auto& p : copy) { p->OnRemoteDied(wptr<IRemoteObject>(shared_from_this())); } }
};
struct IRemoteDevStaCallback {
    virtual ~IRemoteDevStaCallback() = default;
    sptr<IRemoteObject> object = std::make_shared<IRemoteObject>();
    std::function<void(const Data&)> fn;
    sptr<IRemoteObject> AsObject() const { return object; }
    void OnDeviceStatusChanged(const Data& d) { if (fn) { fn(d); } }
};
struct DeviceStatusManager : std::enable_shared_from_this<DeviceStatusManager> {
    struct classcomp { bool operator()(sptr<IRemoteDevStaCallback> a, sptr<IRemoteDevStaCallback> b) const { return a->AsObject() < b->AsObject(); } };
#include "actual_manager_death.inc"
    ~DeviceStatusManager();
    void Init() { devicestatusCBDeathRecipient_ = std::make_shared<DeviceStatusCallbackDeathRecipient>(weak_from_this()); }
    bool Enable(Type type) { ++starts[type]; if (duringStart) { duringStart(); } return !failEnable; }
    bool Disable(Type type) { ++stops[type]; return true; }
    int32_t NotifyDeviceStatusChange(const Data& data);
    void Subscribe(Type, ActivityEvent, ReportLatencyNs, sptr<IRemoteDevStaCallback>);
    void Unsubscribe(Type, ActivityEvent, sptr<IRemoteDevStaCallback>);
    bool HasObjectLocked(const sptr<IRemoteObject>&) const;
    void ReconcileType(Type);
    void RemoveDeadCallback(const wptr<IRemoteObject>&);
    std::mutex mutex_;
    sptr<IRemoteObject::DeathRecipient> devicestatusCBDeathRecipient_;
    std::map<Type, std::set<sptr<IRemoteDevStaCallback>, classcomp>> listeners_;
    std::map<Type, std::map<sptr<IRemoteDevStaCallback>, ActivityEvent, classcomp>> listenerEvents_;
    std::set<Type> enabledTypes_, changingTypes_, failedStopTypes_;
    std::map<Type, int> starts, stops;
    bool failEnable = false;
    std::function<void()> duringStart;
};
#include "actual_manager.inc"
}}}

void ManagerCase(const std::string& name)
{
    auto manager = std::make_shared<DeviceStatusManager>(); manager->Init();
    auto first = std::make_shared<IRemoteDevStaCallback>(); auto second = std::make_shared<IRemoteDevStaCallback>();
    if (name == "manager_first_last") {
        manager->Subscribe(TYPE_STILL, ENTER_EXIT, SHORT, first);
        manager->Subscribe(TYPE_STILL, ENTER_EXIT, SHORT, first);
        manager->Subscribe(TYPE_STILL, ENTER_EXIT, SHORT, second);
        manager->Subscribe(TYPE_HORIZONTAL_POSITION, ENTER_EXIT, SHORT, first);
        Check(manager->starts[TYPE_STILL] == 1 && manager->starts[TYPE_HORIZONTAL_POSITION] == 1, "first listener must start backend once per logical type");
        manager->Unsubscribe(TYPE_STILL, ENTER_EXIT, first);
        Check(manager->stops[TYPE_STILL] == 0, "remaining same-type listener lost backend");
        manager->Unsubscribe(TYPE_STILL, ENTER_EXIT, second);
        Check(manager->stops[TYPE_STILL] == 1 && manager->stops[TYPE_HORIZONTAL_POSITION] == 0, "last own-type stop must not depend on global empty");
        manager->Unsubscribe(TYPE_HORIZONTAL_POSITION, ENTER_EXIT, first);
        Check(manager->stops[TYPE_HORIZONTAL_POSITION] == 1 && first->object->deaths.empty(), "remaining type/death recipient leaked");
    } else if (name == "manager_rollback") {
        manager->failEnable = true; manager->Subscribe(TYPE_STILL, ENTER_EXIT, SHORT, first);
        Check(manager->listeners_.empty() && manager->listenerEvents_.empty() && first->object->deaths.empty(), "failed enable retained listener/death state");
        manager->failEnable = false; first->object->fail = true; manager->Subscribe(TYPE_STILL, ENTER_EXIT, SHORT, first);
        Check(manager->listeners_.empty(), "failed death registration retained listener");
    } else if (name == "manager_death") {
        manager->Subscribe(TYPE_STILL, ENTER_EXIT, SHORT, first);
        manager->Subscribe(TYPE_HORIZONTAL_POSITION, ENTER_EXIT, SHORT, first);
        first->object->Die();
        Check(manager->listeners_.empty() && manager->stops[TYPE_STILL] == 1 && manager->stops[TYPE_HORIZONTAL_POSITION] == 1, "death did not release every own logical backend");
        // Death recipient remains safe after its owning manager is destroyed.
        auto recipient = manager->devicestatusCBDeathRecipient_; manager.reset();
        recipient->OnRemoteDied(wptr<IRemoteObject>(first->object));
    } else if (name == "manager_reentry") {
        manager->duringStart = [manager, first] { manager->Unsubscribe(TYPE_STILL, ENTER_EXIT, first); };
        manager->Subscribe(TYPE_STILL, ENTER_EXIT, SHORT, first); manager->duringStart = nullptr;
        Check(manager->listeners_.empty() && manager->stops[TYPE_STILL] == 1, "reentrant off during real enable leaked backend");
        manager->Subscribe(TYPE_STILL, ENTER_EXIT, SHORT, first);
        first->fn = [manager, first](const Data&) { manager->Unsubscribe(TYPE_STILL, ENTER_EXIT, first); };
        manager->NotifyDeviceStatusChange(Data{TYPE_STILL, VALUE_ENTER}); first->fn = nullptr;
        Check(manager->listeners_.empty() && manager->stops[TYPE_STILL] == 2, "callback ran under registry lock or reentrant off failed");
    } else {
        int enter = 0, exit = 0;
        first->fn = [&](const Data&) { ++enter; }; second->fn = [&](const Data&) { ++exit; };
        manager->Subscribe(TYPE_STILL, ENTER, SHORT, first); manager->Subscribe(TYPE_STILL, EXIT, SHORT, second);
        manager->NotifyDeviceStatusChange(Data{TYPE_STILL, VALUE_ENTER}); manager->NotifyDeviceStatusChange(Data{TYPE_STILL, VALUE_EXIT});
        Check(enter == 1 && exit == 1, "a later listener overwrote another listener event selector");
    }
}

int main(int argc, char** argv)
{
    Check(argc == 3, "library and case required");
    const std::string library = argv[1], name = argv[2];
    if (name.rfind("manager_", 0) == 0) { ManagerCase(name); std::cout << name << ": pass actual functions\n"; return 0; }
    DEVICESTATUS_ALGO_LIB_PATH = library;
    auto client = std::make_shared<DeviceStatusMsdpClientImpl>();
    Recorded recorded; std::atomic<int> reentrantResult{-999};
    std::mutex gateMutex; std::condition_variable gate;
    bool release = false; std::atomic<bool> entered{false}, returned{false};
    std::weak_ptr<DeviceStatusMsdpClientImpl> weak = client;
    client->RegisterImpl([&](const Data& data) {
        recorded.Add(data);
        if (name == "external_callback_quiesce" && data.type == TYPE_STILL && data.value == VALUE_ENTER) {
            std::unique_lock lock(gateMutex); entered = true;
            gate.wait(lock, [&] { return release; }); returned = true;
        }
        if (name == "callback_stop" && data.type == TYPE_STILL && data.value == VALUE_ENTER) {
            auto owner = weak.lock(); reentrantResult = owner->AlgoDisable(TYPE_STILL);
        }
        return RET_OK;
    });
    if (name == "relative_unsupported") {
        Check(client->AlgoHandle(TYPE_RELATIVE_STILL) != RET_OK && subscriptions == 0 && !Mapped(library), "unsupported relativeStill manufactured a backend");
    } else if (name == "owner_required") {
        void* handle = dlopen(library.c_str(), RTLD_NOW); Check(handle != nullptr, dlerror());
        auto test = reinterpret_cast<bool(*)()>(dlsym(handle, "batch_stack_owner_init"));
        Check(test != nullptr && !test(), "stack/unowned algorithm Init did not fail safely");
        Check(dlclose(handle) == 0, "close stack-owner test DSO");
    } else if (name == "batch_rollback") {
        batchFailure = 1;
        Check(client->AlgoHandle(TYPE_STILL) != RET_OK && subscriptions == 1 && unsubscriptions == 1, "SetBatch failure not rolled back truthfully");
        Check(!Mapped(library), "failed initialization left worker/DSO active");
        Check(client->AlgoHandle(TYPE_STILL) == RET_OK, "retry after complete initialization rollback failed");
        Check(client->AlgoDisable(TYPE_STILL) == RET_OK && Wait([&] { return !Mapped(library); }), "rollback retry did not retire");
    } else if (name == "external_callback_quiesce") {
        Check(client->AlgoHandle(TYPE_STILL) == RET_OK, "real backend start failed");
        Five(); Check(Wait([&] { return entered.load(); }), "actual callback did not enter blocking boundary");
        auto start = std::chrono::steady_clock::now();
        int result = client->AlgoDisable(TYPE_STILL);
        auto elapsed = std::chrono::steady_clock::now() - start;
        Check(result != RET_OK && elapsed >= std::chrono::milliseconds(800) && elapsed < std::chrono::milliseconds(1800),
            "external unsubscribe was unbounded or falsely successful while callback was blocked");
        Check(Mapped(library) && deactivations == 0 && !returned, "timeout destroyed owner or stopped/unloaded executing algorithm");
        { std::lock_guard lock(gateMutex); release = true; } gate.notify_one();
        Check(Wait([&] { return returned.load(); }), "blocked actual callback did not return");
        Check(client->AlgoDisable(TYPE_STILL) == RET_OK && Wait([&] { return !Mapped(library); }),
            "successful retry did not stop/join/unload actual worker");
    } else if (name == "restart_reload") {
        for (int i = 0; i < 3; ++i) {
            Check(client->AlgoHandle(TYPE_STILL) == RET_OK, "actual DSO reload/worker restart failed");
            Five();
            Check(client->AlgoDisable(TYPE_STILL) == RET_OK && Wait([&] { return !Mapped(library); }), "worker not joined before actual DSO unload");
        }
        Check(subscriptions == 3 && unsubscriptions == 3, "physical registration leaked across generations");
    } else {
        Check(client->AlgoHandle(TYPE_STILL) == RET_OK, "public TYPE_STILL has no genuine algorithm backend");
        if (name == "public_type_and_shared_input") {
            Check(client->AlgoHandle(TYPE_ABSOLUTE_STILL) == RET_OK && client->AlgoHandle(TYPE_HORIZONTAL_POSITION) == RET_OK &&
                client->AlgoHandle(TYPE_VERTICAL_POSITION) == RET_OK && client->AlgoHandle(TYPE_STILL) == RET_OK, "parallel logical subscriptions failed");
            Check(subscriptions == 1 && activations == 1, "physical acceleration was registered more than once");
        }
        Five(); Check(Wait([&] { return recorded.Saw(TYPE_STILL, VALUE_ENTER); }), "actual threshold algorithm did not report public logical type");
        if (name == "callback_stop") {
            Check(Wait([&] { return reentrantResult != -999; }) && reentrantResult == RET_OK && Wait([&] { return !Mapped(library); }), "callback reentrant cleanup deadlocked/unloaded executing code");
        } else if (name == "deactivate_retry") {
            deactivateFailure = 1;
            Check(client->AlgoDisable(TYPE_STILL) != RET_OK && Mapped(library), "failed physical stop was falsely closed/unloaded");
            Check(client->AlgoDisable(TYPE_STILL) == RET_OK && Wait([&] { return !Mapped(library); }), "physical stop retry lost logical state or failed to join");
        } else {
            if (name == "public_type_and_shared_input") {
                Check(recorded.Saw(TYPE_ABSOLUTE_STILL, VALUE_ENTER) && recorded.Saw(TYPE_HORIZONTAL_POSITION, VALUE_ENTER), "logical callbacks were globally aliased");
                Check(client->AlgoDisable(TYPE_STILL) == RET_OK && deactivations == 0, "duplicate logical reference prematurely stopped sensor");
                for (Type type : {TYPE_STILL, TYPE_ABSOLUTE_STILL, TYPE_HORIZONTAL_POSITION, TYPE_VERTICAL_POSITION}) {
                    Check(client->AlgoDisable(type) == RET_OK, "parallel type cancellation failed");
                }
            } else { Check(client->AlgoDisable(TYPE_STILL) == RET_OK, "actual stop failed"); }
            Check(Wait([&] { return !Mapped(library); }), "actual provider worker remains mapped after complete retirement");
        }
    }
    std::cout << name << ": pass actual functions and Linux lifecycle\n";
    return 0;
}
#endif
