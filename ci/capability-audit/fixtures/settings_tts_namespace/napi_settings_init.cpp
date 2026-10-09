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
#include <map>
#include <string>
#include "napi_settings.h"
#include "napi_settings_log.h"

namespace OHOS {
namespace Settings {
class TableName
{
public:
    static const std::string GLOBAL;
    static const std::string SYSTEM;
    static const std::string SECURE;
};

class DomainName
{
public:
    static const std::string DEVICE_SHARED;
    static const std::string USER_PROPERTY;
    static const std::string USER_SECURITY;
};

class Date
{
public:
    static const std::string DATE_FORMAT;
    static const std::string TIME_FORMAT;
    static const std::string AUTO_GAIN_TIME;
    static const std::string AUTO_GAIN_TIME_ZONE;
};

class Display
{
public:
    static const std::string FONT_SCALE;
    static const std::string SCREEN_BRIGHTNESS_STATUS;
    static const std::string AUTO_SCREEN_BRIGHTNESS;
    static const int AUTO_SCREEN_BRIGHTNESS_MODE;
    static const int MANUAL_SCREEN_BRIGHTNESS_MODE;
    static const std::string SCREEN_OFF_TIMEOUT;
    static const std::string DEFAULT_SCREEN_ROTATION;
    static const std::string ANIMATOR_DURATION_SCALE;
    static const std::string TRANSITION_ANIMATION_SCALE;
    static const std::string WINDOW_ANIMATION_SCALE;
    static const std::string DISPLAY_INVERSION_STATUS;
};

class General
{
public:
    static const std::string SETUP_WIZARD_FINISHED;
    static const std::string END_BUTTON_ACTION;
    static const std::string AIRPLANE_MODE_STATUS;
    static const std::string ACCELEROMETER_ROTATION_STATUS;
    static const std::string DEVICE_PROVISION_STATUS;
    static const std::string HDC_STATUS;
    static const std::string BOOT_COUNTING;
    static const std::string CONTACT_METADATA_SYNC_STATUS;
    static const std::string DEVELOPMENT_SETTINGS_STATUS;
    static const std::string DEVICE_NAME;
    static const std::string USB_STORAGE_STATUS;
    static const std::string DEBUGGER_WAITING;
    static const std::string DEBUG_APP_PACKAGE;
    static const std::string ACCESSIBILITY_STATUS;
    static const std::string ACTIVATED_ACCESSIBILITY_SERVICES;
    static const std::string GEOLOCATION_ORIGINS_ALLOWED;
    static const std::string SKIP_USE_HINTS;
    static const std::string TOUCH_EXPLORATION_STATUS;
};

class Input
{
public:
    static const std::string DEFAULT_INPUT_METHOD;
    static const std::string ACTIVATED_INPUT_METHOD_SUB_MODE;
    static const std::string ACTIVATED_INPUT_METHODS;
    static const std::string SELECTOR_VISIBILITY_FOR_INPUT_METHOD;
    static const std::string AUTO_CAPS_TEXT_INPUT;
    static const std::string AUTO_PUNCTUATE_TEXT_INPUT;
    static const std::string AUTO_REPLACE_TEXT_INPUT;
    static const std::string SHOW_PASSWORD_TEXT_INPUT;
};

class Network
{
public:
    static const std::string DATA_ROAMING_STATUS;
    static const std::string HTTP_PROXY_CFG;
    static const std::string NETWORK_PREFERENCE_USAGE;
};

class Phone
{
public:
    static const std::string RTT_CALLING_STATUS;
};

class Sound
{
public:
    static const std::string VIBRATE_WHILE_RINGING;
    static const std::string DEFAULT_ALARM_ALERT;
    static const std::string DTMF_TONE_TYPE_WHILE_DIALING;
    static const std::string DTMF_TONE_WHILE_DIALING;
    static const std::string HAPTIC_FEEDBACK_STATUS;
    static const std::string AFFECTED_MODE_RINGER_STREAMS;
    static const std::string AFFECTED_MUTE_STREAMS;
    static const std::string DEFAULT_NOTIFICATION_SOUND;
    static const std::string DEFAULT_RINGTONE;
    static const std::string SOUND_EFFECTS_STATUS;
    static const std::string VIBRATE_STATUS;
    // temp audio key, it will be modify in the feature
    static const std::string AUDIO_RINGTONE;
    static const std::string AUDIO_MEDIA;
    static const std::string AUDIO_VOICECALL;
};

class TTS
{
public:
    static const std::string DEFAULT_TTS_PITCH;
    static const std::string DEFAULT_TTS_RATE;
    static const std::string DEFAULT_TTS_SYNTH;
    static const std::string ENABLED_TTS_PLUGINS;
};

class Wireless
{
public:
    static const std::string BLUETOOTH_RADIO;
    static const std::string CELL_RADIO;
    static const std::string NFC_RADIO;
    static const std::string AIRPLANE_MODE_RADIOS;
    static const std::string BLUETOOTH_STATUS;
    static const std::string BLUETOOTH_DISCOVER_ABILITY_STATUS;
    static const std::string BLUETOOTH_DISCOVER_TIMEOUT;
    static const std::string WIFI_DHCP_MAX_RETRY_COUNT;
    static const std::string WIFI_TO_MOBILE_DATA_AWAKE_TIMEOUT;
    static const std::string WIFI_STATUS;
    static const std::string WIFI_WATCHDOG_STATUS;
    static const std::string WIFI_RADIO;
    static const std::string OWNER_LOCKDOWN_WIFI_CFG;
};

class Power
{
public:
    static const std::string SUSPEND_SOURCES_CFG;
};

const std::string TableName::GLOBAL = "global";
const std::string TableName::SYSTEM = "system";
const std::string TableName::SECURE = "secure";
const std::string DomainName::DEVICE_SHARED = "global";
const std::string DomainName::USER_PROPERTY = "system";
const std::string DomainName::USER_SECURITY = "secure";

const std::string Date::DATE_FORMAT = "settings.date.date_format";
const std::string Date::TIME_FORMAT = "settings.date.time_format";
const std::string Date::AUTO_GAIN_TIME = "settings.date.auto_gain_time";
const std::string Date::AUTO_GAIN_TIME_ZONE = "settings.date.auto_gain_time_zone";

const std::string Display::FONT_SCALE = "font_scale";
const std::string Display::SCREEN_BRIGHTNESS_STATUS = "settings.display.screen_brightness_status";
const std::string Display::AUTO_SCREEN_BRIGHTNESS = "settings.display.auto_screen_brightness";
const int Display::AUTO_SCREEN_BRIGHTNESS_MODE = 1;
const int Display::MANUAL_SCREEN_BRIGHTNESS_MODE = 0;
const std::string Display::SCREEN_OFF_TIMEOUT = "settings.display.screen_off_timeout";
const std::string Display::DEFAULT_SCREEN_ROTATION = "settings.display.default_screen_rotation";
const std::string Display::ANIMATOR_DURATION_SCALE = "settings.display.animator_duration_scale";
const std::string Display::TRANSITION_ANIMATION_SCALE = "settings.display.transition_animation_scale";
const std::string Display::WINDOW_ANIMATION_SCALE = "settings.display.window_animation_scale";
const std::string Display::DISPLAY_INVERSION_STATUS = "settings.display.display_inversion_status";

const std::string General::SETUP_WIZARD_FINISHED = "settings.general.setup_wizard_finished";
const std::string General::END_BUTTON_ACTION = "settings.general.end_button_action";
const std::string General::AIRPLANE_MODE_STATUS = "settings.general.airplane_mode_status";
const std::string General::ACCELEROMETER_ROTATION_STATUS = "settings.general.accelerometer_rotation_status";
const std::string General::DEVICE_PROVISION_STATUS = "settings.general.device_provision_status";
const std::string General::HDC_STATUS = "settings.general.hdc_status";
const std::string General::BOOT_COUNTING = "settings.general.boot_counting";
const std::string General::CONTACT_METADATA_SYNC_STATUS = "settings.general.contact_metadata_sync_status";
const std::string General::DEVELOPMENT_SETTINGS_STATUS = "settings.general.development_settings_status";
const std::string General::DEVICE_NAME = "settings.general.device_name";
const std::string General::USB_STORAGE_STATUS = "settings.general.usb_storage_status";
const std::string General::DEBUGGER_WAITING = "settings.general.debugger_waiting";
const std::string General::DEBUG_APP_PACKAGE = "settings.general.debug_app_package";
const std::string General::ACCESSIBILITY_STATUS = "settings.general.accessibility_status";
const std::string General::ACTIVATED_ACCESSIBILITY_SERVICES = "settings.general.activated_accessibility_services";
const std::string General::GEOLOCATION_ORIGINS_ALLOWED = "settings.general.geolocation_origins_allowed";
const std::string General::SKIP_USE_HINTS = "settings.general.skip_use_hints";
const std::string General::TOUCH_EXPLORATION_STATUS = "settings.general.touch_exploration_status";

const std::string Input::DEFAULT_INPUT_METHOD = "settings.input.default_input_method";
const std::string Input::ACTIVATED_INPUT_METHOD_SUB_MODE = "settings.input.activated_input_method_submode";
const std::string Input::ACTIVATED_INPUT_METHODS = "settings.input.activated_input_methods";
const std::string Input::SELECTOR_VISIBILITY_FOR_INPUT_METHOD = "settings.input.selector_visibility_for_input_method";
const std::string Input::AUTO_CAPS_TEXT_INPUT = "settings.input.auto_caps_text_input";
const std::string Input::AUTO_PUNCTUATE_TEXT_INPUT = "settings.input.auto_punctuate_text_input";
const std::string Input::AUTO_REPLACE_TEXT_INPUT = "settings.input.auto_replace_text_input";
const std::string Input::SHOW_PASSWORD_TEXT_INPUT = "settings.input.show_password_text_input";

const std::string Network::DATA_ROAMING_STATUS = "settings.network.data_roaming_status";
const std::string Network::HTTP_PROXY_CFG = "settings.network.http_proxy_cfg";
const std::string Network::NETWORK_PREFERENCE_USAGE = "settings.network.network_preference_usage";

const std::string Phone::RTT_CALLING_STATUS = "settings.phone.rtt_calling_status";

const std::string Sound::VIBRATE_WHILE_RINGING = "settings.sound.vibrate_while_ringing";
const std::string Sound::DEFAULT_ALARM_ALERT = "settings.sound.default_alarm_alert";
const std::string Sound::DTMF_TONE_TYPE_WHILE_DIALING = "settings.sound.dtmf_tone_type_while_dialing";
const std::string Sound::DTMF_TONE_WHILE_DIALING = "settings.sound.dtmf_tone_while_dialing";
const std::string Sound::HAPTIC_FEEDBACK_STATUS = "settings.sound.haptic_feedback_status";
const std::string Sound::AFFECTED_MODE_RINGER_STREAMS = "settings.sound.affected_mode_ringer_streams";
const std::string Sound::AFFECTED_MUTE_STREAMS = "settings.sound.affected_mute_streams";
const std::string Sound::DEFAULT_NOTIFICATION_SOUND = "settings.sound.default_notification_sound";
const std::string Sound::DEFAULT_RINGTONE = "settings.sound.default_ringtone";
const std::string Sound::SOUND_EFFECTS_STATUS = "settings.sound.sound_effects_status";
const std::string Sound::VIBRATE_STATUS = "settings.sound.vibrate_status";

const std::string TTS::DEFAULT_TTS_PITCH = "settings.tts.default_tts_pitch";
const std::string TTS::DEFAULT_TTS_RATE = "settings.tts.default_tts_rate";
const std::string TTS::DEFAULT_TTS_SYNTH = "settings.tts.default_tts_synth";
const std::string TTS::ENABLED_TTS_PLUGINS = "settings.tts.enabled_tts_plugins";

const std::string Wireless::BLUETOOTH_RADIO = "settings.wireless.bluetooth_radio";
const std::string Wireless::CELL_RADIO = "settings.wireless.cell_radio";
const std::string Wireless::NFC_RADIO = "settings.wireless.nfc_radio";
const std::string Wireless::AIRPLANE_MODE_RADIOS = "settings.wireless.airplane_mode_radios";
const std::string Wireless::BLUETOOTH_STATUS = "settings.wireless.bluetooth_status";
const std::string Wireless::BLUETOOTH_DISCOVER_ABILITY_STATUS = "settings.wireless.bluetooth_discoverability_status";
const std::string Wireless::BLUETOOTH_DISCOVER_TIMEOUT = "settings.wireless.bluetooth_discover_timeout";
const std::string Wireless::WIFI_DHCP_MAX_RETRY_COUNT = "settings.wireless.wifi_dhcp_max_retry_count";
const std::string Wireless::WIFI_TO_MOBILE_DATA_AWAKE_TIMEOUT = "settings.wireless.wifi_to_mobile_data_awake_timeout";
const std::string Wireless::WIFI_STATUS = "settings.wireless.wifi_status";
const std::string Wireless::WIFI_WATCHDOG_STATUS = "settings.wireless.wifi_watchdog_status";
const std::string Wireless::WIFI_RADIO = "settings.wireless.wifi_radio";
const std::string Wireless::OWNER_LOCKDOWN_WIFI_CFG = "settings.wireless.owner_lockdown_wifi_cfg";

const std::string Power::SUSPEND_SOURCES_CFG = "settings.power.suspend_sources";

const std::string TableName_CLASS_NAME = "tableName";
const std::string DomainName_CLASS_NAME = "domainName";
const std::string DATE_CLASS_NAME = "date";
const std::string DISPLAY_CLASS_NAME = "display";
const std::string GENERAL_CLASS_NAME = "general";
const std::string INPUT_CLASS_NAME = "input";
const std::string NETWORK_CLASS_NAME = "network";
const std::string PHONE_CLASS_NAME = "phone";
const std::string SOUND_CLASS_NAME = "sound";
const std::string TTS_CLASS_NAME = "tts";
const std::string WIRELESS_CLASS_NAME = "wireless";
const std::string POWER_CLASS_NAME = "power";

napi_value ClassConstructor(napi_env env, napi_callback_info info)
{
    SETTING_LOG_INFO("%{public}s is called", __FUNCTION__);
    size_t argc = 0;
    napi_value argv = nullptr;
    napi_value thisArg = nullptr;
    void* data = nullptr;
    napi_get_cb_info(env, info, &argc, &argv, &thisArg, &data);

    napi_value global = 0;
    napi_get_global(env, &global);
    SETTING_LOG_INFO("%{public}s is end", __FUNCTION__);
    return thisArg;
}

void InitTableNameMap(napi_env env, std::map<const char*, napi_value> &paramMap)
{
    napi_value varGlobal = nullptr;
    napi_create_string_utf8(env,
        TableName::GLOBAL.c_str(), NAPI_AUTO_LENGTH, &varGlobal);
    paramMap["GLOBAL"] = varGlobal;

    napi_value varSystem = nullptr;
    napi_create_string_utf8(env,
        TableName::SYSTEM.c_str(), NAPI_AUTO_LENGTH, &varSystem);
    paramMap["SYSTEM"] = varSystem;

    napi_value varSecure = nullptr;
    napi_create_string_utf8(env,
        TableName::SECURE.c_str(), NAPI_AUTO_LENGTH, &varSecure);
    paramMap["SECURE"] = varSecure;
}

void InitDomainNameMap(napi_env env, std::map<const char*, napi_value> &paramMap)
{
    napi_value varGlobal = nullptr;
    napi_create_string_utf8(env,
        DomainName::DEVICE_SHARED.c_str(), NAPI_AUTO_LENGTH, &varGlobal);
    paramMap["DEVICE_SHARED"] = varGlobal;

    napi_value varSystem = nullptr;
    napi_create_string_utf8(env,
        DomainName::USER_PROPERTY.c_str(), NAPI_AUTO_LENGTH, &varSystem);
    paramMap["USER_PROPERTY"] = varSystem;

    napi_value varSecure = nullptr;
    napi_create_string_utf8(env,
        DomainName::USER_SECURITY.c_str(), NAPI_AUTO_LENGTH, &varSecure);
    paramMap["USER_SECURITY"] = varSecure;
}

void InitDateMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    napi_value dateFormat = nullptr;
    napi_create_string_utf8(env,
        Date::DATE_FORMAT.c_str(), NAPI_AUTO_LENGTH, &dateFormat);
    paramMap["DATE_FORMAT"] = dateFormat;

