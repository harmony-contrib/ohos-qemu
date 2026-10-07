"""Actual patched helper snippets; deliberately not guest Parcel/FD acceptance."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/foundation/graphic/graphic_2d/async_caller_identity'
SPEC = importlib.util.spec_from_file_location('rs_transaction_validation_baseline', COMPONENT / 'verify_source.py')
RS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RS)


def run_sanitized(source):
    compiler = shutil.which('clang++')
    if not compiler:
        raise AssertionError('an actual C++ compiler is required')
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        path, binary = root / 'probe.cpp', root / 'probe'
        path.write_text(source)
        compiled = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                   '-fsanitize=address,undefined', str(path), '-o', str(binary)],
                                  capture_output=True, text=True)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        executed = subprocess.run([str(binary)], capture_output=True, text=True)
        if executed.returncode:
            raise AssertionError(executed.stdout + executed.stderr)


PREFIX = '''#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <vector>
using binder_size_t = uint64_t;
struct flat_binder_object { uint32_t type, flags; uint64_t binder, cookie; };
static_assert(sizeof(flat_binder_object)==24);
'''


class RsTransactionValidationTests(unittest.TestCase):
    def test_actual_offsets_validator_bounds_order_overlap_and_binder_four_byte_alignment(self):
        main = '''int main() {
    assert(IsValidAshmemObjectOffsets(nullptr,0,0));
    assert(!IsValidAshmemObjectOffsets(nullptr,1,32));
    const binder_size_t valid[]={4,28,52};
    assert(IsValidAshmemObjectOffsets(valid,3,76));
    assert(!IsValidAshmemObjectOffsets(valid,3,75));
    const binder_size_t duplicate[]={4,4}, overlap[]={4,24}, reversed[]={28,4};
    assert(!IsValidAshmemObjectOffsets(duplicate,2,80));
    assert(!IsValidAshmemObjectOffsets(overlap,2,80));
    assert(!IsValidAshmemObjectOffsets(reversed,2,80));
    const binder_size_t wrapping[]={std::numeric_limits<binder_size_t>::max()-7};
    assert(!IsValidAshmemObjectOffsets(wrapping,1,UINT32_MAX));
    assert(!IsValidAshmemObjectOffsets(wrapping,1,std::numeric_limits<size_t>::max()));
    for (size_t size=0;size<160;++size) for (binder_size_t offset=0;offset<192;++offset) {
        const bool expected=offset<=size && size-offset>=sizeof(flat_binder_object) && offset%4==0;
        assert(IsValidAshmemObjectOffsets(&offset,1,size)==expected);
    }
    std::vector<binder_size_t> many(4096);
    for(size_t i=0;i<many.size();++i) many[i]=4+i*sizeof(flat_binder_object);
    assert(IsValidAshmemObjectOffsets(many.data(),many.size(),4+many.size()*sizeof(flat_binder_object)));
}
'''
        run_sanitized(PREFIX + RS.OFFSETS_VALIDATION + main)

    def test_actual_restore_checks_count_before_multiplication_and_handles_incomplete_injection(self):
        mocks = '''static bool failAllocation=false, failCopy=false;
static unsigned fdInjections=0;
static int observedPid=0;
void* checkedMalloc(size_t bytes) { return failAllocation?nullptr:std::malloc(bytes); }
constexpr int EOK=0;
int memcpy_s(void* out,size_t capacity,const void* in,size_t bytes) {
    if(failCopy || bytes>capacity) return -1;
    std::memcpy(out,in,bytes); return EOK;
}
struct AshmemFdWorker {};
struct MessageParcel {
    int32_t count=1;
    bool readCount=true, missingBuffer=false, partialInjection=false, nullTable=false;
    size_t dataSize=32, readCalls=0, readBytes=0;
    std::vector<unsigned char> raw;
    std::vector<binder_size_t> objects;
    bool ReadInt32(int32_t& value) { value=count; return readCount; }
    size_t GetReadableBytes() { return raw.size()-4; }
    size_t GetDataSize() { return dataSize; }
    const uint8_t* ReadBuffer(size_t bytes) {
        ++readCalls; readBytes=bytes;
        return missingBuffer || bytes>GetReadableBytes()?nullptr:raw.data()+4;
    }
    void InjectOffsets(binder_size_t pointer,size_t size) {
        assert(pointer%alignof(binder_size_t)==0);
        auto* offsets=reinterpret_cast<binder_size_t*>(pointer);
        if(partialInjection) --size;
        objects.assign(offsets,offsets+size);
    }
    size_t GetOffsetsSize() { return objects.size(); }
    uintptr_t GetObjectOffsets() { return nullTable?0:reinterpret_cast<uintptr_t>(objects.data()); }
    void Fill(std::initializer_list<binder_size_t> values) {
        raw.resize(4+values.size()*sizeof(binder_size_t));
        size_t index=4;
        for(auto value:values) { std::memcpy(raw.data()+index,&value,sizeof(value)); index+=sizeof(value); }
    }
};
struct RSAshmemHelper {
    static void InjectFileDescriptor(std::shared_ptr<MessageParcel>&, MessageParcel*,
        std::unique_ptr<AshmemFdWorker>&,pid_t pid) { ++fdInjections; observedPid=pid; }
};
#define malloc checkedMalloc
'''
        main = '''#undef malloc
int main() {
    for(unsigned test=0;test<12;++test) {
        auto data=std::make_shared<MessageParcel>();
        MessageParcel ashmem;
        ashmem.Fill({4});
        std::unique_ptr<AshmemFdWorker> worker;
        fdInjections=0; observedPid=0; failAllocation=failCopy=false;
        bool expected=false;
        switch(test) {
            case 0: expected=true; break;
            case 1: ashmem.count=0; expected=true; break;
            case 2: ashmem.count=-1; break;
            case 3: ashmem.readCount=false; break;
            case 4: ashmem.count=0x20000001; break;
            case 5: ashmem.missingBuffer=true; break;
            case 6: data->partialInjection=true; break;
            case 7: data->nullTable=true; break;
            case 8: failAllocation=true; break;
            case 9: failCopy=true; break;
            case 10: ashmem.Fill({UINT64_MAX-7}); break;
            case 11: ashmem.count=2; ashmem.Fill({4,4}); data->dataSize=80; break;
        }
        assert(RestoreAshmemObjectOffsets(data,&ashmem,worker,77)==expected);
        assert(fdInjections==static_cast<unsigned>(test==0));
        assert(observedPid==(test==0?77:0));
        if(test==0) assert(ashmem.readBytes==sizeof(binder_size_t));
        if(test==1 || test==2 || test==3 || test==4) assert(ashmem.readCalls==0);
    }
}
'''
        run_sanitized(PREFIX + mocks + RS.OFFSETS_VALIDATION + RS.RESTORE_OFFSETS + main)

    def test_actual_enum_guards_exhaustive_read_success_and_defined_values(self):
        replacements = RS.REPLACEMENTS[RS.TRANSACTION]
        follow = replacements[0][1]
        scene = replacements[1][1].split('    scene_ = ', 1)[0]
        source = '''#include <cassert>
#include <cstdint>
enum class FollowType : uint8_t { NONE=0,FOLLOW_TO_PARENT=1,FOLLOW_TO_SELF=2 };
enum class RSTransactionDataScenes : uint8_t { Default=0,Rebuild=1 };
struct Parcel { bool read; bool ReadUint8(uint8_t&) { return read; } };
bool decodeFollow(Parcel parcel,uint8_t followType) {
''' + follow + '''                return false;
            }
    return true;
}
bool decodeScene(bool flag,uint8_t scene) {
''' + scene + '''    return true;
}
int main() {
    for(unsigned value=0;value<=UINT8_MAX;++value) for(bool read:{false,true}) {
        assert(decodeFollow({read},static_cast<uint8_t>(value))==(read && value<=2));
        assert(decodeScene(read,static_cast<uint8_t>(value))==(read && value<=1));
    }
}
'''
        # Range-for initializer_list needs its actual standard declaration.
        run_sanitized('#include <initializer_list>\n' + source)

    def test_pinned_component_covers_all_fourteen_sources_and_safe_cleanup_guards(self):
        self.assertEqual({path for path, _, _ in RS.FILES}, set(RS.REPLACEMENTS))
        self.assertEqual(len(RS.FILES), 14)
        for _, before, after in RS.FILES:
            self.assertEqual(len(before), 64)
            self.assertEqual(len(after), 64)
            self.assertNotEqual(before, after)
        copy_guard = RS.REPLACEMENTS[RS.FILE][2][1]
        self.assertLess(copy_guard.index('GetOffsetsSize() != objectNum'), copy_guard.index('CopyFileDescriptor'))
        self.assertLess(copy_guard.index('FlushBuffer()'), copy_guard.index('return nullptr'))
        restore_caller = next(new for old, new in RS.REPLACEMENTS[RS.ASHMEM]
                              if 'Failed injection may hold borrowed FD numbers' in old)
        self.assertNotIn('dataParcel->FlushBuffer();', restore_caller)
        self.assertNotIn('free(base)', restore_caller)
        for old, new in RS.REPLACEMENTS[RS.FILE]:
            if 'parcel data Read failed' in old or 'parcel data not match' in old:
                self.assertIn('free(base);', old)
                self.assertNotIn('free(base);', new)

    def test_snapshot_owns_malloc_and_never_publishes_shared_object_metadata(self):
        snapshot = next(new for old, new in RS.REPLACEMENTS[RS.ASHMEM]
                        if 'auto dataParcel = std::make_shared<MessageParcel>(ashmemAllocator.release())' in old)
        self.assertIn('CopyFromAshmem(dataSize)', snapshot)
        self.assertIn('std::make_shared<MessageParcel>()', snapshot)
        self.assertNotIn('GetData()', snapshot)
        self.assertNotIn('release()', snapshot)
        self.assertEqual(snapshot.count('free(data)'), 1)
        self.assertLess(snapshot.index('if (!dataParcel->ParseFrom'), snapshot.index('free(data)'))


if __name__ == '__main__':
    unittest.main()
