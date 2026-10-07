"""Exact source fragments for the paired, private RS Binder-object repair.

This is patch-generation/test input, not an installed runtime module. Object
readers only see the original local/kernel-translated MessageParcel or the
Binder sidecar. No reader receives raw cookies from an ashmem snapshot.
"""

MARSHALLING_HEADER = 'rosen/modules/render_service_base/include/transaction/rs_marshalling_helper.h'
MARSHALLING_SOURCE = 'rosen/modules/render_service_base/src/platform/ohos/rs_marshalling_helper.cpp'
SERVICE_STUB = 'rosen/modules/render_service/main/render_server/transaction/zidl/rs_client_to_service_connection_stub.cpp'

SPTR_TRAIT = '''#ifdef ROSEN_OHOS
    template<typename T>
    struct is_sptr : std::false_type {};

    template<typename T>
    struct is_sptr<sptr<T>> : std::true_type {};
#else
    template<typename T>
    struct is_sptr : std::false_type {};
#endif

'''

SPTR_DECLARATIONS = '''#ifdef ROSEN_OHOS
    // These command arguments are IPC objects, never process-local POD.
    static bool Marshalling(Parcel& parcel, const sptr<IRemoteObject>& object);
    static bool Unmarshalling(Parcel& parcel, sptr<IRemoteObject>& object);
    static bool Marshalling(Parcel& parcel, const sptr<RSIBufferAvailableCallback>& callback);
    static bool Unmarshalling(Parcel& parcel, sptr<RSIBufferAvailableCallback>& callback);
#endif

'''

SPTR_SOURCE = '''bool RSMarshallingHelper::Marshalling(Parcel& parcel, const sptr<IRemoteObject>& object)
{
    return parcel.WriteBool(object != nullptr) &&
        (object == nullptr || static_cast<MessageParcel&>(parcel).WriteRemoteObject(object));
}

bool RSMarshallingHelper::Unmarshalling(Parcel& parcel, sptr<IRemoteObject>& object)
{
    object = nullptr;
    bool present = false;
    if (!parcel.ReadBool(present)) {
        return false;
    }
    if (!present) {
        return true;
    }
    object = static_cast<MessageParcel&>(parcel).ReadRemoteObject();
    return object != nullptr;
}

bool RSMarshallingHelper::Marshalling(Parcel& parcel, const sptr<RSIBufferAvailableCallback>& callback)
{
    const sptr<IRemoteObject> object = callback == nullptr ? nullptr : callback->AsObject();
    if (callback != nullptr && object == nullptr) {
        return false;
    }
    return Marshalling(parcel, object);
}

bool RSMarshallingHelper::Unmarshalling(Parcel& parcel, sptr<RSIBufferAvailableCallback>& callback)
{
    callback = nullptr;
    sptr<IRemoteObject> object;
    if (!Unmarshalling(parcel, object)) {
        return false;
    }
    if (object == nullptr) {
        return true;
    }
    callback = iface_cast<RSIBufferAvailableCallback>(object);
    return callback != nullptr;
}

'''

