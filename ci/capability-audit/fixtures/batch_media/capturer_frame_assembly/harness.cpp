// Executes the production byte assembler; no replacement of the class under test.
// External HDI/graph scheduling and real audio are separate native/guest gates.
#include "hpae_capture_frame_assembler.h"
#include <algorithm>
#include <cassert>
#include <condition_variable>
#include <iostream>
#include <thread>

using OHOS::AudioStandard::HPAE::HpaeCaptureFrameAssembler;
constexpr size_t ALIGN = 4;
constexpr size_t OUTPUT = 960 * ALIGN;
constexpr size_t READ = 8192;

std::vector<char> Challenge(size_t size, size_t offset = 0)
{
    std::vector<char> result(size);
    for (size_t n = 0; n < size; ++n) {
        result[n] = static_cast<char>(1 + ((n + offset) % 127));
    }
    return result;
}

void Drain(HpaeCaptureFrameAssembler &queue, uint64_t lease, std::vector<char> &output)
{
    while (queue.HasFrame(lease)) {
        assert(queue.PublishFrame(lease, [&](const char *frame) {
            output.insert(output.end(), frame, frame + OUTPUT);
        }));
    }
}

int main()
{
    HpaeCaptureFrameAssembler queue;
    auto lease = queue.Begin(OUTPUT, ALIGN, READ);
    assert(lease != 0);
    auto challenge = Challenge(18 * READ);
    std::vector<char> output;
    for (size_t n = 0; n < 17; ++n) {
        assert(queue.Append(lease, challenge.data() + n * READ, READ));
        Drain(queue, lease, output);
    }
    // The E failure: 17*2048 - 36*960 == 256 real frames remain.
    // An empty/error result cannot authorize publication or consume this prefix.
    assert(output.size() == 36 * OUTPUT);
    assert(!queue.HasFrame(lease));
    assert(!queue.PublishFrame(lease, [](const char *) { assert(false); }));
    assert(!queue.Append(lease, challenge.data(), 0));
    assert(!queue.Append(lease, nullptr, ALIGN));
    assert(!queue.Append(lease, challenge.data(), 3));
    assert(!queue.Append(lease, challenge.data(), READ + ALIGN));
    assert(queue.Append(lease, challenge.data() + 17 * READ, READ));
    Drain(queue, lease, output);
    assert(std::equal(output.begin(), output.end(), challenge.begin()));
    assert(std::none_of(output.begin(), output.end(), [](char value) { return value == 0; }));

    // Genuine aligned short reads accumulate exactly; no pad, drop or clock.
    queue.Invalidate(); lease = queue.Begin(OUTPUT, ALIGN, READ); output.clear();
    auto shortData = Challenge(OUTPUT * 3);
    size_t consumed = 0;
    for (size_t part : {size_t(508), size_t(1028), size_t(4), size_t(6140), size_t(3840)}) {
        size_t remaining = part;
        while (remaining != 0) {
            size_t size = std::min(remaining, READ);
            assert(queue.Append(lease, shortData.data() + consumed, size));
            consumed += size; remaining -= size; Drain(queue, lease, output);
        }
    }
    assert(consumed == shortData.size());
    assert(output == shortData);

    // A real read lease crossing lifecycle invalidation cannot publish or append.
    for (const char *boundary : {"Stop", "Flush", "Release", "Reset", "reopen"}) {
        (void)boundary;
        queue.Invalidate(); lease = queue.Begin(OUTPUT, ALIGN, READ);
        assert(queue.Append(lease, challenge.data(), ALIGN));
        std::mutex mutex; std::condition_variable cv; bool entered = false, proceed = false;
        bool accepted = true, published = true;
        std::thread delayedRead([&, oldLease = lease] {
            { std::unique_lock<std::mutex> lock(mutex); entered = true; cv.notify_one();
              cv.wait(lock, [&] { return proceed; }); }
            accepted = queue.Append(oldLease, challenge.data(), READ);
            published = queue.PublishFrame(oldLease, [](const char *) { assert(false); });
        });
        { std::unique_lock<std::mutex> lock(mutex); cv.wait(lock, [&] { return entered; }); }
        queue.Invalidate(); auto next = queue.Begin(OUTPUT, ALIGN, READ); assert(next != lease);
        { std::lock_guard<std::mutex> lock(mutex); proceed = true; cv.notify_one(); }
        delayedRead.join(); assert(!accepted && !published && !queue.IsCurrent(lease));
        auto fresh = Challenge(OUTPUT, 71); output.clear();
        assert(queue.Append(next, fresh.data(), fresh.size())); Drain(queue, next, output);
        assert(output == fresh);
    }

    // Geometry changes also retire a real lease and its incomplete cached bytes.
    lease = queue.Begin(OUTPUT, ALIGN, READ);
    assert(queue.Append(lease, challenge.data(), ALIGN));
    auto changed = queue.Begin(OUTPUT / 2, ALIGN, READ);
    assert(changed != lease && !queue.IsCurrent(lease));
    assert(!queue.HasFrame(changed));
    assert(queue.Begin(0, ALIGN, READ) == 0);
    assert(queue.Begin(OUTPUT, 0, READ) == 0);
    assert(queue.Begin(OUTPUT, ALIGN, READ - 1) == 0);
    std::cout << "production assembler: exact bytes, 704-frame boundary, short/empty reads and retired leases\n";
}
