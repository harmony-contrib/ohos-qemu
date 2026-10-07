"""Actual RS repair fragments with owning fixtures and OS FDs, not guest Binder acceptance."""
import importlib.util
from pathlib import Path
import unittest

from test_rs_transaction_validation import RS, run_sanitized

COMPONENT = Path(__file__).resolve().parents[2] / 'patches/common/foundation/graphic/graphic_2d/async_caller_identity'
SPEC = importlib.util.spec_from_file_location('tested_rs_object_encoding', COMPONENT / 'object_encoding.py')
OBJ = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBJ)

PREFIX = r'''#include <cassert>
#include <climits>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <functional>
#include <map>
#include <memory>
#include <thread>
#include <unistd.h>
#include <sys/wait.h>
#include <vector>
using binder_size_t=uint64_t;
enum : uint32_t { BINDER_TYPE_FD=1, BINDER_TYPE_FDR=2, BINDER_TYPE_BINDER=3,
    BINDER_TYPE_HANDLE=4, BINDER_TYPE_PTR=5, BINDER_TYPE_WEAK_HANDLE=6 };
constexpr uint32_t BINDER_BUFFER_FLAG_HAS_DBINDER=uint32_t(1)<<31;
struct binder_object_header { uint32_t type; };
struct flat_binder_object {
    binder_object_header hdr; uint32_t flags;
    union { uint64_t binder; uint32_t handle; }; uint64_t cookie;
};
struct binder_buffer_object {
    binder_object_header hdr; uint32_t flags; uint64_t buffer,length,parent,parent_offset;
};
struct dbinder_negotiation_data { unsigned char data[600]; };
static_assert(sizeof(flat_binder_object)==24 && sizeof(binder_buffer_object)==40);
constexpr int EOK=0;
int memcpy_s(void* out,size_t capacity,const void* in,size_t size) {
    if(size>capacity) return -1;
    std::memcpy(out,in,size);return EOK;
}
template<typename T> using sptr=std::shared_ptr<T>;
struct IRemoteObject { virtual ~IRemoteObject()=default; bool dbinder=false; };
struct RSIBufferAvailableCallback : IRemoteObject, std::enable_shared_from_this<RSIBufferAvailableCallback> {
    unsigned calls=0;
    sptr<IRemoteObject> AsObject() { return shared_from_this(); }
    void OnBufferAvailable() { ++calls; }
};
template<typename T> sptr<T> iface_cast(const sptr<IRemoteObject>& object) {
    return std::dynamic_pointer_cast<T>(object);
}
static int failWriteObject=-1, writeObjects=0;
static std::vector<int> allDuplicates;
bool Closed(int fd) { return fcntl(fd,F_GETFD)==-1; }
struct MessageParcel {
    std::vector<unsigned char> bytes;
    std::vector<binder_size_t> offsets;
    std::map<size_t,sptr<IRemoteObject>> remotes;
    std::vector<int> ownedFds;
    size_t read=0, capacity=200*1024;
    ~MessageParcel() { for(int fd:ownedFds) ::close(fd); }
    uintptr_t GetData() const { return reinterpret_cast<uintptr_t>(bytes.data()); }
    size_t GetDataSize() const { return bytes.size(); }
    size_t GetOffsetsSize() const { return offsets.size(); }
    uintptr_t GetObjectOffsets() const { return reinterpret_cast<uintptr_t>(offsets.data()); }
    size_t GetReadableBytes() const { return bytes.size()-read; }
    size_t GetReadPosition() const { return read; }
    size_t GetMaxCapacity() const { return capacity; }
    bool SetMaxCapacity(size_t value) { if(value<=capacity) return false;capacity=value;return true; }
    bool RewindRead(size_t pos) { if(pos>bytes.size())return false;read=pos;return true; }
    bool WriteBuffer(const void* data,size_t size) {
        if(!data || !size || size>capacity-bytes.size())return false;
        const auto* start=static_cast<const unsigned char*>(data);
        bytes.insert(bytes.end(),start,start+size);return true;
    }
    const unsigned char* ReadBuffer(size_t size) {
        if(size>GetReadableBytes())return nullptr;
        auto* result=bytes.data()+read;read+=size;return result;
    }
    bool WriteUint32(uint32_t value) { return WriteBuffer(&value,sizeof(value)); }
    bool WriteInt32(int32_t value) { return WriteBuffer(&value,sizeof(value)); }
    bool ReadUint32(uint32_t& value) {
        auto* data=ReadBuffer(sizeof(value));if(!data)return false;std::memcpy(&value,data,sizeof(value));return true;
    }
    bool ReadInt32(int32_t& value) {
        auto* data=ReadBuffer(sizeof(value));if(!data)return false;std::memcpy(&value,data,sizeof(value));return true;
    }
    bool WriteBool(bool value) { return WriteInt32(value); }
    bool ReadBool(bool& value) { int32_t raw=0;if(!ReadInt32(raw))return false;value=raw!=0;return true; }
    bool WriteRemoteObject(const sptr<IRemoteObject>& object) {
        if(!object || ++writeObjects==failWriteObject)return false;
        const size_t offset=bytes.size();
        if(object->dbinder) {
            binder_buffer_object ptr {};
            ptr.hdr.type=BINDER_TYPE_PTR;ptr.flags=BINDER_BUFFER_FLAG_HAS_DBINDER;
            ptr.buffer=reinterpret_cast<uintptr_t>(object.get());ptr.length=sizeof(dbinder_negotiation_data);
            if(!WriteBuffer(&ptr,sizeof(ptr)))return false;
            offsets.push_back(offset);
        }
        flat_binder_object flat {};
        flat.hdr.type=BINDER_TYPE_BINDER;flat.cookie=reinterpret_cast<uintptr_t>(object.get());
        const size_t strong=bytes.size();
        if(!WriteBuffer(&flat,sizeof(flat)))return false;
        offsets.push_back(strong);remotes[offset]=object;return true;
    }
    sptr<IRemoteObject> ReadRemoteObject() {
        auto found=remotes.find(read);if(found==remotes.end())return nullptr;
        flat_binder_object flat {};
        if(bytes.size()-read<sizeof(flat))return nullptr;
        std::memcpy(&flat,bytes.data()+read,sizeof(flat));
        read+=flat.hdr.type==BINDER_TYPE_PTR?sizeof(binder_buffer_object)+sizeof(flat):sizeof(flat);
        if(read>bytes.size())return nullptr;
        return found->second;
    }
    bool WriteFileDescriptor(int source) {
        if(source<0 || ++writeObjects==failWriteObject)return false;
        const int fd=dup(source);if(fd<0)return false;allDuplicates.push_back(fd);
        flat_binder_object flat {};flat.hdr.type=BINDER_TYPE_FD;flat.handle=fd;flat.cookie=1;
        const size_t offset=bytes.size();
        if(!WriteBuffer(&flat,sizeof(flat))) { close(fd);return false; }
        offsets.push_back(offset);ownedFds.push_back(fd);return true;
    }
    int ReadFileDescriptor() {
        bool found=false;for(size_t offset:offsets)found|=offset==read;
        if(!found || bytes.size()-read<sizeof(flat_binder_object))return -1;
        flat_binder_object flat {};std::memcpy(&flat,bytes.data()+read,sizeof(flat));read+=sizeof(flat);
        if(flat.hdr.type!=BINDER_TYPE_FD && flat.hdr.type!=BINDER_TYPE_FDR)return -1;
        const int fd=dup(static_cast<int32_t>(flat.handle));if(fd>=0)allDuplicates.push_back(fd);return fd;
    }
};
using Parcel=MessageParcel;
#define RS_PROFILER_COPY_PARCEL(snapshot) std::make_shared<MessageParcel>()
struct RSAshmemHelper {
    static std::shared_ptr<MessageParcel> CopyTransactionParcel(MessageParcel& source);
};
struct RSMarshallingHelper {
    static bool Marshalling(Parcel&,const sptr<IRemoteObject>&);
    static bool Unmarshalling(Parcel&,sptr<IRemoteObject>&);
    static bool Marshalling(Parcel&,const sptr<RSIBufferAvailableCallback>&);
    static bool Unmarshalling(Parcel&,sptr<RSIBufferAvailableCallback>&);
};
'''

