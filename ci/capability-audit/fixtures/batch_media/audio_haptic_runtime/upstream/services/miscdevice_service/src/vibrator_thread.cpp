/*
 * Copyright (c) 2022 Huawei Device Co., Ltd.
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

#include "vibrator_thread.h"

#include <sys/prctl.h>

#include "custom_vibration_matcher.h"
#ifdef OHOS_BUILD_ENABLE_QOS
#include "concurrent_task_client.h"
#include "qos.h"
#endif // OHOS_BUILD_ENABLE_QOS
#include "sensors_errors.h"

#undef LOG_TAG
#define LOG_TAG "VibratorThread"

namespace OHOS {
namespace Sensors {
namespace {
const std::string VIBRATE_CONTROL_THREAD_NAME = "OS_VibControl";
constexpr int32_t DELAY_TIME1 = 5;    /** ms */
constexpr int32_t DELAY_TIME2 = 10;   /** ms */
constexpr size_t RETRY_NUMBER = 6;
constexpr int32_t MAX_VIBRATE_COUNT = 1000;
#ifdef HDF_DRIVERS_INTERFACE_VIBRATOR
constexpr size_t COMPOSITE_EFFECT_PART = 128;
#endif // HDF_DRIVERS_INTERFACE_VIBRATOR
}  // namespace

bool VibratorThread::Run()
{
    CALL_LOG_ENTER;
    prctl(PR_SET_NAME, VIBRATE_CONTROL_THREAD_NAME.c_str());
#ifdef OHOS_BUILD_ENABLE_QOS
    SetQosForThread();
#endif // OHOS_BUILD_ENABLE_QOS
    VibrateInfo info = GetCurrentVibrateInfo();
    VibratorIdentifierIPC identifier = GetCurrentVibrateParams();
    std::vector<HdfWaveInformation> waveInfos = GetCurrentWaveInfo();
    MISC_HILOGD("info.mode:%{public}s, deviceId:%{public}d, vibratorId:%{public}d",
                info.mode.c_str(), identifier.deviceId, identifier.vibratorId);
    if (info.mode == VIBRATE_TIME) {
        int32_t ret = PlayOnce(info, identifier);
        if (ret != SUCCESS) {
            MISC_HILOGE("Play once vibration fail, package:%{public}s", info.packageName.c_str());
            return false;
        }
    } else if (info.mode == VIBRATE_PRESET) {
        int32_t ret = PlayEffect(info, identifier);
        if (ret != SUCCESS) {
            MISC_HILOGE("Play effect vibration fail, package:%{public}s", info.packageName.c_str());
            return false;
        }
    } else if (info.mode == VIBRATE_CUSTOM_HD) {
        int32_t ret = PlayCustomByHdHptic(info, identifier);
        if (ret != SUCCESS) {
            MISC_HILOGE("Play custom vibration by hd haptic fail, package:%{public}s", info.packageName.c_str());
            return false;
        }
    } else if (info.mode == VIBRATE_CUSTOM_COMPOSITE_EFFECT || info.mode == VIBRATE_CUSTOM_COMPOSITE_TIME) {
#ifdef HDF_DRIVERS_INTERFACE_VIBRATOR
        int32_t ret = PlayCustomByCompositeEffect(info, identifier, waveInfos);
        if (ret != SUCCESS) {
            MISC_HILOGE("Play custom vibration by composite effect fail, package:%{public}s", info.packageName.c_str());
            return false;
        }
#endif // HDF_DRIVERS_INTERFACE_VIBRATOR
    }
    return false;
}

int32_t VibratorThread::PlayOnce(const VibrateInfo &info, const VibratorIdentifierIPC& identifier)
{
    std::unique_lock<std::mutex> vibrateLck(vibrateMutex_);
    int32_t ret = VibratorDevice.StartOnce(identifier, static_cast<uint32_t>(info.duration));
    if (ret != SUCCESS) {
        MISC_HILOGE("StartOnce fail, duration:%{public}d", info.duration);
        return ERROR;
    }
    cv_.wait_for(vibrateLck, std::chrono::milliseconds(info.duration), [this] { return exitFlag_.load(); });
    if (exitFlag_) {
#ifdef HDF_DRIVERS_INTERFACE_VIBRATOR
        VibratorDevice.Stop(identifier, HDF_VIBRATOR_MODE_ONCE);
#endif // HDF_DRIVERS_INTERFACE_VIBRATOR
        MISC_HILOGD("Stop duration:%{public}d, package:%{public}s", info.duration, info.packageName.c_str());
        return SUCCESS;
    }
    return SUCCESS;
}

void VibratorThread::HandleMultipleVibrations(const VibratorIdentifierIPC& identifier)
{
    if (VibratorDevice.IsVibratorRunning(identifier)) {
        VibratorDevice.Stop(identifier, HDF_VIBRATOR_MODE_PRESET);
        VibratorDevice.Stop(identifier, HDF_VIBRATOR_MODE_HDHAPTIC);
        for (size_t i = 0; i < RETRY_NUMBER; i++) {
            if (!VibratorDevice.IsVibratorRunning(identifier)) {
                MISC_HILOGI("No running vibration");
                return;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(DELAY_TIME1));
        }
        MISC_HILOGW("Unstopped vibration");
    }
}

