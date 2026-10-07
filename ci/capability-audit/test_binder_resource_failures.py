"""Actual repaired helpers with OS FDs and explicit seams, not guest Binder."""
import unittest

from test_rs_receiver_ownership import IPC, PREFIX
from test_rs_transaction_validation import run_sanitized


class BinderResourceFailureTests(unittest.TestCase):
    def test_delivered_fd_cleanup_ignores_kernel_owned_fda_and_untrusted_fdr(self):
        declarations = r'''
using binder_object_header=decltype(flat_binder_object{}.hdr);
constexpr uint32_t BINDER_TYPE_FDA=4;
struct binder_transaction_data {
    uint64_t data_size=0,offsets_size=0;
    struct { struct { uint64_t buffer=0,offsets=0; } ptr; } data;
};
'''
        main = r'''int main() {
    const int source=open("/dev/null",O_RDONLY);
    const int duplicate=dup(source),arrayFd=dup(source),foreign=dup(source);
    assert(source>=0 && duplicate>=0 && arrayFd>=0 && foreign>=0);
    MessageParcel parcel;parcel.bytes.resize(76);
    Put(parcel,4,BINDER_TYPE_FD,duplicate);
    Put(parcel,28,BINDER_TYPE_FDA,arrayFd);
    Put(parcel,52,BINDER_TYPE_FDR,foreign);
    std::vector<uint8_t> bytes(28);
    const binder_size_t table[]={4,28,52};
    std::memcpy(bytes.data()+4,table,sizeof(table));
    binder_transaction_data transaction;
    transaction.data_size=parcel.bytes.size();transaction.offsets_size=sizeof(table);
    transaction.data.ptr.buffer=parcel.GetData();
    transaction.data.ptr.offsets=reinterpret_cast<uintptr_t>(bytes.data()+4);
    CloseDeliveredFileDescriptors(transaction);
    assert(Closed(duplicate) && !Closed(source) && !Closed(arrayFd) && !Closed(foreign));
    // No object table was published in this stand-in Parcel. In the real
    // rejection path BC_FREE_BUFFER follows; only kernel owns FDA closure.
    close(arrayFd);close(foreign);close(source);
    const pid_t child=fork();assert(child>=0);
    if(child==0) {
        close(0);const int fd=open("/dev/null",O_RDONLY);assert(fd==0);
        MessageParcel data;data.bytes.resize(28);Put(data,4,BINDER_TYPE_FD,0);
        binder_size_t offset=4;
        binder_transaction_data zero;
        zero.data_size=28;zero.offsets_size=sizeof(offset);
        zero.data.ptr.buffer=data.GetData();zero.data.ptr.offsets=reinterpret_cast<uintptr_t>(&offset);
        CloseDeliveredFileDescriptors(zero);assert(Closed(0));_exit(0);
    }
    int status=0;assert(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
}
'''
        run_sanitized(PREFIX + IPC.CLEAR_FDS + declarations + IPC.DELIVERED_FDS + main)

    def test_delivered_metadata_rejects_wrap_and_malformed_tables_without_closing_foreign_fd(self):
        declarations = r'''
using binder_object_header=decltype(flat_binder_object{}.hdr);
struct binder_transaction_data {
    uint64_t data_size=0,offsets_size=0;
    struct { struct { uint64_t buffer=0,offsets=0; } ptr; } data;
};
'''
        main = r'''int main() {
    const int fd=open("/dev/null",O_RDONLY);assert(fd>=0);
    MessageParcel parcel;parcel.bytes.resize(28);Put(parcel,4,BINDER_TYPE_FD,fd);
    binder_size_t table=UINT64_MAX;
    binder_transaction_data transaction;
    transaction.data_size=28;transaction.offsets_size=sizeof(table);
    transaction.data.ptr.buffer=parcel.GetData();transaction.data.ptr.offsets=reinterpret_cast<uintptr_t>(&table);
    CloseDeliveredFileDescriptors(transaction);assert(!Closed(fd));
    table=4;transaction.offsets_size=7;
    CloseDeliveredFileDescriptors(transaction);assert(!Closed(fd));
    transaction.offsets_size=sizeof(table);transaction.data.ptr.buffer=UINTPTR_MAX-3;
    CloseDeliveredFileDescriptors(transaction);assert(!Closed(fd));
    transaction.data.ptr.buffer=parcel.GetData();transaction.data.ptr.offsets=UINTPTR_MAX-3;
    CloseDeliveredFileDescriptors(transaction);assert(!Closed(fd));close(fd);
}
'''
        run_sanitized(PREFIX + IPC.CLEAR_FDS + declarations + IPC.DELIVERED_FDS + main)

    def test_raw_data_fd_zero_and_remote_marker_have_distinct_ownership(self):
        changes = dict(IPC.PARCEL_RESOURCE_REPLACEMENTS)
        read_guard = changes['    if (readRawDataFd_ > 0) {\n']
        write_guard = changes['    if (writeRawDataFd_ > 0) {\n']
        restore = changes['    writeRawDataFd_ = 0;\n']
        remote_guard = changes['    /* if rawDataFd_ == 0 means rawData is received from remote */\n'
                               '    if (rawData_ != nullptr && writeRawDataFd_ == 0) {\n']
        source = r'''#include <cassert>
#include <cerrno>
#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>
constexpr int REMOTE_RAW_DATA_FD=-2;
int closeCount=0;
constexpr unsigned IPC_FD_TAG=1;
int fdsan_close_with_tag(int fd,unsigned) { ++closeCount;return close(fd); }
struct RawOwner {
    int readRawDataFd_=-1,writeRawDataFd_=-1;
    void* rawData_=nullptr;
    ~RawOwner() {
''' + read_guard + r'''        ::fdsan_close_with_tag(readRawDataFd_,IPC_FD_TAG);
        readRawDataFd_=-1;
    }
''' + write_guard + r'''        ::fdsan_close_with_tag(writeRawDataFd_,IPC_FD_TAG);
        writeRawDataFd_=-1;
    }
    }
    void Restore() { rawData_=this;
''' + restore + r'''    }
    bool Remote() const {
''' + remote_guard + r'''        return true;
    }
    return false;
    }
};
bool Closed(int fd) { errno=0;return fcntl(fd,F_GETFD)==-1 && errno==EBADF; }
int main() {
    for(unsigned mode=0;mode<3;++mode) {
        const pid_t child=fork();assert(child>=0);
        if(child==0) {
            close(0);const int zero=open("/dev/null",O_RDONLY);assert(zero==0);
            {
                RawOwner owner;
                if(mode==0) owner.readRawDataFd_=zero;
                else if(mode==1) owner.writeRawDataFd_=zero;
                else { owner.Restore();assert(owner.Remote()); }
                if(mode!=2) assert(!owner.Remote());
            }
            if(mode==2) { assert(closeCount==0 && !Closed(0));close(0); }
            else assert(closeCount==1 && Closed(0));
            _exit(0);
        }
        int status=0;
        assert(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
    }
}
'''
        run_sanitized(source)

    def test_read_ashmem_allocation_failure_and_success_transfer_duplicate_once(self):
        tail = dict(IPC.PARCEL_RESOURCE_REPLACEMENTS)['    return new (std::nothrow) Ashmem(fd, size);\n']
        source = r'''#include <cassert>
#include <cerrno>
#include <cstdlib>
#include <fcntl.h>
#include <new>
#include <unistd.h>
bool failAllocation=false;
struct Ashmem {
    int fd;
    Ashmem(int value,int):fd(value) {}
    ~Ashmem() { close(fd); }
    static void* operator new(size_t bytes,const std::nothrow_t&) noexcept {
        return failAllocation ? nullptr : std::malloc(bytes);
    }
    static void operator delete(void* value) noexcept { std::free(value); }
};
template<class T> using sptr=T*;
sptr<Ashmem> Create(int fd,int size) {
''' + tail + r'''}
bool Closed(int fd) { errno=0;return fcntl(fd,F_GETFD)==-1 && errno==EBADF; }
int main() {
    const int source=open("/dev/null",O_RDONLY);assert(source>=0);
    for(bool fail:{false,true}) {
        failAllocation=fail;const int duplicate=dup(source);assert(duplicate>=0);
        auto* object=Create(duplicate,4096);
        if(fail) { assert(object==nullptr && Closed(duplicate)); }
        else { assert(object!=nullptr && !Closed(duplicate));delete object;assert(Closed(duplicate)); }
        const int reuse=open("/dev/null",O_RDONLY);assert(reuse>=0 && !Closed(reuse));close(reuse);
        assert(!Closed(source));
    }
    close(source);
}
'''
        run_sanitized('#include <initializer_list>\n' + source)


if __name__ == '__main__':
    unittest.main()
