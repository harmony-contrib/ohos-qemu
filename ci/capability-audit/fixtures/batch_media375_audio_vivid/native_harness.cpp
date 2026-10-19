/* Controlled dependencies around the unmodified installed function body.
 * Synthetic metadata here proves range/state rejection only, not AudioVivid.
 */
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <memory>
#include <vector>

#define FALSE_RETURN_V_MSG(condition, result, ...) do { if (!(condition)) return result; } while (0)
constexpr int64_t HST_TIME_NONE = -1;
static int copyCalls = 0, failCopy = 0;
static int memcpy_s(void *to, size_t capacity, const void *from, size_t count)
{
    if (++copyCalls == failCopy || to == nullptr || from == nullptr || count > capacity) return -1;
    std::memcpy(to, from, count);
    return 0;
}
namespace AudioStandard {
struct BufferDesc {
    uint8_t *buffer = nullptr;
    size_t bufLength = 0, dataLength = 0;
    uint8_t *metaBuffer = nullptr;
    size_t metaLength = 0;
    uint64_t position = 0, timeStampInNs = 0, syncFramePts = 0;
};
}
namespace Tag { constexpr int OH_MD_KEY_AUDIO_VIVID_METADATA = 1; }
struct Meta {
    bool present = true;
    std::vector<uint8_t> bytes {10, 11, 12, 13};
    bool GetData(int, std::vector<uint8_t> &out) const { if (!present) return false; out = bytes; return true; }
};
struct Memory {
    std::array<uint8_t, 16> bytes {{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15}};
    bool null = false;
    int32_t capacity = 16, offset = 2, used = 5;
    uint8_t *GetAddr() { return null ? nullptr : bytes.data(); }
    int32_t GetCapacity() { return capacity; }
    int32_t GetOffset() { return offset; }
    int32_t GetSize() { return used; }
};
struct AVBuffer {
    std::shared_ptr<Memory> memory_ = std::make_shared<Memory>();
    std::shared_ptr<Meta> meta_ = std::make_shared<Meta>();
    int64_t pts_ = 700;
};
struct AudioSink {
    bool isAudioPass_ = false;
    std::atomic<size_t> availDataSize_ {4};
    int32_t currentQueuedBufferOffset_ = 1;
    bool CopyAudioVividBufferData(AudioStandard::BufferDesc &, std::shared_ptr<AVBuffer> &,
        size_t &, size_t &, int64_t &);
};

// ACTUAL_FUNCTION

struct Fixture {
    AudioSink sink;
    std::array<uint8_t, 16> pcm, meta;
    AudioStandard::BufferDesc desc;
    std::shared_ptr<AVBuffer> buffer = std::make_shared<AVBuffer>();
    size_t remaining = 8, cache = 4;
    int64_t pts = HST_TIME_NONE;
    Fixture() {
        pcm.fill(0xa5); meta.fill(0xa6);
        desc.buffer = pcm.data(); desc.bufLength = 16; desc.dataLength = 2;
        desc.metaBuffer = meta.data(); desc.metaLength = 4; desc.syncFramePts = 99;
        copyCalls = 0; failCopy = 0;
    }
    bool call() { return sink.CopyAudioVividBufferData(desc, buffer, remaining, cache, pts); }
};

int main()
{
    unsigned scenarios = 0;
    const std::vector<std::function<void(Fixture &)>> invalid {
        [](auto &f) { f.desc.buffer = nullptr; },
        [](auto &f) { f.buffer.reset(); },
        [](auto &f) { f.buffer->memory_.reset(); },
        [](auto &f) { f.buffer->memory_->null = true; },
        [](auto &f) { f.buffer->memory_->capacity = -1; },
        [](auto &f) { f.buffer->memory_->offset = -1; },
        [](auto &f) { f.buffer->memory_->used = -1; },
        [](auto &f) { f.buffer->memory_->offset = 17; },
        [](auto &f) { f.buffer->memory_->offset = 13; },
        [](auto &f) { f.sink.currentQueuedBufferOffset_ = -1; },
        [](auto &f) { f.sink.currentQueuedBufferOffset_ = 6; },
        [](auto &f) { f.cache = 0; },
        [](auto &f) { f.cache = 3; },
        [](auto &f) { f.cache = 5; },
        [](auto &f) { f.remaining = 3; },
        [](auto &f) { f.desc.dataLength = 17; },
        [](auto &f) { f.desc.dataLength = SIZE_MAX; },
        [](auto &f) { f.desc.bufLength = 5; },
        [](auto &f) { f.sink.availDataSize_ = 3; },
        [](auto &f) { f.buffer->meta_.reset(); },
        [](auto &f) { f.desc.metaBuffer = nullptr; },
        [](auto &f) { f.desc.metaLength = 0; },
        [](auto &f) { f.buffer->meta_->present = false; },
        [](auto &f) { f.buffer->meta_->bytes.pop_back(); },
        [](auto &f) { f.buffer->meta_->bytes.push_back(14); },
        [](auto &) { failCopy = 1; },
        [](auto &) { failCopy = 2; },
    };
    for (const auto &mutate : invalid) {
        Fixture f; mutate(f);
        const auto data = f.desc.dataLength, size = f.remaining, cache = f.cache,
            queued = f.sink.availDataSize_.load();
        const auto sync = f.desc.syncFramePts;
        const auto pts = f.pts;
        const auto offset = f.sink.currentQueuedBufferOffset_;
        assert(!f.call());
        assert(f.desc.dataLength == data && f.remaining == size && f.cache == cache &&
            f.sink.availDataSize_.load() == queued && f.desc.syncFramePts == sync &&
            f.pts == pts && f.sink.currentQueuedBufferOffset_ == offset);
        ++scenarios;
    }
    {
        Fixture f; assert(f.call());
        assert((std::array<uint8_t,4>{f.pcm[2],f.pcm[3],f.pcm[4],f.pcm[5]} == std::array<uint8_t,4>{3,4,5,6}));
        assert((std::array<uint8_t,4>{f.meta[0],f.meta[1],f.meta[2],f.meta[3]} == std::array<uint8_t,4>{10,11,12,13}));
        assert(f.pcm[1] == 0xa5 && f.pcm[6] == 0xa5 && f.meta[4] == 0xa6);
        assert(f.desc.dataLength == 6 && f.remaining == 4 && f.sink.availDataSize_ == 0 &&
            f.sink.currentQueuedBufferOffset_ == 0 && f.pts == 700 && f.desc.syncFramePts == 99);
        assert(!f.call()); // consumed input cannot underflow/replay the queue counter
        ++scenarios;
    }
    for (int64_t pts : {HST_TIME_NONE, int64_t(300)}) {
        Fixture f; f.sink.isAudioPass_ = true; f.buffer->meta_.reset();
        f.desc.metaBuffer = nullptr; f.desc.metaLength = 0; f.pts = pts;
        assert(f.call());
        assert(copyCalls == 1 && f.desc.syncFramePts == static_cast<uint64_t>(pts == HST_TIME_NONE ? 700 : pts));
        assert(f.meta[0] == 0xa6);
        ++scenarios;
    }
    std::printf("%u controlled actual-function scenarios passed; no codec/plugin/guest evidence\n", scenarios);
}
