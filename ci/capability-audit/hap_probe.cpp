#include <BasicServicesKit/ohbattery_info.h>
#include <ConnectivityKit/bluetooth/oh_bluetooth.h>
#include <ConnectivityKit/wifi/oh_wifi.h>
#include <LocationKit/oh_location.h>
#include <napi/native_api.h>
#include <network/netmanager/net_connection.h>
#include <ohaudio/native_audio_manager.h>
#include <ohaudio/native_audio_routing_manager.h>
#include <ohaudio/native_audiorenderer.h>
#include <ohaudio/native_audiostreambuilder.h>
#include <ohcamera/camera_manager.h>
#include <sensors/oh_sensor.h>
#include <sensors/vibrator.h>
#include <telephony/core_service/telephony_radio.h>
#include <window_manager/oh_display_manager.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <unistd.h>

namespace {
constexpr const char *RESULT = "/data/storage/el2/base/files/capability-results.log";
volatile int g_locationCallbackCount = 0;
volatile int g_sensorCallbackCount = 0;
volatile uint32_t g_audioWriteCallbacks = 0;
volatile uint32_t g_audioWriteBytes = 0;
volatile int32_t g_audioCallbackError = 0;

void Report(const char *format, ...)
{
    FILE *file = fopen(RESULT, "a");
    if (file == nullptr) {
        return;
    }
    va_list arguments;
    va_start(arguments, format);
    vfprintf(file, format, arguments);
    va_end(arguments);
    fputc('\n', file);
    fclose(file);
}

void OnLocation(Location_Info *location, void *)
{
    ++g_locationCallbackCount;
    Location_BasicInfo info = OH_LocationInfo_GetBasicInfo(location);
    Report("location.callback.count=%d latitude=%.8f longitude=%.8f source=%d",
        g_locationCallbackCount, info.latitude, info.longitude, info.locationSourceType);
}

void OnSensor(Sensor_Event *event)
{
    if (event == nullptr) {
        return;
    }
    ++g_sensorCallbackCount;
    if (g_sensorCallbackCount == 1) {
        Sensor_Type type = static_cast<Sensor_Type>(0);
        float *data = nullptr;
        uint32_t length = 0;
        int32_t typeResult = OH_SensorEvent_GetType(event, &type);
        int32_t dataResult = OH_SensorEvent_GetData(event, &data, &length);
        Report("sensor.callback.first type_result=%d type=%d data_result=%d length=%u",
            typeResult, type, dataResult, length);
    }
}

void ProbeCamera()
{
    Camera_Manager *manager = nullptr;
    Camera_Device *cameras = nullptr;
    uint32_t count = 0;
    Camera_ErrorCode create = OH_Camera_GetCameraManager(&manager);
    Report("camera.manager.result=%d manager=%d", create, manager != nullptr);
    if (manager == nullptr) {
        return;
    }
    Camera_ErrorCode enumerate = OH_CameraManager_GetSupportedCameras(manager, &cameras, &count);
    Report("camera.devices.result=%d count=%u", enumerate, count);
    if (cameras != nullptr) {
        Report("camera.devices.delete=%d", OH_CameraManager_DeleteSupportedCameras(manager, cameras, count));
    }
    Report("camera.manager.delete=%d", OH_Camera_DeleteCameraManager(manager));
}

void ProbeSensor()
{
    uint32_t count = 0;
    Sensor_Result countResult = OH_Sensor_GetInfos(nullptr, &count);
    Report("sensor.infos.count.result=%d count=%u", countResult, count);
    if (countResult != SENSOR_SUCCESS || count == 0) {
        return;
    }
    Sensor_Info **infos = OH_Sensor_CreateInfos(count);
    Sensor_Result enumerateResult = OH_Sensor_GetInfos(infos, &count);
    Report("sensor.infos.enumerate.result=%d count=%u", enumerateResult, count);
    if (infos != nullptr) {
        Report("sensor.infos.destroy=%d", OH_Sensor_DestroyInfos(infos, count));
    }

    Sensor_Subscriber *subscriber = OH_Sensor_CreateSubscriber();
    Sensor_SubscriptionId *id = OH_Sensor_CreateSubscriptionId();
    Sensor_SubscriptionAttribute *attribute = OH_Sensor_CreateSubscriptionAttribute();
    if (subscriber == nullptr || id == nullptr || attribute == nullptr) {
        Report("sensor.subscribe.created=0");
    } else {
        int32_t callbackResult = OH_SensorSubscriber_SetCallback(subscriber, OnSensor);
        int32_t typeResult = OH_SensorSubscriptionId_SetType(id, SENSOR_TYPE_ACCELEROMETER);
        int32_t intervalResult = OH_SensorSubscriptionAttribute_SetSamplingInterval(attribute, 200000000);
        Sensor_Result subscribeResult = SENSOR_PARAMETER_ERROR;
        Sensor_Result unsubscribeResult = SENSOR_PARAMETER_ERROR;
        if (callbackResult == SENSOR_SUCCESS && typeResult == SENSOR_SUCCESS && intervalResult == SENSOR_SUCCESS) {
            subscribeResult = OH_Sensor_Subscribe(id, attribute, subscriber);
            if (subscribeResult == SENSOR_SUCCESS) {
                sleep(2);
                unsubscribeResult = OH_Sensor_Unsubscribe(id, subscriber);
            }
        }
        Report("sensor.subscribe.callback=%d type=%d interval=%d subscribe=%d unsubscribe=%d callbacks=%d",
            callbackResult, typeResult, intervalResult, subscribeResult, unsubscribeResult, g_sensorCallbackCount);
    }
    if (id != nullptr) {
        OH_Sensor_DestroySubscriptionId(id);
    }
    if (attribute != nullptr) {
        OH_Sensor_DestroySubscriptionAttribute(attribute);
    }
    if (subscriber != nullptr) {
        OH_Sensor_DestroySubscriber(subscriber);
    }
}

void ProbeAudio()
{
    OH_AudioManager *manager = nullptr;
    OH_AudioScene scene = AUDIO_SCENE_DEFAULT;
    OH_AudioRoutingManager *routing = nullptr;
    OH_AudioDeviceDescriptorArray *devices = nullptr;
    Report("audio.manager.result=%d", OH_GetAudioManager(&manager));
    if (manager != nullptr) {
        Report("audio.scene.result=%d scene=%d", OH_GetAudioScene(manager, &scene), scene);
    }
    Report("audio.routing.result=%d", OH_AudioManager_GetAudioRoutingManager(&routing));
    if (routing == nullptr) {
        return;
    }
    OH_AudioCommon_Result result =
        OH_AudioRoutingManager_GetDevices(routing, AUDIO_DEVICE_FLAG_ALL, &devices);
    Report("audio.devices.result=%d count=%u", result, devices == nullptr ? 0 : devices->size);
    if (devices != nullptr) {
        Report("audio.devices.release=%d", OH_AudioRoutingManager_ReleaseDevices(routing, devices));
    }
}

int32_t OnAudioWrite(OH_AudioRenderer *, void *, void *buffer, int32_t length)
{
    if (buffer != nullptr && length > 0) {
        std::memset(buffer, 0, static_cast<size_t>(length));
        ++g_audioWriteCallbacks;
        g_audioWriteBytes += static_cast<uint32_t>(length);
    }
    return 0;
}

int32_t OnAudioEvent(OH_AudioRenderer *, void *, OH_AudioStream_Event event)
{
    Report("audio.stream.event=%d", event);
    return 0;
}

int32_t OnAudioInterrupt(
    OH_AudioRenderer *, void *, OH_AudioInterrupt_ForceType type, OH_AudioInterrupt_Hint hint)
{
    Report("audio.stream.interrupt.type=%d hint=%d", type, hint);
    return 0;
}

int32_t OnAudioError(OH_AudioRenderer *, void *, OH_AudioStream_Result error)
{
    g_audioCallbackError = error;
    Report("audio.stream.callback_error=%d", error);
    return 0;
}

void ProbeAudioStream()
{
    OH_AudioStreamBuilder *builder = nullptr;
    OH_AudioRenderer *renderer = nullptr;
    OH_AudioStream_State state = AUDIOSTREAM_STATE_INVALID;
    OH_AudioRenderer_Callbacks callbacks{
        OnAudioWrite,
        OnAudioEvent,
        OnAudioInterrupt,
        OnAudioError,
    };
    OH_AudioStream_Result result =
        OH_AudioStreamBuilder_Create(&builder, AUDIOSTREAM_TYPE_RENDERER);
    Report("audio.stream.builder_create=%d builder=%d", result, builder != nullptr);
    if (result != AUDIOSTREAM_SUCCESS || builder == nullptr) {
        return;
    }

    Report("audio.stream.set_rate=%d", OH_AudioStreamBuilder_SetSamplingRate(builder, 48000));
    Report("audio.stream.set_channels=%d", OH_AudioStreamBuilder_SetChannelCount(builder, 2));
    Report("audio.stream.set_format=%d",
        OH_AudioStreamBuilder_SetSampleFormat(builder, AUDIOSTREAM_SAMPLE_S16LE));
    Report("audio.stream.set_encoding=%d",
        OH_AudioStreamBuilder_SetEncodingType(builder, AUDIOSTREAM_ENCODING_TYPE_RAW));
    Report("audio.stream.set_latency=%d",
        OH_AudioStreamBuilder_SetLatencyMode(builder, AUDIOSTREAM_LATENCY_MODE_NORMAL));
    Report("audio.stream.set_usage=%d",
        OH_AudioStreamBuilder_SetRendererInfo(builder, AUDIOSTREAM_USAGE_MUSIC));
    Report("audio.stream.set_callbacks=%d",
        OH_AudioStreamBuilder_SetRendererCallback(builder, callbacks, nullptr));
    Report("audio.stream.set_frame_size=%d",
        OH_AudioStreamBuilder_SetFrameSizeInCallback(builder, 480));

    result = OH_AudioStreamBuilder_GenerateRenderer(builder, &renderer);
    Report("audio.stream.generate=%d renderer=%d", result, renderer != nullptr);
    if (result == AUDIOSTREAM_SUCCESS && renderer != nullptr) {
        int64_t frames = -1;
        Report("audio.stream.start=%d", OH_AudioRenderer_Start(renderer));
        usleep(750000);
        Report("audio.stream.state_result=%d state=%d",
            OH_AudioRenderer_GetCurrentState(renderer, &state), state);
        Report("audio.stream.frames_result=%d frames=%lld",
            OH_AudioRenderer_GetFramesWritten(renderer, &frames), static_cast<long long>(frames));
        Report("audio.stream.callbacks=%u bytes=%u error=%d",
            g_audioWriteCallbacks, g_audioWriteBytes, g_audioCallbackError);
        Report("audio.stream.stop=%d", OH_AudioRenderer_Stop(renderer));
        Report("audio.stream.release=%d", OH_AudioRenderer_Release(renderer));
    }
    Report("audio.stream.builder_destroy=%d", OH_AudioStreamBuilder_Destroy(builder));
}

void ProbeBatteryAndDisplay()
{
    uint64_t id = 0;
    int32_t width = 0;
    int32_t height = 0;
    uint32_t refresh = 0;
    Report("battery.capacity=%d plugged_type=%d", OH_BatteryInfo_GetCapacity(),
        static_cast<int>(OH_BatteryInfo_GetPluggedType()));
    int32_t idResult = OH_NativeDisplayManager_GetDefaultDisplayId(&id);
    int32_t widthResult = OH_NativeDisplayManager_GetDefaultDisplayWidth(&width);
    int32_t heightResult = OH_NativeDisplayManager_GetDefaultDisplayHeight(&height);
    int32_t refreshResult = OH_NativeDisplayManager_GetDefaultDisplayRefreshRate(&refresh);
    Report("display.id.result=%d id=%llu", idResult, static_cast<unsigned long long>(id));
    Report("display.width.result=%d width=%d", widthResult, width);
    Report("display.height.result=%d height=%d", heightResult, height);
    Report("display.refresh.result=%d hz=%u", refreshResult, refresh);
}

void ProbeConnectivityAndDeviceServices()
{
    Bluetooth_SwitchState bluetoothState = BLUETOOTH_STATE_OFF;
    Bluetooth_ResultCode bluetoothResult = OH_Bluetooth_GetBluetoothSwitchState(&bluetoothState);
    Report("bluetooth.switch.result=%d state=%d", bluetoothResult, bluetoothState);

    bool wifiEnabled = false;
    Wifi_ResultCode wifiResult = OH_Wifi_IsWifiEnabled(&wifiEnabled);
    Report("wifi.enabled.result=%d enabled=%d", wifiResult, wifiEnabled);

    bool locationEnabled = false;
    Location_ResultCode locationResult = OH_Location_IsLocatingEnabled(&locationEnabled);
    Report("location.enabled.result=%d enabled=%d", locationResult, locationEnabled);
    Location_RequestConfig *locationConfig = OH_Location_CreateRequestConfig();
    Report("location.config.created=%d", locationConfig != nullptr);
    if (locationConfig != nullptr) {
        OH_LocationRequestConfig_SetInterval(locationConfig, 1);
        OH_LocationRequestConfig_SetCallback(locationConfig, OnLocation, nullptr);
        Location_ResultCode startLocation = OH_Location_StartLocating(locationConfig);
        if (startLocation == LOCATION_SUCCESS) {
            sleep(10);
        }
        Location_ResultCode stopLocation = OH_Location_StopLocating(locationConfig);
        Report("location.start.result=%d stop.result=%d callbacks=%d",
            startLocation, stopLocation, g_locationCallbackCount);
        OH_Location_DestroyRequestConfig(locationConfig);
    }

    int32_t hasDefault = -1;
    NetConn_NetHandle handle{};
    int32_t hasDefaultResult = OH_NetConn_HasDefaultNet(&hasDefault);
    int32_t getDefaultResult = OH_NetConn_GetDefaultNet(&handle);
    Report("network.has_default.result=%d has_default=%d", hasDefaultResult, hasDefault);
    Report("network.get_default.result=%d net_id=%d", getDefaultResult, handle.netId);

    Telephony_NetworkState telephonyState{};
    Telephony_RadioResult telephonyResult = OH_Telephony_GetNetworkState(&telephonyState);
    Report("telephony.network.result=%d", telephonyResult);

    Vibrator_Attribute vibratorAttribute{};
    int32_t vibratorResult = OH_Vibrator_PlayVibration(10, vibratorAttribute);
    int32_t vibratorCancel = OH_Vibrator_Cancel();
    Report("vibrator.play.result=%d cancel=%d", vibratorResult, vibratorCancel);
}

napi_value Run(napi_env env, napi_callback_info)
{
    unlink(RESULT);
    ProbeCamera();
    ProbeSensor();
    ProbeAudio();
    ProbeAudioStream();
    ProbeBatteryAndDisplay();
    ProbeConnectivityAndDeviceServices();
    Report("SUMMARY complete=1");
    napi_value result;
    napi_get_undefined(env, &result);
    return result;
}

napi_value Append(napi_env env, napi_callback_info info)
{
    size_t argc = 1;
    napi_value argv[1] = {nullptr};
    napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr);
    if (argc == 1 && argv[0] != nullptr) {
        size_t size = 0;
        if (napi_get_value_string_utf8(env, argv[0], nullptr, 0, &size) == napi_ok) {
            char *message = new char[size + 1]();
            if (napi_get_value_string_utf8(env, argv[0], message, size + 1, &size) == napi_ok) {
                Report("%s", message);
            }
            delete[] message;
        }
    }
    napi_value result;
    napi_get_undefined(env, &result);
    return result;
}