    napi_value timeFormat = nullptr;
    napi_create_string_utf8(env,
        Date::TIME_FORMAT.c_str(), NAPI_AUTO_LENGTH, &timeFormat);
    paramMap["TIME_FORMAT"] = timeFormat;

    napi_value autoGainTime = nullptr;
    napi_create_string_utf8(env,
        Date::AUTO_GAIN_TIME.c_str(), NAPI_AUTO_LENGTH, &autoGainTime);
    paramMap["AUTO_GAIN_TIME"] = autoGainTime;

    napi_value autoGainTimeZone = nullptr;
    napi_create_string_utf8(env,
        Date::AUTO_GAIN_TIME_ZONE.c_str(), NAPI_AUTO_LENGTH, &autoGainTimeZone);
    paramMap["AUTO_GAIN_TIME_ZONE"] = autoGainTimeZone;
}

void InitDisplayMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    napi_value fontScale = nullptr;
    napi_create_string_utf8(env,
        Display::FONT_SCALE.c_str(), NAPI_AUTO_LENGTH, &fontScale);
    paramMap["FONT_SCALE"] = fontScale;

    napi_value brightnessStatus = nullptr;
    napi_create_string_utf8(env,
        Display::SCREEN_BRIGHTNESS_STATUS.c_str(), NAPI_AUTO_LENGTH, &brightnessStatus);
    paramMap["SCREEN_BRIGHTNESS_STATUS"] = brightnessStatus;

