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

#include "stationary_server.h"

#include <chrono>
#include <cmath>
#include <condition_variable>
#include <tokenid_kit.h>

#include "hisysevent.h"
#include "hitrace_meter.h"

#include "devicestatus_define.h"
#include "devicestatus_dumper.h"
#include "devicestatus_hisysevent.h"
#include "stationary_data.h"
#include "stationary_params.h"
#include "sensor_agent.h"
#include "sensor_agent_type.h"
#include "sensor_manager.h"

#undef LOG_TAG
#define LOG_TAG "StationaryServer"

namespace OHOS {
namespace Msdp {
namespace DeviceStatus {
namespace {
#ifdef MOTION_ENABLE
constexpr int32_t MOTION_TYPE_STAND = 3602;
constexpr int32_t STATUS_ENTER = 1;
constexpr int32_t STATUS_EXIT = 0;
std::map<Type, int32_t> MOTION_TYPE_MAP {
    { Type::TYPE_STAND, MOTION_TYPE_STAND },
};
std::map<int32_t, Type> DEVICE_STATUS_TYPE_MAP {
    { MOTION_TYPE_STAND, Type::TYPE_STAND },
};
#endif
constexpr int32_t RET_NO_SUPPORT = 801;
constexpr int32_t RET_NO_SYSTEM_API = 202;
constexpr int32_t SENSOR_SAMPLING_INTERVAL = 10000000;
constexpr int32_t WAIT_SENSOR_DATA_TIMEOUT_MS = 1000;
constexpr int32_t ROTATION_MAT_LEN = 3;
constexpr int32_t MAT_IDX_0 = 0;
constexpr int32_t MAT_IDX_1 = 1;
constexpr int32_t MAT_IDX_2 = 2;
constexpr float DOUBLE_FACTOR = 2.0F;
constexpr float PI = 3.141592653589846;
constexpr float EPSILON_FLOAT = 1e-6;
std::optional<RotationVectorData> cacheRotVecData_;
std::mutex g_mtx;
std::condition_variable g_cv;
} // namespace

static void OnReceivedData(SensorEvent *event)
{
    if (event == nullptr) {
        return;
    }
    if (event->sensorTypeId == SENSOR_TYPE_ID_ROTATION_VECTOR) {
        std::unique_lock lockGrd(g_mtx);
        RotationVectorData *data = reinterpret_cast<RotationVectorData *>(event->data);
        if (data == nullptr) {
            FI_HILOGE("data is null");
            return;
        }
        cacheRotVecData_ = std::make_optional(*data);
        FI_HILOGI("rotation vec collect succ");
        g_cv.notify_all();
    }
}

#ifdef MOTION_ENABLE
void MotionCallback::OnMotionChanged(const MotionEvent &motionEvent)
{
    Data data;
    data.type = DEVICE_STATUS_TYPE_MAP[motionEvent.type];
    switch (motionEvent.status) {
        case STATUS_ENTER:
            data.value = VALUE_ENTER;
            break;
        case STATUS_EXIT:
            data.value = VALUE_EXIT;
            break;
        default:
            data.value = VALUE_INVALID;
            break;
    }
    event_(data);
}

void RemoteDevStaCallbackDeathRecipient::OnRemoteDied(const wptr<IRemoteObject> &remote)
{
    event_(remote);
}
#endif

StationaryServer::StationaryServer()
{
    manager_.Init();
#ifdef MOTION_ENABLE
    auto deathRecipientCB = [this](const wptr<IRemoteObject> &remote) {
        this->StationaryServerDeathRecipient(remote);
    };
    devStaCBDeathRecipient_ = new (std::nothrow) RemoteDevStaCallbackDeathRecipient(deathRecipientCB);
#endif
}

int32_t StationaryServer::SubscribeStationaryCallback(CallingContext &context, int32_t type, int32_t event,
    int32_t latency, const sptr<IRemoteDevStaCallback> &subCallback)
{
    Type stationaryType = static_cast<Type>(type);
    ActivityEvent stationaryEvent = static_cast<ActivityEvent>(event);
    ReportLatencyNs stationaryLatency = static_cast<ReportLatencyNs>(latency);
    if (stationaryType == Type::TYPE_STAND) {
#ifdef MOTION_ENABLE
        return SubscribeMotion(stationaryType, subCallback);
#else
        return RET_NO_SUPPORT;
#endif
    } else {
        Subscribe(context, stationaryType, stationaryEvent, stationaryLatency, subCallback);
    }
    return RET_OK;
}

int32_t StationaryServer::UnsubscribeStationaryCallback(CallingContext &context, int32_t type, int32_t event,
    const sptr<IRemoteDevStaCallback> &unsubCallback)
{
    Type stationaryType = static_cast<Type>(type);
    ActivityEvent stationaryEvent = static_cast<ActivityEvent>(event);
    if (stationaryType == Type::TYPE_STAND) {
#ifdef MOTION_ENABLE
        return UnsubscribeMotion(stationaryType, unsubCallback);
#else
        return RET_NO_SUPPORT;
#endif
    } else {
        Unsubscribe(context, stationaryType, stationaryEvent, unsubCallback);
    }
    return RET_OK;
}

int32_t StationaryServer::GetDeviceStatusData(CallingContext &context, int32_t type,
    int32_t &replyType, int32_t &replyValue)
{
    Type stationaryType = static_cast<Type>(type);
    Data data = GetCache(context, stationaryType);
    replyType = static_cast<int32_t>(data.type);
    replyValue = static_cast<int32_t>(data.value);
    return RET_OK;
}

int32_t StationaryServer::GetDevicePostureDataSync(CallingContext &context, DevicePostureData &data)
{
    if (!IsSystemCalling(context)) {
        return RET_NO_SYSTEM_API;
    }
#ifndef DEVICE_STATUS_SENSOR_ENABLE
    return RET_NO_SUPPORT;
#else
    if (!SensorManager::IsSupportedSensor(SENSOR_TYPE_ID_ROTATION_VECTOR)) {
        FI_HILOGE("rotation vector sensor is not supported");
        return RET_NO_SUPPORT;
    }
    // 订阅sensor获取四元数
    SensorManager sensorManager(SENSOR_TYPE_ID_ROTATION_VECTOR, SENSOR_SAMPLING_INTERVAL);
    sensorManager.SetCallback(&OnReceivedData);
    sensorManager.StartSensor();
    std::unique_lock lockGrd(g_mtx);
    g_cv.wait_for(lockGrd, std::chrono::milliseconds(WAIT_SENSOR_DATA_TIMEOUT_MS));
    sensorManager.StopSensor();
    // 数据转换
    if (cacheRotVecData_ == std::nullopt) {
        FI_HILOGE("get cache data failed, sensor no data, timeout");
        return RET_ERR;
    }
    TransQuaternionsToZXYRot(cacheRotVecData_.value(), data);
    return RET_OK;
#endif
}

#ifdef DEVICE_STATUS_SENSOR_ENABLE
void StationaryServer::TransQuaternionsToZXYRot(RotationVectorData quaternions, DevicePostureData &data)
{
    // 四元数表示法： w+xi+yj+zk
    float x = quaternions.x;
    float y = quaternions.y;
    float z = quaternions.z;
    float w = quaternions.w;
    FI_HILOGI("x:%{public}f, y:%{public}f, z:%{public}f, w:%{public}f", x, y, z, w);
    // 计算旋转矩阵
    std::vector<std::vector<float>> rotationMat(ROTATION_MAT_LEN, std::vector<float>(ROTATION_MAT_LEN, 0.0F));
    rotationMat[MAT_IDX_0][MAT_IDX_0] = 1 - DOUBLE_FACTOR * y * y - DOUBLE_FACTOR * z * z;
    rotationMat[MAT_IDX_0][MAT_IDX_1] = DOUBLE_FACTOR * x * y - DOUBLE_FACTOR * w * z;
    rotationMat[MAT_IDX_0][MAT_IDX_2] = DOUBLE_FACTOR * x * z + DOUBLE_FACTOR * w * y;
    rotationMat[MAT_IDX_1][MAT_IDX_0] = DOUBLE_FACTOR * x * y + DOUBLE_FACTOR * w * z;
    rotationMat[MAT_IDX_1][MAT_IDX_1] = 1 - DOUBLE_FACTOR * x * x - DOUBLE_FACTOR * z * z;
    rotationMat[MAT_IDX_1][MAT_IDX_2] = DOUBLE_FACTOR * y * z - DOUBLE_FACTOR * w * x;
    rotationMat[MAT_IDX_2][MAT_IDX_0] = DOUBLE_FACTOR * x * z - DOUBLE_FACTOR * w * y;
    rotationMat[MAT_IDX_2][MAT_IDX_1] = DOUBLE_FACTOR * y * z + DOUBLE_FACTOR * w * x;
    rotationMat[MAT_IDX_2][MAT_IDX_2] = 1 - DOUBLE_FACTOR * x * x - DOUBLE_FACTOR * y * y;
    auto transFunc = [](const float angle) -> float {
        float ret = angle;
        if (angle < 0) {
            ret = angle + 2 * PI;
        }
        return ret;
    };
    auto pitch = transFunc(std::atan2(-rotationMat[MAT_IDX_2][MAT_IDX_0], rotationMat[MAT_IDX_2][MAT_IDX_2]));
    auto yaw = transFunc(std::atan2(-rotationMat[MAT_IDX_0][MAT_IDX_1], rotationMat[MAT_IDX_1][MAT_IDX_1]));
    float roll = 0.0F;
    if (std::cos(pitch) >= EPSILON_FLOAT) {
        roll = transFunc(std::atan2(rotationMat[MAT_IDX_2][MAT_IDX_1],
            rotationMat[MAT_IDX_2][MAT_IDX_2] / std::cos(pitch)));
    } else {
        roll = transFunc(std::atan2(rotationMat[MAT_IDX_2][MAT_IDX_1],
            -rotationMat[MAT_IDX_2][MAT_IDX_0] / std::sin(pitch)));
    }
    data.rollRad = roll;
    data.yawRad = yaw;
    data.pitchRad = pitch;
}
#endif

bool StationaryServer::IsSystemCalling(CallingContext &context)
{
    if (IsSystemServiceCalling(context)) {
        return true;
    }
    return Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID(context.fullTokenId);
}

bool StationaryServer::IsSystemServiceCalling(CallingContext &context)
{
    auto flag = Security::AccessToken::AccessTokenKit::GetTokenTypeFlag(context.tokenId);
    if ((flag == Security::AccessToken::ATokenTypeEnum::TOKEN_NATIVE) ||
        (flag == Security::AccessToken::ATokenTypeEnum::TOKEN_SHELL)) {
        FI_HILOGI("system service calling, flag:%{public}u", flag);
        return true;
    }
    return false;
}

void StationaryServer::DumpDeviceStatusSubscriber(int32_t fd) const
{
    DS_DUMPER->DumpDeviceStatusSubscriber(fd);
}

void StationaryServer::DumpDeviceStatusChanges(int32_t fd) const
{
    DS_DUMPER->DumpDeviceStatusChanges(fd);
}

void StationaryServer::DumpCurrentDeviceStatus(int32_t fd)
{
    std::vector<Data> datas;

    for (auto type = TYPE_ABSOLUTE_STILL; type <= TYPE_LID_OPEN; type = static_cast<Type>(type + 1)) {
        Data data = manager_.GetLatestDeviceStatusData(type);
        if (data.value != OnChangedValue::VALUE_INVALID) {
            datas.emplace_back(data);
        }
    }
    DS_DUMPER->DumpDeviceStatusCurrentStatus(fd, datas);
}

void StationaryServer::Subscribe(CallingContext &context, Type type, ActivityEvent event,
    ReportLatencyNs latency, sptr<IRemoteDevStaCallback> callback)
{
    FI_HILOGI("SubscribeStationary(type:%{public}d,event:%{public}d,latency:%{public}d)", type, event, latency);
    auto appInfo = std::make_shared<AppInfo>();
    appInfo->uid = context.uid;
    appInfo->pid = context.pid;
    appInfo->tokenId = context.tokenId;
    manager_.GetPackageName(appInfo->tokenId, appInfo->packageName);
    appInfo->type = type;
    appInfo->callback = callback;
    DS_DUMPER->SaveAppInfo(appInfo);
    StartTrace(HITRACE_TAG_MSDP, "serviceSubscribeStart");
    manager_.Subscribe(type, event, latency, callback);
    FinishTrace(HITRACE_TAG_MSDP);
    ReportSensorSysEvent(context, type, true);
    WriteSubscribeHiSysEvent(appInfo->uid, appInfo->packageName, type);
}

void StationaryServer::Unsubscribe(CallingContext &context, Type type,
    ActivityEvent event, sptr<IRemoteDevStaCallback> callback)
{
    FI_HILOGI("UnsubscribeStationary(type:%{public}d,event:%{public}d)", type, event);
    auto appInfo = std::make_shared<AppInfo>();
    appInfo->uid = context.uid;
    appInfo->pid = context.pid;
    appInfo->tokenId = context.tokenId;
    appInfo->packageName = DS_DUMPER->GetPackageName(appInfo->tokenId);
    appInfo->type = type;
    appInfo->callback = callback;
    DS_DUMPER->RemoveAppInfo(appInfo);
    StartTrace(HITRACE_TAG_MSDP, "serviceUnSubscribeStart");
    manager_.Unsubscribe(type, event, callback);
    FinishTrace(HITRACE_TAG_MSDP);
    ReportSensorSysEvent(context, type, false);
    WriteUnSubscribeHiSysEvent(appInfo->uid, appInfo->packageName, type);
}

Data StationaryServer::GetCache(CallingContext &context, const Type &type)
{
    return manager_.GetLatestDeviceStatusData(type);
}

void StationaryServer::ReportSensorSysEvent(CallingContext &context, int32_t type, bool enable)
{
    std::string packageName;
    manager_.GetPackageName(context.tokenId, packageName);
    int32_t ret = HiSysEventWrite(
        OHOS::HiviewDFX::HiSysEvent::Domain::MSDP,
        std::string(enable ? "Subscribe" : "Unsubscribe"),
        OHOS::HiviewDFX::HiSysEvent::EventType::STATISTIC,
        "UID", context.uid,
        "PKGNAME", packageName,
        "TYPE", type);
    if (ret != 0) {
        FI_HILOGE("HiviewDFX write failed, error:%{public}d", ret);
    }
}

#ifdef MOTION_ENABLE
int32_t StationaryServer::SubscribeMotion(Type type, sptr<IRemoteDevStaCallback> callback)
{
    FI_HILOGD("Enter");
    std::lock_guard lockGrd(mtx_);
    int32_t ret = 0;
    if (motionCallback_ == nullptr) {
        FI_HILOGI("create motion callback and subscribe");
        auto event = [this, type](const Data &data) {
            this->NotifyMotionCallback(type, data);
        };
        motionCallback_ = new (std::nothrow) MotionCallback(event);
        ret = SubscribeCallback(MOTION_TYPE_MAP[type], motionCallback_);
        if (ret != RET_OK) {
            FI_HILOGE("subscribe motion failed, ret = %{public}d", ret);
            motionCallback_ = nullptr;
            return ret;
        }
    }
    FI_HILOGI("motionCallback is not null, subscribe ok");
    auto iter = deviceStatusMotionCallbacks_.find(type);
    if (iter == deviceStatusMotionCallbacks_.end()) {
        deviceStatusMotionCallbacks_[type] = std::set<sptr<IRemoteDevStaCallback>, DevStaCallbackCmp>();
    }
    deviceStatusMotionCallbacks_[type].insert(callback);
    auto object = callback->AsObject();
    object->AddDeathRecipient(devStaCBDeathRecipient_);
    if (motionCallback_ != nullptr && cacheData_.find(type) != cacheData_.end()) {
        callback->OnDeviceStatusChanged(cacheData_[type]);
    }
    return ret;
}

int32_t StationaryServer::UnsubscribeMotion(Type type, sptr<IRemoteDevStaCallback> callback)
{
    FI_HILOGI("Enter");
    std::lock_guard lockGrd(mtx_);
    auto iter = deviceStatusMotionCallbacks_.find(type);
    if (iter == deviceStatusMotionCallbacks_.end()) {
        FI_HILOGE("dont find callback set in callbacks, failed");
        return RET_ERR;
    }
    auto callbackIter = deviceStatusMotionCallbacks_[type].find(callback);
    if (callbackIter == deviceStatusMotionCallbacks_[type].end()) {
        FI_HILOGE("dont find callback in callback set, failed");
        return RET_ERR;
    }
    deviceStatusMotionCallbacks_[type].erase(callbackIter);
    auto object = callback->AsObject();
    object->RemoveDeathRecipient(devStaCBDeathRecipient_);
    if (deviceStatusMotionCallbacks_[type].size() == 0) {
        int32_t ret = UnsubscribeCallback(MOTION_TYPE_MAP[type], motionCallback_);
        motionCallback_ = nullptr;
        if (ret != RET_OK) {
            FI_HILOGE("unsubscribe motion failed, ret = %{public}d", ret);
            return RET_ERR;
        }
        FI_HILOGI("unsubscribe motion succ");
        auto cacheIter = cacheData_.find(type);
        if (cacheIter != cacheData_.end()) {
            cacheData_.erase(cacheIter);
            FI_HILOGI("cache data clear");
        }
    }
    return RET_OK;
}

void StationaryServer::StationaryServerDeathRecipient(const wptr<IRemoteObject> &remote)
{
    FI_HILOGW("Enter recv death notice");
    sptr<IRemoteObject> client = remote.promote();
    if (client == nullptr) {
        FI_HILOGE("OnRemoteDied failed, client is nullptr");
        return;
    }
    sptr<IRemoteDevStaCallback> callback = iface_cast<IRemoteDevStaCallback>(client);
    if (callback == nullptr) {
        FI_HILOGE("OnRemoteDied failed, callback is nullptr");
        return;
    }
    std::vector<std::pair<Type, sptr<IRemoteDevStaCallback>>> delCallbacks;
    {
        std::lock_guard lockGrd(mtx_);
        for (auto &[type, set] : deviceStatusMotionCallbacks_) {
            for (auto &callbackInSet : set) {
                if (callbackInSet->AsObject() == callback->AsObject()) {
                    delCallbacks.push_back(std::make_pair(type, callbackInSet));
                }
            }
        }
    }
    for (auto &[delType, delCallback] : delCallbacks) {
        UnsubscribeMotion(delType, delCallback);
        FI_HILOGW("remote died, unsubscribe motion");
    }
}

void StationaryServer::NotifyMotionCallback(Type type, const Data &data)
{
    FI_HILOGI("Enter, type %{public}d, data.value %{public}d", type, data.value);
    std::lock_guard lockGrd(mtx_);
    cacheData_[type] = data;
    auto iter = deviceStatusMotionCallbacks_.find(type);
    if (iter == deviceStatusMotionCallbacks_.end()) {
        FI_HILOGW("callbacks is empty");
        return;
    }
    for (auto callback : iter->second) {
        callback->OnDeviceStatusChanged(data);
    }
}
#endif
} // namespace DeviceStatus
} // namespace Msdp
} // namespace OHOS