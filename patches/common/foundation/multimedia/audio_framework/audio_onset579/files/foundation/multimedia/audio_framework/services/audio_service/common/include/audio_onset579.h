/* SPDX-License-Identifier: Apache-2.0
 * Bounded, observational lineage. No audio samples, queue ownership, DSP mode,
 * accepted-byte accounting or presentation clocks are changed by this header.
 */
#ifndef OHOS_AUDIO_ONSET579_H
#define OHOS_AUDIO_ONSET579_H
#include <array>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
namespace OHOS { namespace AudioStandard { namespace Onset579 {
constexpr uint32_t MAX_SPANS = 64;
constexpr uint32_t MAX_PCM = 16384;
struct Span {
    uint64_t cut = 0; // actual server read observation, never a queue timestamp
    uint32_t begin = 0; // frame in the cut's pre-fade PCM
    uint32_t out = 0;   // frame in the current actual PCM buffer
    uint32_t frames = 0;
};
struct Spans {
    std::array<Span, MAX_SPANS> spans {};
    uint32_t count = 0;
    bool valid = true;
    void Clear() { count = 0; valid = true; }
    void Unknown() { count = 0; valid = false; }
    void Add(Span s)
    {
        if (!valid || !s.cut || !s.frames) { return; }
        if (s.out > UINT32_MAX - s.frames || s.begin > UINT32_MAX - s.frames) { Unknown(); return; }
        for (uint32_t i = 0; i < count; ++i) {
            Span &p = spans[i];
            if (p.cut == s.cut && p.out + p.frames == s.out && p.begin + p.frames == s.begin) {
                p.frames += s.frames; return;
            }
        }
        if (count == MAX_SPANS) { Unknown(); return; }
        spans[count++] = s;
    }
    void Append(const Spans &other, uint32_t shift = 0)
    {
        if (!other.valid) { Unknown(); return; }
        for (uint32_t i = 0; i < other.count; ++i) {
            Span s = other.spans[i];
            if (s.out > UINT32_MAX - shift) { Unknown(); return; }
            s.out += shift; Add(s);
        }
    }
    Spans Slice(uint32_t first, uint32_t frames) const
    {
        Spans result;
        if (!valid || first > UINT32_MAX - frames) { result.Unknown(); return result; }
        for (uint32_t i = 0; i < count; ++i) {
            const Span &s = spans[i];
            uint32_t lo = std::max(first, s.out), hi = std::min(first + frames, s.out + s.frames);
            if (lo < hi) { result.Add({s.cut, s.begin + lo - s.out, lo - first, hi - lo}); }
        }
        return result;
    }
    void Consume(uint32_t frames) { *this = Slice(frames, UINT32_MAX - frames); }
};
enum class Kind : uint32_t { READ = 1, MIXED_PACKET = 2, READ_COMMIT = 3, UNKNOWN_PATH = 4 };
// These symbols live once in the existing audio_common DSO. The thread-local
// ReadCut is consumed on the same synchronous real OnStreamData call stack.
void Initialize(); // constructors/control thread only, never RT callbacks
uint64_t NewInstance();
void ClearRead();
uint64_t PrepareRead(uint64_t renderer, int32_t uid, uint32_t session, uint64_t ringFrame,
    uint32_t frames, uint32_t rate, uint32_t channels, uint32_t format,
    const void *first, size_t firstBytes, const void *second, size_t secondBytes);
void CommitRead(uint64_t cut, bool committed);
Spans TakeRead(int32_t uid, uint32_t session, uint32_t frames);
void Packet(uint64_t outputInstance, uint32_t rate, uint32_t channels, uint32_t format,
    const Spans &spans, const void *bytes, size_t byteCount);
} } }
#endif
