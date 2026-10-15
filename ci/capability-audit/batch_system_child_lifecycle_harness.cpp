// Execute the real callback TU, manager TU and extracted Create entrypoints.
#include "native_child_callback.h"
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace OHOS;
using namespace OHOS::AbilityRuntime;
#define CHECK(test) do { if (!(test)) throw std::runtime_error(#test); } while (0)

namespace {
std::atomic<int> calls{0};
std::atomic<int> proxyAttempts{0};
int lastError = -1;
bool failProxy = false;
bool reenter = false;
bool dropOwner = false;
bool ownerWasAlive = false;
NativeChildCallback* observed = nullptr;
sptr<NativeChildCallback> owner;
sptr<IRemoteObject> child;
int dispatchMode = 0;

void Started(int code, OHIPCRemoteProxy* proxy)
{
    ++calls;
    lastError = code;
    delete proxy; // Public callback owns the returned proxy.
    if (reenter && calls == 1) {
        observed->OnError(913);
        observed->OnNativeChildStarted(child);
    }
    if (dropOwner) {
        owner = nullptr;
        ownerWasAlive = IRemoteObject::live == 2; // child + callback's local strong reference.
    }
}

void Direct(const std::string& scenario)
{
    child = new IRemoteObject;
    owner = new NativeChildCallback(Started);
    observed = owner.GetRefPtr();
    ChildCallbackManager::GetInstance().AddRemoteObject(owner);
    if (scenario == "null_child") {
        owner->OnNativeChildStarted(nullptr);
        CHECK(calls == 1 && lastError == NCP_ERR_INTERNAL && proxyAttempts == 0);
    } else if (scenario == "proxy_failure") {
        failProxy = true;
        owner->OnNativeChildStarted(child);
        CHECK(calls == 1 && lastError == NCP_ERR_INTERNAL && proxyAttempts == 1);
        owner->OnError(913);
        CHECK(calls == 1);
    } else if (scenario == "error_then_success") {
        owner->OnError(913);
        owner->OnNativeChildStarted(child);
        owner->OnError(914);
        CHECK(calls == 1 && lastError == 913 && proxyAttempts == 0);
    } else if (scenario == "success_then_error") {
        owner->OnNativeChildStarted(child);
        owner->OnError(913);
        owner->OnNativeChildStarted(child);
        CHECK(calls == 1 && lastError == 0 && proxyAttempts == 1);
    } else if (scenario == "callback_reentry") {
        reenter = true;
        owner->OnNativeChildStarted(child);
        CHECK(calls == 1 && lastError == 0 && proxyAttempts == 1);
    } else if (scenario == "drop_last_owner" || scenario == "drop_last_owner_error") {
        dropOwner = true;
        if (scenario == "drop_last_owner") observed->OnNativeChildStarted(child);
        else observed->OnError(913);
        CHECK(calls == 1 && ownerWasAlive);
        CHECK(IRemoteObject::live == 1);
    } else if (scenario == "concurrent_terminal") {
        std::atomic<int> ready{0};
        std::atomic<bool> go{false};
        std::vector<std::thread> threads;
        for (int i = 0; i < 32; ++i) {
            threads.emplace_back([&, i] {
                ++ready;
                while (!go.load()) std::this_thread::yield();
                if (i % 2) owner->OnError(913);
                else owner->OnNativeChildStarted(child);
            });
        }
        while (ready != 32) std::this_thread::yield();
        go = true;
        for (auto& thread : threads) thread.join();
        CHECK(calls == 1 && proxyAttempts <= 1);
    } else {
        throw std::runtime_error("unknown direct scenario");
    }
    // Holding only this caller proves the manager released its retained stub.
    if (owner) CHECK(owner->StrongCount() == 1);
    owner = nullptr;
    child = nullptr;
    CHECK(IRemoteObject::live == 0);
}

void Creation(const std::string& scenario)
{
    const bool configs = scenario.find("configs") != std::string::npos;
    if (scenario.find("early_success") != std::string::npos) dispatchMode = 1;
    else if (scenario.find("early_error") != std::string::npos) dispatchMode = 2;
    else if (scenario.find("reject") != std::string::npos) dispatchMode = 3;
    else dispatchMode = 0;
    child = new IRemoteObject;
    Ability_ChildProcessConfigs config;
    auto result = configs ? OH_Ability_CreateNativeChildProcessWithConfigs("libchild.so", &config, Started) :
        OH_Ability_CreateNativeChildProcess("libchild.so", Started);
    CHECK(result == (dispatchMode == 3 ? NCP_ERR_INTERNAL : NCP_NO_ERROR));
    if (dispatchMode == 0) {
        // Delayed notification must still have a retained object after Create returns.
        CHECK(IRemoteObject::live == 2 && observed->StrongCount() == 1);
        owner = observed;
        owner->OnNativeChildStarted(child);
        CHECK(owner->StrongCount() == 1);
        owner = nullptr;
    }
    CHECK(calls == (dispatchMode == 3 ? 0 : 1));
    CHECK(IRemoteObject::live == 1);
    child = nullptr;
    CHECK(IRemoteObject::live == 0);
}

void ExitCallbacks()
{
    owner = new NativeChildCallback(nullptr);
    static int exits = 0;
    auto exited = +[](int pid, int signal) { CHECK(pid == 41 && signal == 9); ++exits; };
    owner->AddExitCallback(exited);
    owner->AddExitCallback(exited);
    CHECK(owner->GetExitCallbacks().size() == 1);
    CHECK(owner->OnNativeChildExit(41, 9) == NCP_NO_ERROR && exits == 1);
    CHECK(owner->RemoveExitCallback(exited) == NCP_NO_ERROR && owner->IsCallbacksEmpty());
    CHECK(owner->RemoveExitCallback(exited) == NCP_ERR_CALLBACK_NOT_EXIST);
    owner = nullptr;
    CHECK(IRemoteObject::live == 0);
}
}

OHIPCRemoteProxy* CreateIPCRemoteProxy(sptr<IRemoteObject> remote)
{
    ++proxyAttempts;
    return failProxy ? nullptr : new OHIPCRemoteProxy{remote};
}

ChildProcessManagerErrorCode ChildProcessManager::CreateNativeChildProcessByAppSpawnFork(
    const std::string&, const sptr<IRemoteObject>& callback, const std::string&, bool, bool)
{
    observed = dynamic_cast<NativeChildCallback*>(callback.GetRefPtr());
    if (dispatchMode == 1) observed->OnNativeChildStarted(child);
    if (dispatchMode == 2) observed->OnError(913);
    return dispatchMode == 3 ? ChildProcessManagerErrorCode::ERR_INTERNAL : ChildProcessManagerErrorCode::ERR_OK;
}

int main(int argc, char** argv)
{
    try {
        CHECK(argc == 2);
        std::string scenario(argv[1]);
        if (scenario.find("create_") == 0) Creation(scenario);
        else if (scenario == "exit_callbacks") ExitCallbacks();
        else Direct(scenario);
        std::cout << scenario << ": pass\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << argv[1] << ": " << error.what() << '\n';
        return 1;
    }
}