FIXTURES = r'''
std::shared_ptr<MessageParcel> MakeSidecar(std::shared_ptr<MessageParcel>& dataParcel) {
    auto ashmemParcel=std::make_shared<MessageParcel>();
'''+OBJ.CREATE_SIDECAR+r'''
    return ashmemParcel;
}
std::shared_ptr<MessageParcel> Snapshot(const MessageParcel& source) {
    auto result=std::make_shared<MessageParcel>();result->bytes=source.bytes;return result;
}
std::shared_ptr<MessageParcel> Mixed(int fd,sptr<IRemoteObject> first,sptr<IRemoteObject> second) {
    auto source=std::make_shared<MessageParcel>();
    assert(source->WriteUint32(101) && source->WriteRemoteObject(first) && source->WriteUint32(202));
    assert(source->WriteFileDescriptor(fd) && source->WriteUint32(303));
    assert(source->WriteRemoteObject(second) && source->WriteFileDescriptor(fd) && source->WriteUint32(404));
    // The private FDR form must be treated as an FD, not discarded or borrowed.
    auto* last=source->bytes.data()+source->offsets.back();uint32_t type=BINDER_TYPE_FDR;
    std::memcpy(last,&type,sizeof(type));return source;
}
void CheckMixed(MessageParcel& parcel,const sptr<IRemoteObject>& first,const sptr<IRemoteObject>& second) {
    assert(parcel.RewindRead(0));uint32_t word=0;
    assert(parcel.ReadUint32(word) && word==101 && parcel.ReadRemoteObject()==first);
    assert(parcel.ReadUint32(word) && word==202);
    int fd=parcel.ReadFileDescriptor();assert(fd>=0 && !Closed(fd));close(fd);
    assert(parcel.ReadUint32(word) && word==303 && parcel.ReadRemoteObject()==second);
    fd=parcel.ReadFileDescriptor();assert(fd>=0 && !Closed(fd));close(fd);
    assert(parcel.ReadUint32(word) && word==404 && parcel.GetReadableBytes()==0);
}
'''