OBJECT_HELPERS = '''// Versioned private ashmem sidecar: strong Binder objects plus owning FDs.
constexpr uint32_t RS_OBJECT_SIDECAR_VERSION = 0x52534F31;
constexpr uint32_t RS_OBJECT_FD = 1;
constexpr uint32_t RS_OBJECT_REMOTE = 2;

struct RSParcelObjectSlot {
    size_t offset = 0;
    size_t end = 0;
    uint32_t kind = 0;
};

class RSParcelReadPosition final {
public:
    explicit RSParcelReadPosition(MessageParcel& parcel) : parcel_(parcel), position_(parcel.GetReadPosition()) {}
    ~RSParcelReadPosition()
    {
        // The saved position was valid before any read and the source is not modified.
        (void)parcel_.RewindRead(position_);
    }
private:
    MessageParcel& parcel_;
    const size_t position_;
};

bool BuildRSObjectLayout(const MessageParcel& parcel, const binder_size_t* offsets, size_t count,
    std::vector<RSParcelObjectSlot>& slots)
{
    const size_t size = parcel.GetDataSize();
    if (!IsValidAshmemObjectOffsets(offsets, count, size)) {
        return false;
    }
    size_t previousEnd = 0;
    for (size_t index = 0; index < count; ++index) {
        const size_t offset = static_cast<size_t>(offsets[index]);
        if (offset < previousEnd) {
            return false;
        }
        flat_binder_object flat {};
        if (memcpy_s(&flat, sizeof(flat), reinterpret_cast<const void*>(parcel.GetData() + offset),
            sizeof(flat)) != EOK) {
            return false;
        }
        RSParcelObjectSlot slot { offset, offset + sizeof(flat), RS_OBJECT_REMOTE };
        if (flat.hdr.type == BINDER_TYPE_FD || flat.hdr.type == BINDER_TYPE_FDR) {
            slot.kind = RS_OBJECT_FD;
        } else if (flat.hdr.type == BINDER_TYPE_PTR) {
            // DBinder's PTR and its following strong object are one logical
            // object. The buffer/cookie are deliberately never dereferenced here.
            binder_buffer_object buffer {};
            if (sizeof(buffer) > size - offset ||
                memcpy_s(&buffer, sizeof(buffer), reinterpret_cast<const void*>(parcel.GetData() + offset),
                    sizeof(buffer)) != EOK ||
                buffer.flags != BINDER_BUFFER_FLAG_HAS_DBINDER ||
                buffer.length != sizeof(dbinder_negotiation_data) ||
                index + 1 >= count || offsets[index + 1] != offset + sizeof(buffer)) {
                return false;
            }
            const size_t next = static_cast<size_t>(offsets[++index]);
            if (memcpy_s(&flat, sizeof(flat), reinterpret_cast<const void*>(parcel.GetData() + next),
                sizeof(flat)) != EOK ||
                (flat.hdr.type != BINDER_TYPE_BINDER && flat.hdr.type != BINDER_TYPE_HANDLE)) {
                return false;
            }
            slot.end = next + sizeof(flat);
        } else if (flat.hdr.type != BINDER_TYPE_BINDER && flat.hdr.type != BINDER_TYPE_HANDLE) {
            // Weak references, FDA and arbitrary pointer objects are not RS
            // command arguments. Do not acquire anything described by raw bytes.
            return false;
        }
        previousEnd = slot.end;
        slots.push_back(slot);
    }
    return true;
}

bool CopyRSObject(MessageParcel& source, MessageParcel& destination, uint32_t kind)
{
    if (kind == RS_OBJECT_REMOTE) {
        const auto object = source.ReadRemoteObject();
        // WriteRemoteObject owns a real sptr (and any DBinder backing buffer).
        return object != nullptr && destination.WriteRemoteObject(object);
    }
    if (kind != RS_OBJECT_FD) {
        return false;
    }
    const int fd = source.ReadFileDescriptor();
    if (fd < 0) {
        return false;
    }
    const bool written = destination.WriteFileDescriptor(fd);
    // ReadFileDescriptor and WriteFileDescriptor each duplicate: this temporary
    // belongs to neither Parcel, including on the partial-write failure path.
    ::close(fd);
    return written;
}

std::shared_ptr<MessageParcel> RebuildRSObjectParcel(const MessageParcel& snapshot,
    const std::vector<RSParcelObjectSlot>& slots, MessageParcel& objects, bool sidecar)
{
    const size_t size = snapshot.GetDataSize();
    // Re-encoding a local strong object as DBinder can add one buffer descriptor.
    // Bound allocation by the already bounded payload; check before arithmetic.
    if (slots.size() > (SIZE_MAX - size) / sizeof(binder_buffer_object)) {
        return nullptr;
    }
    auto parcel = RS_PROFILER_COPY_PARCEL(snapshot);
    const size_t capacity = size + slots.size() * sizeof(binder_buffer_object);
    if (capacity > parcel->GetMaxCapacity() && !parcel->SetMaxCapacity(capacity)) {
        return nullptr;
    }
    const RSParcelReadPosition restore(objects);
    size_t previousEnd = 0;
    for (const auto& slot : slots) {
        if (slot.offset > previousEnd &&
            !parcel->WriteBuffer(reinterpret_cast<const void*>(snapshot.GetData() + previousEnd),
                slot.offset - previousEnd)) {
            return nullptr;
        }
        uint32_t kind = slot.kind;
        if (sidecar) {
            if (!objects.ReadUint32(kind) || kind != slot.kind) {
                return nullptr;
            }
        } else if (!objects.RewindRead(slot.offset)) {
            return nullptr;
        }
        if (!CopyRSObject(objects, *parcel, kind) || (!sidecar && objects.GetReadPosition() != slot.end)) {
            return nullptr;
        }
        previousEnd = slot.end;
    }
    if (sidecar && objects.GetReadableBytes() != 0) {
        return nullptr;
    }
    if (size > previousEnd &&
        !parcel->WriteBuffer(reinterpret_cast<const void*>(snapshot.GetData() + previousEnd), size - previousEnd)) {
        return nullptr;
    }
    return parcel;
}

bool RestoreRSObjectSidecar(std::shared_ptr<MessageParcel>& snapshot, MessageParcel& sidecar)
{
    int32_t count = 0;
    uint32_t version = 0;
    if (!sidecar.ReadInt32(count) || count < 0 ||
        !sidecar.ReadUint32(version) || version != RS_OBJECT_SIDECAR_VERSION ||
        static_cast<size_t>(count) > sidecar.GetReadableBytes() / sizeof(binder_size_t) ||
        static_cast<size_t>(count) > snapshot->GetDataSize() / sizeof(flat_binder_object)) {
        return false;
    }
    std::vector<binder_size_t> offsets(static_cast<size_t>(count));
    if (count > 0) {
        const size_t bytes = offsets.size() * sizeof(binder_size_t);
        const auto* raw = sidecar.ReadBuffer(bytes);
        if (raw == nullptr || memcpy_s(offsets.data(), bytes, raw, bytes) != EOK) {
            return false;
        }
    }
    std::vector<RSParcelObjectSlot> slots;
    if (!BuildRSObjectLayout(*snapshot, offsets.data(), offsets.size(), slots)) {
        return false;
    }
    auto parcel = RebuildRSObjectParcel(*snapshot, slots, sidecar, true);
    if (parcel == nullptr) {
        return false;
    }
    // The discarded snapshot never had object offsets: no raw cookie or FD is
    // published even during failure cleanup. Only standard writers add offsets.
    snapshot = std::move(parcel);
    return true;
}

'''

