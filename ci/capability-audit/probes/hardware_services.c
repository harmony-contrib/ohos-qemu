#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include <BasicServicesKit/ohbattery_info.h>
#include <ConnectivityKit/bluetooth/oh_bluetooth.h>
#include <ConnectivityKit/wifi/oh_wifi.h>
#include <LocationKit/oh_location.h>
#include <multimedia/image_effect/image_effect.h>
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

static void probe_battery(void)
{
    printf("battery.capacity=%d\n", OH_BatteryInfo_GetCapacity());
    printf("battery.plugged_type=%d\n", (int)OH_BatteryInfo_GetPluggedType());
}

static void probe_bluetooth(void)
{
    Bluetooth_SwitchState state = BLUETOOTH_STATE_OFF;
    Bluetooth_ResultCode result = OH_Bluetooth_GetBluetoothSwitchState(&state);
    printf("bluetooth.switch.result=%d state=%d\n", result, state);
}

static void probe_wifi(void)
{
    bool enabled = false;
    Wifi_ResultCode result = OH_Wifi_IsWifiEnabled(&enabled);
    printf("wifi.enabled.result=%d enabled=%d\n", result, enabled);
}

static void probe_location(void)
{
    bool enabled = false;
    Location_ResultCode result = OH_Location_IsLocatingEnabled(&enabled);
    printf("location.enabled.result=%d enabled=%d\n", result, enabled);
}

static void probe_network(void)
{
    int32_t hasDefault = -1;
    NetConn_NetHandle handle = {0};
    printf("network.has_default.result=%d has_default=%d\n",
        OH_NetConn_HasDefaultNet(&hasDefault), hasDefault);
    printf("network.get_default.result=%d net_id=%d\n",
        OH_NetConn_GetDefaultNet(&handle), handle.netId);
}

static void probe_audio(void)
{
    OH_AudioManager *manager = NULL;
    OH_AudioScene scene = AUDIO_SCENE_DEFAULT;
    OH_AudioRoutingManager *routing = NULL;
    OH_AudioDeviceDescriptorArray *devices = NULL;
    OH_AudioCommon_Result getManager = OH_GetAudioManager(&manager);
    printf("audio.manager.result=%d manager=%p\n", getManager, (void *)manager);
    if (manager != NULL) {
        printf("audio.scene.result=%d scene=%d\n", OH_GetAudioScene(manager, &scene), scene);
    }
    OH_AudioCommon_Result getRouting = OH_AudioManager_GetAudioRoutingManager(&routing);
    printf("audio.routing.result=%d manager=%p\n", getRouting, (void *)routing);
    if (routing != NULL) {
        OH_AudioCommon_Result getDevices =
            OH_AudioRoutingManager_GetDevices(routing, AUDIO_DEVICE_FLAG_ALL, &devices);
        printf("audio.devices.result=%d count=%u\n", getDevices, devices == NULL ? 0 : devices->size);
        if (devices != NULL) {
            printf("audio.devices.release=%d\n", OH_AudioRoutingManager_ReleaseDevices(routing, devices));
        }
    }
}

static volatile uint32_t audioWriteCallbacks;
static volatile uint32_t audioWriteBytes;
static volatile int32_t audioCallbackError;

static int32_t on_audio_write(
    OH_AudioRenderer *renderer, void *userData, void *buffer, int32_t length)
{
    (void)renderer;
    (void)userData;
    if (buffer != NULL && length > 0) {
        memset(buffer, 0, (size_t)length);
        audioWriteCallbacks++;
        audioWriteBytes += (uint32_t)length;
    }
    return 0;
}

static int32_t on_audio_event(
    OH_AudioRenderer *renderer, void *userData, OH_AudioStream_Event event)
{
    (void)renderer;
    (void)userData;
    printf("audio_stream.event=%d\n", event);
    return 0;
}

