/* Copyright (c) 2026 OpenHarmony QEMU contributors. Licensed under Apache-2.0. */
// Real HDI IPC/runtime test, not a substitute for normal-app CAPI/JSON decoding.
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>
#include <unistd.h>
#include "v2_0/ivibrator_interface.h"

using namespace OHOS::HDI::Vibrator::V2_0;
using Clock = std::chrono::steady_clock;

static const char *Architecture()
{
#if defined(__aarch64__)
    return "arm64";
#elif defined(__arm__)
    return "armv7a";
#elif defined(__x86_64__)
    return "x86_64";
#else
    return "unknown";
#endif
}

static bool Check(const char *name, bool pass)
{
    std::printf("{\"kind\":\"case\",\"name\":\"%s\",\"pass\":%s}\n", name, pass ? "true" : "false");
    std::fflush(stdout);
    return pass;
}

static CompositeEffect Time(int32_t delay, int32_t duration, uint16_t intensity = 50)
{
    CompositeEffect value {};
    value.timeEffect = {delay, duration, intensity, 0};
    return value;
}

class RuntimeProbe {
public:
    OHOS::sptr<IVibratorInterface> driver;
    const DeviceVibratorInfo device {0, 0};

    ~RuntimeProbe()
    {
        if (driver != nullptr) {
            // Always clear only this isolated QA VM's virtual effect on exit.
            driver->Stop(device, HDF_VIBRATOR_MODE_ONCE);
        }
    }

    bool Running(bool expected)
    {
        bool state = !expected;
        return driver->IsVibratorRunning(device, state) == 0 && state == expected;
    }

    bool ExpiredBetween(Clock::time_point began, int64_t minimum, int64_t maximum)
    {
        while (true) {
            bool state = true;
            if (driver->IsVibratorRunning(device, state) != 0) {
                return false;
            }
            const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - began).count();
            if (!state) {
                return elapsed >= minimum && elapsed <= maximum;
            }
            if (elapsed > maximum) {
                return false;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }

    bool Run()
    {
        driver = IVibratorInterface::Get();
        if (!Check("connect", driver != nullptr)) {
            return false;
        }
        HapticCapacity capacity {};
        if (!Check("time_capacity_only", driver->GetHapticCapacity(device, capacity) == 0 &&
            capacity.isSupportTimeDelay && !capacity.isSupportHdHaptic && !capacity.isSupportPresetMapping)) {
            return false;
        }
        std::vector<HdfVibratorInfo> info;
        if (!Check("info_local", driver->GetVibratorInfo(info) == 0 && info.size() == 1 &&
            info[0].deviceId == 0 && info[0].vibratorId == 0 && info[0].isLocal == 1 &&
            !info[0].isSupportIntensity && !info[0].isSupportFrequency)) {
            return false;
        }
        if (!Check("oneshot_running", driver->StartOnce(device, 1000) == 0 && Running(true)) ||
            !Check("oneshot_cancel", driver->Stop(device, HDF_VIBRATOR_MODE_ONCE) == 0 && Running(false))) {
            return false;
        }
        auto began = Clock::now();
        if (!Check("oneshot_expiry", driver->StartOnce(device, 200) == 0 && Running(true) &&
            ExpiredBetween(began, 150, 1500))) {
            return false;
        }
        HdfEffectInfo effectInfo {-1, false};
        if (!Check("preset_known", driver->GetEffectInfo(device, "haptic.clock.timer", effectInfo) == 0 &&
            effectInfo.isSupportEffect && effectInfo.duration == 100 &&
            driver->Start(device, "haptic.clock.timer") == 0 && Running(true) &&
            driver->Stop(device, HDF_VIBRATOR_MODE_PRESET) == 0 && Running(false)) ||
            !Check("preset_unknown_no_change", driver->StartOnce(device, 5000) == 0 &&
            driver->GetEffectInfo(device, "qemu.unknown.effect", effectInfo) == 0 &&
            !effectInfo.isSupportEffect && effectInfo.duration == 0 &&
            driver->Start(device, "qemu.unknown.effect") != 0 && Running(true))) {
            return false;
        }
        HdfCompositeEffect sequence {HDF_EFFECT_TYPE_TIME,
            {Time(0, 1000), Time(1250, 250), Time(250, 0, 0)}};
        began = Clock::now();
        if (!Check("upstream_stop_marker", driver->EnableCompositeEffect(device, sequence) == 0 && Running(true)) ||
            !Check("timeline_no_double_count", ExpiredBetween(began, 1300, 2200))) {
            return false;
        }
        sequence.compositeEffects = {Time(-1, 20)};
        if (!Check("invalid_sequence_no_change", driver->StartOnce(device, 5000) == 0 &&
            driver->EnableCompositeEffect(device, sequence) != 0 && Running(true)) ||
            !Check("wrong_device_no_change", driver->StartOnce({1, 0}, 10000) != 0 && Running(true)) ||
            !Check("unsupported_modulation", driver->EnableVibratorModulation(device, 1000, 50, 50) != 0 && Running(true)) ||
            !Check("cleaned", driver->Stop(device, HDF_VIBRATOR_MODE_ONCE) == 0 && Running(false))) {
            return false;
        }
        return true;
    }
};

int main(int argc, char **argv)
{
    if (argc != 2 || std::strlen(argv[1]) != 32 ||
        std::strspn(argv[1], "0123456789abcdef") != 32 || getuid() != 0 || geteuid() != 0) {
        std::fprintf(stderr, "Usage (isolated NEW QA guest root): vibrator_hdi NEW_32_HEX_RUN_ID\n");
        return 2;
    }
    std::printf("{\"kind\":\"run\",\"run_id\":\"%s\",\"arch\":\"%s\",\"uid\":%u,\"euid\":%u}\n",
        argv[1], Architecture(), static_cast<unsigned>(getuid()), static_cast<unsigned>(geteuid()));
    RuntimeProbe probe;
    if (!probe.Run()) {
        return 1;
    }
    std::printf("{\"kind\":\"complete\",\"run_id\":\"%s\"}\n", argv[1]);
    return 0;
}