void ReportModuleExports(napi_env env, const char *name, napi_value module)
{
    napi_value propertyNames = nullptr;
    napi_status status = napi_get_property_names(env, module, &propertyNames);
    uint32_t count = 0;
    if (status == napi_ok) {
        status = napi_get_array_length(env, propertyNames, &count);
    }
    Report("module.exports=%s|status:%d|count:%u", name, status, count);
    if (status != napi_ok) {
        return;
    }
    for (uint32_t index = 0; index < count; ++index) {
        napi_value property = nullptr;
        napi_value text = nullptr;
        size_t size = 0;
        if (napi_get_element(env, propertyNames, index, &property) != napi_ok ||
            napi_coerce_to_string(env, property, &text) != napi_ok ||
            napi_get_value_string_utf8(env, text, nullptr, 0, &size) != napi_ok) {
            Report("module.export=%s|index:%u|key:<unreadable>", name, index);
            continue;
        }
        char *key = new char[size + 1]();
        if (napi_get_value_string_utf8(env, text, key, size + 1, &size) == napi_ok) {
            for (size_t offset = 0; offset < size; ++offset) {
                if (key[offset] == '\n' || key[offset] == '\r' || key[offset] == '|') {
                    key[offset] = '_';
                }
            }
            napi_value value = nullptr;
            napi_status valueStatus = napi_get_property(env, module, property, &value);
            napi_valuetype valueType = napi_undefined;
            if (valueStatus == napi_ok && value != nullptr) {
                valueStatus = napi_typeof(env, value, &valueType);
            }
            Report("module.export=%s|index:%u|key:%s|type:%d|status:%d",
                name, index, key, valueType, valueStatus);
        }
        delete[] key;
    }
}

