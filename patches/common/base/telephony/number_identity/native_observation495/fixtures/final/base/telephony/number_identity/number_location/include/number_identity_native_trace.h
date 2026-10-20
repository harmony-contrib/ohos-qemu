/* Diagnostic observations only; no business verdict or caller authority. */
#ifndef OHOS_NUMBER_IDENTITY_NATIVE_TRACE495_H
#define OHOS_NUMBER_IDENTITY_NATIVE_TRACE495_H

#include <atomic>
#include <cerrno>
#include <cstdint>
#include <string>
#include <time.h>
#include <unistd.h>
#include "number_identity_log_wrapper.h"

namespace OHOS {
namespace Telephony {
namespace NumberNativeObservation495 {

// Hidden inline functions have one ODR state inside the provider DSO.  Other
// DSOs cannot preempt this counter.  IDs and record sequence share this counter;
// gaps are valid, zero/wrap or ambiguous concurrent histories are not proof.
__attribute__((visibility("hidden"))) inline uint64_t NextId()
{
    static std::atomic<uint64_t> next { 1 };
    return next.fetch_add(1, std::memory_order_relaxed);
}

__attribute__((visibility("hidden"))) inline int Route(const std::string &uri)
{
    if (uri == "datashare:///com.ohos.numberlocationability") { return 1; }
    if (uri == "datashare:///com.ohos.numbermarkability/number_mark_info") { return 2; }
    if (uri == "datashare:///com.ohos.numbermarkability/api/process_number") { return 3; }
    if (uri == "datashare:///com.ohos.numbermarkability/number_mark") { return 4; }
    return 0;
}

__attribute__((visibility("hidden"))) inline void Observe(const char *event, uint64_t instance,
    uint64_t connection, uint64_t request, int route, int result,
    int callingPid = 0, int callingUid = 0, uint32_t callingToken = 0)
{
    const int savedErrno = errno;
    struct timespec observedTime = {};
    const bool clockOk = clock_gettime(CLOCK_MONOTONIC, &observedTime) == 0;
    const uint64_t monotonicNs = clockOk ? static_cast<uint64_t>(observedTime.tv_sec) * 1000000000ULL +
        static_cast<uint64_t>(observedTime.tv_nsec) : 0;
    const uint64_t sequence = NextId();
    NUMBER_IDENTITY_LOGI("NUMBER_NATIVE495 v=1 event=%{public}s seq=%{public}llu mono_ns=%{public}llu "
        "pid=%{public}d tid=%{public}d instance=%{public}llu connection=%{public}llu request=%{public}llu "
        "route=%{public}d result=%{public}d caller_pid=%{public}d caller_uid=%{public}d caller_token=%{public}u",
        event, static_cast<unsigned long long>(sequence), static_cast<unsigned long long>(monotonicNs), getpid(), gettid(),
        static_cast<unsigned long long>(instance), static_cast<unsigned long long>(connection),
        static_cast<unsigned long long>(request), route, result, callingPid, callingUid, callingToken);
    errno = savedErrno;
}
} // namespace NumberNativeObservation495
} // namespace Telephony
} // namespace OHOS
#endif // OHOS_NUMBER_IDENTITY_NATIVE_TRACE495_H
