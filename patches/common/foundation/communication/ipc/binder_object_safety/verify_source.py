#!/usr/bin/env python3
"""Preserve four-byte Binder object alignment without unaligned typed access."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/ipc'
REVISION = 'b8d3e96cfcf382c8fae54502679ac8b3d827b428'
INVOKER = 'ipc/native/src/core/invoker/source/binder_invoker.cpp'
PARCEL = 'ipc/native/src/core/framework/source/message_parcel.cpp'
ALIGNED_OBJECT = '''    flat_binder_object alignedObject {};
    if (memcpy_s(&alignedObject, sizeof(alignedObject), buffer, sizeof(alignedObject)) != EOK) {
        return RETURN_VALUE;
    }
    const auto* flat = &alignedObject;
'''
CLEAR_FDS = '''void MessageParcel::ClearFileDescriptor()
{
    const auto* objects = reinterpret_cast<const binder_size_t*>(GetObjectOffsets());
    if (objects == nullptr || GetData() == 0) {
        return;
    }
    for (size_t i = 0; i < GetOffsetsSize(); ++i) {
        const binder_size_t offset = objects[i];
        if (offset > GetDataSize() || sizeof(flat_binder_object) > GetDataSize() - offset) {
            ZLOGE(LOG_LABEL, "object offset is outside parcel data");
            break;
        }
        flat_binder_object flat {};
        if (memcpy_s(&flat, sizeof(flat), reinterpret_cast<const void*>(GetData() + offset), sizeof(flat)) != EOK) {
            break;
        }
        const int32_t fd = static_cast<int32_t>(flat.handle);
        if (flat.hdr.type == BINDER_TYPE_FD && fd >= 0) {
            ::close(fd);
        }
    }
}
'''
CONTAINS_FDS = '''bool MessageParcel::ContainFileDescriptors() const
{
    const auto* objects = reinterpret_cast<const binder_size_t*>(GetObjectOffsets());
    if (objects == nullptr || GetData() == 0) {
        return false;
    }
    for (size_t i = 0; i < GetOffsetsSize(); ++i) {
        const binder_size_t offset = objects[i];
        if (offset > GetDataSize() || sizeof(flat_binder_object) > GetDataSize() - offset) {
            ZLOGE(LOG_LABEL, "object offset is outside parcel data");
            break;
        }
        flat_binder_object flat {};
        if (memcpy_s(&flat, sizeof(flat), reinterpret_cast<const void*>(GetData() + offset), sizeof(flat)) != EOK) {
            break;
        }
        if (flat.hdr.type == BINDER_TYPE_FD) {
            return true;
        }
    }
    return false;
}
'''
DELIVERED_FDS = '''// Only kernel-delivered transactions may enter this helper. Ordinary FD
// objects belong to userspace; FDA arrays are closed by BC_FREE_BUFFER in the
// kernel, and FDR is not a Linux Binder object type.
static void CloseDeliveredFileDescriptors(const binder_transaction_data& transaction)
{
    const size_t dataSize = static_cast<size_t>(transaction.data_size);
    const size_t offsetsBytes = static_cast<size_t>(transaction.offsets_size);
    const uintptr_t data = static_cast<uintptr_t>(transaction.data.ptr.buffer);
    const uintptr_t offsets = static_cast<uintptr_t>(transaction.data.ptr.offsets);
    if (dataSize != transaction.data_size || offsetsBytes != transaction.offsets_size ||
        data != transaction.data.ptr.buffer || offsets != transaction.data.ptr.offsets ||
        data == 0 || offsets == 0 || offsetsBytes % sizeof(binder_size_t) != 0 ||
        dataSize > UINTPTR_MAX - data || offsetsBytes > UINTPTR_MAX - offsets) {
        return;
    }
    const size_t count = offsetsBytes / sizeof(binder_size_t);
    if (count > dataSize / sizeof(binder_object_header)) {
        return;
    }
    for (size_t i = 0; i < count; ++i) {
        binder_size_t offset = 0;
        if (memcpy_s(&offset, sizeof(offset), reinterpret_cast<const void*>(
            offsets + i * sizeof(offset)), sizeof(offset)) != EOK || offset > dataSize ||
            sizeof(flat_binder_object) > dataSize - static_cast<size_t>(offset)) {
            continue;
        }
        flat_binder_object object {};
        if (memcpy_s(&object, sizeof(object), reinterpret_cast<const void*>(data + offset),
            sizeof(object)) != EOK) {
            continue;
        }
        const int32_t fd = static_cast<int32_t>(object.handle);
        if (object.hdr.type == BINDER_TYPE_FD && fd >= 0) {
            ::close(fd);
        }
    }
}

'''

PARCEL_RESOURCE_REPLACEMENTS = (
    ('    if (readRawDataFd_ > 0) {\n', '    if (readRawDataFd_ >= 0) {\n'),
    ('    if (writeRawDataFd_ > 0) {\n', '    if (writeRawDataFd_ >= 0) {\n'),
    ('    writeRawDataFd_ = 0;\n',
     '    // A negative state marker cannot be confused with an owned FD 0.\n'
     '    writeRawDataFd_ = REMOTE_RAW_DATA_FD;\n'),
    ('    /* if rawDataFd_ == 0 means rawData is received from remote */\n'
     '    if (rawData_ != nullptr && writeRawDataFd_ == 0) {\n',
     '    /* REMOTE_RAW_DATA_FD means rawData is received from remote. */\n'
     '    if (rawData_ != nullptr && writeRawDataFd_ == REMOTE_RAW_DATA_FD) {\n'),
    ('    return new (std::nothrow) Ashmem(fd, size);\n',
     '    sptr<Ashmem> ashmem = new (std::nothrow) Ashmem(fd, size);\n'
     '    if (ashmem == nullptr) {\n        ::close(fd);\n    }\n'
     '    return ashmem;\n'),
)


def repair_failure_resources(value, relative):
    if relative == INVOKER:
        anchor = '#ifndef CONFIG_IPC_SINGLE\nstatic constexpr pid_t INVALID_PID = -1;\n'
        value = value.replace(anchor, DELIVERED_FDS + anchor)
        old = '        ZLOGE(LABEL, "BinderAllocator Creation failed");\n        return;\n'
        new = ('        ZLOGE(LABEL, "BinderAllocator Creation failed");\n'
               '        CloseDeliveredFileDescriptors(tr);\n'
               '        FreeBuffer(reinterpret_cast<void*>(tr.data.ptr.buffer));\n        return;\n')
        if value.count(old) != 1 or value.count(DELIVERED_FDS) != 1:
            raise ValueError('unknown Binder transaction failure structure')
        value = value.replace(old, new)
        start = value.index('int BinderInvoker::HandleReply(MessageParcel *reply, bool &isStubRet)\n')
        end = value.index('int BinderInvoker::HandleCommandsInner(', start)
        section = value[start:end]
        old_release = '        FreeBuffer(reinterpret_cast<void *>(tr->data.ptr.buffer));\n'
        if section.count(old_release) != 4:
            raise ValueError('unknown Binder reply failure structure')
        section = section.replace(old_release, '        CloseDeliveredFileDescriptors(*tr);\n' + old_release)
        old = '    const binder_transaction_data *tr = reinterpret_cast<const binder_transaction_data *>(buffer);\n'
        new = ('    binder_transaction_data alignedTransaction {};\n'
               '    if (memcpy_s(&alignedTransaction, sizeof(alignedTransaction), buffer, readSize) != EOK) {\n'
               '        return IPC_INVOKER_INVALID_DATA_ERR;\n    }\n'
               '    const binder_transaction_data *tr = &alignedTransaction;\n')
        if section.count(old) != 1:
            raise ValueError('unknown Binder reply metadata reader')
        section = section.replace(old, new)
        return value[:start] + section + value[end:]
    if relative == PARCEL:
        anchor = 'void AcquireObject(flat_binder_object *flat, const void *cookie)\n'
        if value.count(anchor) != 1:
            raise ValueError('unknown Parcel namespace structure')
        value = value.replace(anchor, 'static constexpr int REMOTE_RAW_DATA_FD = -2;\n\n' + anchor)
        for old, new in PARCEL_RESOURCE_REPLACEMENTS:
            if value.count(old) != 1:
                raise ValueError('unknown Parcel resource failure structure')
            value = value.replace(old, new)
        return value
    raise ValueError('unknown IPC resource source')

# These are the two direct object-reading paths used when RS unmarshals its
# receiver-private snapshot. Token/cookie/object-registry checks remain intact.
def repaired_source(original, relative):
    if relative == INVOKER:
        old = '    auto *flat = reinterpret_cast<const flat_binder_object *>(buffer);\n'
        if original.count(old) != 2:
            raise ValueError('unknown pinned Binder object reader structure')
        value = original.replace(old, ALIGNED_OBJECT.replace('RETURN_VALUE', 'nullptr'), 1)
        value = value.replace(old, ALIGNED_OBJECT.replace('RETURN_VALUE', 'fd'), 1)
        return repair_failure_resources(value, relative)
    if relative == PARCEL:
        start = original.index('void MessageParcel::ClearFileDescriptor()\n')
        end = original.index('bool MessageParcel::WriteInterfaceToken(', start)
        section = original[start:end]
        if section.count('reinterpret_cast<flat_binder_object *>') != 2:
            raise ValueError('unknown pinned Parcel FD cleanup structure')
        value = original[:start] + CLEAR_FDS + '\n' + CONTAINS_FDS + '\n' + original[end:]
        return repair_failure_resources(value, relative)
    raise ValueError('unknown IPC object safety source')


FILES = (
    (INVOKER, '37165e4b4511ccadac7c80b9de88769ddccac4eb6242adb4b785ccb5a49e2704', '93e2d90d24e1ccd419290bea666782ffaa77538968197c8cab9ecce4f004d3e0'),
    (PARCEL, '2f4d216c9a54534840b8c6ac7d81b9627fd9271bd9009b5289eb9a6ee0ce6349', '9bc8e467a30f809007e7545256439070a36c1f4c956f96416a66efde633c0eac'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('Binder object safety patch present: ' + str(validate(args.source_root, args.require_patched)))


if __name__ == '__main__':
    main()
