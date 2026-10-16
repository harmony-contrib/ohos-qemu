/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#include "isensor_interface_vdi.h"
#include "qemu_sensor_input.h"
#include "sensor_type.h"
#include <atomic>
#include <mutex>
#include <new>

namespace OHOS::HDI::Sensor::V1_1 {
namespace {
constexpr int32_t ACCELEROMETER = SENSOR_TYPE_ACCELEROMETER;
bool ValidHandle(const SensorHandle& handle)
{
    return handle.deviceId == DEFAULT_DEVICE_ID && handle.sensorType == ACCELEROMETER &&
        handle.sensorId == DEFAULT_SENSOR_ID && handle.location == DEFAULT_LOCATION;
}
class QemuSensorVdi final : public ISensorInterfaceVdi {
public:
    QemuSensorVdi() : input_({"/dev/unix/socket/qemu_sensor/input", 0}) {}
    ~QemuSensorVdi() override { input_.Stop(); }
    int32_t Init() override { return input_.Start() ? SENSOR_SUCCESS : SENSOR_FAILURE; }
    int32_t GetAllSensorInfo(std::vector<HdfSensorInformationVdi>& info) override
    {
        if (!input_.IsRunning()) return SENSOR_FAILURE;
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
        info.push_back(std::move(sensor));
        return SENSOR_SUCCESS;
    }
    int32_t GetDeviceSensorInfo(int32_t deviceId, std::vector<HdfSensorInformationVdi>& info) override
    { return deviceId == DEFAULT_DEVICE_ID ? GetAllSensorInfo(info) : SENSOR_INVALID_PARAM; }
    int32_t Enable(int32_t id) override
    { return id != ACCELEROMETER ? SENSOR_INVALID_PARAM : Result(input_.Enable()); }
    int32_t Disable(int32_t id) override
    { return id != ACCELEROMETER ? SENSOR_INVALID_PARAM : Result(input_.Disable()); }
    int32_t SetBatch(int32_t id, int64_t sampling, int64_t reporting) override
    {
        if (id != ACCELEROMETER || sampling < Qemu::MIN_INTERVAL_NS || sampling > Qemu::MAX_INTERVAL_NS ||
            reporting < 0 || reporting > Qemu::MAX_INTERVAL_NS) return SENSOR_INVALID_PARAM;
        return Result(input_.SetBatch(sampling, reporting));
    }
    int32_t SetSaBatch(int32_t id, int64_t sampling, int64_t reporting) override
    { return SetBatch(id, sampling, reporting); }
    int32_t SetMode(int32_t id, int32_t mode) override
    {
        if (id != ACCELEROMETER) return SENSOR_INVALID_PARAM;
        if (!input_.IsRunning()) return SENSOR_FAILURE;
        if (mode != SENSOR_MODE_DEFAULT && mode != SENSOR_MODE_REALTIME) return SENSOR_NOT_SUPPORT;
        mode_ = mode;
        return SENSOR_SUCCESS;
    }
    int32_t SetOption(int32_t id, uint32_t option) override
    {
        if (id != ACCELEROMETER) return SENSOR_INVALID_PARAM;
        if (!input_.IsRunning()) return SENSOR_FAILURE;
        return option == 0 ? SENSOR_SUCCESS : SENSOR_NOT_SUPPORT;
    }
    int32_t Register(int32_t group, const sptr<ISensorCallbackVdi>& callback) override
    {
        if (group != TRADITIONAL_SENSOR_TYPE || !callback) return SENSOR_INVALID_PARAM;
        return Result(input_.Register(callback.GetRefPtr(), [this, callback](const Qemu::Acceleration& sample) {
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
        }));
    }
    int32_t Unregister(int32_t group, const sptr<ISensorCallbackVdi>& callback) override
    {
        if (group != TRADITIONAL_SENSOR_TYPE || !callback) return SENSOR_INVALID_PARAM;
        return Result(input_.Unregister(callback.GetRefPtr()));
    }
    int32_t Enable(SensorHandle handle) override
    { return ValidHandle(handle) ? Enable(ACCELEROMETER) : SENSOR_INVALID_PARAM; }
    int32_t Disable(SensorHandle handle) override
    { return ValidHandle(handle) ? Disable(ACCELEROMETER) : SENSOR_INVALID_PARAM; }
    int32_t SetBatch(SensorHandle handle, int64_t sampling, int64_t reporting) override
    { return ValidHandle(handle) ? SetBatch(ACCELEROMETER, sampling, reporting) : SENSOR_INVALID_PARAM; }
    int32_t SetSaBatch(SensorHandle handle, int64_t sampling, int64_t reporting) override
    { return SetBatch(handle, sampling, reporting); }
    int32_t SetMode(SensorHandle handle, int32_t mode) override
    { return ValidHandle(handle) ? SetMode(ACCELEROMETER, mode) : SENSOR_INVALID_PARAM; }
    int32_t SetOption(SensorHandle handle, uint32_t option) override
    { return ValidHandle(handle) ? SetOption(ACCELEROMETER, option) : SENSOR_INVALID_PARAM; }
    int32_t GetSdcSensorInfo(std::vector<SdcSensorInfoVdi>&) override { return SENSOR_NOT_SUPPORT; }
    int32_t RegSensorPlugCallBack(const sptr<V3_0::ISensorPlugCallback>& callback) override
    {
        if (!callback || !input_.IsRunning()) return SENSOR_INVALID_PARAM;
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