COPY_TRANSACTION = '''std::shared_ptr<MessageParcel> RSAshmemHelper::CopyTransactionParcel(MessageParcel& source)
{
    const auto* offsets = reinterpret_cast<const binder_size_t*>(source.GetObjectOffsets());
    std::vector<RSParcelObjectSlot> slots;
    if (!BuildRSObjectLayout(source, offsets, source.GetOffsetsSize(), slots)) {
        return nullptr;
    }
    return RebuildRSObjectParcel(source, slots, source, false);
}

'''

CREATE_SIDECAR = '''    // The shared bytes are payload only. Every descriptor/object travels in
    // the outer Binder transaction and is decoded while that transaction lives.
    const auto* offsets = reinterpret_cast<const binder_size_t*>(dataParcel->GetObjectOffsets());
    const size_t count = dataParcel->GetOffsetsSize();
    std::vector<RSParcelObjectSlot> slots;
    if (count > INT32_MAX || !BuildRSObjectLayout(*dataParcel, offsets, count, slots) ||
        !ashmemParcel->WriteInt32(static_cast<int32_t>(count)) ||
        !ashmemParcel->WriteUint32(RS_OBJECT_SIDECAR_VERSION) ||
        (count > 0 && !ashmemParcel->WriteBuffer(offsets, count * sizeof(binder_size_t)))) {
        return nullptr;
    }
    const RSParcelReadPosition restore(*dataParcel);
    for (const auto& slot : slots) {
        if (!dataParcel->RewindRead(slot.offset) || !ashmemParcel->WriteUint32(slot.kind) ||
            !CopyRSObject(*dataParcel, *ashmemParcel, slot.kind) || dataParcel->GetReadPosition() != slot.end) {
            return nullptr;
        }
    }
'''