static int32_t on_audio_interrupt(
    OH_AudioRenderer *renderer, void *userData,
    OH_AudioInterrupt_ForceType type, OH_AudioInterrupt_Hint hint)
{
    (void)renderer;
    (void)userData;
    printf("audio_stream.interrupt.type=%d hint=%d\n", type, hint);
    return 0;
}

static int32_t on_audio_error(
    OH_AudioRenderer *renderer, void *userData, OH_AudioStream_Result error)
{
    (void)renderer;
    (void)userData;
    audioCallbackError = error;
    printf("audio_stream.callback_error=%d\n", error);
    return 0;
}

static void probe_audio_stream(void)
{
    OH_AudioStreamBuilder *builder = NULL;
    OH_AudioRenderer *renderer = NULL;
    OH_AudioStream_State state = AUDIOSTREAM_STATE_INVALID;
    OH_AudioRenderer_Callbacks callbacks = {
        .OH_AudioRenderer_OnWriteData = on_audio_write,
        .OH_AudioRenderer_OnStreamEvent = on_audio_event,
        .OH_AudioRenderer_OnInterruptEvent = on_audio_interrupt,
        .OH_AudioRenderer_OnError = on_audio_error,
    };
    OH_AudioStream_Result result =
        OH_AudioStreamBuilder_Create(&builder, AUDIOSTREAM_TYPE_RENDERER);
    printf("audio_stream.builder_create=%d builder=%p\n", result, (void *)builder);
    if (result != AUDIOSTREAM_SUCCESS || builder == NULL) {
        return;
    }

    printf("audio_stream.set_rate=%d\n",
        OH_AudioStreamBuilder_SetSamplingRate(builder, 48000));
    printf("audio_stream.set_channels=%d\n",
        OH_AudioStreamBuilder_SetChannelCount(builder, 2));
    printf("audio_stream.set_format=%d\n",
        OH_AudioStreamBuilder_SetSampleFormat(builder, AUDIOSTREAM_SAMPLE_S16LE));
    printf("audio_stream.set_encoding=%d\n",
        OH_AudioStreamBuilder_SetEncodingType(builder, AUDIOSTREAM_ENCODING_TYPE_RAW));
    printf("audio_stream.set_latency=%d\n",
        OH_AudioStreamBuilder_SetLatencyMode(builder, AUDIOSTREAM_LATENCY_MODE_NORMAL));
    printf("audio_stream.set_usage=%d\n",
        OH_AudioStreamBuilder_SetRendererInfo(builder, AUDIOSTREAM_USAGE_MUSIC));
    printf("audio_stream.set_callbacks=%d\n",
        OH_AudioStreamBuilder_SetRendererCallback(builder, callbacks, NULL));
    printf("audio_stream.set_frame_size=%d\n",
        OH_AudioStreamBuilder_SetFrameSizeInCallback(builder, 480));

    result = OH_AudioStreamBuilder_GenerateRenderer(builder, &renderer);
    printf("audio_stream.generate=%d renderer=%p\n", result, (void *)renderer);
    if (result == AUDIOSTREAM_SUCCESS && renderer != NULL) {
        int64_t frames = -1;
        printf("audio_stream.start=%d\n", OH_AudioRenderer_Start(renderer));
        usleep(750000);
        printf("audio_stream.state_result=%d state=%d\n",
            OH_AudioRenderer_GetCurrentState(renderer, &state), state);
        printf("audio_stream.frames_result=%d frames=%lld\n",
            OH_AudioRenderer_GetFramesWritten(renderer, &frames), (long long)frames);
        printf("audio_stream.callbacks=%u bytes=%u error=%d\n",
            audioWriteCallbacks, audioWriteBytes, audioCallbackError);
        printf("audio_stream.stop=%d\n", OH_AudioRenderer_Stop(renderer));
        printf("audio_stream.release=%d\n", OH_AudioRenderer_Release(renderer));
    }
    printf("audio_stream.builder_destroy=%d\n", OH_AudioStreamBuilder_Destroy(builder));
}

