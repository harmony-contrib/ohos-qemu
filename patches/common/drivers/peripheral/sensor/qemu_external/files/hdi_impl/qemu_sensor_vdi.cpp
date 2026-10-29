/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#include "isensor_interface_vdi.h"
#include "qemu_sensor_input.h"
#include "qemu_rotation_input.h"
#include "qemu_headposture_input.h"
#include "sensor_type.h"
#include <atomic>
#include <mutex>
#include <new>

namespace OHOS::HDI::Sensor::V1_1 {
namespace {
constexpr int32_t ACCELEROMETER = SENSOR_TYPE_ACCELEROMETER;
constexpr int32_t ROTATION_VECTOR = SENSOR_TYPE_ROTATION_VECTOR;
constexpr int32_t HEADPOSTURE = 268; // Actual sensor_agent_type.h and HDI adapter.
bool ValidHandle(const SensorHandle& handle)
{
    return handle.deviceId == DEFAULT_DEVICE_ID && (handle.sensorType == ACCELEROMETER || handle.sensorType == ROTATION_VECTOR || handle.sensorType == HEADPOSTURE) &&
        handle.sensorId == DEFAULT_SENSOR_ID && handle.location == DEFAULT_LOCATION;
}
class QemuSensorVdi final : public ISensorInterfaceVdi {
public:
    QemuSensorVdi() : input_({"/dev/unix/socket/qemu_sensor/input", 0}),
        rotation_({"/dev/unix/socket/qemu_sensor/rotation", 0}),
        head_({"/dev/unix/socket/qemu_sensor/headposture", 0}) {}
    ~QemuSensorVdi() override { head_.Stop(); rotation_.Stop(); input_.Stop(); }
    int32_t Init() override
    {
        if (!input_.Start()) return SENSOR_FAILURE;
        if (!rotation_.Start()) { input_.Stop(); return SENSOR_FAILURE; }
        if (!head_.Start()) { rotation_.Stop(); input_.Stop(); return SENSOR_FAILURE; }
        return SENSOR_SUCCESS;
    }
    int32_t GetAllSensorInfo(std::vector<HdfSensorInformationVdi>& info) override
    {
        if (!input_.IsRunning() || !rotation_.IsRunning() || !head_.IsRunning()) return SENSOR_FAILURE;
        HdfSensorInformationVdi sensor{};
        sensor.sensorName = "QEMU external accelerometer";
        sensor.vendorName = "OpenHarmony QEMU";
        sensor.firmwareVersion = "qemu-ext-v1";
        sensor.hardwareVersion = "virtual-v1";
        sensor.sensorTypeId = ACCELEROMETER;
        sensor.sensorId = ACCELEROMETER;
        sensor.sensorHandle.deviceId = DEFAULT_DEVICE_ID;
        sensor.sensorHandle.sensorType = ACCELEROMETER;
        sensor.sensorHandle.sensorId = DEFAULT_SENSOR_ID;
        sensor.sensorHandle.location = DEFAULT_LOCATION;
        sensor.maxRange = Qemu::MAX_ACCELERATION;
        sensor.accuracy = 0.001F;
        sensor.power = 0.0F; // No physical sensor power consumption in this virtual device.
        sensor.minDelay = Qemu::MIN_INTERVAL_NS;
        sensor.maxDelay = Qemu::MAX_INTERVAL_NS;
        sensor.fifoMaxEventCount = 0;
        info.push_back(sensor);
        sensor.sensorName = "QEMU external rotation vector";
        sensor.firmwareVersion = "qemu-rotation-v1";
        sensor.sensorTypeId = ROTATION_VECTOR;
        sensor.sensorId = ROTATION_VECTOR;
        sensor.sensorHandle.sensorType = ROTATION_VECTOR;
        sensor.maxRange = 1.0F;
        sensor.accuracy = 0.0001F;
        info.push_back(sensor);
        sensor.sensorName = "QEMU external head posture";
        sensor.firmwareVersion = "qemu-headposture-v1";
        sensor.sensorTypeId = HEADPOSTURE;
        sensor.sensorId = HEADPOSTURE;
        sensor.sensorHandle.sensorType = HEADPOSTURE;
        info.push_back(std::move(sensor));
        return SENSOR_SUCCESS;
    }
    int32_t GetDeviceSensorInfo(int32_t deviceId, std::vector<HdfSensorInformationVdi>& info) override
    { return deviceId == DEFAULT_DEVICE_ID ? GetAllSensorInfo(info) : SENSOR_INVALID_PARAM; }
    int32_t Enable(int32_t id) override
    { return id == HEADPOSTURE ? Result(head_.Enable()) : (id == ROTATION_VECTOR ? Result(rotation_.Enable()) :
        (id != ACCELEROMETER ? SENSOR_INVALID_PARAM : Result(input_.Enable()))); }
    int32_t Disable(int32_t id) override
    { return id == HEADPOSTURE ? Result(head_.Disable()) : (id == ROTATION_VECTOR ? Result(rotation_.Disable()) :
        (id != ACCELEROMETER ? SENSOR_INVALID_PARAM : Result(input_.Disable()))); }
    int32_t SetBatch(int32_t id, int64_t sampling, int64_t reporting) override
    {
        if ((id != ACCELEROMETER && id != ROTATION_VECTOR && id != HEADPOSTURE) || sampling < Qemu::MIN_INTERVAL_NS || sampling > Qemu::MAX_INTERVAL_NS ||
            reporting < 0 || reporting > Qemu::MAX_INTERVAL_NS) return SENSOR_INVALID_PARAM;
        return Result(id == HEADPOSTURE ? head_.SetBatch(sampling, reporting) :
            (id == ROTATION_VECTOR ? rotation_.SetBatch(sampling, reporting) : input_.SetBatch(sampling, reporting)));
    }
    int32_t SetSaBatch(int32_t id, int64_t sampling, int64_t reporting) override
    { return SetBatch(id, sampling, reporting); }
    int32_t SetMode(int32_t id, int32_t mode) override
    {
        if (id != ACCELEROMETER && id != ROTATION_VECTOR && id != HEADPOSTURE) return SENSOR_INVALID_PARAM;
        if (!input_.IsRunning() || !rotation_.IsRunning() || !head_.IsRunning()) return SENSOR_FAILURE;
        if (mode != SENSOR_MODE_DEFAULT && mode != SENSOR_MODE_REALTIME) return SENSOR_NOT_SUPPORT;
        if (id == HEADPOSTURE) headMode_ = mode; else if (id == ROTATION_VECTOR) rotationMode_ = mode; else mode_ = mode;
        return SENSOR_SUCCESS;
    }
    int32_t SetOption(int32_t id, uint32_t option) override
    {
        if (id != ACCELEROMETER && id != ROTATION_VECTOR && id != HEADPOSTURE) return SENSOR_INVALID_PARAM;
        if (!input_.IsRunning() || !rotation_.IsRunning() || !head_.IsRunning()) return SENSOR_FAILURE;
        return option == 0 ? SENSOR_SUCCESS : SENSOR_NOT_SUPPORT;
    }
    int32_t Register(int32_t group, const sptr<ISensorCallbackVdi>& callback) override
    {
        if (group != TRADITIONAL_SENSOR_TYPE || !callback) return SENSOR_INVALID_PARAM;
        const bool acceleration = input_.Register(callback.GetRefPtr(), [this, callback](const Qemu::Acceleration& sample) {
            HdfSensorEventsVdi event{};
            event.sensorId = ACCELEROMETER;
            event.deviceSensorInfo = {DEFAULT_DEVICE_ID, ACCELEROMETER, DEFAULT_SENSOR_ID, DEFAULT_LOCATION};
            event.version = 1;
            event.timestamp = sample.timestamp;
            event.mode = mode_.load();
            const float values[] = {sample.x, sample.y, sample.z};
            const auto* bytes = reinterpret_cast<const uint8_t*>(values);
            event.data.assign(bytes, bytes + sizeof(values));
            event.dataLen = sizeof(values);
            callback->OnDataEventVdi(event);
        });
        if (!acceleration) return SENSOR_FAILURE;
        const bool rotation = rotation_.Register(callback.GetRefPtr(), [this, callback](const Qemu::Rotation::Quaternion& sample) {
            HdfSensorEventsVdi event{};
            event.sensorId = ROTATION_VECTOR;
            event.deviceSensorInfo = {DEFAULT_DEVICE_ID, ROTATION_VECTOR, DEFAULT_SENSOR_ID, DEFAULT_LOCATION};
            event.version = 1;
            event.timestamp = sample.timestamp;
            event.mode = rotationMode_.load();
            const float values[] = {sample.x, sample.y, sample.z, sample.w};
            const auto* bytes = reinterpret_cast<const uint8_t*>(values);
            event.data.assign(bytes, bytes + sizeof(values));
            event.dataLen = sizeof(values);
            callback->OnDataEventVdi(event);
        });
        if (!rotation) { input_.Unregister(callback.GetRefPtr()); return SENSOR_FAILURE; }
        const bool head = head_.Register(callback.GetRefPtr(), [this, callback](const Qemu::HeadPosture::Posture& sample) {
            HdfSensorEventsVdi event{};
            event.sensorId = HEADPOSTURE;
            event.deviceSensorInfo = {DEFAULT_DEVICE_ID, HEADPOSTURE, DEFAULT_SENSOR_ID, DEFAULT_LOCATION};
            event.version = 1;
            event.timestamp = sample.timestamp;
            event.mode = headMode_.load();
            // Actual adapter reads float indices1,3..6 then emits 20B order/wxyz.
            const float values[] = {0.0F, static_cast<float>(sample.order), 0.0F,
                sample.w, sample.x, sample.y, sample.z};
            const auto* bytes = reinterpret_cast<const uint8_t*>(values);
            event.data.assign(bytes, bytes + sizeof(values));
            event.dataLen = sizeof(values);
            callback->OnDataEventVdi(event);
        });
        if (!head) { rotation_.Unregister(callback.GetRefPtr()); input_.Unregister(callback.GetRefPtr()); return SENSOR_FAILURE; }
        return SENSOR_SUCCESS;
    }
    int32_t Unregister(int32_t group, const sptr<ISensorCallbackVdi>& callback) override
    {
        if (group != TRADITIONAL_SENSOR_TYPE || !callback) return SENSOR_INVALID_PARAM;
        const bool head = head_.Unregister(callback.GetRefPtr());
        const bool rotation = rotation_.Unregister(callback.GetRefPtr());
        const bool acceleration = input_.Unregister(callback.GetRefPtr());
        return Result(head && rotation && acceleration);
    }
    int32_t Enable(SensorHandle handle) override
    { return ValidHandle(handle) ? Enable(handle.sensorType) : SENSOR_INVALID_PARAM; }
    int32_t Disable(SensorHandle handle) override
    { return ValidHandle(handle) ? Disable(handle.sensorType) : SENSOR_INVALID_PARAM; }
    int32_t SetBatch(SensorHandle handle, int64_t sampling, int64_t reporting) override
    { return ValidHandle(handle) ? SetBatch(handle.sensorType, sampling, reporting) : SENSOR_INVALID_PARAM; }
    int32_t SetSaBatch(SensorHandle handle, int64_t sampling, int64_t reporting) override
    { return SetBatch(handle, sampling, reporting); }
    int32_t SetMode(SensorHandle handle, int32_t mode) override
    { return ValidHandle(handle) ? SetMode(handle.sensorType, mode) : SENSOR_INVALID_PARAM; }
    int32_t SetOption(SensorHandle handle, uint32_t option) override
    { return ValidHandle(handle) ? SetOption(handle.sensorType, option) : SENSOR_INVALID_PARAM; }
    int32_t GetSdcSensorInfo(std::vector<SdcSensorInfoVdi>&) override { return SENSOR_NOT_SUPPORT; }
    int32_t RegSensorPlugCallBack(const sptr<V3_0::ISensorPlugCallback>& callback) override
    {
        if (!callback || !input_.IsRunning() || !rotation_.IsRunning() || !head_.IsRunning()) return SENSOR_INVALID_PARAM;
        std::lock_guard<std::mutex> lock(plugMutex_);
        for (const auto& registered : plugCallbacks_) if (registered == callback) return SENSOR_SUCCESS;
        if (plugCallbacks_.size() == 32) return SENSOR_FAILURE;
        plugCallbacks_.push_back(callback);
        return SENSOR_SUCCESS; // Fixed topology: enumeration supplies this always-present virtual sensor.
    }
    int32_t UnRegSensorPlugCallBack(const sptr<V3_0::ISensorPlugCallback>& callback) override
    {
        std::lock_guard<std::mutex> lock(plugMutex_);
        for (auto entry = plugCallbacks_.begin(); entry != plugCallbacks_.end(); ++entry) {
            if (*entry == callback) { plugCallbacks_.erase(entry); return SENSOR_SUCCESS; }
        }
        return SENSOR_INVALID_PARAM;
    }
private:
    static int32_t Result(bool success) { return success ? SENSOR_SUCCESS : SENSOR_FAILURE; }
    Qemu::SensorInput input_;
    Qemu::Rotation::SensorInput rotation_;
    Qemu::HeadPosture::SensorInput head_;
    std::atomic<int32_t> headMode_{SENSOR_MODE_REALTIME};
    std::atomic<int32_t> rotationMode_{SENSOR_MODE_REALTIME};
    std::atomic<int32_t> mode_{SENSOR_MODE_REALTIME};
    std::mutex plugMutex_;
    std::vector<sptr<V3_0::ISensorPlugCallback>> plugCallbacks_;
};

int32_t CreateQemuSensor(HdfVdiBase* base)
{
    if (!base) return HDF_FAILURE;
    auto* wrapper = reinterpret_cast<WrapperSensorVdi*>(base);
    if (wrapper->sensorModule) return HDF_FAILURE;
    wrapper->sensorModule = new (std::nothrow) QemuSensorVdi;
    return wrapper->sensorModule ? HDF_SUCCESS : HDF_FAILURE;
}
int32_t DestroyQemuSensor(HdfVdiBase* base)
{
    if (!base) return HDF_FAILURE;
    auto* wrapper = reinterpret_cast<WrapperSensorVdi*>(base);
    delete wrapper->sensorModule;
    wrapper->sensorModule = nullptr;
    return HDF_SUCCESS;
}
WrapperSensorVdi sensorVdi = {
    .base = {
        .moduleVersion = 1,
        .moduleName = "qemu_external_sensor",
        .CreateVdiInstance = CreateQemuSensor,
        .DestoryVdiInstance = DestroyQemuSensor,
    },
    .sensorModule = nullptr,
};
} // namespace
extern "C" HDF_VDI_INIT(sensorVdi);
} // namespace OHOS::HDI::Sensor::V1_1
