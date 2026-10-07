// Real platform implementation is linked separately; not an ArkWeb session test.
#include <pthread.h>
#include <stdio.h>
#include <unistd.h>
#include "rtc_base/platform_thread_types.h"

namespace {
constexpr int THREADS = 16;
constexpr int CYCLES = 16;
struct Row {
    pid_t id;
    webrtc::PlatformThreadRef ref;
    bool valid;
};
struct Work {
    Row* row;
    pthread_barrier_t* barrier;
};
void* Worker(void* argument)
{
    auto* work = static_cast<Work*>(argument);
    auto& row = *work->row;
    row.id = webrtc::CurrentThreadId();
    row.ref = webrtc::CurrentThreadRef();
    row.valid = row.id > 0 && row.id == gettid() && row.id == webrtc::CurrentThreadId() &&
                webrtc::IsThreadRefEqual(row.ref, pthread_self());
    pthread_barrier_wait(work->barrier);
    pthread_barrier_wait(work->barrier);
    return nullptr;
}
}

int main()
{
    int errors = 0;
    int checks = 0;
    const auto mainId = webrtc::CurrentThreadId();
    const auto mainRef = webrtc::CurrentThreadRef();
    if (mainId <= 0 || mainId != gettid() || !webrtc::IsThreadRefEqual(mainRef, pthread_self())) {
        return 2;
    }
    for (int cycle = 0; cycle < CYCLES; ++cycle) {
        Row rows[THREADS] {};
        Work work[THREADS] {};
        pthread_t threads[THREADS] {};
        pthread_barrier_t barrier;
        if (pthread_barrier_init(&barrier, nullptr, THREADS + 1) != 0) {
            return 3;
        }
        for (int i = 0; i < THREADS; ++i) {
            work[i] = {&rows[i], &barrier};
            // Abort this isolated test process on creation failure: do not
            // leave already-created workers hanging at an undersized barrier.
            if (pthread_create(&threads[i], nullptr, Worker, &work[i]) != 0) {
                return 4;
            }
        }
        pthread_barrier_wait(&barrier);
        for (int i = 0; i < THREADS; ++i) {
            ++checks;
            errors += !rows[i].valid || rows[i].id == mainId || webrtc::IsThreadRefEqual(rows[i].ref, mainRef);
            for (int j = 0; j < i; ++j) {
                ++checks;
                errors += rows[i].id == rows[j].id || webrtc::IsThreadRefEqual(rows[i].ref, rows[j].ref);
            }
        }
        pthread_barrier_wait(&barrier);
        for (auto thread : threads) {
            if (pthread_join(thread, nullptr) != 0) {
                return 5;
            }
        }
        if (pthread_barrier_destroy(&barrier) != 0) {
            return 6;
        }
    }
    printf("{\"case\":\"real_webrtc_ohos_thread_id\",\"cycles\":%d,\"threads\":%d,\"checks\":%d,\"errors\":%d}\n",
           CYCLES, THREADS, checks, errors);
    return errors ? 1 : 0;
}
