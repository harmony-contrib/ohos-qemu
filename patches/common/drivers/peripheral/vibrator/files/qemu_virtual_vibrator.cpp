/*
 * Copyright (c) 2026 OpenHarmony QEMU contributors.
 * Licensed under the Apache License, Version 2.0.
 */

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <new>
#include <string>
#include <vector>

#include "hdf_base.h"
#include "hdf_log.h"
#include "ivibrator_interface_vdi.h"

#define HDF_LOG_TAG qemu_virtual_vibrator

namespace OHOS {
namespace HDI {
namespace Vibrator {
namespace V1_1 {
namespace {

using Clock = std::chrono::steady_clock;
using DeviceVibratorInfo = OHOS::HDI::Vibrator::V2_0::DeviceVibratorInfo;

constexpr int32_t QEMU_DEVICE_ID = 0;
constexpr int32_t QEMU_VIBRATOR_ID = 0;
constexpr int32_t QEMU_VIBRATOR_POSITION = 0;
constexpr int32_t QEMU_PRESET_DURATION_MS = 100;

bool IsQemuVibrator(const DeviceVibratorInfo &info)
{
    const bool deviceMatches = info.deviceId == -1 || info.deviceId == QEMU_DEVICE_ID;
    const bool vibratorMatches = info.vibratorId == -1 || info.vibratorId == QEMU_VIBRATOR_ID;
    return deviceMatches && vibratorMatches;
}

class QemuVirtualVibrator final : public IVibratorInterfaceVdi {
public:
    int32_t Init() override
    {
        std::lock_guard<std::mutex> lock(mutex_);
        running_ = false;
        hasDeadline_ = false;
        return HDF_SUCCESS;
    }

    int32_t StartOnce(uint32_t duration) override
    {
        if (duration == 0) {
            return HDF_ERR_INVALID_PARAM;
        }
        SetTimedState(duration);
        return HDF_SUCCESS;
    }

    int32_t Start(const std::string &effectType) override
    {
        if (effectType.empty()) {
            return HDF_ERR_INVALID_PARAM;
        }
        SetTimedState(QEMU_PRESET_DURATION_MS);
        return HDF_SUCCESS;
    }

    int32_t Stop(HdfVibratorModeVdi mode) override
    {
        if (mode < VDI_VIBRATOR_MODE_ONCE || mode >= VDI_VIBRATOR_MODE_BUTT) {
            return HDF_ERR_INVALID_PARAM;
        }
        StopState();
        return HDF_SUCCESS;
    }

    int32_t GetVibratorInfo(std::vector<HdfVibratorInfoVdi> &vibratorInfo) override
    {
        vibratorInfo.clear();
        vibratorInfo.push_back({
            false,
            false,
            0,
            0,
            0,
            0,
            QEMU_DEVICE_ID,
            QEMU_VIBRATOR_ID,
            QEMU_VIBRATOR_POSITION,
            1,
        });
        return HDF_SUCCESS;
    }

    int32_t GetDeviceVibratorInfo(std::vector<HdfVibratorInfoVdi> &vibratorInfo) override
    {
        return GetVibratorInfo(vibratorInfo);
    }

    int32_t EnableVibratorModulation(uint32_t, uint16_t, int16_t) override
    {
        return HDF_ERR_NOT_SUPPORT;
    }

    int32_t EnableCompositeEffect(const HdfCompositeEffectVdi &effect) override
    {
        if (effect.effects.empty()) {
            return HDF_ERR_INVALID_PARAM;
        }

        uint64_t duration = 0;
        for (const auto &item : effect.effects) {
            if (effect.type == VDI_EFFECT_TYPE_TIME) {
                if (item.timeEffect.delay < 0 || item.timeEffect.time <= 0) {
                    return HDF_ERR_INVALID_PARAM;
                }
                duration += static_cast<uint64_t>(item.timeEffect.delay) +
                    static_cast<uint64_t>(item.timeEffect.time);
            } else if (effect.type == VDI_EFFECT_TYPE_PRIMITIVE) {
                if (item.primitiveEffect.delay < 0) {
                    return HDF_ERR_INVALID_PARAM;
                }
                duration += static_cast<uint64_t>(item.primitiveEffect.delay) + QEMU_PRESET_DURATION_MS;
            } else {
                return HDF_ERR_INVALID_PARAM;
            }
        }
        SetTimedState(static_cast<uint32_t>(std::min<uint64_t>(duration, UINT32_MAX)));
        return HDF_SUCCESS;
    }

    int32_t GetEffectInfo(const std::string &effectType, HdfEffectInfoVdi &effectInfo) override
    {
        effectInfo.duration = effectType.empty() ? 0 : QEMU_PRESET_DURATION_MS;
        effectInfo.isSupportEffect = !effectType.empty();
        return effectType.empty() ? HDF_ERR_INVALID_PARAM : HDF_SUCCESS;
    }

    int32_t IsVibratorRunning(bool &state) override
    {
        std::lock_guard<std::mutex> lock(mutex_);
        RefreshStateLocked();
        state = running_;
        return HDF_SUCCESS;
    }

    int32_t PlayHapticPattern(const HapticPaketVdi &) override
    {
        return HDF_ERR_NOT_SUPPORT;
    }

    int32_t GetHapticCapacity(HapticCapacityVdi &capacity) override
    {
        capacity = {false, false, false, QEMU_VIBRATOR_ID, false, 0};
        return HDF_SUCCESS;
    }

    int32_t GetHapticStartUpTime(int32_t, int32_t &startUpTime) override
    {
        startUpTime = 0;
        return HDF_ERR_NOT_SUPPORT;
    }

    int32_t StartByIntensity(const std::string &, uint16_t) override
    {
        return HDF_ERR_NOT_SUPPORT;
    }

