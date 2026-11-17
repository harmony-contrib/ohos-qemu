/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef QEMU_SENSOR_INPUT_H
#define QEMU_SENSOR_INPUT_H
#include "qemu_sensor_protocol.h"
#include <functional>
#include <memory>
#include <string>
#include <sys/types.h>

namespace OHOS::HDI::Sensor::Qemu {
struct InputConfig {
    std::string socketPath;
    uid_t writerUid;
};
class SensorInput final {
public:
    using Callback = std::function<void(const Acceleration&)>;
    explicit SensorInput(InputConfig config);
    ~SensorInput();
    SensorInput(const SensorInput&) = delete;
    SensorInput& operator=(const SensorInput&) = delete;
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
    static void Dispatch(const std::shared_ptr<State>&, Acceleration, uint64_t generation);
};
} // namespace OHOS::HDI::Sensor::Qemu
#endif