int32_t VibratorThread::PlayEffect(const VibrateInfo &info, const VibratorIdentifierIPC& identifier)
{
    std::unique_lock<std::mutex> vibrateLck(vibrateMutex_);
    if (info.count < 0 || info.count > MAX_VIBRATE_COUNT) {
        MISC_HILOGE("Vibratorinfo's count is invalid, count:%{public}d", info.count);
        return ERROR;
    }
    for (int32_t i = 0; i < info.count; ++i) {
        std::string effect = info.effect;
        int32_t duration = info.duration;
        if (i >= 1) { /**Multiple vibration treatment*/
            HandleMultipleVibrations(identifier);
            duration += DELAY_TIME2;
        }
        int32_t ret = VibratorDevice.StartByIntensity(identifier, effect, info.intensity);
        if (ret != SUCCESS) {
            MISC_HILOGE("Vibrate effect %{public}s failed, ", effect.c_str());
            return ERROR;
        }
        cv_.wait_for(vibrateLck, std::chrono::milliseconds(duration), [this] { return exitFlag_.load(); });
        if (exitFlag_) {
#ifdef HDF_DRIVERS_INTERFACE_VIBRATOR
            VibratorDevice.Stop(identifier, HDF_VIBRATOR_MODE_PRESET);
#endif // HDF_DRIVERS_INTERFACE_VIBRATOR
            MISC_HILOGD("Stop effect:%{public}s, package:%{public}s", effect.c_str(), info.packageName.c_str());
            return SUCCESS;
        }
    }
    return SUCCESS;
}

int32_t VibratorThread::PlayCustomByHdHptic(const VibrateInfo &info, const VibratorIdentifierIPC& identifier)
{
    std::unique_lock<std::mutex> vibrateLck(vibrateMutex_);
    const std::vector<VibratePattern> &patterns = info.package.patterns;
    size_t patternSize = patterns.size();
    for (size_t i = 0; i < patternSize; ++i) {
        int32_t delayTime;
        if (i == 0) {
            delayTime = patterns[i].startTime;
        } else {
            delayTime = patterns[i].startTime - patterns[i - 1].startTime;
        }
        cv_.wait_for(vibrateLck, std::chrono::milliseconds(delayTime), [this] { return exitFlag_.load(); });
        if (exitFlag_) {
#ifdef HDF_DRIVERS_INTERFACE_VIBRATOR
            VibratorDevice.Stop(identifier, HDF_VIBRATOR_MODE_HDHAPTIC);
#endif // HDF_DRIVERS_INTERFACE_VIBRATOR
            MISC_HILOGD("Stop hd haptic, package:%{public}s", info.packageName.c_str());
            return SUCCESS;
        }
#ifdef HDF_DRIVERS_INTERFACE_VIBRATOR
        HandleMultipleVibrations(identifier);
#endif // HDF_DRIVERS_INTERFACE_VIBRATOR
        int32_t ret = VibratorDevice.PlayPattern(identifier, patterns[i]);
        if (ret != SUCCESS) {
            MISC_HILOGE("Vibrate hd haptic failed");
            return ERROR;
        }
    }
    return SUCCESS;
}

VibrateInfo VibratorThread::copyInfoWithIndexEvents(const VibrateInfo& originalInfo,
    const VibratorIdentifierIPC& identifier)
{
    VibrateInfo newInfo = originalInfo;
    VibratePackage newPackage;
    int32_t parseDuration = 0;

    for (const auto& pattern : originalInfo.package.patterns) {
        VibratePattern newPattern;
        newPattern.startTime = pattern.startTime;
        newPattern.patternDuration = pattern.patternDuration;

        for (const auto& event : pattern.events) {
            if (event.index == 0 || event.index == identifier.position) {
                newPattern.events.push_back(event);
                parseDuration = event.duration;
            }
        }

        if (!newPattern.events.empty()) {
            newPackage.patterns.push_back(newPattern);
        }
    }

    newInfo.package = newPackage;
    newInfo.package.packageDuration = parseDuration;
    return newInfo;
}

#ifdef HDF_DRIVERS_INTERFACE_VIBRATOR
int32_t VibratorThread::PlayCustomByCompositeEffect(const VibrateInfo &info, const VibratorIdentifierIPC& identifier,
    const std::vector<HdfWaveInformation> &waveInfo)
{
    CustomVibrationMatcher matcher(identifier, waveInfo);
    HdfCompositeEffect hdfCompositeEffect;
    VibrateInfo newInfo = copyInfoWithIndexEvents(info, identifier);
    if (newInfo.mode == VIBRATE_CUSTOM_COMPOSITE_EFFECT) {
        hdfCompositeEffect.type = HDF_EFFECT_TYPE_PRIMITIVE;
        int32_t ret = matcher.TransformEffect(newInfo.package, hdfCompositeEffect.compositeEffects);
        if (ret != SUCCESS) {
            MISC_HILOGE("Transform pattern to predefined wave fail");
            return ERROR;
        }
    } else if (newInfo.mode == VIBRATE_CUSTOM_COMPOSITE_TIME) {
        hdfCompositeEffect.type = HDF_EFFECT_TYPE_TIME;
        int32_t ret = matcher.TransformTime(info.package, hdfCompositeEffect.compositeEffects);
        if (ret != SUCCESS) {
            MISC_HILOGE("Transform pattern to time series fail");
            return ERROR;
        }
    }
    return PlayCompositeEffect(newInfo, hdfCompositeEffect, identifier);
}

