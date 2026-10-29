#!/usr/bin/env python3
"""Use only kernel-trusted identity for asynchronous zero-PID RS commits."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/graphic/graphic_2d'
REVISION = '81cc9ca9509bccd86c435064136fe45591d29eeb'
FILE = 'rosen/modules/render_service/core/transaction/zidl/rs_client_to_render_connection_stub.cpp'
HEADER = 'rosen/modules/render_service/core/transaction/zidl/rs_client_to_render_connection_stub.h'
CONNECTION = 'rosen/modules/render_service/core/transaction/rs_client_to_render_connection.cpp'
ASHMEM = 'rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp'
TRANSACTION = 'rosen/modules/render_service_base/src/transaction/rs_transaction_data.cpp'
PIPELINE = 'rosen/modules/render_service/core/rs_render_pipeline_agent.cpp'
ASHMEM_HEADER = 'rosen/modules/render_service_base/include/transaction/rs_ashmem_helper.h'
UNMARSHAL = 'rosen/modules/render_service/core/transaction/rs_unmarshal_thread.cpp'
DELEGATE = 'rosen/modules/render_service_base/src/feature/delegate_composite/rs_delegate_composite_callback_manager.cpp'
MAIN_THREAD_HEADER = 'rosen/modules/render_service/core/pipeline/main_thread/rs_main_thread.h'
MAIN_THREAD = 'rosen/modules/render_service/core/pipeline/main_thread/rs_main_thread.cpp'
OFFSETS_VALIDATION = '''bool IsValidAshmemObjectOffsets(const binder_size_t* offsets, size_t count, size_t dataSize)
{
    if (count > 0 && offsets == nullptr) {
        return false;
    }
    size_t previousEnd = 0;
    for (size_t i = 0; i < count; ++i) {
        const binder_size_t offset = offsets[i];
        if (offset < previousEnd || offset > dataSize ||
            sizeof(flat_binder_object) > dataSize - static_cast<size_t>(offset) ||
            offset % sizeof(uint32_t) != 0) {
            return false;
        }
        previousEnd = static_cast<size_t>(offset) + sizeof(flat_binder_object);
    }
    return true;
}

'''
RESTORE_OFFSETS = '''bool RestoreAshmemObjectOffsets(std::shared_ptr<MessageParcel>& dataParcel, MessageParcel* ashmemParcel,
    std::unique_ptr<AshmemFdWorker>& ashmemFdWorker, pid_t callingPid)
{
    int32_t offsetSize = 0;
    if (!ashmemParcel->ReadInt32(offsetSize) || offsetSize < 0) {
        return false;
    }
    const size_t count = static_cast<size_t>(offsetSize);
    // Division precedes multiplication, including on ARM32 Binder64.
    if (count > ashmemParcel->GetReadableBytes() / sizeof(binder_size_t) ||
        count > dataParcel->GetDataSize() / sizeof(flat_binder_object)) {
        return false;
    }
    if (count == 0) {
        return true;
    }
    const size_t bytes = count * sizeof(binder_size_t);
    const auto* rawOffsets = ashmemParcel->ReadBuffer(bytes);
    if (rawOffsets == nullptr) {
        return false;
    }
    // Parcel buffers are only 4-byte aligned, even with Binder64 offsets.
    std::unique_ptr<binder_size_t, decltype(&free)> offsets(
        static_cast<binder_size_t*>(malloc(bytes)), &free);
    if (!offsets || memcpy_s(offsets.get(), bytes, rawOffsets, bytes) != EOK ||
        !IsValidAshmemObjectOffsets(offsets.get(), count, dataParcel->GetDataSize())) {
        return false;
    }
    dataParcel->InjectOffsets(reinterpret_cast<binder_size_t>(offsets.get()), count);
    if (dataParcel->GetOffsetsSize() != count || dataParcel->GetObjectOffsets() == 0) {
        return false;
    }
    RSAshmemHelper::InjectFileDescriptor(dataParcel, ashmemParcel, ashmemFdWorker, callingPid);
    return true;
}

'''
CALLER_CONTEXT = '''// Internal request-scoped identity; not a Parcel field or public IPC API.
class RSScopedAsyncCallerPid final {
public:
    explicit RSScopedAsyncCallerPid(pid_t callingPid) : previous_(Current())
    {
        Current() = callingPid;
    }

    ~RSScopedAsyncCallerPid()
    {
        Current() = previous_;
    }

    RSScopedAsyncCallerPid(const RSScopedAsyncCallerPid&) = delete;
    RSScopedAsyncCallerPid& operator=(const RSScopedAsyncCallerPid&) = delete;

    static pid_t Get()
    {
        return Current();
    }

private:
    static pid_t& Current()
    {
        static thread_local pid_t callingPid = 0;
        return callingPid;
    }

    const pid_t previous_;
};

'''
OLD_IDENTITY = '    pid_t callingPid = GetCallingPid();\n    RSMarshallingHelper::SetCallingPid(callingPid);\n'
NEW_IDENTITY = '''    pid_t callingPid = GetCallingPid();
    const bool isAsyncZeroPidCommit =
        code == static_cast<uint32_t>(RSIClientToRenderConnectionInterfaceCode::COMMIT_TRANSACTION) &&
        callingPid == 0 && (option.GetFlags() & MessageOption::TF_ASYNC) != 0;
    if (isAsyncZeroPidCommit) {
        // Linux keeps the asynchronous wire PID zero. Only the kernel sender
        // info may supply the real identity; never trust a Parcel/command PID.
        callingPid = IPCSkeleton::GetCallingRealPid();
        if (callingPid <= 0) {
            return ERR_INVALID_STATE;
        }
    }
    const RSScopedAsyncCallerPid asyncCaller(isAsyncZeroPidCommit ? callingPid : 0);
    RSMarshallingHelper::SetCallingPid(callingPid);
'''
REPLACEMENTS = {
    FILE: (('#include "ivsync_connection.h"\n', '#include "ipc_skeleton.h"\n#include "ivsync_connection.h"\n'),
           (OLD_IDENTITY, NEW_IDENTITY),
           ('        parcelCopied->InjectOffsets(old.GetObjectOffsets(), objectNum);\n'
            '        CopyFileDescriptor(old, *parcelCopied);\n',
            '        parcelCopied->InjectOffsets(old.GetObjectOffsets(), objectNum);\n'
            '        if (parcelCopied->GetOffsetsSize() != objectNum || parcelCopied->GetObjectOffsets() == 0) {\n'
            '            // No FD has been duplicated yet; discard borrowed object metadata.\n'
            '            parcelCopied->FlushBuffer();\n            return nullptr;\n        }\n'
            '        CopyFileDescriptor(old, *parcelCopied);\n'),
           ('        RS_LOGE("RSClientToRenderConnectionStub::CopyParcelIfNeed parcel data Read failed");\n'
            '        free(base);\n',
            '        RS_LOGE("RSClientToRenderConnectionStub::CopyParcelIfNeed parcel data Read failed");\n'),
           ('        RS_LOGE("RSClientToRenderConnectionStub::CopyParcelIfNeed parcel data not match");\n'
            '        free(base);\n',
            '        RS_LOGE("RSClientToRenderConnectionStub::CopyParcelIfNeed parcel data not match");\n'),
           ('                    CommitTransaction(transactionData);\n',
            '                    ret = CommitTransaction(transactionData);\n'),
           ('                CommitTransaction(transactionData);\n',
            '                ret = CommitTransaction(transactionData);\n')),
    HEADER: (('namespace Rosen {\nclass RSClientToRenderConnectionStub',
              'namespace Rosen {\n' + CALLER_CONTEXT + 'class RSClientToRenderConnectionStub'),),
    CONNECTION: (('    pid_t callingPid = GetCallingPid();\n    bool isTokenTypeValid = true;\n',
                  '    pid_t callingPid = GetCallingPid();\n'
                  '    if (callingPid == 0 && RSScopedAsyncCallerPid::Get() > 0) {\n'
                  '        callingPid = RSScopedAsyncCallerPid::Get();\n'
                  '    }\n    bool isTokenTypeValid = true;\n'),),
    ASHMEM: (
        ('#include <memory>\n', '#include <cstdlib>\n#include <memory>\n'),
        ('thread_local bool g_isUnmarshalThread = false;\n}\n',
         'thread_local bool g_isUnmarshalThread = false;\n\n' + OFFSETS_VALIDATION + RESTORE_OFFSETS + '}\n'),
        ('        if (offset + sizeof(flat_binder_object) > dataParcel->GetDataSize()) {\n',
         '        if (offset > dataParcel->GetDataSize() ||\n'
         '            sizeof(flat_binder_object) > dataParcel->GetDataSize() - static_cast<size_t>(offset)) {\n'),
        ('    dataParcel->ParseFrom(reinterpret_cast<uintptr_t>(data), dataSize);\n\n'
         '    int32_t offsetSize = ashmemParcel->ReadInt32();\n'
         '    if (offsetSize > 0) {\n'
         '        auto* offsets = ashmemParcel->ReadBuffer(sizeof(binder_size_t) * offsetSize);\n'
         '        if (offsets == nullptr) {\n'
         '            ROSEN_LOGE("ParseFromAshmemParcel: read object offsets failed");\n'
         '            return nullptr;\n        }\n'
         '        // restore array that record the offsets of all fds\n'
         '        dataParcel->InjectOffsets(reinterpret_cast<binder_size_t>(offsets), offsetSize);\n'
         '        // restore all fds\n'
         '        InjectFileDescriptor(dataParcel, ashmemParcel, ashmemFdWorker, callingPid);\n    }\n',
         '    if (!dataParcel->ParseFrom(reinterpret_cast<uintptr_t>(data), dataSize)) {\n'
         '        return nullptr;\n    }\n\n'
         '    if (!RestoreAshmemObjectOffsets(dataParcel, ashmemParcel, ashmemFdWorker, callingPid)) {\n'
         '        // Failed injection may hold borrowed FD numbers. Clear them before destruction.\n'
         '        dataParcel->FlushBuffer();\n'
         '        ROSEN_LOGE("ParseFromAshmemParcel: invalid or incomplete object offsets");\n'
         '        return nullptr;\n    }\n'),
    ),
    TRANSACTION: (
        ('            if (!parcel.ReadUint8(followType)) {\n',
         '            if (!parcel.ReadUint8(followType) ||\n'
         '                followType > static_cast<uint8_t>(FollowType::FOLLOW_TO_SELF)) {\n'),
        ('    scene_ = static_cast<RSTransactionDataScenes>(scene);\n',
         '    if (!flag || (scene != static_cast<uint8_t>(RSTransactionDataScenes::Default) &&\n'
         '        scene != static_cast<uint8_t>(RSTransactionDataScenes::Rebuild))) {\n'
         '        return false;\n    }\n'
         '    scene_ = static_cast<RSTransactionDataScenes>(scene);\n'),
    ),
}

# Keep these private helpers byte-based: Binder64 objects may start at a legal
# four-byte offset without satisfying the C++ structure's eight-byte alignment.
SANITIZE_FDS = '''bool SanitizeAshmemFileDescriptors(MessageParcel& parcel, const binder_size_t* offsets, size_t count)
{
    for (size_t i = 0; i < count; ++i) {
        flat_binder_object flat {};
        auto* bytes = reinterpret_cast<void*>(parcel.GetData() + offsets[i]);
        if (memcpy_s(&flat, sizeof(flat), bytes, sizeof(flat)) != EOK) {
            return false;
        }
        if (flat.hdr.type == BINDER_TYPE_FD || flat.hdr.type == BINDER_TYPE_FDR) {
            // These numbers belong to the sender, not to this process. Never
            // publish them in the receiver's object table, even on failure.
            flat.hdr.type = BINDER_TYPE_FD;
            flat.handle = static_cast<uint32_t>(-1);
            flat.cookie = 1;
            if (memcpy_s(bytes, sizeof(flat), &flat, sizeof(flat)) != EOK) {
                return false;
            }
        }
    }
    return true;
}

bool RestoreAshmemFileDescriptors(std::shared_ptr<MessageParcel>& parcel, MessageParcel* ashmem,
    std::unique_ptr<AshmemFdWorker>& worker, pid_t callingPid)
{
    worker = std::make_unique<AshmemFdWorker>(callingPid);
    const auto* offsets = reinterpret_cast<const binder_size_t*>(parcel->GetObjectOffsets());
    for (size_t i = 0; i < parcel->GetOffsetsSize(); ++i) {
        const binder_size_t offset = offsets[i];
        if (offset > parcel->GetDataSize() || sizeof(flat_binder_object) > parcel->GetDataSize() - offset) {
            return false;
        }
        flat_binder_object flat {};
        auto* bytes = reinterpret_cast<void*>(parcel->GetData() + offset);
        if (memcpy_s(&flat, sizeof(flat), bytes, sizeof(flat)) != EOK) {
            return false;
        }
        if (flat.hdr.type != BINDER_TYPE_FD) {
            continue;
        }
        const int fd = ashmem->ReadFileDescriptor();
        if (fd < 0) {
            return false;
        }
        flat.handle = static_cast<uint32_t>(fd);
        if (memcpy_s(bytes, sizeof(flat), &flat, sizeof(flat)) != EOK) {
            ::close(fd);
            return false;
        }
        // The Parcel owns every duplicate until the async path FlushBuffer()s
        // and explicitly transfers that responsibility to this worker.
        worker->InsertFdWithOffset(fd, offset, true);
    }
    return true;
}

'''

RECEIVER_RESTORE_OFFSETS = RESTORE_OFFSETS.replace(
         '    dataParcel->InjectOffsets(reinterpret_cast<binder_size_t>(offsets.get()), count);\n',
         '    if (!SanitizeAshmemFileDescriptors(*dataParcel, offsets.get(), count)) {\n'
         '        return false;\n    }\n'
         '    dataParcel->InjectOffsets(reinterpret_cast<binder_size_t>(offsets.get()), count);\n').replace(
         '    RSAshmemHelper::InjectFileDescriptor(dataParcel, ashmemParcel, ashmemFdWorker, callingPid);\n'
         '    return true;\n',
         '    return RestoreAshmemFileDescriptors(dataParcel, ashmemParcel, ashmemFdWorker, callingPid);\n')

REPLACEMENTS[ASHMEM] += (
    (OFFSETS_VALIDATION + RESTORE_OFFSETS, OFFSETS_VALIDATION + SANITIZE_FDS + RECEIVER_RESTORE_OFFSETS),
    ('    if (fd_ > 0) {\n', '    if (fd_ >= 0) {\n'),
    ('            if (fd > 0) {\n', '            if (fd >= 0) {\n'),
    ('        const flat_binder_object* flat = reinterpret_cast<flat_binder_object*>(data + object[i]);\n'
     '        if (flat->hdr.type == BINDER_TYPE_FD) {\n'
     '            if (!ashmemParcel->WriteFileDescriptor(flat->handle)) {\n'
     '                ROSEN_LOGE("RSAshmemHelper::CopyFileDescriptor failed, fd:%{public}u", flat->handle);\n',
     '        flat_binder_object flat {};\n'
     '        const binder_size_t offset = object[i];\n'
     '        if (offset > dataParcel->GetDataSize() ||\n'
     '            sizeof(flat) > dataParcel->GetDataSize() - offset ||\n'
     '            memcpy_s(&flat, sizeof(flat), reinterpret_cast<void*>(data + offset), sizeof(flat)) != EOK) {\n'
     '            return;\n        }\n'
     '        if (flat.hdr.type == BINDER_TYPE_FD || flat.hdr.type == BINDER_TYPE_FDR) {\n'
     '            if (!ashmemParcel->WriteFileDescriptor(static_cast<int32_t>(flat.handle))) {\n'
     '                ROSEN_LOGE("RSAshmemHelper::CopyFileDescriptor failed, fd:%{public}u", flat.handle);\n'),
    ('''    ashmemFdWorker = std::make_unique<AshmemFdWorker>(callingPid);
    binder_size_t* object = reinterpret_cast<binder_size_t*>(dataParcel->GetObjectOffsets());
    size_t objectNum = dataParcel->GetOffsetsSize();
    uintptr_t data = dataParcel->GetData();
    for (size_t i = 0; i < objectNum; i++) {
        binder_size_t offset = object[i];
        if (offset > dataParcel->GetDataSize() ||
            sizeof(flat_binder_object) > dataParcel->GetDataSize() - static_cast<size_t>(offset)) {
            ROSEN_LOGW("RSAshmemHelper::InjectFileDescriptor offset invalid");
            continue;
        }
        flat_binder_object* flat = reinterpret_cast<flat_binder_object*>(data + offset);
        if (flat->hdr.type == BINDER_TYPE_FD || flat->hdr.type == BINDER_TYPE_FDR) {
            int32_t val = ashmemParcel->ReadFileDescriptor();
            if (val < 0) {
                ROSEN_LOGW("RSAshmemHelper::InjectFileDescriptor failed, fd:%{public}d, handle:%{public}u", val,
                    flat->handle);
            }
            flat->handle = static_cast<uint32_t>(val);
            if (ashmemFdWorker) {
                bool shouldCloseFd = flat->hdr.type == BINDER_TYPE_FD;
                ashmemFdWorker->InsertFdWithOffset(val, offset, shouldCloseFd);
            }
        }
    }
''', '''    const auto* offsets = reinterpret_cast<const binder_size_t*>(dataParcel->GetObjectOffsets());
    const size_t count = dataParcel->GetOffsetsSize();
    if (!IsValidAshmemObjectOffsets(offsets, count, dataParcel->GetDataSize()) ||
        !SanitizeAshmemFileDescriptors(*dataParcel, offsets, count) ||
        !RestoreAshmemFileDescriptors(dataParcel, ashmemParcel, ashmemFdWorker, callingPid)) {
        ROSEN_LOGE("RSAshmemHelper::InjectFileDescriptor failed to restore receiver-owned FDs");
    }
'''),
    ('    auto ashmemAllocator = AshmemAllocator::CreateAshmemAllocatorWithFd(fd, dataSize, PROT_READ | PROT_WRITE);\n',
     '    auto ashmemAllocator = AshmemAllocator::CreateAshmemAllocatorWithFd(fd, dataSize, PROT_READ);\n'),
    ('    void* data = ashmemAllocator->GetData();\n'
     '    auto dataParcel = std::make_shared<MessageParcel>(ashmemAllocator.release());\n'
     '    if (!dataParcel->ParseFrom(reinterpret_cast<uintptr_t>(data), dataSize)) {\n'
     '        return nullptr;\n    }\n',
     '    // Only a private snapshot may hold object metadata or queued commands.\n'
     '    void* data = ashmemAllocator->CopyFromAshmem(dataSize);\n'
     '    if (data == nullptr) {\n        return nullptr;\n    }\n'
     '    auto dataParcel = std::make_shared<MessageParcel>();\n'
     '    if (!dataParcel->ParseFrom(reinterpret_cast<uintptr_t>(data), dataSize)) {\n'
     '        free(data);\n        return nullptr;\n    }\n'),
    ('        // Failed injection may hold borrowed FD numbers. Clear them before destruction.\n'
     '        dataParcel->FlushBuffer();\n',
     '        // Sanitized metadata contains only receiver-owned FDs, including\n'
     '        // partial restoration. Let the Parcel release them exactly once.\n'),
)

REPLACEMENTS[FILE] += (
    ('#include "ipc_skeleton.h"\n', '#include <cstring>\n\n#include "ipc_skeleton.h"\n'),
    ('''        const flat_binder_object* flat = reinterpret_cast<flat_binder_object*>(data + object[i]);
        flat_binder_object* copiedFlat = reinterpret_cast<flat_binder_object*>(copiedData + copiedObject[i]);

        if (flat->hdr.type == BINDER_TYPE_FD && flat->handle >= 0) {
            int32_t val = dup(flat->handle);
''', '''        flat_binder_object flat {};
        std::memcpy(&flat, reinterpret_cast<const void*>(data + object[i]), sizeof(flat));

        if (flat.hdr.type == BINDER_TYPE_FD || flat.hdr.type == BINDER_TYPE_FDR) {
            int32_t val = dup(static_cast<int32_t>(flat.handle));
'''),
    ('                    static_cast<uint32_t>(flat->handle));\n'
     '            }\n            copiedFlat->handle = static_cast<uint32_t>(val);\n',
     '                    flat.handle);\n            }\n'
     '            flat.hdr.type = BINDER_TYPE_FD;\n'
     '            flat.handle = static_cast<uint32_t>(val);\n'
     '            flat.cookie = 1;\n'
     '            std::memcpy(reinterpret_cast<void*>(copiedData + copiedObject[i]), &flat, sizeof(flat));\n'),
)
REPLACEMENTS[TRANSACTION] += (
    ('        if (command != nullptr &&\n            command->GetType() == RSCommandType::CANVAS_NODE &&\n',
     '        if (command != nullptr && command->IsCallingPidValid() &&\n'
     '            command->GetType() == RSCommandType::CANVAS_NODE &&\n'),
)
REPLACEMENTS[PIPELINE] = (
    ('''    if (transactionData && transactionData->GetDVSyncUpdate()) {
        pipeline->GetMainThread()->DVSyncUpdate(
            transactionData->GetDVSyncTime(), transactionData->GetTimestamp());
    }
    bool isProcessBySingleFrame =
        pipeline->GetMainThread()->IsNeedProcessBySingleFrameComposer(transactionData);
    if (isProcessBySingleFrame) {
        pipeline->GetMainThread()->ProcessDataBySingleFrameComposer(transactionData);
    } else {
        pipeline->GetMainThread()->RecvRSTransactionData(transactionData);
    }
''', '''    // Keep the commit asynchronous, but never inspect or mutate the node map
    // from the Binder thread. The queued task owns its transaction on cancel.
    pipeline->ScheduleMainThreadTask([pipeline, data = std::move(transactionData)]() mutable {
        auto* mainThread = pipeline->GetMainThread();
        if (mainThread == nullptr || data == nullptr) {
            return;
        }
        if (data->GetDVSyncUpdate()) {
            mainThread->DVSyncUpdate(data->GetDVSyncTime(), data->GetTimestamp());
        }
        if (mainThread->IsNeedProcessBySingleFrameComposer(data)) {
            mainThread->ProcessDataBySingleFrameComposer(data);
        } else {
            mainThread->RecvRSTransactionData(data);
        }
    });
'''),
)

FD_SCOPE_HEADER = '''// This scope is constructed and destroyed only by the executing task.
class RSB_EXPORT AshmemFdContainerScope final {
public:
    explicit AshmemFdContainerScope(AshmemFdWorker* worker);
    ~AshmemFdContainerScope();

private:
    DISALLOW_COPY_AND_MOVE(AshmemFdContainerScope);
    AshmemFdContainer& container_;
    std::unordered_map<binder_size_t, int> previousFds_;
    const bool previousUse_;
    const bool previousUnmarshal_;
};

'''
FD_SCOPE_SOURCE = '''AshmemFdContainerScope::AshmemFdContainerScope(AshmemFdWorker* worker)
    : container_(AshmemFdContainer::Instance()), previousFds_(std::move(container_.fds_)),
      previousUse_(container_.isUseFdContainer_), previousUnmarshal_(g_isUnmarshalThread)
{
    AshmemFdContainer::SetIsUnmarshalThread(true);
    container_.isUseFdContainer_ = false;
    if (worker != nullptr) {
        worker->PushFdsToContainer();
    }
}

AshmemFdContainerScope::~AshmemFdContainerScope()
{
    // Never defer TLS cleanup to the final shared worker owner: that owner
    // may be the producer, or a queue cancellation thread.
    container_.fds_ = std::move(previousFds_);
    container_.isUseFdContainer_ = previousUse_;
    AshmemFdContainer::SetIsUnmarshalThread(previousUnmarshal_);
}

'''
NO_WAIT_PERMIT = '''class NoWaitTaskPermit final {
public:
    explicit NoWaitTaskPermit(std::atomic<int>& count) : count_(count)
    {
        count_.fetch_add(1);
    }
    ~NoWaitTaskPermit()
    {
        Complete();
    }
    void Complete()
    {
        if (pending_.exchange(false)) {
            count_.fetch_sub(1);
        }
    }

private:
    std::atomic<int>& count_;
    std::atomic<bool> pending_ { true };
};

class NoWaitTaskCompletion final {
public:
    explicit NoWaitTaskCompletion(std::shared_ptr<NoWaitTaskPermit> permit) : permit_(std::move(permit)) {}
    ~NoWaitTaskCompletion()
    {
        if (permit_) {
            permit_->Complete();
        }
    }

private:
    const std::shared_ptr<NoWaitTaskPermit> permit_;
};

'''
REPLACEMENTS[ASHMEM_HEADER] = (
    ('\nclass AshmemFdWorker;\n', '\nclass AshmemFdWorker;\nclass AshmemFdContainerScope;\n'),
    ('    friend class AshmemFdWorker;\n',
     '    friend class AshmemFdWorker;\n    friend class AshmemFdContainerScope;\n'),
    ('class RSB_EXPORT RSAshmemHelper {\n', FD_SCOPE_HEADER + 'class RSB_EXPORT RSAshmemHelper {\n'),
)
REPLACEMENTS[ASHMEM] += (
    ('    if (!isFdContainerUpdated_) {\n        return;\n    }\n'
     '    AshmemFdContainer::Instance().Clear();\n', ''),
    ('AshmemFdWorker::AshmemFdWorker(const pid_t callingPid) : callingPid_(callingPid) {}\n',
     FD_SCOPE_SOURCE + 'AshmemFdWorker::AshmemFdWorker(const pid_t callingPid) : callingPid_(callingPid) {}\n'),
)
REPLACEMENTS[UNMARSHAL] = (
    ('const std::shared_ptr<AppExecFwk::AppMgrClient> GetAppMgrClient()\n',
     NO_WAIT_PERMIT + 'const std::shared_ptr<AppExecFwk::AppMgrClient> GetAppMgrClient()\n'),
    ('    RSTaskMessage::RSTask task = [this, parcel = parcel, isPendingUnmarshal, isNonSystemAppCalling, callingPid,\n'
     '        ashmemFdWorker = std::shared_ptr(std::move(ashmemFdWorker)), ashmemFlowControlUnit, parcelNumber]() {\n',
     '    // Register before publication; each non-wait task owns exactly one permit.\n'
     '    auto noWaitPermit = waitUnmarshalling ? nullptr : std::make_shared<NoWaitTaskPermit>(noNeedWaitTaskNum_);\n'
     '    RSTaskMessage::RSTask task = [this, parcel = parcel, isPendingUnmarshal, isNonSystemAppCalling, callingPid,\n'
     '        ashmemFdWorker = std::shared_ptr(std::move(ashmemFdWorker)), ashmemFlowControlUnit, parcelNumber,\n'
     '        noWaitPermit]() {\n'
     '        NoWaitTaskCompletion complete(noWaitPermit);\n'),
    ('        AshmemFdContainer::SetIsUnmarshalThread(true);\n'
     '        if (ashmemFdWorker) {\n            ashmemFdWorker->PushFdsToContainer();\n        }\n',
     '        AshmemFdContainerScope fdScope(ashmemFdWorker.get());\n'),
    ('        if (noNeedWaitTaskNum_ > 0) {\n            noNeedWaitTaskNum_--;\n        }\n', ''),
    ('    if (!waitUnmarshalling) {\n        noNeedWaitTaskNum_++;\n    }\n', ''),
)

DELEGATE_REGISTRATION = '''            // pid/tid are routing metadata, never authority to change the caller.
            const pid_t listenerCaller = GetCallingPid();
            if ((option.GetFlags() & MessageOption::TF_ASYNC) != 0 || listenerCaller <= 0 ||
                pid != listenerCaller || tid == 0 || tid > INT32_MAX ||
                (listenerId >> 48) != (static_cast<uint64_t>(listenerCaller) & 0xFFFF)) {
                return ERR_INVALID_STATE;
            }
'''
REPLACEMENTS[FILE] += (
    ('            sptr<RSISurfaceTransactionListener> listener = iface_cast<RSISurfaceTransactionListener>(listenerObject);\n',
     DELEGATE_REGISTRATION +
     '            sptr<RSISurfaceTransactionListener> listener = iface_cast<RSISurfaceTransactionListener>(listenerObject);\n'),
)
REPLACEMENTS[DELEGATE] = (
    ('        if (cmd) {\n            cmd->Process(context);\n',
     '        if (cmd && cmd->IsCallingPidValid()) {\n            cmd->Process(context);\n'),
    ('        if (!command) {\n            continue;\n        }\n'
     '        command->SetCallingPidValid(true);\n',
     '        // A delegate listener is not a privilege or node-ownership grant.\n'
     '        if (!command || !command->IsCallingPidValid()) {\n'
     '            ++it;\n            continue;\n        }\n'),
)
FREEZE_SCREEN_PARENT = '''        auto screenNode = displayNode == nullptr ? nullptr :
            RSBaseRenderNode::ReinterpretCast<RSScreenRenderNode>(displayNode->GetParent().lock());
'''
REPLACEMENTS[PIPELINE] += (
    ('        auto screenNode = displayNode == nullptr ? nullptr :\n'
     '            std::static_pointer_cast<RSScreenRenderNode>(displayNode->GetParent().lock());\n',
     FREEZE_SCREEN_PARENT),
)

COMMIT_PAYLOAD_SCOPE = '''// Receiver-observed size, not an application-supplied accounting field.
class RSScopedCommitPayloadSize final {
public:
    explicit RSScopedCommitPayloadSize(size_t bytes) : previous_(Current())
    {
        Current() = bytes;
    }
    ~RSScopedCommitPayloadSize()
    {
        Current() = previous_;
    }
    RSScopedCommitPayloadSize(const RSScopedCommitPayloadSize&) = delete;
    RSScopedCommitPayloadSize& operator=(const RSScopedCommitPayloadSize&) = delete;
    static size_t Get()
    {
        return Current();
    }

private:
    static size_t& Current()
    {
        static thread_local size_t bytes = 0;
        return bytes;
    }
    const size_t previous_;
};

'''
COMMIT_QUEUE_BUDGET = '''// Bound only the newly introduced main-thread commit queue. Byte accounting
// measures receiver-observed serialized data, not every heap object in RS.
constexpr size_t COMMIT_QUEUE_COUNT_LIMIT = 512;
constexpr size_t COMMIT_PID_COUNT_LIMIT = 128;
constexpr size_t COMMIT_QUEUE_BYTES_LIMIT = 256 * 1024 * 1024;
constexpr size_t COMMIT_PID_BYTES_LIMIT = 64 * 1024 * 1024;
constexpr size_t COMMIT_INTERNAL_SIZE_CHARGE = 4 * 1024 * 1024;

class RSCommitQueueBudget final {
public:
    static std::shared_ptr<RSCommitQueueBudget> Instance()
    {
        static auto budget = std::make_shared<RSCommitQueueBudget>();
        return budget;
    }
    bool Acquire(pid_t pid, size_t bytes)
    {
        if (pid <= 0 || bytes > COMMIT_PID_BYTES_LIMIT) {
            return false;
        }
        std::lock_guard<std::mutex> lock(mutex_);
        if (count_ >= COMMIT_QUEUE_COUNT_LIMIT || bytes > COMMIT_QUEUE_BYTES_LIMIT - bytes_) {
            return false;
        }
        auto it = usage_.find(pid);
        if (it != usage_.end() && (it->second.count >= COMMIT_PID_COUNT_LIMIT ||
            bytes > COMMIT_PID_BYTES_LIMIT - it->second.bytes)) {
            return false;
        }
        auto& usage = usage_[pid];
        ++usage.count;
        usage.bytes += bytes;
        ++count_;
        bytes_ += bytes;
        return true;
    }
    void Release(pid_t pid, size_t bytes)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = usage_.find(pid);
        if (it == usage_.end()) {
            return;
        }
        --it->second.count;
        it->second.bytes -= bytes;
        --count_;
        bytes_ -= bytes;
        if (it->second.count == 0) {
            usage_.erase(it);
        }
    }

private:
    struct Usage { size_t count = 0; size_t bytes = 0; };
    std::mutex mutex_;
    std::unordered_map<pid_t, Usage> usage_;
    size_t count_ = 0;
    size_t bytes_ = 0;
};

class RSCommitQueuePermit final {
public:
    static std::shared_ptr<RSCommitQueuePermit> Create(pid_t pid, size_t bytes)
    {
        // No decoded-transaction or public IPC class layout is changed.
        bytes = bytes == 0 ? COMMIT_INTERNAL_SIZE_CHARGE : bytes;
        auto budget = RSCommitQueueBudget::Instance();
        auto permit = std::make_shared<RSCommitQueuePermit>(pid, bytes, budget);
        if (!budget->Acquire(pid, bytes)) {
            return nullptr;
        }
        permit->pending_.store(true);
        return permit;
    }
    RSCommitQueuePermit(pid_t pid, size_t bytes, std::shared_ptr<RSCommitQueueBudget> budget)
        : pid_(pid), bytes_(bytes), budget_(std::move(budget)) {}
    ~RSCommitQueuePermit()
    {
        Complete();
    }
    void Complete()
    {
        if (pending_.exchange(false)) {
            budget_->Release(pid_, bytes_);
        }
    }

private:
    const pid_t pid_;
    const size_t bytes_;
    // A queued permit retains the budget even during static shutdown.
    const std::shared_ptr<RSCommitQueueBudget> budget_;
    std::atomic<bool> pending_ { false };
};

class RSCommitQueueCompletion final {
public:
    explicit RSCommitQueueCompletion(std::shared_ptr<RSCommitQueuePermit> permit) : permit_(std::move(permit)) {}
    ~RSCommitQueueCompletion()
    {
        permit_->Complete();
    }

private:
    const std::shared_ptr<RSCommitQueuePermit> permit_;
};

bool PostBoundedCommit(RSMainThread* mainThread, const std::shared_ptr<RSRenderPipeline>& pipeline,
    std::unique_ptr<RSTransactionData>& transactionData, const std::shared_ptr<RSCommitQueuePermit>& permit)
{
    auto task = [mainThread, pipeline, transaction = std::move(transactionData), permit]() mutable {
        RSCommitQueueCompletion complete(permit);
        // Do not leave an input alive in a producer-retained scheduled closure.
        auto data = std::move(transaction);
        // Retain the pipeline that owns this main-thread endpoint.
        (void)pipeline;
        if (mainThread == nullptr || data == nullptr) {
            return;
        }
#ifndef ROSEN_CROSS_PLATFORM
        RsDelegateCompositeCallbackManager::GetInstance().PrepareDelegateCompositeCommand(data);
#endif
        if (data->GetDVSyncUpdate()) {
            mainThread->DVSyncUpdate(data->GetDVSyncTime(), data->GetTimestamp());
        }
        if (mainThread->IsNeedProcessBySingleFrameComposer(data)) {
            mainThread->ProcessDataBySingleFrameComposer(data);
        } else {
            mainThread->RecvRSTransactionData(data);
        }
    };
    auto [scheduledTask, taskFuture] = ST::ScheduledTask<decltype(task)>::Create(std::move(task));
    (void)taskFuture;
    return mainThread != nullptr && mainThread->TryPostTask([task = std::move(scheduledTask)]() { task->Run(); });
}

'''
BOUNDED_COMMIT_SUBMIT = '''    auto permit = RSCommitQueuePermit::Create(callingPid, RSScopedCommitPayloadSize::Get());
    if (!permit) {
        RS_LOGW("CommitTransaction main-thread queue quota exceeded");
        return ERR_INVALID_STATE;
    }
    if (!PostBoundedCommit(pipeline->GetMainThread(), pipeline, transactionData, permit)) {
        return ERR_INVALID_STATE;
    }
'''
TRY_POST_TASK = '''bool RSMainThread::TryPostTask(RSTaskMessage::RSTask task)
{
    return handler_ && handler_->PostTask(std::move(task), AppExecFwk::EventQueue::Priority::IMMEDIATE);
}

'''
REPLACEMENTS[HEADER] += (
    ('#include <unordered_set>\n', '#include <cstddef>\n#include <unordered_set>\n'),
    ('class RSClientToRenderConnectionStub :', COMMIT_PAYLOAD_SCOPE + 'class RSClientToRenderConnectionStub :'),
)
REPLACEMENTS[FILE] += (
    ('\n                    ret = CommitTransaction(transactionData);\n',
     '\n                    const RSScopedCommitPayloadSize payloadSize(data.GetDataSize());\n'
     '                    ret = CommitTransaction(transactionData);\n'),
    ('\n                ret = CommitTransaction(transactionData);\n',
     '\n                const RSScopedCommitPayloadSize payloadSize(parsedParcel->GetDataSize());\n'
     '                ret = CommitTransaction(transactionData);\n'),
)
REPLACEMENTS[PIPELINE] += (
    ('#include "rs_render_pipeline_agent.h"\n',
     '#include "rs_render_pipeline_agent.h"\n#include <atomic>\n#include <mutex>\n#include <unordered_map>\n'
     '#include "transaction/zidl/rs_client_to_render_connection_stub.h"\n'),
    ('const std::string UNFREEZE_SCREEN_TASK_NAME = "UNFREEZE_SCREEN_TASK";\n\n',
     'const std::string UNFREEZE_SCREEN_TASK_NAME = "UNFREEZE_SCREEN_TASK";\n\n' + COMMIT_QUEUE_BUDGET),
    ('#ifndef ROSEN_CROSS_PLATFORM\n'
     '    RsDelegateCompositeCallbackManager::GetInstance().PrepareDelegateCompositeCommand(transactionData);\n'
     '#endif\n\n', ''),
    ('ErrCode RSRenderPipelineAgent::CommitTransaction(pid_t callingPid, bool isTokenTypeValid,\n'
     '    bool isNonSystemAppCalling, std::unique_ptr<RSTransactionData>& transactionData)\n'
     '{\n    auto pipeline = rsRenderPipeline_.lock();\n    if (!pipeline) {\n',
     'ErrCode RSRenderPipelineAgent::CommitTransaction(pid_t callingPid, bool isTokenTypeValid,\n'
     '    bool isNonSystemAppCalling, std::unique_ptr<RSTransactionData>& transactionData)\n'
     '{\n    auto pipeline = rsRenderPipeline_.lock();\n'
     '    if (!pipeline || !transactionData || !isTokenTypeValid) {\n'),
    (REPLACEMENTS[PIPELINE][0][1], BOUNDED_COMMIT_SUBMIT),
)
REPLACEMENTS[MAIN_THREAD_HEADER] = (
    ('    void PostTask(RSTaskMessage::RSTask task);\n',
     '    void PostTask(RSTaskMessage::RSTask task);\n    bool TryPostTask(RSTaskMessage::RSTask task);\n'),
)
REPLACEMENTS[MAIN_THREAD] = (
    ('void RSMainThread::PostTask(RSTaskMessage::RSTask task)\n',
     TRY_POST_TASK + 'void RSMainThread::PostTask(RSTaskMessage::RSTask task)\n'),
)


def repaired_source(original, relative=FILE):
    value = original
    for old, new in REPLACEMENTS[relative]:
        if value.count(old) != 1:
            raise ValueError('unexpected pinned RS client connection source structure')
        value = value.replace(old, new)
    return value


FILES = (
    (FILE, 'd3c1790da1042acff629726057e18c19ba5f32efe0e283d2f1352dbcc1977a50', 'a5253aab95399004410d6bee38c8678040f2221c16e794c538084d1b9b254d00'),
    (HEADER, '9e7749ac5b8310b69026c45cc2eb6c029ca27c07eb67167e1fc93543b78f4440', '43a39416b8e2673fb50fcf30affd3273610dbca882157e203226c46cbbb06612'),
    (CONNECTION, '69d19ff515d830a0a877e268207aa397761bf283854f2c83f4195e650935e38a', 'ff0a630a19a82a53dd2915533fde0eab4630d0a99cbbfc11d311265c04dde863'),
    (ASHMEM, 'a1b7cf61507284f1513c1a1c19c047ec011fa6aaeb3d29dde4ac315702edc81a', 'dde9d016ac9f1f3b4a1008016b4ab9c0e707f6160ffe4ea24e180c9f1a612e74'),
    (TRANSACTION, '7ea3ee960b62a948ca826b3cfe38d8c63bd88d8abdf8993e958f661196bd5bfb', '6032bb30c7863c0b8d861d24add0e73f578f752754e88309fa8265921dca3ede'),
    (PIPELINE, 'c112f8bb5af73a6a756abfb24b37c3af3354cf8fee0b1089414644e4900efde6', '7c1cc508d1943899548e54bfe95d33eb4ddb8cb1919e7f0f84ec9e1e6d75fece'),
    (ASHMEM_HEADER, '3908a51a76ce2dacadd79b9e192ef702034a1dc0ed5174201bc9b3d0a3f66510', 'b240f668ad283c6a23b51e3bb923f264b219ee648e439e59a74806d83a227b2a'),
    (UNMARSHAL, 'ed983812f72682a8541e696c205d5c0f7129ce84b753784b81bb6905f83aa026', 'fad87b4eb5c95dfa7bba78cefeca6d7ec48891839357c0684bf13ccc5ef143d7'),
    (DELEGATE, 'b176f428390912aa30861d1c67c2fa62363d92aa56897f1545c79889cbeaf122', 'ff977ddd893964549534b457d2af89cd2640f9ba6e029a625553a031c5f0d56f'),
    (MAIN_THREAD_HEADER, 'f3193e5e0b08cda00ef2e947e3cc54bce297c964c3b5e2a9154ae02bab77ae25', 'c763c63a960446b8a5f79018c87540a454cb25dadb241b93b075db89785b7399'),
    (MAIN_THREAD, 'f5b9571b4753192b26f26976b19d7e7e57f3eb2e5d06a3a03d9353c81ee5a594', 'de3337aa30614ba2ff405098cbde0c5e654325dfe49ff4d6858f08c0f24dfe5b'),
)


# Private object coding is paired with identity/queue hardening in one exact
# stack. A separately ordered component would reject shared-file final states.
import importlib.util as _importlib_util
_object_spec = _importlib_util.spec_from_file_location(
    'rs_private_object_replacements', Path(__file__).with_name('object_encoding_replacements.py'))
_object_repairs = _importlib_util.module_from_spec(_object_spec)
_object_spec.loader.exec_module(_object_repairs)
for _relative, _pairs in _object_repairs.REPLACEMENTS.items():
    REPLACEMENTS[_relative] = REPLACEMENTS.get(_relative, ()) + _pairs
_object_files = {entry[0]: entry for entry in _object_repairs.FILES}
FILES = tuple(_object_files.pop(entry[0], entry) for entry in FILES) + tuple(_object_files.values())


def validate(root, require_patched=False):
    if {entry[0] for entry in FILES} != set(REPLACEMENTS):
        raise ValueError('incomplete RS identity component baseline')
    successor = 'ab3f257b5afb0e96e485948aeeff89affe3a87fe4f65101d1f259b4c48fea3b6'
    successor_files = tuple((entry[0], successor, successor) if entry[0] == FILE else entry
                            for entry in FILES)
    try:
        return validate_component(root, PROJECT, REVISION, successor_files, require_patched=True)
    except ValueError:
        pass
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('RS trusted async commit identity patch present: ' + str(validate(args.source_root, args.require_patched)))


if __name__ == '__main__':
    main()
