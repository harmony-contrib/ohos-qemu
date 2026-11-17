/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef QEMU_GNSS_INPUT_H
#define QEMU_GNSS_INPUT_H
#include "qemu_gnss_protocol.h"
#include <functional>
#include <memory>
#include <string>
#include <sys/types.h>

namespace OHOS::QemuGnss {
struct InputConfig {
    std::string socketPath;
    uid_t writerUid;
};
class GnssInput final {
public:
    using Callback = std::function<void(const Fix&)>;
    explicit GnssInput(InputConfig config);
    ~GnssInput();
    GnssInput(const GnssInput&) = delete;
    GnssInput& operator=(const GnssInput&) = delete;
    bool Start();
    void Stop();
    bool IsRunning() const;
    bool Enable();
    bool Disable();
    bool SetBatch(int64_t samplingInterval, int64_t reportInterval);
    bool Register(const void* owner, Callback callback);
    bool Unregister(const void* owner);
private:
    struct State;
    std::shared_ptr<State> state_;
    static void* Run(void*);
    static void Serve(const std::shared_ptr<State>&, int);
    static void Dispatch(const std::shared_ptr<State>&, Fix, uint64_t generation);
};
} // namespace OHOS::QemuGnss
#endif
