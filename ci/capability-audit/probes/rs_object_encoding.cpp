// SPDX-License-Identifier: Apache-2.0
// Exercise the newly packaged RS/IPC DSOs, not a copied implementation.
// These are in-process real-class boundary tests; ordinary Web/Vulkan tests
// independently cover the actual cross-process RS and application paths.
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <thread>
#include <unistd.h>
#include <vector>
#include <ipc_object_stub.h>
#include <iremote_stub.h>
#include "ipc_callbacks/buffer_available_callback.h"
#include "platform/ohos/transaction/zidl/rs_iclient_to_render_connection.h"
#include "transaction/rs_ashmem_helper.h"
#include "transaction/rs_marshalling_helper.h"

using namespace OHOS;
using namespace OHOS::Rosen;
namespace {
const char* runId = nullptr;
unsigned cases = 0;
bool passed = true;
std::atomic<unsigned> remoteDestroyed {0};
std::atomic<unsigned> callbackDestroyed {0};
std::atomic<unsigned> callbacks {0};

class Remote final : public IPCObjectStub {
public:
    Remote() : IPCObjectStub(u"org.harmonycontrib.rsObjectBoundary") {}
    ~Remote() override { ++remoteDestroyed; }
};
class Callback final : public IRemoteStub<RSIBufferAvailableCallback> {
public:
    ~Callback() override { ++callbackDestroyed; }
    void OnBufferAvailable() override { ++callbacks; }
};

class RestoreStdin final {
public:
    RestoreStdin(bool enabled, int saved) : enabled_(enabled), saved_(saved) {}
    ~RestoreStdin()
    {
        if (!enabled_) return;
        if (saved_ >= 0) {
            if (dup2(saved_, STDIN_FILENO) != STDIN_FILENO) passed = false;
            close(saved_);
        } else {
            close(STDIN_FILENO); // Original stdin was closed.
        }
    }
private:
    bool enabled_;
    int saved_;
};

bool Case(const char* name, bool ok)
{
    ++cases;
    passed &= ok;
    std::printf("{\"type\":\"case\",\"run_id\":\"%s\",\"name\":\"%s\",\"passed\":%s}\n",
        runId, name, ok ? "true" : "false");
    std::fflush(stdout);
    return ok;
}

std::shared_ptr<MessageParcel> Payload(size_t size, int fd, bool objects)
{
    auto result = std::make_shared<MessageParcel>();
    if (result->GetMaxCapacity() < 1024 * 1024 && !result->SetMaxCapacity(1024 * 1024)) return nullptr;
    std::vector<uint8_t> padding(size, 0x3c);
    sptr<IRemoteObject> object = objects ? sptr<IRemoteObject>(new Remote) : nullptr;
    sptr<RSIBufferAvailableCallback> callback = objects ? sptr<RSIBufferAvailableCallback>(new Callback) : nullptr;
    if (!result->WriteInterfaceToken(RSIClientToRenderConnection::GetDescriptor()) ||
        !result->WriteInt32(0) || !result->WriteUint32(static_cast<uint32_t>(size)) ||
        (size != 0 && !result->WriteBuffer(padding.data(), padding.size())) ||
        !RSMarshallingHelper::Marshalling(*result, object) ||
        !RSMarshallingHelper::Marshalling(*result, callback) ||
        (fd >= 0 && !result->WriteFileDescriptor(fd)) || !result->WriteUint32(0x12345678)) {
        return nullptr;
    }
    return result;
}

std::shared_ptr<MessageParcel> Parse(std::shared_ptr<MessageParcel>& outer)
{
    if (outer == nullptr || !outer->RewindRead(0) ||
        outer->ReadInterfaceToken() != RSIClientToRenderConnection::GetDescriptor() ||
        outer->ReadInt32() != 1) {
        return nullptr;
    }
    std::unique_ptr<AshmemFdWorker> worker;
    std::shared_ptr<AshmemFlowControlUnit> flow;
    auto result = RSAshmemHelper::ParseFromAshmemParcel(outer.get(), worker, flow, getpid());
    return worker == nullptr ? result : nullptr;
}

bool Decode(MessageParcel& parcel, size_t size, bool ashmem, bool hasFd, bool objects, bool fdZero)
{
    if (!ashmem && (parcel.ReadInterfaceToken() != RSIClientToRenderConnection::GetDescriptor() ||
        parcel.ReadInt32() != 0)) {
        return false;
    }
    uint32_t length = 0;
    if (!parcel.ReadUint32(length) || length != size) return false;
    if (size != 0) {
        const auto* padding = parcel.ReadBuffer(size);
        if (padding == nullptr) return false;
        for (size_t index = 0; index < size; ++index) {
            if (padding[index] != 0x3c) return false;
        }
    }
    sptr<IRemoteObject> object;
    sptr<RSIBufferAvailableCallback> callback;
    if (!RSMarshallingHelper::Unmarshalling(parcel, object) ||
        !RSMarshallingHelper::Unmarshalling(parcel, callback) ||
        (object != nullptr) != objects || (callback != nullptr) != objects) return false;
    if (objects) {
        if (object->GetObjectDescriptor() != u"org.harmonycontrib.rsObjectBoundary") return false;
        const unsigned previous = callbacks.load();
        callback->OnBufferAvailable();
        if (callbacks.load() != previous + 1) return false;
    }
    if (hasFd) {
        const int duplicate = parcel.ReadFileDescriptor();
        if (duplicate < 0) return false;
        const bool valid = fcntl(duplicate, F_GETFD) >= 0 && (!fdZero || duplicate == STDIN_FILENO);
        const int closed = close(duplicate);
        if (!valid || closed != 0) return false;
    }
    uint32_t trailer = 0;
    return parcel.ReadUint32(trailer) && trailer == 0x12345678 && parcel.GetReadableBytes() == 0;
}

bool RoundTrip(size_t size, bool ashmem, bool fdZero, bool objects, bool cancel)
{
    const unsigned oldRemote = remoteDestroyed.load();
    const unsigned oldCallback = callbackDestroyed.load();
    const int savedStdin = fdZero ? dup(STDIN_FILENO) : -1;
    if (fdZero && savedStdin < 0 && errno != EBADF) return false;
    const RestoreStdin restoreStdin(fdZero, savedStdin);
    int fd = open("/dev/null", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    if (fdZero && fd != 0) {
        if (dup2(fd, STDIN_FILENO) < 0) {
            close(fd); return false;
        }
        close(fd);
        fd = STDIN_FILENO;
    }
    auto source = Payload(size, fd, objects);
    close(fd);
    // Keep 0 available until copying, ashmem parsing and the consumer finish:
    // real dup/ashmem operations must handle a returned FD 0, not merely an
    // input 0 that WriteFileDescriptor immediately duplicates to a positive FD.
    if (source == nullptr || !source->RewindRead(sizeof(uint32_t))) return false;
    const size_t position = source->GetReadPosition();
    std::shared_ptr<MessageParcel> output;
    if (ashmem) {
        auto outer = RSAshmemHelper::CreateAshmemParcel(source);
        if (source->GetReadPosition() != position) return false;
        source.reset();
        if (objects && (remoteDestroyed.load() != oldRemote || callbackDestroyed.load() != oldCallback)) return false;
        output = Parse(outer);
        outer.reset();
    } else {
        output = RSAshmemHelper::CopyTransactionParcel(*source);
        if (source->GetReadPosition() != position) return false;
        source.reset();
    }
    if (output == nullptr || (objects &&
        (remoteDestroyed.load() != oldRemote || callbackDestroyed.load() != oldCallback))) return false;
    bool ok = true;
    // Destruction and consumption happen on a different thread, after both
    // the source request and outer sidecar have been destroyed.
    std::thread task([parcel = std::move(output), &ok, size, ashmem, objects, cancel, fdZero]() mutable {
        if (!cancel) ok = Decode(*parcel, size, ashmem, true, objects, fdZero);
        parcel.reset();
    });
    task.join();
    if (fdZero && (fcntl(STDIN_FILENO, F_GETFD) >= 0 || errno != EBADF)) return false;
    return ok && remoteDestroyed.load() == oldRemote + (objects ? 1 : 0) &&
        callbackDestroyed.load() == oldCallback + (objects ? 1 : 0);
}

bool BadSidecar(unsigned mutation)
{
    const unsigned oldRemote = remoteDestroyed.load();
    const unsigned oldCallback = callbackDestroyed.load();
    auto source = Payload(4096, -1, true);
    if (source == nullptr) return false;
    auto outer = RSAshmemHelper::CreateAshmemParcel(source);
    if (outer == nullptr) return false;
    if (!outer->RewindRead(0) || outer->ReadInterfaceToken() != RSIClientToRenderConnection::GetDescriptor() ||
        outer->ReadInt32() != 1) return false;
    uint32_t size = 0;
    if (!outer->ReadUint32(size) || size != source->GetDataSize()) return false;
    const int fd = outer->ReadFileDescriptor();
    if (fd < 0) return false;
    close(fd);
    const size_t countPosition = outer->GetReadPosition();
    int32_t count = 0;
    if (!outer->ReadInt32(count) || count != 2) return false;
    const size_t versionPosition = outer->GetReadPosition();
    if (mutation < 3) {
        const size_t position = mutation == 2 ? versionPosition : countPosition;
        const uint32_t value = mutation == 0 ? UINT32_MAX : mutation == 1 ? INT32_MAX : 0xDEADBEEF;
        if (outer->GetDataSize() < sizeof(value) || position > outer->GetDataSize() - sizeof(value)) return false;
        // This is our own writable sidecar. RewindWrite would truncate the
        // Parcel and discard its object table, testing a different condition.
        // Change only the field; keep real owning Binder/FD entries intact.
        std::memcpy(reinterpret_cast<uint8_t*>(outer->GetData()) + position, &value, sizeof(value));
    } else {
        if (!outer->WriteUint32(0)) return false; // Append unconsumed bytes.
    }
    source.reset();
    auto decoded = Parse(outer);
    const bool rejected = decoded == nullptr;
    decoded.reset();
    outer.reset();
    return rejected && remoteDestroyed.load() == oldRemote + 1 && callbackDestroyed.load() == oldCallback + 1;
}
} // namespace

int main(int argc, char** argv)
{
    if (argc != 2 || std::strlen(argv[1]) != 32 ||
        std::strspn(argv[1], "0123456789abcdef") != 32) return 2;
    runId = argv[1];
    std::printf("{\"type\":\"identity\",\"run_id\":\"%s\",\"uid\":%u,\"pointer_bits\":%zu,"
        "\"scope\":\"packaged_RS_IPC_real_class_boundaries_NOT_cross_process_or_UI\"}\n",
        runId, static_cast<unsigned>(getuid()), sizeof(void*) * 8);
    for (const bool ashmem : {false, true}) {
        for (const size_t size : {size_t(0), size_t(65536), size_t(900000)}) {
            char name[96];
            std::snprintf(name, sizeof(name), "%s_objects_fd_%zu", ashmem ? "ashmem" : "ordinary", size);
            Case(name, RoundTrip(size, ashmem, false, true, false));
        }
        Case(ashmem ? "ashmem_null_objects" : "ordinary_null_objects", RoundTrip(0, ashmem, false, false, false));
        Case(ashmem ? "ashmem_fd_zero" : "ordinary_fd_zero", RoundTrip(0, ashmem, true, true, false));
        Case(ashmem ? "ashmem_cross_thread_cancel" : "ordinary_cross_thread_cancel", RoundTrip(900000, ashmem, false, true, true));
        bool repeats = true;
        for (unsigned index = 0; index < 128; ++index) repeats &= RoundTrip(256, ashmem, false, true, index % 2 == 0);
        Case(ashmem ? "ashmem_128_lifetimes" : "ordinary_128_lifetimes", repeats);
    }
    for (unsigned mutation = 0; mutation < 4; ++mutation) {
        const char* names[] = {"negative_count_rejected", "oversized_count_rejected", "wrong_version_rejected", "trailing_sidecar_rejected"};
        Case(names[mutation], BadSidecar(mutation));
    }
    std::printf("{\"type\":\"summary\",\"run_id\":\"%s\",\"cases\":%u,\"passed\":%s,"
        "\"first_artifact_behavior_gate_passed\":false}\n", runId, cases, passed ? "true" : "false");
    return passed ? 0 : 1;
}
