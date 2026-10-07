"""Sanitized actual patch helpers with real OS FDs; not guest IPC acceptance."""
import importlib.util
from pathlib import Path
import unittest

from test_rs_transaction_validation import RS, run_sanitized

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'ipc_object_safety', ROOT / 'patches/common/foundation/communication/ipc/binder_object_safety/verify_source.py')
IPC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IPC)

PREFIX = r'''#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <set>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
using binder_size_t = uint64_t;
[[maybe_unused]] constexpr uint32_t BINDER_TYPE_FD=1, BINDER_TYPE_FDR=2, BINDER_TYPE_HANDLE=3;
struct flat_binder_object {
    struct { uint32_t type; } hdr;
    uint32_t flags;
    union { uint64_t binder; uint32_t handle; };
    uint64_t cookie;
};
static_assert(sizeof(flat_binder_object)==24 && alignof(flat_binder_object)==8);
constexpr int EOK=0;
bool failCopy=false;
int memcpy_s(void* out,size_t capacity,const void* in,size_t bytes) {
    if (failCopy || bytes>capacity) return -1;
    std::memcpy(out,in,bytes); return EOK;
}
#define ZLOGE(...) ((void)0)
struct MessageParcel {
    std::vector<unsigned char> bytes;
    std::vector<binder_size_t> offsets;
    std::vector<int> inputFds;
    size_t fdCursor=0;
    int32_t count=0;
    bool failTable=false;
    ~MessageParcel() { ClearFileDescriptor(); }
    uintptr_t GetData() const { return reinterpret_cast<uintptr_t>(bytes.data()); }
    size_t GetDataSize() const { return bytes.size(); }
    uintptr_t GetObjectOffsets() const { return reinterpret_cast<uintptr_t>(offsets.data()); }
    size_t GetOffsetsSize() const { return offsets.size(); }
    bool ReadInt32(int32_t& out) { out=count; return true; }
    size_t GetReadableBytes() const { return bytes.size(); }
    const uint8_t* ReadBuffer(size_t size) { return size<=bytes.size()?bytes.data():nullptr; }
    int ReadFileDescriptor() {
        return fdCursor<inputFds.size()?dup(inputFds[fdCursor++]):-1;
    }
    void InjectOffsets(binder_size_t pointer,size_t size) {
        auto* table=reinterpret_cast<const binder_size_t*>(pointer);
        if(failTable) --size;
        offsets.assign(table,table+size);
    }
    void FlushBuffer() { offsets.clear(); bytes.clear(); }
    void ClearFileDescriptor();
    bool ContainFileDescriptors() const;
};
struct AshmemFdWorker {
    bool manual=false;
    std::set<int> fds;
    explicit AshmemFdWorker(pid_t) {}
    ~AshmemFdWorker() { if(manual) for(int fd:fds) if(fd>=0) close(fd); }
    void InsertFdWithOffset(int fd,binder_size_t,bool shouldClose) {
        assert(shouldClose && fd>=0); fds.insert(fd);
    }
};
void Put(MessageParcel& parcel,size_t offset,uint32_t type,int fd) {
    flat_binder_object flat{};
    flat.hdr.type=type;flat.handle=static_cast<uint32_t>(fd);
    std::memcpy(parcel.bytes.data()+offset,&flat,sizeof(flat));
}
int GetFd(const MessageParcel& parcel,size_t offset) {
    flat_binder_object flat{};
    std::memcpy(&flat,parcel.bytes.data()+offset,sizeof(flat));
    assert(flat.hdr.type==BINDER_TYPE_FD);
    return static_cast<int32_t>(flat.handle);
}
bool Closed(int fd) { errno=0;return fcntl(fd,F_GETFD)==-1 && errno==EBADF; }
'''


def receiver_source(main):
    return (PREFIX + IPC.CLEAR_FDS + IPC.CONTAINS_FDS + RS.OFFSETS_VALIDATION + RS.SANITIZE_FDS
            + RS.RECEIVER_RESTORE_OFFSETS + main)