    napi_value autoScreenStatus = nullptr;
    napi_create_string_utf8(env,
        Display::AUTO_SCREEN_BRIGHTNESS.c_str(), NAPI_AUTO_LENGTH, &autoScreenStatus);
    paramMap["AUTO_SCREEN_BRIGHTNESS"] = autoScreenStatus;

    napi_value autoMode = nullptr;
    napi_create_int32(env,
        Display::AUTO_SCREEN_BRIGHTNESS_MODE, &autoMode);
    paramMap["AUTO_SCREEN_BRIGHTNESS_MODE"] = autoMode;

    napi_value manualMode = nullptr;
    napi_create_int32(env,
        Display::MANUAL_SCREEN_BRIGHTNESS_MODE, &manualMode);
    paramMap["MANUAL_SCREEN_BRIGHTNESS_MODE"] = manualMode;

    napi_value screenOffTimeout = nullptr;
    napi_create_string_utf8(env,
        Display::SCREEN_OFF_TIMEOUT.c_str(), NAPI_AUTO_LENGTH, &screenOffTimeout);
    paramMap["SCREEN_OFF_TIMEOUT"] = screenOffTimeout;

    napi_value defScreenRotation = nullptr;
    napi_create_string_utf8(env,
        Display::DEFAULT_SCREEN_ROTATION.c_str(), NAPI_AUTO_LENGTH, &defScreenRotation);
    paramMap["DEFAULT_SCREEN_ROTATION"] = defScreenRotation;