int32_t VibratorThread::PlayCompositeEffect(const VibrateInfo &info, const HdfCompositeEffect &hdfCompositeEffect,
    const VibratorIdentifierIPC& identifier)
{
    std::unique_lock<std::mutex> vibrateLck(vibrateMutex_);
    HdfCompositeEffect effectsPart;
    effectsPart.type = hdfCompositeEffect.type;
    size_t effectSize = hdfCompositeEffect.compositeEffects.size();
    int32_t delayTime = 0;
    for (size_t i = 0; i < effectSize; ++i) {
        effectsPart.compositeEffects.push_back(hdfCompositeEffect.compositeEffects[i]);
        if (effectsPart.type == HDF_EFFECT_TYPE_TIME) {
            delayTime += hdfCompositeEffect.compositeEffects[i].timeEffect.delay;
        } else if (effectsPart.type == HDF_EFFECT_TYPE_PRIMITIVE) {
            delayTime += hdfCompositeEffect.compositeEffects[i].primitiveEffect.delay;
        } else {
            MISC_HILOGE("Effect type is valid");
            return ERROR;
        }
        if ((effectsPart.compositeEffects.size() >= COMPOSITE_EFFECT_PART) || (i == (effectSize - 1))) {
            int32_t ret = VibratorDevice.EnableCompositeEffect(identifier, effectsPart);
            if (ret != SUCCESS) {
                MISC_HILOGE("EnableCompositeEffect failed");
                return ERROR;
            }
            cv_.wait_for(vibrateLck, std::chrono::milliseconds(delayTime), [this] { return exitFlag_.load(); });
            delayTime = 0;
            effectsPart.compositeEffects.clear();
        }
        if (exitFlag_) {
            VibratorDevice.Stop(identifier, HDF_VIBRATOR_MODE_PRESET);
            MISC_HILOGD("Stop composite effect part, package:%{public}s", info.packageName.c_str());
            return SUCCESS;
        }
    }
    return SUCCESS;
}
#endif // HDF_DRIVERS_INTERFACE_VIBRATOR

void VibratorThread::UpdateVibratorEffect(const VibrateInfo &info, const VibratorIdentifierIPC& identifier,
    std::vector<HdfWaveInformation> &waveInfos)
{
    std::unique_lock<std::mutex> lck(currentVibrationMutex_);
    currentVibration_ = info;
    currentVibrateParams_ = identifier;
    waveInfos_ = waveInfos;
}

VibrateInfo VibratorThread::GetCurrentVibrateInfo()
{
    std::unique_lock<std::mutex> lck(currentVibrationMutex_);
    return currentVibration_;
}

VibratorIdentifierIPC VibratorThread::GetCurrentVibrateParams()
{
    std::unique_lock<std::mutex> lck(currentVibrationMutex_);
    return currentVibrateParams_;
}

std::vector<HdfWaveInformation> VibratorThread::GetCurrentWaveInfo()
{
    std::unique_lock<std::mutex> lck(currentVibrationMutex_);
    return waveInfos_;
}

void VibratorThread::SetExitStatus(bool status)
{
    exitFlag_.store(status);
}

void VibratorThread::NotifyExit()
{
    std::lock_guard<std::mutex> lck(vibrateMutex_);
    exitFlag_.store(true);
    cv_.notify_one();
}

void VibratorThread::ResetVibrateInfo()
{
    std::unique_lock<std::mutex> lck(currentVibrationMutex_);
    currentVibration_.mode = "";
    currentVibration_.packageName = "";
    currentVibration_.pid = -1;
    currentVibration_.uid = -1;
    currentVibration_.usage = 0;
    currentVibration_.systemUsage = false;
    currentVibration_.duration = 0;
    currentVibration_.effect = "";
    currentVibration_.count = 0;
    currentVibration_.intensity = 0;
}

#ifdef OHOS_BUILD_ENABLE_QOS
void VibratorThread::SetQosForThread()
{
    std::unordered_map<std::string, std::string> payload;
    payload["pid"] = std::to_string(getpid());
    OHOS::ConcurrentTask::ConcurrentTaskClient::GetInstance().RequestAuth(payload);
    auto ret = OHOS::QOS::SetThreadQos(OHOS::QOS::QosLevel::QOS_USER_INTERACTIVE);
    if (ret != 0) {
        MISC_HILOGE("Set vibrator thread qos failed, ret:%{public}d", ret);
    } else {
        MISC_HILOGD("Set vibrator thread qos success");
    }
}
#endif // OHOS_BUILD_ENABLE_QOS
}  // namespace Sensors
}  // namespace OHOS