static void probe_camera(void)
{
    Camera_Manager *manager = NULL;
    Camera_Device *cameras = NULL;
    uint32_t count = 0;
    Camera_ErrorCode result = OH_Camera_GetCameraManager(&manager);
    printf("camera.manager.result=%d manager=%p\n", result, (void *)manager);
    if (manager != NULL) {
        result = OH_CameraManager_GetSupportedCameras(manager, &cameras, &count);
        printf("camera.devices.result=%d count=%u\n", result, count);
        if (cameras != NULL) {
            printf("camera.devices.delete=%d\n",
                OH_CameraManager_DeleteSupportedCameras(manager, cameras, count));
        }
        printf("camera.manager.delete=%d\n", OH_Camera_DeleteCameraManager(manager));
    }
}

static void probe_sensor(void)
{
    Sensor_Info *infos = NULL;
    uint32_t count = 0;
    Sensor_Result result = OH_Sensor_GetInfos(&infos, &count);
    printf("sensor.infos.result=%d count=%u\n", result, count);
}

static void probe_vibrator(void)
{
    Vibrator_Attribute attribute = {0};
    int32_t result = OH_Vibrator_PlayVibration(10, attribute);
    printf("vibrator.play.result=%d cancel=%d\n", result, OH_Vibrator_Cancel());
}

static void probe_telephony(void)
{
    Telephony_NetworkState state = {0};
    Telephony_RadioResult result = OH_Telephony_GetNetworkState(&state);
    printf("telephony.network.result=%d\n", result);
}

static void probe_display(void)
{
    uint64_t id = 0;
    int32_t width = 0;
    int32_t height = 0;
    uint32_t refresh = 0;
    printf("display.id.result=%d id=%llu\n",
        OH_NativeDisplayManager_GetDefaultDisplayId(&id), (unsigned long long)id);
    printf("display.width.result=%d width=%d\n",
        OH_NativeDisplayManager_GetDefaultDisplayWidth(&width), width);
    printf("display.height.result=%d height=%d\n",
        OH_NativeDisplayManager_GetDefaultDisplayHeight(&height), height);
    printf("display.refresh.result=%d hz=%u\n",
        OH_NativeDisplayManager_GetDefaultDisplayRefreshRate(&refresh), refresh);
}

static void probe_image_effect(void)
{
    OH_ImageEffect *effect = OH_ImageEffect_Create("capability-audit");
    printf("image_effect.create=%d\n", effect != NULL);
    if (effect == NULL) {
        return;
    }
    OH_EffectFilter *filter = OH_ImageEffect_AddFilter(effect, OH_EFFECT_BRIGHTNESS_FILTER);
    printf("image_effect.add_brightness=%d count=%d\n",
        filter != NULL, OH_ImageEffect_GetFilterCount(effect));
    printf("image_effect.release=%d\n", OH_ImageEffect_Release(effect));
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
#if defined(PROBE_BATTERY)
    probe_battery();
#elif defined(PROBE_BLUETOOTH)
    probe_bluetooth();
#elif defined(PROBE_WIFI)
    probe_wifi();
#elif defined(PROBE_LOCATION)
    probe_location();
#elif defined(PROBE_NETWORK)
    probe_network();
#elif defined(PROBE_AUDIO)
    probe_audio();
#elif defined(PROBE_AUDIO_STREAM)
    probe_audio_stream();
#elif defined(PROBE_CAMERA)
    probe_camera();
#elif defined(PROBE_SENSOR)
    probe_sensor();
#elif defined(PROBE_VIBRATOR)
    probe_vibrator();
#elif defined(PROBE_TELEPHONY)
    probe_telephony();
#elif defined(PROBE_DISPLAY)
    probe_display();
#elif defined(PROBE_IMAGE_EFFECT)
    probe_image_effect();
#else
#error One PROBE_* family must be selected
#endif
    return 0;
}