    napi_value animatorDurationScale = nullptr;
    napi_create_string_utf8(env,
        Display::ANIMATOR_DURATION_SCALE.c_str(), NAPI_AUTO_LENGTH, &animatorDurationScale);
    paramMap["ANIMATOR_DURATION_SCALE"] = animatorDurationScale;

    napi_value transiAnimationScale = nullptr;
    napi_create_string_utf8(env,
        Display::TRANSITION_ANIMATION_SCALE.c_str(), NAPI_AUTO_LENGTH, &transiAnimationScale);
    paramMap["TRANSITION_ANIMATION_SCALE"] = transiAnimationScale;

    napi_value windowAnimationScale = nullptr;
    napi_create_string_utf8(env,
        Display::WINDOW_ANIMATION_SCALE.c_str(), NAPI_AUTO_LENGTH, &windowAnimationScale);
    paramMap["WINDOW_ANIMATION_SCALE"] = windowAnimationScale;

    napi_value displayInversionStatus = nullptr;
    napi_create_string_utf8(env,
        Display::DISPLAY_INVERSION_STATUS.c_str(), NAPI_AUTO_LENGTH, &displayInversionStatus);
    paramMap["DISPLAY_INVERSION_STATUS"] = displayInversionStatus;
}

void InitGeneralMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    napi_value setupWizFinished = nullptr;
    napi_create_string_utf8(env,
        General::SETUP_WIZARD_FINISHED.c_str(), NAPI_AUTO_LENGTH, &setupWizFinished);
    paramMap["SETUP_WIZARD_FINISHED"] = setupWizFinished;

    napi_value endButtonAction = nullptr;
    napi_create_string_utf8(env,
        General::END_BUTTON_ACTION.c_str(), NAPI_AUTO_LENGTH, &endButtonAction);
    paramMap["END_BUTTON_ACTION"] = endButtonAction;

    napi_value airplaneModeStatus = nullptr;
    napi_create_string_utf8(env,
        General::AIRPLANE_MODE_STATUS.c_str(), NAPI_AUTO_LENGTH, &airplaneModeStatus);
    paramMap["AIRPLANE_MODE_STATUS"] = airplaneModeStatus;

    napi_value acceleRotationStatus = nullptr;
    napi_create_string_utf8(env,
        General::ACCELEROMETER_ROTATION_STATUS.c_str(), NAPI_AUTO_LENGTH, &acceleRotationStatus);
    paramMap["ACCELEROMETER_ROTATION_STATUS"] = acceleRotationStatus;

    napi_value devProvisionStatus = nullptr;
    napi_create_string_utf8(env,
        General::DEVICE_PROVISION_STATUS.c_str(), NAPI_AUTO_LENGTH, &devProvisionStatus);
    paramMap["DEVICE_PROVISION_STATUS"] = devProvisionStatus;

    napi_value hdcStatus = nullptr;
    napi_create_string_utf8(env,
        General::HDC_STATUS.c_str(), NAPI_AUTO_LENGTH, &hdcStatus);
    paramMap["HDC_STATUS"] = hdcStatus;

    napi_value bootCounting = nullptr;
    napi_create_string_utf8(env,
        General::BOOT_COUNTING.c_str(), NAPI_AUTO_LENGTH, &bootCounting);
    paramMap["BOOT_COUNTING"] = bootCounting;

    napi_value contactMetaSyncStatus = nullptr;
    napi_create_string_utf8(env,
        General::CONTACT_METADATA_SYNC_STATUS.c_str(), NAPI_AUTO_LENGTH, &contactMetaSyncStatus);
    paramMap["CONTACT_METADATA_SYNC_STATUS"] = contactMetaSyncStatus;

    napi_value developSettingStatus = nullptr;
    napi_create_string_utf8(env,
        General::DEVELOPMENT_SETTINGS_STATUS.c_str(), NAPI_AUTO_LENGTH, &developSettingStatus);
    paramMap["DEVELOPMENT_SETTINGS_STATUS"] = developSettingStatus;

    napi_value deviceName = nullptr;
    napi_create_string_utf8(env,
        General::DEVICE_NAME.c_str(), NAPI_AUTO_LENGTH, &deviceName);
    paramMap["DEVICE_NAME"] = deviceName;

    napi_value usbStorageStatus = nullptr;
    napi_create_string_utf8(env,
        General::USB_STORAGE_STATUS.c_str(), NAPI_AUTO_LENGTH, &usbStorageStatus);
    paramMap["USB_STORAGE_STATUS"] = usbStorageStatus;

    napi_value debuggerWaiting = nullptr;
    napi_create_string_utf8(env,
        General::DEBUGGER_WAITING.c_str(), NAPI_AUTO_LENGTH, &debuggerWaiting);
    paramMap["DEBUGGER_WAITING"] = debuggerWaiting;

    napi_value debugAppPackage = nullptr;
    napi_create_string_utf8(env,
        General::DEBUG_APP_PACKAGE.c_str(), NAPI_AUTO_LENGTH, &debugAppPackage);
    paramMap["DEBUG_APP_PACKAGE"] = debugAppPackage;

    napi_value accessibilityStatus = nullptr;
    napi_create_string_utf8(env,
        General::ACCESSIBILITY_STATUS.c_str(), NAPI_AUTO_LENGTH, &accessibilityStatus);
    paramMap["ACCESSIBILITY_STATUS"] = accessibilityStatus;

    napi_value activAccessServices = nullptr;
    napi_create_string_utf8(env,
        General::ACTIVATED_ACCESSIBILITY_SERVICES.c_str(), NAPI_AUTO_LENGTH, &activAccessServices);
    paramMap["ACTIVATED_ACCESSIBILITY_SERVICES"] = activAccessServices;

    napi_value geoOriginsAllowed = nullptr;
    napi_create_string_utf8(env,
        General::GEOLOCATION_ORIGINS_ALLOWED.c_str(), NAPI_AUTO_LENGTH, &geoOriginsAllowed);
    paramMap["GEOLOCATION_ORIGINS_ALLOWED"] = geoOriginsAllowed;

    napi_value skipUseHints = nullptr;
    napi_create_string_utf8(env,
        General::SKIP_USE_HINTS.c_str(), NAPI_AUTO_LENGTH, &skipUseHints);
    paramMap["SKIP_USE_HINTS"] = skipUseHints;

    napi_value touchExplorationStatus = nullptr;
    napi_create_string_utf8(env,
        General::TOUCH_EXPLORATION_STATUS.c_str(), NAPI_AUTO_LENGTH, &touchExplorationStatus);
    paramMap["TOUCH_EXPLORATION_STATUS"] = touchExplorationStatus;
}

void InitInputMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    napi_value defInputMethod = nullptr;
    napi_create_string_utf8(env,
            Input::DEFAULT_INPUT_METHOD.c_str(), NAPI_AUTO_LENGTH, &defInputMethod);
    paramMap["DEFAULT_INPUT_METHOD"] = defInputMethod;

    napi_value activeSubMode = nullptr;
    napi_create_string_utf8(env,
            Input::ACTIVATED_INPUT_METHOD_SUB_MODE.c_str(), NAPI_AUTO_LENGTH, &activeSubMode);
    paramMap["ACTIVATED_INPUT_METHOD_SUB_MODE"] = activeSubMode;

    napi_value activatedInputMethod = nullptr;
    napi_create_string_utf8(env,
            Input::ACTIVATED_INPUT_METHODS.c_str(), NAPI_AUTO_LENGTH, &activatedInputMethod);
    paramMap["ACTIVATED_INPUT_METHODS"] = activatedInputMethod;

    napi_value selectorVisibility = nullptr;
    napi_create_string_utf8(env,
            Input::SELECTOR_VISIBILITY_FOR_INPUT_METHOD.c_str(), NAPI_AUTO_LENGTH, &selectorVisibility);
    paramMap["SELECTOR_VISIBILITY_FOR_INPUT_METHOD"] = selectorVisibility;

    napi_value autoCapsTextInput = nullptr;
    napi_create_string_utf8(env,
            Input::AUTO_CAPS_TEXT_INPUT.c_str(), NAPI_AUTO_LENGTH, &autoCapsTextInput);
    paramMap["AUTO_CAPS_TEXT_INPUT"] = autoCapsTextInput;

    napi_value autoPunctuate = nullptr;
    napi_create_string_utf8(env,
            Input::AUTO_PUNCTUATE_TEXT_INPUT.c_str(), NAPI_AUTO_LENGTH, &autoPunctuate);
    paramMap["AUTO_PUNCTUATE_TEXT_INPUT"] = autoPunctuate;

    napi_value autoReplace = nullptr;
    napi_create_string_utf8(env,
            Input::AUTO_REPLACE_TEXT_INPUT.c_str(), NAPI_AUTO_LENGTH, &autoReplace);
    paramMap["AUTO_REPLACE_TEXT_INPUT"] = autoReplace;

    napi_value showPassword = nullptr;
    napi_create_string_utf8(env,
            Input::SHOW_PASSWORD_TEXT_INPUT.c_str(), NAPI_AUTO_LENGTH, &showPassword);
    paramMap["SHOW_PASSWORD_TEXT_INPUT"] = showPassword;
}

void InitNetworkMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    SETTING_LOG_INFO("%{public}s is called", __FUNCTION__);

    napi_value dataRoamingStatus = nullptr;
    napi_create_string_utf8(env,
            Network::DATA_ROAMING_STATUS.c_str(), NAPI_AUTO_LENGTH, &dataRoamingStatus);
    paramMap["DATA_ROAMING_STATUS"] = dataRoamingStatus;

    napi_value httpProxyCfg = nullptr;
    napi_create_string_utf8(env,
            Network::HTTP_PROXY_CFG.c_str(), NAPI_AUTO_LENGTH, &httpProxyCfg);
    paramMap["HTTP_PROXY_CFG"] = httpProxyCfg;

    napi_value networkPrefUsage = nullptr;
    napi_create_string_utf8(env,
            Network::NETWORK_PREFERENCE_USAGE.c_str(), NAPI_AUTO_LENGTH, &networkPrefUsage);
    paramMap["NETWORK_PREFERENCE_USAGE"] = networkPrefUsage;

    SETTING_LOG_INFO("%{public}s is end", __FUNCTION__);
}

void InitPhoneMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    SETTING_LOG_INFO("%{public}s is called", __FUNCTION__);

    napi_value rttCallingStatus = nullptr;
    napi_create_string_utf8(env,
        Phone::RTT_CALLING_STATUS.c_str(), NAPI_AUTO_LENGTH, &rttCallingStatus);
    paramMap["RTT_CALLING_STATUS"] = rttCallingStatus;

    SETTING_LOG_INFO("%{public}s is end", __FUNCTION__);
}

void InitSoundMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    napi_value vibrateWhileRinging = nullptr;
    napi_create_string_utf8(env,
        Sound::VIBRATE_WHILE_RINGING.c_str(), NAPI_AUTO_LENGTH, &vibrateWhileRinging);
    paramMap["VIBRATE_WHILE_RINGING"] = vibrateWhileRinging;

    napi_value defAlarmAlert = nullptr;
    napi_create_string_utf8(env,
        Sound::DEFAULT_ALARM_ALERT.c_str(), NAPI_AUTO_LENGTH, &defAlarmAlert);
    paramMap["DEFAULT_ALARM_ALERT"] = defAlarmAlert;

    napi_value dtmfToneType = nullptr;
    napi_create_string_utf8(env,
        Sound::DTMF_TONE_TYPE_WHILE_DIALING.c_str(), NAPI_AUTO_LENGTH, &dtmfToneType);
    paramMap["DTMF_TONE_TYPE_WHILE_DIALING"] = dtmfToneType;

    napi_value dtmfTone = nullptr;
    napi_create_string_utf8(env,
        Sound::DTMF_TONE_WHILE_DIALING.c_str(), NAPI_AUTO_LENGTH, &dtmfTone);
    paramMap["DTMF_TONE_WHILE_DIALING"] = dtmfTone;

    napi_value hapticFeedbackStatus = nullptr;
    napi_create_string_utf8(env,
        Sound::HAPTIC_FEEDBACK_STATUS.c_str(), NAPI_AUTO_LENGTH, &hapticFeedbackStatus);
    paramMap["HAPTIC_FEEDBACK_STATUS"] = hapticFeedbackStatus;

    napi_value affectedModeRingerStreams = nullptr;
    napi_create_string_utf8(env,
        Sound::AFFECTED_MODE_RINGER_STREAMS.c_str(), NAPI_AUTO_LENGTH, &affectedModeRingerStreams);
    paramMap["AFFECTED_MODE_RINGER_STREAMS"] = affectedModeRingerStreams;

    napi_value affectedMuteStreams = nullptr;
    napi_create_string_utf8(env,
        Sound::AFFECTED_MUTE_STREAMS.c_str(), NAPI_AUTO_LENGTH, &affectedMuteStreams);
    paramMap["AFFECTED_MUTE_STREAMS"] = affectedMuteStreams;

    napi_value defNotificationSound = nullptr;
    napi_create_string_utf8(env,
        Sound::DEFAULT_NOTIFICATION_SOUND.c_str(), NAPI_AUTO_LENGTH, &defNotificationSound);
    paramMap["DEFAULT_NOTIFICATION_SOUND"] = defNotificationSound;

    napi_value defRingtone = nullptr;
    napi_create_string_utf8(env,
        Sound::DEFAULT_RINGTONE.c_str(), NAPI_AUTO_LENGTH, &defRingtone);
    paramMap["DEFAULT_RINGTONE"] = defRingtone;

    napi_value soundEffectsStatus = nullptr;
    napi_create_string_utf8(env,
        Sound::SOUND_EFFECTS_STATUS.c_str(), NAPI_AUTO_LENGTH, &soundEffectsStatus);
    paramMap["SOUND_EFFECTS_STATUS"] = soundEffectsStatus;

    napi_value vibrateStatus = nullptr;
    napi_create_string_utf8(env,
        Sound::VIBRATE_STATUS.c_str(), NAPI_AUTO_LENGTH, &vibrateStatus);
    paramMap["VIBRATE_STATUS"] = vibrateStatus;
}

void InitTTSMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    napi_value defTTSPitch = nullptr;
    napi_create_string_utf8(env,
        TTS::DEFAULT_TTS_PITCH.c_str(), NAPI_AUTO_LENGTH, &defTTSPitch);
    paramMap["DEFAULT_TTS_PITCH"] = defTTSPitch;

    napi_value defTTSRate = nullptr;
    napi_create_string_utf8(env,
        TTS::DEFAULT_TTS_RATE.c_str(), NAPI_AUTO_LENGTH, &defTTSRate);
    paramMap["DEFAULT_TTS_RATE"] = defTTSRate;

    napi_value defTTSSynth = nullptr;
    napi_create_string_utf8(env,
        TTS::DEFAULT_TTS_SYNTH.c_str(), NAPI_AUTO_LENGTH, &defTTSSynth);
    paramMap["DEFAULT_TTS_SYNTH"] = defTTSSynth;

    napi_value enableTTSPlugins = nullptr;
    napi_create_string_utf8(env,
        TTS::ENABLED_TTS_PLUGINS.c_str(), NAPI_AUTO_LENGTH, &enableTTSPlugins);
    paramMap["ENABLED_TTS_PLUGINS"] = enableTTSPlugins;
}

void InitWirelessMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    napi_value bluetoothRadio = nullptr;
    napi_create_string_utf8(env,
        Wireless::BLUETOOTH_RADIO.c_str(), NAPI_AUTO_LENGTH, &bluetoothRadio);
    paramMap["BLUETOOTH_RADIO"] = bluetoothRadio;

    napi_value cellRadio = nullptr;
    napi_create_string_utf8(env,
        Wireless::CELL_RADIO.c_str(), NAPI_AUTO_LENGTH, &cellRadio);
    paramMap["CELL_RADIO"] = cellRadio;

    napi_value nfcRadio = nullptr;
    napi_create_string_utf8(env,
        Wireless::NFC_RADIO.c_str(), NAPI_AUTO_LENGTH, &nfcRadio);
    paramMap["NFC_RADIO"] = nfcRadio;

    napi_value airplaneModeRadios = nullptr;
    napi_create_string_utf8(env,
        Wireless::AIRPLANE_MODE_RADIOS.c_str(), NAPI_AUTO_LENGTH, &airplaneModeRadios);
    paramMap["AIRPLANE_MODE_RADIOS"] = airplaneModeRadios;

    napi_value bluetoothStatus = nullptr;
    napi_create_string_utf8(env,
        Wireless::BLUETOOTH_STATUS.c_str(), NAPI_AUTO_LENGTH, &bluetoothStatus);
    paramMap["BLUETOOTH_STATUS"] = bluetoothStatus;

    napi_value blDiscoverAbilityStatus = nullptr;
    napi_create_string_utf8(env,
        Wireless::BLUETOOTH_DISCOVER_ABILITY_STATUS.c_str(), NAPI_AUTO_LENGTH, &blDiscoverAbilityStatus);
    paramMap["BLUETOOTH_DISCOVER_ABILITY_STATUS"] = blDiscoverAbilityStatus;

    napi_value blDiscoverTimeout = nullptr;
    napi_create_string_utf8(env,
        Wireless::BLUETOOTH_DISCOVER_TIMEOUT.c_str(), NAPI_AUTO_LENGTH, &blDiscoverTimeout);
    paramMap["BLUETOOTH_DISCOVER_TIMEOUT"] = blDiscoverTimeout;

    napi_value wifiDHCPMaxRetryCount = nullptr;
    napi_create_string_utf8(env,
        Wireless::WIFI_DHCP_MAX_RETRY_COUNT.c_str(), NAPI_AUTO_LENGTH, &wifiDHCPMaxRetryCount);
    paramMap["WIFI_DHCP_MAX_RETRY_COUNT"] = wifiDHCPMaxRetryCount;

    napi_value wifiToMobileDataAwakeTimeout = nullptr;
    napi_create_string_utf8(env,
        Wireless::WIFI_TO_MOBILE_DATA_AWAKE_TIMEOUT.c_str(), NAPI_AUTO_LENGTH, &wifiToMobileDataAwakeTimeout);
    paramMap["WIFI_TO_MOBILE_DATA_AWAKE_TIMEOUT"] = wifiToMobileDataAwakeTimeout;

    napi_value wifiStatus = nullptr;
    napi_create_string_utf8(env,
        Wireless::WIFI_STATUS.c_str(), NAPI_AUTO_LENGTH, &wifiStatus);
    paramMap["WIFI_STATUS"] = wifiStatus;

    napi_value wifiWatchDogStatus = nullptr;
    napi_create_string_utf8(env,
        Wireless::WIFI_WATCHDOG_STATUS.c_str(), NAPI_AUTO_LENGTH, &wifiWatchDogStatus);
    paramMap["WIFI_WATCHDOG_STATUS"] = wifiWatchDogStatus;

    napi_value wifiRadio = nullptr;
    napi_create_string_utf8(env,
        Wireless::WIFI_RADIO.c_str(), NAPI_AUTO_LENGTH, &wifiRadio);
    paramMap["WIFI_RADIO"] = wifiRadio;

    napi_value ownerLockdownWifiCfg = nullptr;
    napi_create_string_utf8(env,
        Wireless::OWNER_LOCKDOWN_WIFI_CFG.c_str(), NAPI_AUTO_LENGTH, &ownerLockdownWifiCfg);
    paramMap["OWNER_LOCKDOWN_WIFI_CFG"] = ownerLockdownWifiCfg;
}