    int32_t StartOnce(const DeviceVibratorInfo &info, uint32_t duration) override
    {
        return IsQemuVibrator(info) ? StartOnce(duration) : HDF_ERR_INVALID_PARAM;
    }

    int32_t Start(const DeviceVibratorInfo &info, const std::string &effectType) override
    {
        return IsQemuVibrator(info) ? Start(effectType) : HDF_ERR_INVALID_PARAM;
    }

    int32_t Stop(const DeviceVibratorInfo &info, HdfVibratorModeVdi mode) override
    {
        return IsQemuVibrator(info) ? Stop(mode) : HDF_ERR_INVALID_PARAM;
    }

    int32_t GetDeviceVibratorInfo(
        const DeviceVibratorInfo &info, std::vector<HdfVibratorInfoVdi> &vibratorInfo) override
    {
        return IsQemuVibrator(info) ? GetVibratorInfo(vibratorInfo) : HDF_ERR_INVALID_PARAM;
    }

    int32_t EnableVibratorModulation(
        const DeviceVibratorInfo &info, uint32_t duration, uint16_t intensity, int16_t frequency) override
    {
        return IsQemuVibrator(info) ? EnableVibratorModulation(duration, intensity, frequency) :
            HDF_ERR_INVALID_PARAM;
    }

    int32_t EnableCompositeEffect(
        const DeviceVibratorInfo &info, const HdfCompositeEffectVdi &effect) override
    {
        return IsQemuVibrator(info) ? EnableCompositeEffect(effect) : HDF_ERR_INVALID_PARAM;
    }

    int32_t GetEffectInfo(
        const DeviceVibratorInfo &info, const std::string &effectType, HdfEffectInfoVdi &effectInfo) override
    {
        return IsQemuVibrator(info) ? GetEffectInfo(effectType, effectInfo) : HDF_ERR_INVALID_PARAM;
    }

    int32_t IsVibratorRunning(const DeviceVibratorInfo &info, bool &state) override
    {
        return IsQemuVibrator(info) ? IsVibratorRunning(state) : HDF_ERR_INVALID_PARAM;
    }

    int32_t PlayHapticPattern(const DeviceVibratorInfo &info, const HapticPaketVdi &pkg) override
    {
        return IsQemuVibrator(info) ? PlayHapticPattern(pkg) : HDF_ERR_INVALID_PARAM;
    }

    int32_t GetHapticCapacity(const DeviceVibratorInfo &info, HapticCapacityVdi &capacity) override
    {
        return IsQemuVibrator(info) ? GetHapticCapacity(capacity) : HDF_ERR_INVALID_PARAM;
    }

    int32_t GetHapticStartUpTime(const DeviceVibratorInfo &info, int32_t mode, int32_t &startUpTime) override
    {
        return IsQemuVibrator(info) ? GetHapticStartUpTime(mode, startUpTime) : HDF_ERR_INVALID_PARAM;
    }

    int32_t StartByIntensity(
        const DeviceVibratorInfo &info, const std::string &effectType, uint16_t intensity) override
    {
        return IsQemuVibrator(info) ? StartByIntensity(effectType, intensity) : HDF_ERR_INVALID_PARAM;
    }

    int32_t StopVibrateBySessionId(const DeviceVibratorInfo &info, uint32_t) override
    {
        if (!IsQemuVibrator(info)) {
            return HDF_ERR_INVALID_PARAM;
        }
        StopState();
        return HDF_SUCCESS;
    }

private:
    void SetTimedState(uint32_t duration)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        running_ = true;
        hasDeadline_ = true;
        deadline_ = Clock::now() + std::chrono::milliseconds(duration);
        HDF_LOGI("QEMU virtual vibrator started for %{public}u ms", duration);
    }

    void StopState()
    {
        std::lock_guard<std::mutex> lock(mutex_);
        running_ = false;
        hasDeadline_ = false;
        HDF_LOGI("QEMU virtual vibrator stopped");
    }

    void RefreshStateLocked()
    {
        if (running_ && hasDeadline_ && Clock::now() >= deadline_) {
            running_ = false;
            hasDeadline_ = false;
        }
    }

    std::mutex mutex_;
    bool running_ = false;
    bool hasDeadline_ = false;
    Clock::time_point deadline_ {};
};

int32_t CreateVdiInstance(struct HdfVdiBase *vdiBase)
{
    if (vdiBase == nullptr) {
        return HDF_ERR_INVALID_PARAM;
    }
    auto *wrapper = reinterpret_cast<VdiWrapperVibrator *>(vdiBase);
    wrapper->vibratorModule = new (std::nothrow) QemuVirtualVibrator();
    if (wrapper->vibratorModule == nullptr) {
        return HDF_ERR_MALLOC_FAIL;
    }
    return wrapper->vibratorModule->Init();
}

int32_t DestroyVdiInstance(struct HdfVdiBase *vdiBase)
{
    if (vdiBase == nullptr) {
        return HDF_ERR_INVALID_PARAM;
    }
    auto *wrapper = reinterpret_cast<VdiWrapperVibrator *>(vdiBase);
    delete wrapper->vibratorModule;
    wrapper->vibratorModule = nullptr;
    return HDF_SUCCESS;
}

struct VdiWrapperVibrator g_qemuVibratorVdi = {
    .base = {
        .moduleVersion = 1,
        .moduleName = "qemu_virtual_vibrator",
        .CreateVdiInstance = CreateVdiInstance,
        .DestoryVdiInstance = DestroyVdiInstance,
    },
    .vibratorModule = nullptr,
};

} // namespace

extern "C" HDF_VDI_INIT(g_qemuVibratorVdi);

} // namespace V1_1
} // namespace Vibrator
} // namespace HDI
} // namespace OHOS