class RsReceiverOwnershipTests(unittest.TestCase):
    def test_fd_fdr_four_byte_offsets_early_rejection_and_async_owner_transfer(self):
        main = r'''int main() {
    const int source=open("/dev/null",O_RDONLY), unrelated=open("/dev/null",O_RDONLY);
    assert(source>=0 && unrelated>=0);
    for(unsigned mode=0;mode<4;++mode) {
        auto parcel=std::make_shared<MessageParcel>();parcel->bytes.resize(76);
        Put(*parcel,4,BINDER_TYPE_FDR,unrelated);
        Put(*parcel,28,BINDER_TYPE_FD,unrelated);
        Put(*parcel,52,BINDER_TYPE_HANDLE,unrelated);
        assert((parcel->GetData()+4)%alignof(flat_binder_object)==4);
        MessageParcel outer;outer.bytes.resize(24);outer.count=3;
        const binder_size_t offsets[]={4,28,52};
        std::memcpy(outer.bytes.data(),offsets,sizeof(offsets));
        outer.inputFds={source,source};
        std::unique_ptr<AshmemFdWorker> worker;
        assert(RestoreAshmemObjectOffsets(parcel,&outer,worker,42));
        assert(worker->fds.size()==2 && parcel->ContainFileDescriptors());
        const int first=GetFd(*parcel,4),second=GetFd(*parcel,28);
        assert(first!=second && first!=unrelated && second!=unrelated);
        if(mode==0) { // bad token / non-uni: Parcel alone closes
            parcel.reset();assert(Closed(first) && Closed(second));
            const int reuse=open("/dev/null",O_RDONLY);assert(reuse>=0);
            worker.reset();assert(!Closed(reuse));close(reuse);
        } else if(mode==1) { // queued normal-uni path explicitly changes owner
            parcel->FlushBuffer();worker->manual=true;parcel.reset();
            assert(!Closed(first) && !Closed(second));worker.reset();
            assert(Closed(first) && Closed(second));
        } else if(mode==2) { // cancelled task destroys its owning Parcel
            worker.reset();assert(!Closed(first));parcel.reset();assert(Closed(first) && Closed(second));
        } else { // passive worker must not close before unmarshalling
            worker.reset();assert(!Closed(first) && !Closed(second));parcel.reset();
            assert(Closed(first) && Closed(second));
        }
        assert(!Closed(source) && !Closed(unrelated));
    }
    close(source);close(unrelated);
}
'''
        run_sanitized(receiver_source(main))

    def test_partial_fd_restore_and_partial_object_table_never_close_sender_numbers(self):
        main = r'''int main() {
    const int source=open("/dev/null",O_RDONLY), unrelated=open("/dev/null",O_RDONLY);
    assert(source>=0 && unrelated>=0);
    for(unsigned mode=0;mode<3;++mode) {
        auto parcel=std::make_shared<MessageParcel>();parcel->bytes.resize(52);
        Put(*parcel,4,BINDER_TYPE_FDR,unrelated);Put(*parcel,28,BINDER_TYPE_FD,unrelated);
        MessageParcel outer;outer.bytes.resize(16);outer.count=2;
        const binder_size_t offsets[]={4,28};
        std::memcpy(outer.bytes.data(),offsets,sizeof(offsets));
        if(mode==0) outer.inputFds={source}; // second dup is unavailable
        if(mode==1) parcel->failTable=true; // no duplicate before full table
        if(mode==2) failCopy=true; // rejected before publishing any metadata
        std::unique_ptr<AshmemFdWorker> worker;
        assert(!RestoreAshmemObjectOffsets(parcel,&outer,worker,42));
        failCopy=false;
        std::vector<int> duplicates;
        if(worker) duplicates.assign(worker->fds.begin(),worker->fds.end());
        assert(duplicates.size()==static_cast<size_t>(mode==0));
        parcel.reset();worker.reset();
        for(int fd:duplicates) assert(Closed(fd));
        assert(!Closed(source) && !Closed(unrelated));
    }
    close(source);close(unrelated);
}
'''
        run_sanitized(receiver_source(main))

    def test_actual_parcel_cleanup_fd_zero_in_isolated_child_and_wrapping_offsets(self):
        main = r'''int main() {
    const int source=open("/dev/null",O_RDONLY);assert(source>0);
    const pid_t child=fork();assert(child>=0);
    if(child==0) {
        close(STDIN_FILENO);
        const int fd=dup(source);assert(fd==0);
        {
            MessageParcel parcel;parcel.bytes.resize(28);parcel.offsets={4};
            Put(parcel,4,BINDER_TYPE_FD,fd);assert(parcel.ContainFileDescriptors());
        }
        assert(Closed(0));close(source);_exit(0);
    }
    int status=0;assert(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
    assert(!Closed(source));
    {
        MessageParcel parcel;parcel.bytes.resize(28);parcel.offsets={UINT64_MAX-7};
        Put(parcel,4,BINDER_TYPE_FD,source);assert(!parcel.ContainFileDescriptors());
    }
    assert(!Closed(source));close(source);
}
'''
        run_sanitized(PREFIX + IPC.CLEAR_FDS + IPC.CONTAINS_FDS + main)

    def test_receiver_private_bytes_ignore_subsequent_shared_mapping_mutation(self):
        snapshot = next(new for old, new in RS.REPLACEMENTS[RS.ASHMEM]
                        if 'auto dataParcel = std::make_shared<MessageParcel>(ashmemAllocator.release())' in old)
        # Only the changed control flow is extracted. This deliberately does
        # not assert the host stand-in is the real target Ashmem/Parcel class.
        declarations = r'''struct SnapshotParcel {
    void* owned=nullptr;
    ~SnapshotParcel() { free(owned); }
    bool ParseFrom(uintptr_t data,size_t) { owned=reinterpret_cast<void*>(data);return true; }
};
struct SnapshotAllocator {
    const void* mapped;
    explicit SnapshotAllocator(const void* bytes):mapped(bytes) {}
    void* CopyFromAshmem(size_t size) {
        void* copy=malloc(size);if(copy) std::memcpy(copy,mapped,size);return copy;
    }
};
std::shared_ptr<SnapshotParcel> Snapshot(std::unique_ptr<SnapshotAllocator> ashmemAllocator,size_t dataSize) {
'''
        snapshot = snapshot.replace('MessageParcel', 'SnapshotParcel')
        main = r'''int main() {
    void* shared=mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANON,-1,0);
    assert(shared!=MAP_FAILED);
    const uint32_t before=11,after=22;
    std::memcpy(shared,&before,sizeof(before));
    auto parcel=Snapshot(std::make_unique<SnapshotAllocator>(shared),sizeof(before));assert(parcel);
    std::memcpy(shared,&after,sizeof(after));
    uint32_t observed=0;std::memcpy(&observed,parcel->owned,sizeof(observed));assert(observed==before);
    munmap(shared,4096);parcel.reset();
}
'''
        run_sanitized(PREFIX + declarations + snapshot + '    return dataParcel;\n}\n' + main)


if __name__ == '__main__':
    unittest.main()