void InitPowerMap(napi_env env, std::map<const char*, napi_value>& paramMap)
{
    napi_value suspendSourcesCfg = nullptr;
    napi_create_string_utf8(env,
        Power::SUSPEND_SOURCES_CFG.c_str(), NAPI_AUTO_LENGTH, &suspendSourcesCfg);
    paramMap["SUSPEND_SOURCES_CFG"] = suspendSourcesCfg;
}

void InitConstClassByName(napi_env env, napi_value exports, std::string name)
{
    std::map<const char*, napi_value> propertyMap;
    if (name == DATE_CLASS_NAME) {
        InitDateMap(env, propertyMap);
    } else if (name == DISPLAY_CLASS_NAME) {
        InitDisplayMap(env, propertyMap);
    } else if (name == GENERAL_CLASS_NAME) {
        InitGeneralMap(env, propertyMap);
    } else if (name == INPUT_CLASS_NAME) {
        InitInputMap(env, propertyMap);
    } else if (name == NETWORK_CLASS_NAME) {
        InitNetworkMap(env, propertyMap);
    } else if (name == PHONE_CLASS_NAME) {
        InitPhoneMap(env, propertyMap);
    } else if (name == SOUND_CLASS_NAME) {
        InitSoundMap(env, propertyMap);
    } else if (name == TTS_CLASS_NAME) {
        InitTTSMap(env, propertyMap);
    } else if (name == WIRELESS_CLASS_NAME) {
        InitWirelessMap(env, propertyMap);
    } else if (name == TableName_CLASS_NAME) {
        InitTableNameMap(env, propertyMap);
    } else if (name == DomainName_CLASS_NAME) {
        InitDomainNameMap(env, propertyMap);
    } else if (name == POWER_CLASS_NAME) {
        InitPowerMap(env, propertyMap);
    } else {
        return;
    }

    int i = 0;
    napi_property_descriptor descriptors[propertyMap.size()];
    for (auto it : propertyMap) {
        descriptors[i++] = DECLARE_NAPI_STATIC_PROPERTY(it.first, it.second);
    }

    napi_value result = nullptr;
    napi_define_class(env, name.c_str(), NAPI_AUTO_LENGTH, ClassConstructor, nullptr,
        sizeof(descriptors) / sizeof(*descriptors), descriptors, &result);
    napi_set_named_property(env, exports, name.c_str(), result);
}

napi_value InitNapiClass(napi_env env, napi_value exports)
{
    SETTING_LOG_INFO("%{public}s is called", __FUNCTION__);
    InitConstClassByName(env, exports, TableName_CLASS_NAME);
    InitConstClassByName(env, exports, DomainName_CLASS_NAME);
    InitConstClassByName(env, exports, DATE_CLASS_NAME);
    InitConstClassByName(env, exports, DISPLAY_CLASS_NAME);
    InitConstClassByName(env, exports, GENERAL_CLASS_NAME);
    InitConstClassByName(env, exports, INPUT_CLASS_NAME);
    InitConstClassByName(env, exports, NETWORK_CLASS_NAME);
    InitConstClassByName(env, exports, PHONE_CLASS_NAME);
    InitConstClassByName(env, exports, SOUND_CLASS_NAME);
    InitConstClassByName(env, exports, TTS_CLASS_NAME);
    InitConstClassByName(env, exports, WIRELESS_CLASS_NAME);
    InitConstClassByName(env, exports, POWER_CLASS_NAME);
    SETTING_LOG_INFO("%{public}s is end", __FUNCTION__);
    return exports;
}

} // Settings
} // OHOS