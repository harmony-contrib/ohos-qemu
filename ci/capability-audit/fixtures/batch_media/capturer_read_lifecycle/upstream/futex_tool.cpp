/*
 * Copyright (c) 2024 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#ifndef LOG_TAG
#define LOG_TAG "FutexTool"
#endif

#include "futex_tool.h"

#include <cinttypes>
#include <ctime>
#include "linux/futex.h"
#include <sys/syscall.h>

#include "audio_errors.h"
#include "audio_service_log.h"
#include "audio_utils.h"

namespace OHOS {
namespace AudioStandard {
namespace {
const int32_t WAIT_TRY_COUNT = 50;
const int64_t SEC_TO_NANOSEC = 1000000000;
}
// FUTEX_WAIT using relative timeout value.
void TimeoutToRelativeTime(int64_t timeout, struct timespec &realtime)
{
    int64_t timeoutNanoSec = timeout % SEC_TO_NANOSEC;
    int64_t timeoutSec = timeout / SEC_TO_NANOSEC;

    realtime.tv_nsec = timeoutNanoSec;
    realtime.tv_sec = timeoutSec;
}

FutexCode FutexTool::FutexWait(std::atomic<uint32_t> *futexPtr, int64_t timeout, const std::function<bool(void)> &pred)
{
    CHECK_AND_RETURN_RET_LOG(futexPtr != nullptr, FUTEX_INVALID_PARAMS, "futexPtr is null");
    CHECK_AND_RETURN_RET_LOG(pred, FUTEX_INVALID_PARAMS, "pred err");
    Trace trace("FutexTool::FutexWait");
    uint32_t current = futexPtr->load();
    if (current != IS_READY && current != IS_NOT_READY && current != IS_PRE_EXIT) {
        AUDIO_ERR_LOG("failed: invalid param:%{public}u", current);
        return FUTEX_INVALID_PARAMS;
    }

    int64_t timeIn = ClockTime::GetCurNano();
    int64_t cost = 0;
    struct timespec waitTime;
    if (timeout > 0) { TimeoutToRelativeTime(timeout, waitTime); }

    long res = 0;
    int32_t tryCount = 0;
    while (tryCount < WAIT_TRY_COUNT) {
        uint32_t expect = IS_READY;
        if (!futexPtr->compare_exchange_strong(expect, IS_NOT_READY)) {
            if (expect == IS_PRE_EXIT) {
                AUDIO_ERR_LOG("failed with invalid status:%{public}u", expect);
                return FUTEX_OPERATION_FAILED;
            }
        }

        if (pred()) { return FUTEX_SUCCESS; }

        cost = ClockTime::GetCurNano() - timeIn;
        if (cost >= timeout && timeout > 0) {
            Trace::Count("FutexTool::WaitTimeoutState", static_cast<int64_t>(futexPtr->load()));
            return FUTEX_TIMEOUT;
        }
        if (cost < timeout && timeout > 0) {
            TimeoutToRelativeTime(timeout - cost, waitTime);
        }

        Trace traceSyscall(std::string("syscall expect: ") + std::to_string(expect));
        res = syscall(__NR_futex, futexPtr, FUTEX_WAIT, IS_NOT_READY, (timeout <= 0 ? NULL : &waitTime), NULL, 0);
        auto sysErr = errno;

        if (pred()) { return FUTEX_SUCCESS; }

        if ((res != 0) && (sysErr == ETIMEDOUT)) {
            Trace::Count("FutexTool::WaitTimeoutState", static_cast<int64_t>(futexPtr->load()));
            AUDIO_WARNING_LOG("wait:%{public}" PRId64"ns timeout, result:%{public}ld sysErr[%{public}d]:%{public}s",
                timeout, res, sysErr, strerror(sysErr));
            return FUTEX_TIMEOUT;
        }

        if ((res != 0) && (sysErr != EAGAIN)) {
            AUDIO_WARNING_LOG("result:%{public}ld, sysErr[%{public}d]:%{public}s", res, sysErr, strerror(sysErr));
        }
        tryCount++;
    }
    if (tryCount >= WAIT_TRY_COUNT) { AUDIO_ERR_LOG("too much spurious wake-up"); }
    return FUTEX_OPERATION_FAILED;
}

FutexCode FutexTool::FutexWake(std::atomic<uint32_t> *futexPtr, uint32_t wakeVal)
{
    CHECK_AND_RETURN_RET_LOG(futexPtr != nullptr, FUTEX_INVALID_PARAMS, "futexPtr is null");
    Trace trace("FutexTool::FutexWake");
    uint32_t current = futexPtr->load();
    Trace::Count("FutexTool::WakeCurrent", static_cast<int64_t>(current));
    Trace::Count("FutexTool::WakeVal", static_cast<int64_t>(wakeVal));
    if (current != IS_READY && current != IS_NOT_READY && current != IS_PRE_EXIT) {
        AUDIO_ERR_LOG("failed: invalid param:%{public}u", current);
        return FUTEX_INVALID_PARAMS;
    }
    if (wakeVal == IS_PRE_EXIT) {
        futexPtr->store(IS_PRE_EXIT);
        syscall(__NR_futex, futexPtr, FUTEX_WAKE, INT_MAX, NULL, NULL, 0);
        return FUTEX_SUCCESS;
    }
    uint32_t expect = IS_NOT_READY;
    if (futexPtr->compare_exchange_strong(expect, IS_READY)) {
        Trace::Count("FutexTool::WakeHit", 1);
        Trace traceSyscall(std::string("syscall expect: ") + std::to_string(expect));
        long res = syscall(__NR_futex, futexPtr, FUTEX_WAKE, INT_MAX, NULL, NULL, 0);
        if (res < 0) {
            AUDIO_ERR_LOG("failed:%{public}ld, errno[%{public}d]:%{public}s", res, errno, strerror(errno));
            return FUTEX_OPERATION_FAILED;
        }
        Trace::Count("FutexTool::WakeSyscallRes", res);
    } else {
        Trace::Count("FutexTool::WakeHit", 0);
        Trace::Count("FutexTool::WakeExpectAfterCas", static_cast<int64_t>(expect));
    }
    return FUTEX_SUCCESS;
}
} // namespace AudioStandard
} // namespace OHOS