napi_value LoadModule(napi_env env, napi_callback_info info)
{
    size_t argc = 1;
    napi_value argv[1] = {nullptr};
    napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr);
    if (argc != 1 || argv[0] == nullptr) {
        napi_value invalid;
        napi_create_int32(env, static_cast<int32_t>(napi_invalid_arg), &invalid);
        return invalid;
    }
    size_t size = 0;
    if (napi_get_value_string_utf8(env, argv[0], nullptr, 0, &size) != napi_ok) {
        napi_value invalid;
        napi_create_int32(env, static_cast<int32_t>(napi_string_expected), &invalid);
        return invalid;
    }
    char *name = new char[size + 1]();
    napi_get_value_string_utf8(env, argv[0], name, size + 1, &size);
    napi_value module = nullptr;
    napi_status status = napi_load_module(env, name, &module);
    bool pending = false;
    napi_is_exception_pending(env, &pending);
    if (pending) {
        napi_value exception;
        napi_get_and_clear_last_exception(env, &exception);
    }
    napi_valuetype type = napi_undefined;
    if (module != nullptr) {
        napi_typeof(env, module, &type);
    }
    Report("module.load=%s|status:%d|exception:%d|type:%d", name, status, pending, type);
    if (status == napi_ok && module != nullptr) {
        ReportModuleExports(env, name, module);
    }
    delete[] name;
    napi_value result;
    napi_create_int32(env, static_cast<int32_t>(status), &result);
    return result;
}

napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor methods[] = {
        {"run", nullptr, Run, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"append", nullptr, Append, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"loadModule", nullptr, LoadModule, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    napi_define_properties(env, exports, sizeof(methods) / sizeof(methods[0]), methods);
    return exports;
}

napi_module module{1, 0, nullptr, Init, "capabilityprobe", nullptr, {0}};
}

extern "C" __attribute__((constructor)) void RegisterCapabilityProbe()
{
    napi_module_register(&module);
}
