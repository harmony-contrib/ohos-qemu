// Execute extracted fixed functions with bounded sensor-agent call fault injection.
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <list>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
template<class... Args> void Log(const char*, const Args&...) {}
#define CALL_DEBUG_ENTER ((void)0)
#define FI_HILOGE(...) Log(__VA_ARGS__)
#define FI_HILOGI(...) Log(__VA_ARGS__)
#define FI_HILOGD(...) Log(__VA_ARGS__)
#define CHKPF(p) do { if (!(p)) return false; } while (0)
#define CHKPV(p) do { if (!(p)) return; } while (0)
#define CHECK(p) do { if (!(p)) throw std::runtime_error(#p); } while (0)
using std::abs;
[[maybe_unused]] constexpr int SENSOR_TYPE_ID_ACCELEROMETER = 1;
constexpr double ACC_VALID_THRHD = 160;
constexpr int RATE_MILLISEC = 100100100;
[[maybe_unused]] constexpr size_t MAX_PENDING_ACCEL_SAMPLES = 256;
struct AccelData { float x, y, z; };
struct SensorEvent { int32_t sensorTypeId; uint8_t* data; uint32_t dataLen; };
struct SensorUser { void (*callback)(SensorEvent*) = nullptr; };
int sem_post(int* count) { ++*count; return 0; }
std::string calls;
int batchResult = 0, activateResult = 0, subscribeResult = 0;
int SubscribeSensor(int32_t, SensorUser*) { calls += 'S'; return subscribeResult; }
int SetBatch(int32_t, SensorUser*, int, int) { calls += 'B'; return batchResult; }
int ActivateSensor(int32_t, SensorUser*) { calls += 'A'; return activateResult; }
int DeactivateSensor(int32_t, SensorUser*) { calls += 'D'; return 0; }
int UnsubscribeSensor(int32_t, SensorUser*) { calls += 'U'; return 0; }
class SensorDataCallback {
public:
    bool PushData(int32_t, uint8_t*);
    bool RegisterCallbackSensor(int32_t);
    std::mutex sensorMutex_, dataMutex_;
    SensorUser user_;
    std::list<AccelData> accelDataList_;
    int sem_ = 0;
} sensorCallback;
#define SENSOR_DATA_CB sensorCallback
using Type = int;
using ErrCode = int;
constexpr int RET_OK = 0, RET_ERR = -1;
class DeviceStatusMsdpClientImpl {
public:
    int sensorResult = RET_ERR, algoResult = RET_ERR, mockResult = RET_OK, mockCalls = 0;
    ErrCode InitMsdpImpl(Type);
    int GetSensorHdi(Type) { return sensorResult; }
    int AlgoHandle(Type) { return algoResult; }
    int MockHandle(Type) { ++mockCalls; return mockResult; }
};
#include "actual_msdp_functions.inc"

int main(int argc, char** argv)
{
    try {
        CHECK(argc == 2);
        std::string scenario(argv[1]);
        AccelData sample{1.25F, -2.5F, 9.81F};
        auto* data = reinterpret_cast<uint8_t*>(&sample);
        if (scenario == "nan") {
            sample.x = std::numeric_limits<float>::quiet_NaN();
            CHECK(!sensorCallback.PushData(1, data));
        } else if (scenario == "wrong_type") {
            CHECK(!sensorCallback.PushData(2, data));
        } else if (scenario == "short_event") {
            SensorEvent event{1, data, 0}; SensorDataCallbackImpl(&event);
            CHECK(sensorCallback.accelDataList_.empty());
        } else if (scenario == "bounded_queue") {
            for (size_t i = 0; i < 256; ++i) CHECK(sensorCallback.PushData(1, data));
            CHECK(!sensorCallback.PushData(1, data));
            CHECK(sensorCallback.sem_ == 256 && sensorCallback.accelDataList_.size() == 256);
        } else if (scenario == "batch_rollback") {
            batchResult = -1; CHECK(!sensorCallback.RegisterCallbackSensor(1)); CHECK(calls == "SBU");
        } else if (scenario == "activate_rollback") {
            activateResult = -1; CHECK(!sensorCallback.RegisterCallbackSensor(1)); CHECK(calls == "SBADU");
        } else if (scenario == "no_mock") {
            DeviceStatusMsdpClientImpl client;
            CHECK(client.InitMsdpImpl(1) == RET_ERR && client.mockCalls == 0);
            client.algoResult = RET_OK; CHECK(client.InitMsdpImpl(1) == RET_OK && client.mockCalls == 0);
        } else if (scenario == "default_fallback") {
            DeviceStatusMsdpClientImpl client;
            CHECK(client.InitMsdpImpl(1) == RET_OK && client.mockCalls == 1);
        } else if (scenario == "valid_unaligned_event") {
            uint8_t bytes[sizeof(sample) + 1];
            std::memcpy(bytes + 1, &sample, sizeof(sample));
            SensorEvent event{1, bytes + 1, sizeof(sample)};
            SensorDataCallbackImpl(&event);
            CHECK(sensorCallback.accelDataList_.size() == 1);
            CHECK(sensorCallback.accelDataList_.front().x == sample.x && sensorCallback.sem_ == 1);
        } else if (scenario == "invalid_envelopes") {
            SensorEvent event{1, nullptr, sizeof(sample)}; SensorDataCallbackImpl(&event);
            event = {2, data, sizeof(sample)}; SensorDataCallbackImpl(&event);
            event = {1, data, std::numeric_limits<uint32_t>::max()}; SensorDataCallbackImpl(&event);
            CHECK(sensorCallback.accelDataList_.empty());
        } else if (scenario == "subscribe_failure") {
            subscribeResult = -1; CHECK(!sensorCallback.RegisterCallbackSensor(1)); CHECK(calls == "S");
        } else if (scenario == "valid_register") {
            CHECK(sensorCallback.RegisterCallbackSensor(1)); CHECK(calls == "SBA");
        } else throw std::runtime_error("unknown scenario");
        std::cout << scenario << ": pass\n";
    } catch (const std::exception& error) {
        std::cerr << argv[1] << ": " << error.what() << '\n';
        return 1;
    }
}