def source(main, with_sptr=False):
    return (PREFIX + RS.OFFSETS_VALIDATION + OBJ.OBJECT_HELPERS + OBJ.COPY_TRANSACTION
            + (OBJ.SPTR_SOURCE if with_sptr else '') + FIXTURES + main)


class RsObjectEncodingTests(unittest.TestCase):
    def test_standard_sptr_overloads_roundtrip_null_type_errors_and_lifetime(self):
        main = r'''int main() {
    auto callback=std::make_shared<RSIBufferAvailableCallback>();
    std::weak_ptr<IRemoteObject> weak=callback;
    MessageParcel parcel;
    assert(RSMarshallingHelper::Marshalling(parcel,callback));
    assert(parcel.GetOffsetsSize()==1 && parcel.GetDataSize()==4+sizeof(flat_binder_object));
    callback.reset();assert(!weak.expired());
    sptr<RSIBufferAvailableCallback> result;
    assert(RSMarshallingHelper::Unmarshalling(parcel,result) && result);
    result->OnBufferAvailable();assert(result->calls==1);
    MessageParcel null;sptr<IRemoteObject> empty;
    assert(RSMarshallingHelper::Marshalling(null,empty) && null.offsets.empty());
    sptr<IRemoteObject> stale=std::make_shared<IRemoteObject>();
    assert(RSMarshallingHelper::Unmarshalling(null,stale) && !stale);
    MessageParcel missing;assert(!RSMarshallingHelper::Unmarshalling(missing,result) && !result);
    MessageParcel invalid;assert(invalid.WriteBool(true));
    assert(!RSMarshallingHelper::Unmarshalling(invalid,stale) && !stale);
    MessageParcel wrong;auto other=std::make_shared<IRemoteObject>();
    assert(RSMarshallingHelper::Marshalling(wrong,other));
    assert(!RSMarshallingHelper::Unmarshalling(wrong,result) && !result);
    writeObjects=0;failWriteObject=1;MessageParcel failure;
    assert(!RSMarshallingHelper::Marshalling(failure,other));
}
'''
        run_sanitized(source(main, with_sptr=True))

    def test_normal_and_ashmem_keep_real_objects_through_request_return_and_cancel(self):
        main = r'''int main() {
    const int fd=open("/dev/null",O_RDONLY);assert(fd>=0);
    for(unsigned mode=0;mode<2;++mode) for(unsigned round=0;round<128;++round) {
        auto first=std::make_shared<IRemoteObject>(), second=std::make_shared<IRemoteObject>();
        second->dbinder=true;
        auto original=Mixed(fd,first,second);assert(original->RewindRead(4));
        std::shared_ptr<MessageParcel> output;
        if(mode==0) {
            output=RSAshmemHelper::CopyTransactionParcel(*original);
            assert(original->GetReadPosition()==4 && output);
        } else {
            auto outer=MakeSidecar(original);assert(outer && original->GetReadPosition()==4);
            output=Snapshot(*original);
            // Shared payload cookies/handles/PTR addresses are untrusted and
            // irrelevant. Preserve only validated layout, never dereference.
            for(size_t offset:original->offsets) {
                flat_binder_object flat {};std::memcpy(&flat,output->bytes.data()+offset,sizeof(flat));
                if(flat.hdr.type!=BINDER_TYPE_PTR)flat.cookie=UINT64_MAX;
                flat.binder=UINT64_MAX; // aliases PTR buffer, never its length
                std::memcpy(output->bytes.data()+offset,&flat,sizeof(flat));
            }
            assert(RestoreRSObjectSidecar(output,*outer));outer.reset();
        }
        original.reset();CheckMixed(*output,first,second);
        std::weak_ptr<IRemoteObject> a=first,b=second;first.reset();second.reset();
        assert(!a.expired() && !b.expired());
        // This mirrors the production queued Parcel's ownership, not a real
        // EventHandler/Binder fixture. Cancellation may occur on another thread.
        std::function<void()> queued=[owned=output] { assert(owned->GetOffsetsSize()>=4); };
        output.reset();std::thread cancel([task=std::move(queued)]() mutable { task=nullptr; });
        queued=nullptr; // a moved-from std::function may retain its small callable
        cancel.join();
        assert(a.expired() && b.expired() && !Closed(fd));
    }
    close(fd);
}
'''
        run_sanitized(source(main))

    def test_dbinder_reencoding_may_change_span_without_losing_following_fields(self):
        main = r'''int main() {
    const int fd=open("/dev/null",O_RDONLY);assert(fd>=0);
    auto a=std::make_shared<IRemoteObject>(),b=std::make_shared<IRemoteObject>();b->dbinder=true;
    auto original=Mixed(fd,a,b),outer=MakeSidecar(original),snapshot=Snapshot(*original);
    const size_t before=snapshot->GetDataSize();
    b->dbinder=false; // same real object, now flattened without negotiation metadata
    assert(RestoreRSObjectSidecar(snapshot,*outer));
    assert(snapshot->GetDataSize()==before-sizeof(binder_buffer_object));
    CheckMixed(*snapshot,a,b);assert(!Closed(fd));close(fd);
}
'''
        run_sanitized(source(main))

    def test_sidecar_failures_release_partial_duplicates_and_never_close_raw_fd_numbers(self):
        main = r'''int main() {
    const int sourceFd=open("/dev/null",O_RDONLY),unrelated=open("/dev/null",O_RDONLY);
    assert(sourceFd>=0 && unrelated>=0);
    auto a=std::make_shared<IRemoteObject>(),b=std::make_shared<IRemoteObject>();b->dbinder=true;
    for(unsigned mode=0;mode<10;++mode) {
        auto original=Mixed(sourceFd,a,b),outer=MakeSidecar(original),snapshot=Snapshot(*original);
        for(size_t offset:original->offsets) {
            flat_binder_object flat {};std::memcpy(&flat,snapshot->bytes.data()+offset,sizeof(flat));
            if(flat.hdr.type==BINDER_TYPE_FD || flat.hdr.type==BINDER_TYPE_FDR) {
                flat.handle=unrelated;std::memcpy(snapshot->bytes.data()+offset,&flat,sizeof(flat));
            }
        }
        if(mode<4) { writeObjects=0;failWriteObject=mode+1; }
        if(mode==4) outer->bytes.resize(outer->bytes.size()-1);
        if(mode==5) outer->bytes.push_back(0); // unconsumed sidecar input
        if(mode==6) { const uint32_t oldVersion=0;std::memcpy(outer->bytes.data()+4,&oldVersion,4); }
        if(mode==7) { const int32_t huge=INT32_MAX;std::memcpy(outer->bytes.data(),&huge,4); }
        if(mode==8) outer->remotes.clear(); // raw cookie cannot replace a genuine translated object
        if(mode==9) {
            const size_t typeOffset=8+original->offsets.size()*sizeof(binder_size_t);
            const uint32_t wrong=RS_OBJECT_FD;std::memcpy(outer->bytes.data()+typeOffset,&wrong,4);
        }
        const size_t firstDuplicate=allDuplicates.size();
        assert(!RestoreRSObjectSidecar(snapshot,*outer));failWriteObject=-1;
        for(size_t i=firstDuplicate;i<allDuplicates.size();++i)assert(Closed(allDuplicates[i]));
        snapshot.reset();outer.reset();original.reset();
        assert(!Closed(sourceFd) && !Closed(unrelated));
    }
    close(sourceFd);close(unrelated);
}
'''
        run_sanitized(source(main))

    def test_layout_rejects_overlap_wrapping_weak_objects_and_invalid_ptr_pairs(self):
        main = r'''int main() {
    const int fd=open("/dev/null",O_RDONLY);assert(fd>=0);
    auto a=std::make_shared<IRemoteObject>(),b=std::make_shared<IRemoteObject>();b->dbinder=true;
    for(unsigned mode=0;mode<10;++mode) {
        auto original=Mixed(fd,a,b),snapshot=Snapshot(*original);auto offsets=original->offsets;
        const size_t ptr=offsets[2];
        if(mode==0)offsets[1]=offsets[0];
        if(mode==1)offsets[0]=UINT64_MAX;
        if(mode==2)offsets[0]=5;
        if(mode==3)offsets[1]=offsets[0]+4;
        if(mode==4) { uint32_t weak=BINDER_TYPE_WEAK_HANDLE;std::memcpy(snapshot->bytes.data()+4,&weak,4); }
        if(mode==5)offsets[3]+=4;
        if(mode==6)offsets.resize(3);
        if(mode==7) { uint64_t bad=0;std::memcpy(snapshot->bytes.data()+ptr+16,&bad,8); }
        if(mode==8) { uint32_t bad=0;std::memcpy(snapshot->bytes.data()+ptr+4,&bad,4); }
        if(mode==9) { uint32_t bad=BINDER_TYPE_FD;std::memcpy(snapshot->bytes.data()+offsets[3],&bad,4); }
        std::vector<RSParcelObjectSlot> slots;
        assert(!BuildRSObjectLayout(*snapshot,offsets.data(),offsets.size(),slots));
        assert(!Closed(fd));
    }
    auto plain=std::make_shared<MessageParcel>();assert(plain->WriteUint32(42));
    auto outer=MakeSidecar(plain),snapshot=Snapshot(*plain);assert(RestoreRSObjectSidecar(snapshot,*outer));
    uint32_t value=0;assert(snapshot->ReadUint32(value) && value==42 && snapshot->offsets.empty());
    close(fd);
}
'''
        run_sanitized(source(main))

    def test_fd_zero_and_sender_failure_keep_single_resource_owner(self):
        main = r'''int main() {
    const int sourceFd=open("/dev/null",O_RDONLY);assert(sourceFd>0);
    const pid_t child=fork();assert(child>=0);
    if(child==0) {
        close(STDIN_FILENO);assert(dup(sourceFd)==0);
        auto original=std::make_shared<MessageParcel>();flat_binder_object flat {};
        flat.hdr.type=BINDER_TYPE_FDR;flat.handle=0;
        assert(original->WriteBuffer(&flat,sizeof(flat)));original->offsets={0};
        auto copied=RSAshmemHelper::CopyTransactionParcel(*original);assert(copied && !Closed(0));
        int fd=copied->ReadFileDescriptor();assert(fd>=0);close(fd);copied.reset();assert(!Closed(0));
        close(0);close(sourceFd);_exit(0);
    }
    int status=0;assert(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
    auto a=std::make_shared<IRemoteObject>(),b=std::make_shared<IRemoteObject>();
    for(unsigned failure=1;failure<=4;++failure) {
        auto original=Mixed(sourceFd,a,b);assert(original->RewindRead(4));
        const size_t begin=allDuplicates.size();writeObjects=0;failWriteObject=failure;
        auto outer=MakeSidecar(original);assert(!outer);failWriteObject=-1;
        assert(original->GetReadPosition()==4 && !Closed(sourceFd));
        for(size_t i=begin;i<allDuplicates.size();++i)assert(Closed(allDuplicates[i]));
    }
    close(sourceFd);
}
'''
        run_sanitized(source(main))

    def test_exact_unified_stack_has_no_raw_sptr_or_borrowed_object_copy_path(self):
        replacements = RS._object_repairs.REPLACEMENTS
        self.assertTrue(any('!is_sptr<T>::value' in new for old, new in replacements[OBJ.MARSHALLING_HEADER]))
        for path in (RS.FILE, OBJ.SERVICE_STUB):
            new_copy = next(new for old, new in replacements[path] if 'void* base = malloc(dataSize)' in old)
            self.assertIn('RSAshmemHelper::CopyTransactionParcel(old)', new_copy)
            self.assertNotIn('InjectOffsets', new_copy)
        new_restore = next(new for old, new in replacements[RS.ASHMEM] if 'if (!RestoreAshmemObjectOffsets' in old)
        self.assertIn('RestoreRSObjectSidecar', new_restore)
        self.assertIn('ashmemFdWorker.reset()', new_restore)
        self.assertNotIn('InjectOffsets', OBJ.OBJECT_HELPERS)
        self.assertNotIn('AcquireObject', OBJ.OBJECT_HELPERS)
        self.assertNotIn('reinterpret_cast<IRemoteObject', OBJ.OBJECT_HELPERS)
        self.assertIn('destination.WriteRemoteObject(object)', OBJ.OBJECT_HELPERS)
        self.assertIn('::close(fd)', OBJ.OBJECT_HELPERS)


if __name__ == '__main__':
    unittest.main()
