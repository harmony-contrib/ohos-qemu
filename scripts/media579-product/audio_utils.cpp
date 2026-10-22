/*
 * Copyright (c) 2022-2026 Huawei Device Co., Ltd.
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
#ifndef LOG_TAG
#define LOG_TAG "AudioUtils"
#endif

#include "audio_utils.h"
#include <cinttypes>
#include <ctime>
#include <sstream>
#include <ostream>
#include <climits>
#include <thread>
#include <string>
#include "audio_utils_c.h"
#include "audio_errors.h"
#include "audio_common_log.h"
#ifdef FEATURE_HITRACE_METER
#include "hitrace_meter.h"
#endif
#include "bundle_mgr_interface.h"
#include "parameter.h"
#include "parameters.h"
#include "tokenid_kit.h"
#include "ipc_skeleton.h"
#include "iservice_registry.h"
#include "access_token.h"
#include "accesstoken_kit.h"
#include "privacy_kit.h"
#include "xcollie/xcollie.h"
#include "xcollie/xcollie_define.h"
#include "securec.h"

using OHOS::Security::AccessToken::AccessTokenKit;
using namespace std::chrono_literals;

namespace OHOS {
namespace AudioStandard {
namespace {
const int32_t YEAR_BASE = 1900;
const size_t MOCK_INTERVAL = 2000;
const int32_t DETECTED_ZERO_THRESHOLD = 1;
const int32_t BLANK_THRESHOLD_MS = 100;
const int32_t SIGNAL_THRESHOLD = 32;
const uint32_t MAX_VALUE_OF_SIGNED_24_BIT = 8388607;
const int64_t PCM_MAYBE_SILENT = 1;
const int64_t PCM_MAYBE_NOT_SILENT = 5;
const int32_t SIGNAL_DATA_SIZE = 96;
const size_t TIME_TEXT_LENGTH = 32;
const size_t DATE_LENGTH = 17;
static uint32_t g_sessionToMock = 0;
constexpr int32_t UID_MEDIA = 1013;
constexpr int32_t UID_AUDIO = 1041;
constexpr int32_t UID_AUDIO_BROKER = 5557;
constexpr int32_t UID_MSDP_SA = 6699;
constexpr int32_t UID_INTELLIGENT_VOICE_SA = 1042;
constexpr int32_t UID_CAAS_SA = 5527;
constexpr int32_t UID_D2D_SA = 7040;
constexpr int32_t UID_DISTRIBUTED_AUDIO_SA = 3055;
constexpr int32_t UID_TELEPHONY_SA = 1001;
constexpr int32_t UID_THPEXTRA_SA = 5000;
constexpr int32_t UID_DMSDP_SA = 7071;
constexpr int32_t BOOTUP_MUSIC_UID = 1003;

const uint32_t UNIQUE_ID_INTERVAL = 8;

constexpr size_t FIRST_CHAR = 1;
constexpr size_t MIN_LEN = 8;
constexpr size_t HEAD_STR_LEN = 2;
constexpr size_t TAIL_STR_LEN = 5;
constexpr size_t VISIBLE_LEN = 3;

constexpr uint8_t UINT8_MID_VALUE = 128;

const int32_t DATA_INDEX_0 = 0;
const int32_t DATA_INDEX_1 = 1;
const int32_t DATA_INDEX_2 = 2;
const int32_t DATA_INDEX_3 = 3;
const int32_t DATA_INDEX_4 = 4;
const int32_t DATA_INDEX_5 = 5;
const int32_t STEREO_CHANNEL_COUNT = 2;
const int BUNDLE_MGR_SERVICE_SYS_ABILITY_ID = 401;
const int32_t MAX_VOLUME_DEGREE = 100;
const int32_t VOLUME_DEGREE_ZERO = 0;
const int32_t VOLUME_LEVEL_ZERO = 0;
const int32_t MID_CORE_START = 4;

const char* DUMP_PULSE_DIR = "/data/data/.pulse_dir/";
const char* DUMP_SERVICE_DIR = "/data/local/tmp/";
const char* DUMP_APP_DIR = "/data/storage/el2/base/cache/";

// keep same with fold_screen_state_internel.h
const std::string FOLD_TYPE_KEY = "const.window.foldscreen.type";
const char DUAL_DISPLAY = '2';
const char SINGLE_POCKET_DISPLAY = '4';
const char SUPER_FOLD_DISPLAY = '5';
std::set<int32_t> RECORD_ALLOW_BACKGROUND_LIST = {
#ifdef AUDIO_BUILD_VARIANT_ROOT
    0, // UID_ROOT
#endif
    UID_MSDP_SA,
    UID_INTELLIGENT_VOICE_SA,
    UID_CAAS_SA,
    UID_D2D_SA,
    UID_DISTRIBUTED_AUDIO_SA,
    UID_TELEPHONY_SA, // used in distributed communication call
    UID_DMSDP_SA
};

const std::set<SourceType> NO_BACKGROUND_CHECK_SOURCE_TYPE = {
    SOURCE_TYPE_PLAYBACK_CAPTURE,
    SOURCE_TYPE_VOICE_CALL,
    SOURCE_TYPE_REMOTE_CAST
};
} // namespace

static std::unordered_map<AudioStreamType, std::string> STREAM_TYPE_NAME_MAP = {
    {STREAM_VOICE_ASSISTANT, "VOICE_ASSISTANT"},
    {STREAM_VOICE_CALL, "VOICE_CALL"},
    {STREAM_SYSTEM, "SYSTEM"},
    {STREAM_RING, "RING"},
    {STREAM_MUSIC, "MUSIC"},
    {STREAM_ALARM, "ALARM"},
    {STREAM_NOTIFICATION, "NOTIFICATION"},
    {STREAM_BLUETOOTH_SCO, "BLUETOOTH_SCO"},
    {STREAM_DTMF, "DTMF"},
    {STREAM_TTS, "TTS"},
    {STREAM_ACCESSIBILITY, "ACCESSIBILITY"},
    {STREAM_ULTRASONIC, "ULTRASONIC"},
    {STREAM_WAKEUP, "WAKEUP"},
    {STREAM_CAMCORDER, "CAMCORDER"},
    {STREAM_ENFORCED_AUDIBLE, "ENFORCED_AUDIBLE"},
    {STREAM_MOVIE, "MOVIE"},
    {STREAM_GAME, "GAME"},
    {STREAM_SPEECH, "SPEECH"},
    {STREAM_SYSTEM_ENFORCED, "SYSTEM_ENFORCED"},
    {STREAM_VOICE_MESSAGE, "VOICE_MESSAGE"},
    {STREAM_NAVIGATION, "NAVIGATION"},
    {STREAM_INTERNAL_FORCE_STOP, "INTERNAL_FORCE_STOP"},
    {STREAM_SOURCE_VOICE_CALL, "SOURCE_VOICE_CALL"},
    {STREAM_VOICE_COMMUNICATION, "VOICE_COMMUNICATION"},
    {STREAM_VOICE_RING, "VOICE_RING"},
    {STREAM_VOICE_CALL_ASSISTANT, "VOICE_CALL_ASSISTANT"},
#ifdef MULTI_ALARM_LEVEL
    {STREAM_ANNOUNCEMENT, "ANNOUNCEMENT"},
    {STREAM_EMERGENCY, "EMERGENCY"},
#endif
};

static const std::unordered_map<DeviceType, std::string> DEVICE_TYPE_NAME_MAP = {
    {DEVICE_TYPE_EARPIECE, "EARPIECE"},
    {DEVICE_TYPE_SPEAKER, "SPEAKER"},
    {DEVICE_TYPE_WIRED_HEADSET, "WIRED_HEADSET"},
    {DEVICE_TYPE_WIRED_HEADPHONES, "WIRED_HEADPHONES"},
    {DEVICE_TYPE_BLUETOOTH_SCO, "BLUETOOTH_SCO"},
    {DEVICE_TYPE_BLUETOOTH_A2DP, "BLUETOOTH_A2DP"},
    {DEVICE_TYPE_NEARLINK, "NEARLINK"},
    {DEVICE_TYPE_MIC, "MIC"},
    {DEVICE_TYPE_HDMI, "HDMI"},
    {DEVICE_TYPE_WAKEUP, "WAKEUP"},
    {DEVICE_TYPE_NONE, "NONE"},
    {DEVICE_TYPE_INVALID, "INVALID"},
    {DEVICE_TYPE_REMOTE_CAST, "REMOTE_CAST"},
    {DEVICE_TYPE_HEARING_AID, "HEARING_AID"},
    {DEVICE_TYPE_BT_SPP, "BT_SPP"},
    {DEVICE_TYPE_LINE_DIGITAL, "LINE_DIGITAL"},
    {DEVICE_TYPE_WIRED_MICIN, "WIRED_MICIN"},
};

static const std::set<SourceType> BACKGROUND_SOURCE_TYPE = {
    SOURCE_TYPE_MIC,
    SOURCE_TYPE_VOICE_COMMUNICATION,
};

uint32_t Util::GetSamplePerFrame(const AudioSampleFormat &format)
{
    uint32_t audioPerSampleLength = 2; // 2 byte
    switch (format) {
        case AudioSampleFormat::SAMPLE_U8:
            audioPerSampleLength = 1;
            break;
        case AudioSampleFormat::SAMPLE_S16LE:
            audioPerSampleLength = 2; // 2 byte
            break;
        case AudioSampleFormat::SAMPLE_S24LE:
            audioPerSampleLength = 3; // 3 byte
            break;
        case AudioSampleFormat::SAMPLE_S32LE:
        case AudioSampleFormat::SAMPLE_F32LE:
            audioPerSampleLength = 4; // 4 byte
            break;
        default:
            break;
    }
    return audioPerSampleLength;
}

bool Util::IsBackgroundSourceType(const SourceType sourceType)
{
    return BACKGROUND_SOURCE_TYPE.find(sourceType) != BACKGROUND_SOURCE_TYPE.end();
}

bool Util::IsScoSupportSource(const SourceType sourceType)
{
    return sourceType == SOURCE_TYPE_VOICE_RECOGNITION || sourceType == SOURCE_TYPE_VOICE_TRANSCRIPTION;
}

bool Util::IsDualToneStreamType(const AudioStreamType streamType)
{
    if (VolumeUtils::IsPCVolumeEnable()) {
        return false;
    }
    // The notification is not dual tone type. But it always uses the volume of the speaker.
    return streamType == STREAM_RING || streamType == STREAM_VOICE_RING ||
        streamType == STREAM_ALARM || streamType == STREAM_NOTIFICATION;
}

bool Util::IsRingerOrAlarmerStreamUsage(const StreamUsage &usage)
{
    return usage == STREAM_USAGE_ALARM || usage == STREAM_USAGE_VOICE_RINGTONE ||
        usage == STREAM_USAGE_RINGTONE || usage == STREAM_USAGE_VOICE_TRANSFER_RINGTONE;
}

bool Util::IsRingerStreamUsage(const StreamUsage &usage)
{
    return usage == STREAM_USAGE_VOICE_RINGTONE || usage == STREAM_USAGE_RINGTONE ||
        usage == STREAM_USAGE_VOICE_TRANSFER_RINGTONE;
}

bool Util::IsRingerAudioScene(const AudioScene &audioScene)
{
    return audioScene == AUDIO_SCENE_RINGING || audioScene == AUDIO_SCENE_VOICE_RINGING;
}

size_t Util::CalculatePcmSizeFromDurationCeiling(std::chrono::nanoseconds duration,
    uint32_t sampleRate, uint32_t bytesPerSample)
{
    size_t sampleCount = static_cast<size_t>((duration * sampleRate) / (1s));
    if (((duration * sampleRate) % (1s)) > (0ns)) {
        sampleCount++;
    }
    return sampleCount * bytesPerSample;
}

std::vector<std::string> Util::SplitString(const std::string& str, char delimiter)
{
    std::vector<std::string> tokens;
    std::string token;
    std::istringstream iss(str);
    
    while (std::getline(iss, token, delimiter)) {
        tokens.push_back(token);
    }
    
    return tokens;
}

bool Util::IsEnhancedRoutingSupported()
{
    static const bool isEnhancedRoutingSupported =
        OHOS::system::GetBoolParameter("const.multimedia.audio.sys_multidevice_capability.enable", false);
    return isEnhancedRoutingSupported;
}

WatchTimeout::WatchTimeout(const std::string &funcName, int64_t timeoutNs) : funcName_(funcName), timeoutNs_(timeoutNs)
{
    startTimeNs_ = ClockTime::GetCurNano();
}

WatchTimeout::~WatchTimeout()
{
    if (!isChecked_) {
        CheckCurrTimeout();
    }
}

void WatchTimeout::CheckCurrTimeout()
{
    int64_t cost = ClockTime::GetCurNano() - startTimeNs_;
    if (cost > timeoutNs_) {
        AUDIO_WARNING_LOG("[%{public}s] cost %{public}" PRId64"ms!", funcName_.c_str(), cost / AUDIO_US_PER_SECOND);
    }
    isChecked_ = true;
}

bool CheckoutSystemAppUtil::CheckoutSystemApp(int32_t uid)
{
    if (uid == BOOTUP_MUSIC_UID) {
        // boot animation must be system app, no need query from BMS, to redeuce boot latency.
        AUDIO_INFO_LOG("boot animation must be system app, no need query from BMS.");
        return true;
    }
    bool isSystemApp = false;
    WatchTimeout guard("SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager():CheckoutSystemApp");
    auto systemAbilityManager = SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager();
    CHECK_AND_RETURN_RET_LOG(systemAbilityManager != nullptr, false, "systemAbilityManager is nullptr");
    guard.CheckCurrTimeout();
    sptr<IRemoteObject> remoteObject = systemAbilityManager->GetSystemAbility(BUNDLE_MGR_SERVICE_SYS_ABILITY_ID);
    CHECK_AND_RETURN_RET_LOG(remoteObject != nullptr, false, "remoteObject is nullptr");
    sptr<AppExecFwk::IBundleMgr> bundleMgrProxy = OHOS::iface_cast<AppExecFwk::IBundleMgr>(remoteObject);
    CHECK_AND_RETURN_RET_LOG(bundleMgrProxy != nullptr, false, "bundleMgrProxy is nullptr");
    WatchTimeout reguard("bundleMgrProxy->CheckIsSystemAppByUid:CheckoutSystemApp");
    isSystemApp = bundleMgrProxy->CheckIsSystemAppByUid(uid);
    reguard.CheckCurrTimeout();
    return isSystemApp;
}

int64_t ClockTime::GetCurNano()
{
    int64_t result = -1; // -1 for bad result.
    struct timespec time;
    clockid_t clockId = CLOCK_MONOTONIC;
    int ret = clock_gettime(clockId, &time);
    CHECK_AND_RETURN_RET_LOG(ret >= 0, result,
        "GetCurNanoTime fail, result:%{public}d", ret);
    result = (time.tv_sec * AUDIO_NS_PER_SECOND) + time.tv_nsec;
    return result;
}

int64_t ClockTime::GetCurMilli()
{
    return GetCurNano() / AUDIO_NS_PER_MILLISECOND;
}

int64_t ClockTime::GetRealNano()
{
    int64_t result = -1; // -1 for bad result
    struct timespec time;
    clockid_t clockId = CLOCK_REALTIME;
    int ret = clock_gettime(clockId, &time);
    CHECK_AND_RETURN_RET_LOG(ret >= 0, result,
        "GetRealNanotime fail, result:%{public}d", ret);
    result = (time.tv_sec * AUDIO_NS_PER_SECOND) + time.tv_nsec;
    return result;
}

int64_t ClockTime::GetBootNano()
{
    int64_t result = -1; // -1 for bad result
    struct timespec time;
    clockid_t clockId = CLOCK_BOOTTIME;
    int ret = clock_gettime(clockId, &time);
    CHECK_AND_RETURN_RET_LOG(ret >= 0, result,
        "GetBootNanotime fail, result:%{public}d", ret);
    result = (time.tv_sec * AUDIO_NS_PER_SECOND) + time.tv_nsec;
    return result;
}

int32_t ClockTime::AbsoluteSleep(int64_t nanoTime)
{
    int32_t ret = -1; // -1 for bad result.
    CHECK_AND_RETURN_RET_LOG(nanoTime > 0, ret,
        "AbsoluteSleep invalid sleep time :%{public}" PRId64 " ns", nanoTime);
    struct timespec time;
    time.tv_sec = nanoTime / AUDIO_NS_PER_SECOND;
    time.tv_nsec = nanoTime - (time.tv_sec * AUDIO_NS_PER_SECOND); // Avoids % operation.

    clockid_t clockId = CLOCK_MONOTONIC;
    ret = clock_nanosleep(clockId, TIMER_ABSTIME, &time, nullptr);
    if (ret != 0) {
        AUDIO_WARNING_LOG("AbsoluteSleep may failed, ret is :%{public}d", ret);
    }

    return ret;
}

std::string ClockTime::NanoTimeToString(int64_t nanoTime)
{
    struct tm *tm_info;
    char buffer[80];
    time_t time_seconds = nanoTime / AUDIO_NS_PER_SECOND;

    tm_info = localtime(&time_seconds);
    if (tm_info == NULL) {
        AUDIO_ERR_LOG("get localtime failed!");
        return "";
    }

    size_t res = strftime(buffer, sizeof(buffer), "%H:%M:%S", tm_info);
    CHECK_AND_RETURN_RET_LOG(res != 0, "", "strftime failed!");
    return std::string(buffer);
}

int32_t ClockTime::RelativeSleep(int64_t nanoTime)
{
    int32_t ret = -1; // -1 for bad result.
    CHECK_AND_RETURN_RET_LOG(nanoTime > 0, ret,
        "AbsoluteSleep invalid sleep time :%{public}" PRId64 " ns", nanoTime);
    struct timespec time;
    time.tv_sec = nanoTime / AUDIO_NS_PER_SECOND;
    time.tv_nsec = nanoTime - (time.tv_sec * AUDIO_NS_PER_SECOND); // Avoids % operation.

    clockid_t clockId = CLOCK_MONOTONIC;
    const int relativeFlag = 0; // flag of relative sleep.
    ret = clock_nanosleep(clockId, relativeFlag, &time, nullptr);
    if (ret != 0) {
        AUDIO_WARNING_LOG("RelativeSleep may failed, ret is :%{public}d", ret);
    }

    return ret;
}

void ClockTime::GetAllTimeStamp(std::vector<uint64_t> &timestamp)
{
    timestamp.resize(Timestamp::Timestampbase::BASESIZE);
    int64_t tmpTime = GetCurNano();
    if (tmpTime > 0) {
        timestamp[Timestamp::Timestampbase::MONOTONIC] = static_cast<uint64_t>(tmpTime);
    }
    tmpTime = GetBootNano();
    if (tmpTime > 0) {
        timestamp[Timestamp::Timestampbase::BOOTTIME] = static_cast<uint64_t>(tmpTime);
    }
}

bool ClockTime::CheckTimeInterval(std::atomic<int64_t> &lastRecordTimestamp, const int64_t timeInterval)
{
    int64_t curTimestamp = GetCurNano();
    CHECK_AND_RETURN_RET(lastRecordTimestamp.load() + timeInterval < curTimestamp, false);
    lastRecordTimestamp.store(curTimestamp);
    return true;
}

void Trace::Count(const std::string &value, int64_t count)
{
#ifdef FEATURE_HITRACE_METER
    CountTrace(HITRACE_TAG_ZAUDIO, value, count);
#endif
}

void Trace::CountVolume(const std::string &value, uint8_t data)
{
#ifdef FEATURE_HITRACE_METER
    if (data == 0) {
        CountTrace(HITRACE_TAG_ZAUDIO, value, PCM_MAYBE_SILENT);
    } else {
        CountTrace(HITRACE_TAG_ZAUDIO, value, PCM_MAYBE_NOT_SILENT);
    }
#endif
}

Trace::Trace(const std::string &value)
{
    isFinished_ = false;
#ifdef FEATURE_HITRACE_METER
    StartTrace(HITRACE_TAG_ZAUDIO, value);
#endif
}

void Trace::End()
{
#ifdef FEATURE_HITRACE_METER
    if (!isFinished_) {
        FinishTrace(HITRACE_TAG_ZAUDIO);
        isFinished_ = true;
    }
#endif
}

Trace::~Trace()
{
    if (!isFinished_) {
        FinishTrace(HITRACE_TAG_ZAUDIO);
        isFinished_ = true;
    }
}

AudioXCollie::AudioXCollie(const std::string &tag, uint32_t timeoutSeconds,
    std::function<void(void *)> func, void *arg, uint32_t flag)
{
    AUDIO_DEBUG_LOG("Start AudioXCollie, tag: %{public}s, timeoutSeconds: %{public}u, flag: %{public}u",
        tag.c_str(), timeoutSeconds, flag);
    id_ = HiviewDFX::XCollie::GetInstance().SetTimer(tag, timeoutSeconds, func, arg, flag);
    tag_ = tag;
    isCanceled_ = false;
}

AudioXCollie::~AudioXCollie()
{
    CancelXCollieTimer();
}

void AudioXCollie::CancelXCollieTimer()
{
    if (!isCanceled_) {
        HiviewDFX::XCollie::GetInstance().CancelTimer(id_);
        isCanceled_ = true;
        AUDIO_DEBUG_LOG("CancelXCollieTimer: cancel timer %{public}s", tag_.c_str());
    }
}

bool PermissionUtil::VerifyIsShell()
{
    auto tokenId = IPCSkeleton::GetCallingTokenID();
    auto tokenTypeFlag = Security::AccessToken::AccessTokenKit::GetTokenTypeFlag(tokenId);
    if (tokenTypeFlag == Security::AccessToken::TOKEN_SHELL) {
        return true;
    }
    return false;
}

bool PermissionUtil::VerifyIsAudio()
{
    int32_t callingUid = IPCSkeleton::GetCallingUid();
    if (UID_AUDIO == callingUid) {
        return true;
    }
#ifdef AUDIO_BUILD_VARIANT_ROOT
    if (callingUid == 0) {
        AUDIO_WARNING_LOG("Root calling!");
        return true;
    }
#endif
    return false;
}

bool PermissionUtil::VerifyIsAudioBroker()
{
    int32_t callingUid = IPCSkeleton::GetCallingUid();
    if (UID_AUDIO_BROKER == callingUid) {
        return true;
    }
    return false;
}

bool PermissionUtil::VerifyIsSystemApp()
{
    uint64_t fullTokenId = IPCSkeleton::GetCallingFullTokenID();
    WatchTimeout guard("Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID");
    bool tmp = Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID(fullTokenId);
    CHECK_AND_RETURN_RET(!tmp, true);

    return false;
}

bool PermissionUtil::VerifySelfPermission()
{
    Security::AccessToken::FullTokenID selfToken = IPCSkeleton::GetSelfTokenID();

    auto tokenTypeFlag = Security::AccessToken::AccessTokenKit::GetTokenTypeFlag(static_cast<uint32_t>(selfToken));

    CHECK_AND_RETURN_RET(tokenTypeFlag != Security::AccessToken::TOKEN_NATIVE, true);

    CHECK_AND_RETURN_RET(tokenTypeFlag != Security::AccessToken::TOKEN_SHELL, true);

    bool tmp = Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID(selfToken);
    CHECK_AND_RETURN_RET(!tmp, true);

    AUDIO_ERR_LOG("Check self app permission reject");
    return false;
}

bool PermissionUtil::VerifyBluetoothPermission()
{
    uid_t callingUid = static_cast<uid_t>(IPCSkeleton::GetCallingUid());
    if (callingUid == UID_MEDIA || callingUid == BOOTUP_MUSIC_UID) {
        // bootup use media kit
        return false;
    }
#ifdef AUDIO_BUILD_VARIANT_ROOT
    // root user case for auto test
    if (callingUid == ROOT_UID) {
        return true;
    }
#endif
    uint32_t tokenId = IPCSkeleton::GetCallingTokenID();

    int res = Security::AccessToken::AccessTokenKit::VerifyAccessToken(tokenId, "ohos.permission.USE_BLUETOOTH");
    CHECK_AND_RETURN_RET(res == Security::AccessToken::PermissionState::PERMISSION_GRANTED, false);

    return true;
}

bool PermissionUtil::VerifySystemPermission()
{
    auto tokenId = IPCSkeleton::GetCallingTokenID();
    auto tokenTypeFlag = Security::AccessToken::AccessTokenKit::GetTokenTypeFlag(tokenId);

    CHECK_AND_RETURN_RET(tokenTypeFlag != Security::AccessToken::TOKEN_NATIVE, true);
#ifdef AUDIO_BUILD_VARIANT_ROOT
    CHECK_AND_RETURN_RET(tokenTypeFlag != Security::AccessToken::TOKEN_SHELL, true);
#endif
    bool tmp = VerifyIsSystemApp();
    CHECK_AND_RETURN_RET(!tmp, true);

    return false;
}

bool PermissionUtil::IsHap()
{
    auto tokenId = IPCSkeleton::GetCallingTokenID();
    auto tokenTypeFlag = Security::AccessToken::AccessTokenKit::GetTokenTypeFlag(tokenId);
    return tokenTypeFlag == Security::AccessToken::TOKEN_HAP;
}

bool PermissionUtil::VerifyPermission(const std::string &permissionName, uint32_t tokenId)
{
    int res = Security::AccessToken::AccessTokenKit::VerifyAccessToken(tokenId, permissionName);
    CHECK_AND_RETURN_RET_LOG(res == Security::AccessToken::PermissionState::PERMISSION_GRANTED,
        false, "Permission denied [%{public}s]", permissionName.c_str());

    return true;
}

bool PermissionUtil::VerifyGeneralPermission(const std::string &permissionName, uint32_t tokenId, bool isRecording)
{
    AUDIO_DEBUG_LOG("Verify permission [%{public}s]", permissionName.c_str());

    uid_t callingUid = static_cast<uid_t>(IPCSkeleton::GetCallingUid());
    if (callingUid == UID_AUDIO) {
        return true;
    }

    if (!isRecording) {
#ifdef AUDIO_BUILD_VARIANT_ROOT
        // root user case for auto test
        if (callingUid == ROOT_UID) {
            return true;
        }
#endif
        tokenId = IPCSkeleton::GetCallingTokenID();
    }

    int res = Security::AccessToken::AccessTokenKit::VerifyAccessToken(tokenId, permissionName);
    CHECK_AND_RETURN_RET_LOG(res == Security::AccessToken::PermissionState::PERMISSION_GRANTED,
        false, "Permission denied [%{public}s]", permissionName.c_str());

    return true;
}

bool PermissionUtil::IsFoldAble(const char ch)
{
    if (ch == DUAL_DISPLAY || ch == SINGLE_POCKET_DISPLAY || ch == SUPER_FOLD_DISPLAY) {
        return true;
    }
    return false;
}

void PermissionUtil::UpdateBGSet()
{
    std::string screenType = system::GetParameter(FOLD_TYPE_KEY, "0,0,0,0");
    AUDIO_INFO_LOG("FoldType param is %{public}s", screenType.c_str());
    if (screenType.empty()) {
        return;
    }
    if (IsFoldAble(screenType[0])) {
        AUDIO_INFO_LOG("Is fold device!");
        RECORD_ALLOW_BACKGROUND_LIST.insert(UID_THPEXTRA_SA);
    }
}

bool PermissionUtil::NeedVerifyBackgroundCapture(int32_t callingUid, SourceType sourceType)
{
    if (RECORD_ALLOW_BACKGROUND_LIST.count(callingUid)) {
        AUDIO_INFO_LOG("internal sa(%{public}d) user directly recording", callingUid);
        return false;
    }
    if (NO_BACKGROUND_CHECK_SOURCE_TYPE.count(sourceType)) {
        AUDIO_INFO_LOG("sourceType %{public}d", sourceType);
        return false;
    }
    return true;
}

bool PermissionUtil::VerifyBackgroundCapture(uint32_t tokenId, uint64_t fullTokenId)
{
    Trace trace("PermissionUtil::VerifyBackgroundCapture");
    if (Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID(fullTokenId)) {
        AUDIO_INFO_LOG("system app recording");
        return true;
    }

    bool ret = Security::AccessToken::PrivacyKit::IsAllowedUsingPermission(tokenId, MICROPHONE_PERMISSION);
    if (!ret) {
        HILOG_COMM_ERROR("[VerifyBackgroundCapture]failed: not allowed!");
    }
    return ret;
}

bool PermissionUtil::VerifyCapturePrivatePlayback(uint32_t tokenId)
{
    static const std::string CAPTURE_PLAYBACK_PRIVATE_PERMISSION = "ohos.permission.CAPTURE_PLAYBACK_PRIVATE";
    return VerifyPermission(CAPTURE_PLAYBACK_PRIVATE_PERMISSION, tokenId);
}

bool PermissionUtil::CheckCallingUidPermission(const std::vector<uid_t> &allowedUids)
{
    CHECK_AND_RETURN_RET_LOG(allowedUids.size() > 0, false, "allowedUids is empty");
    auto callingUid = IPCSkeleton::GetCallingUid();
    if (UID_AUDIO == callingUid) {
        return true;
    }
    for (const auto &uid : allowedUids) {
        if (uid == static_cast<uid_t>(callingUid)) {
            return true;
        }
    }
    return false;
}

std::mutex g_switchMapMutex;
static std::map<SwitchStreamInfo, SwitchState> g_switchStreamRecordMap = {};

bool SwitchStreamUtil::IsSwitchStreamSwitching(SwitchStreamInfo &info, SwitchState targetState)
{
    std::lock_guard<std::mutex> lock(g_switchMapMutex);
    auto iter = g_switchStreamRecordMap.find(info);
    CHECK_AND_RETURN_RET_LOG(iter != g_switchStreamRecordMap.end(), false,
        "can not find info for sessionId:%{public}u in switchStreamRecord", info.sessionId);
    if (iter != g_switchStreamRecordMap.end() && targetState == SWITCH_STATE_CREATED &&
        iter->second == SWITCH_STATE_WAITING && (info.nextState == CAPTURER_PREPARED)) {
        AUDIO_INFO_LOG("stream:%{public}u is recreating , need not check using mic in background !",
            info.sessionId);
        return true;
    }
    if (iter != g_switchStreamRecordMap.end() && targetState == SWITCH_STATE_STARTED &&
        iter->second == SWITCH_STATE_CREATED && (info.nextState == CAPTURER_RUNNING)) {
        AUDIO_INFO_LOG("stream:%{public}u is restarting , need not check using mic in background !",
            info.sessionId);
        return true;
    }
    return false;
}

bool SwitchStreamUtil::InsertSwitchStreamRecord(SwitchStreamInfo &info, SwitchState targetState)
{
    if (RECORD_ALLOW_BACKGROUND_LIST.count(info.callerUid)) {
        AUDIO_INFO_LOG("internal sa(%{public}d) user directly recording, "
            "need not insert into SwitchStreamRecord", info.callerUid);
        return true;
    }
    auto ret = g_switchStreamRecordMap.insert(std::make_pair(info, targetState));
    CHECK_AND_RETURN_RET_LOG(ret.second, false, "Insert stream:%{public}u switchState:%{public}d "
        "into switchStreamRecord failed", info.sessionId, targetState);
    AUDIO_INFO_LOG("Insert stream:%{public}u switchState:%{public}d uid:%{public}d CapturerState:%{public}d"
        "into switchStreamRecord success", info.sessionId, targetState, info.appUid, info.nextState);
    return true;
}

//Remove switchStreamInfo from  switchStreamRecordMap must be called with g_switchMapMutex held
bool SwitchStreamUtil::RemoveSwitchStreamRecord(SwitchStreamInfo &info, SwitchState targetState)
{
    if (g_switchStreamRecordMap.count(info) != 0) {
        g_switchStreamRecordMap.erase(info);

        CHECK_AND_RETURN_RET((g_switchStreamRecordMap.count(info) == 0), false,
            "Remove exist record failed for stream:%{public}u", info.sessionId);
        AUDIO_WARNING_LOG("Exist Record has been Removed for stream:%{public}u", info.sessionId);
    }
    return true;
}

bool SwitchStreamUtil::RemoveAllRecordBySessionId(uint32_t sessionId)
{
    std::lock_guard<std::mutex> lock(g_switchMapMutex);

    for (auto it = g_switchStreamRecordMap.begin(); it != g_switchStreamRecordMap.end();) {
        if (it->first.sessionId == sessionId) {
            it = g_switchStreamRecordMap.erase(it);
        } else {
            ++it;
        }
    }
    return true;
}

bool SwitchStreamUtil::UpdateSwitchStreamRecord(SwitchStreamInfo &info, SwitchState targetState)
{
    std::lock_guard<std::mutex> lock(g_switchMapMutex);
    auto iter = g_switchStreamRecordMap.find(info);
    bool isInfoInRecord = (iter != g_switchStreamRecordMap.end());
    if (!isInfoInRecord) {
        if (targetState == SWITCH_STATE_WAITING) {
            CHECK_AND_RETURN_RET_LOG(SwitchStreamUtil::InsertSwitchStreamRecord(info, targetState),
                false, "Insert switchStream into Record fail!");
        }
        return true;
    }

    switch (targetState) {
        case SWITCH_STATE_WAITING:
            CHECK_AND_RETURN_RET_LOG(SwitchStreamUtil::RemoveSwitchStreamRecord(info, targetState),
                false, "Remove error record for switchStream:%{public}u failed!", iter->first.sessionId);
            CHECK_AND_RETURN_RET_LOG(SwitchStreamUtil::InsertSwitchStreamRecord(info, targetState),
                false, "Retry insert switchStream into record failed!");
            return true;
        case SWITCH_STATE_CREATED:
            CHECK_AND_RETURN_RET_LOG(HandleCreatedSwitchInfoInRecord(info, targetState), false,
                "Handle switch record to SWITCH_STATE_CREATED failed!");
            break;
        case SWITCH_STATE_STARTED:
            CHECK_AND_RETURN_RET_LOG(HandleStartedSwitchInfoInRecord(info, targetState), false,
                "Handle switch record to SWITCH_STATE_STARTED failed!");
            break;
        default:
            CHECK_AND_RETURN_RET_LOG(HandleSwitchInfoInRecord(info, targetState), false,
                "Handle switch info in record failed!");
            break;
    }
    iter = g_switchStreamRecordMap.find(info);
    CHECK_AND_RETURN_RET_LOG(iter != g_switchStreamRecordMap.end(), false, "SwitchStream has been removed!");
    if (iter->first.nextState == info.nextState) {
        g_switchStreamRecordMap[info] = SWITCH_STATE_FINISHED;
        g_switchStreamRecordMap.erase(info);
        AUDIO_INFO_LOG("SwitchStream will finish!Remove Record for stream:%{public}u uid:%{public}d ",
            info.sessionId, info.appUid);
    }

    return true;
}

bool SwitchStreamUtil::HandleCreatedSwitchInfoInRecord(SwitchStreamInfo &info, SwitchState targetState)
{
    auto iter = g_switchStreamRecordMap.find(info);
    if (iter->second == SWITCH_STATE_WAITING && (info.nextState == CAPTURER_PREPARED)) {
        g_switchStreamRecordMap[info] = targetState;
        AUDIO_INFO_LOG("SwitchStream will reCreated!Update Record switchState:%{public}d for"
            "stream:%{public}u uid:%{public}d streamState:%{public}d success",
            targetState, info.sessionId, info.appUid, info.nextState);
    } else {
        CHECK_AND_RETURN_RET_LOG(SwitchStreamUtil::RemoveSwitchStreamRecord(info, targetState),
            false, "Remove Error Record for Stream:%{public}u Failed!", iter->first.sessionId);
    }
    return true;
}

bool SwitchStreamUtil::HandleSwitchInfoInRecord(SwitchStreamInfo &info, SwitchState targetState)
{
    auto iter = g_switchStreamRecordMap.find(info);
    if (((iter->second == SWITCH_STATE_CREATED) || (iter->second == SWITCH_STATE_STARTED)) &&
        (info.nextState == CAPTURER_STOPPED || info.nextState == CAPTURER_PAUSED ||
        info.nextState == CAPTURER_RELEASED || info.nextState == CAPTURER_INVALID)) {
        CHECK_AND_RETURN_RET_LOG(SwitchStreamUtil::RemoveSwitchStreamRecord(info, targetState),
            false, "Remove Finished Record for Stream:%{public}u Failed!", iter->first.sessionId);
    } else if ((iter->second == SWITCH_STATE_WAITING) && (info.nextState == CAPTURER_STOPPED ||
        info.nextState == CAPTURER_PAUSED || info.nextState == CAPTURER_RELEASED ||
        info.nextState == CAPTURER_INVALID)) {
        AUDIO_INFO_LOG("SwitchStream streamState has been changed to [%{public}d] before recreate!",
            info.nextState);
    } else {
        CHECK_AND_RETURN_RET_LOG(SwitchStreamUtil::RemoveSwitchStreamRecord(info, targetState),
            false, "Remove Error Record for Stream:%{public}u Failed!", iter->first.sessionId);
        AUDIO_INFO_LOG("Error Record has been Removed for stream:%{public}u", iter->first.sessionId);
    }
    return true;
}

bool SwitchStreamUtil::HandleStartedSwitchInfoInRecord(SwitchStreamInfo &info, SwitchState targetState)
{
    auto iter = g_switchStreamRecordMap.find(info);
    if ((iter->second == SWITCH_STATE_CREATED) && (info.nextState == CAPTURER_RUNNING)) {
        g_switchStreamRecordMap[info] = targetState;
        AUDIO_INFO_LOG("SwitchStream will reStarted!Update Record switchState:%{public}d for"
            "stream:%{public}u uid:%{public}d streamState:%{public}d success",
            targetState, info.sessionId, info.appUid, info.nextState);
    } else {
        CHECK_AND_RETURN_RET_LOG(SwitchStreamUtil::RemoveSwitchStreamRecord(info, targetState),
            false, "Remove Error Record for Stream:%{public}u Failed!", iter->first.sessionId);
    }
    return true;
}

int32_t PermissionUtil::StartRemoteUsingPermission(const std::string &deviceId, const std::string &deviceName,
    const char* permission)
{
    Trace trace("PrivacyKit::StartRemoteUsingPermission");
    AUDIO_WARNING_LOG("PrivacyKit::StartRemoteUsingPermission deviceId: %{public}s, permission: %{public}s",
        GetEncryptStr(deviceId).c_str(), permission);
    Security::AccessToken::RemoteCallerInfo remoteCallerInfo = {deviceId, deviceName};
    WatchTimeout guard("PrivacyKit::StartRemoteUsingPermission:PermissionUtil::StartUsingPermission");
    int32_t res = Security::AccessToken::PrivacyKit::StartRemoteUsingPermission(remoteCallerInfo, permission);
    guard.CheckCurrTimeout();
    return res;
}

int32_t PermissionUtil::StopRemoteUsingPermission(const std::string &deviceId, const std::string &deviceName,
    const char* permission)
{
    Trace trace("PrivacyKit::StopRemoteUsingPermission");
    AUDIO_WARNING_LOG("PrivacyKit::StopRemoteUsingPermission deviceId: %{public}s, permission: %{public}s",
        GetEncryptStr(deviceId).c_str(), permission);
    Security::AccessToken::RemoteCallerInfo remoteCallerInfo = {deviceId, deviceName};
    WatchTimeout guard("PrivacyKit::StopRemoteUsingPermission:PermissionUtil::StopRemoteUsingPermission");
    int32_t res = Security::AccessToken::PrivacyKit::StopRemoteUsingPermission(remoteCallerInfo, permission);
    guard.CheckCurrTimeout();
    return res;
}

int32_t PermissionUtil::AddRemotePermissionUsedRecord(const std::string &deviceId, const std::string &deviceName,
    const char* permission, int32_t successCount, int32_t failCount)
{
    Security::AccessToken::RemoteCallerInfo remoteCallerInfo = {deviceId, deviceName};
    WatchTimeout guard("Security::AccessToken::PrivacyKit::AddRemotePermissionUsedRecord");
    int32_t res = Security::AccessToken::PrivacyKit::AddRemotePermissionUsedRecord(remoteCallerInfo, permission,
        successCount, failCount);
    guard.CheckCurrTimeout();
    return res;
}

static std::unordered_map<int32_t, std::pair<uint32_t, std::string>> g_solePipeSourceMap = {};

void SolePipe::SetSolePipeSourceInfo(int32_t sourceType, uint32_t routeFlag, const std::string &pipeName)
{
    AUDIO_INFO_LOG("source:%{public}d flag:%{public}u pipe:%{public}s", sourceType, routeFlag, pipeName.c_str());
    g_solePipeSourceMap[sourceType] = std::make_pair(routeFlag, pipeName);
}

bool SolePipe::IsSolePipeSource(int32_t sourceType)
{
    return g_solePipeSourceMap.find(sourceType) != g_solePipeSourceMap.end();
}

bool SolePipe::GetSolePipeBySourceType(int32_t sourceType, uint32_t &routeFlag, std::string &pipeName)
{
    auto it = g_solePipeSourceMap.find(sourceType);
    CHECK_AND_RETURN_RET_LOG(it != g_solePipeSourceMap.end(), false, "can not find sourceType:%{public}d", sourceType);
    routeFlag = it->second.first;
    pipeName = it->second.second;
    AUDIO_INFO_LOG("source:%{public}d flag:%{public}u pipe:%{public}s", sourceType, routeFlag, pipeName.c_str());
    return true;
}

void AdjustStereoToMonoForPCM8Bit(int8_t *data, uint64_t len)
{
    // the number 2: stereo audio has 2 channels
    uint64_t count = len / 2;

    while (count > 0) {
        // the number 2 is the count of stereo audio channels
        data[0] = data[0] / 2 + data[1] / 2;
        data[1] = data[0];
        data += 2;
        count--;
    }
}

void AdjustStereoToMonoForPCM16Bit(int16_t *data, uint64_t len)
{
    uint64_t count = len / 2 / 2;
    // first number 2: stereo audio has 2 channels
    // second number 2: the bit depth of PCM16Bit is 16 bits (2 bytes)

    while (count > 0) {
        // the number 2 is the count of stereo audio channels
        data[0] = data[0] / 2 + data[1] / 2;
        data[1] = data[0];
        data += 2;
        count--;
    }
}

void AdjustStereoToMonoForPCM24Bit(uint8_t *data, uint64_t len)
{
    uint64_t count = len / STEREO_CHANNEL_COUNT / 3; // 3: the bit depth of PCM24Bit is 24 bits (3 bytes)

    while (count > 0) {
        uint32_t leftData = (static_cast<uint32_t>(data[DATA_INDEX_2]) << BIT_16) |
            (static_cast<uint32_t>(data[DATA_INDEX_1]) << BIT_8) |
            (static_cast<uint32_t>(data[DATA_INDEX_0]));
        uint32_t rightData = (static_cast<uint32_t>(data[DATA_INDEX_5]) << BIT_16) |
            (static_cast<uint32_t>(data[DATA_INDEX_4]) << BIT_8) |
            (static_cast<uint32_t>(data[DATA_INDEX_3]));

        leftData = static_cast<uint32_t>(static_cast<int32_t>(leftData << BIT_8) / STEREO_CHANNEL_COUNT +
            static_cast<int32_t>(rightData << BIT_8) / STEREO_CHANNEL_COUNT) >> BIT_8;
        rightData = leftData;

        data[DATA_INDEX_0] = static_cast<uint8_t>(leftData);
        data[DATA_INDEX_1] = static_cast<uint8_t>(leftData >> BIT_8);
        data[DATA_INDEX_2] = static_cast<uint8_t>(leftData >> BIT_16);
        data[DATA_INDEX_3] = static_cast<uint8_t>(rightData);
        data[DATA_INDEX_4] = static_cast<uint8_t>(rightData >> BIT_8);
        data[DATA_INDEX_5] = static_cast<uint8_t>(rightData >> BIT_16);
        data += 6; // 6: 2 channels, 24 bits (3 bytes), 2 * 3 = 6
        count--;
    }
}

void AdjustStereoToMonoForPCM32Bit(int32_t *data, uint64_t len)
{
    uint64_t count = len / 2 / 4;
    // first number 2: stereo audio has 2 channels
    // second number 4: the bit depth of PCM32Bit is 32 bits (4 bytes)

    while (count > 0) {
        // the number 2 is the count of stereo audio channels
        data[0] = data[0] / 2 + data[1] / 2;
        data[1] = data[0];
        data += 2;
        count--;
    }
}

void AdjustAudioBalanceForPCM8Bit(int8_t *data, uint64_t len, float left, float right)
{
    uint64_t count = len / 2;
    // the number 2: stereo audio has 2 channels

    while (count > 0) {
        // the number 2 is the count of stereo audio channels
        data[0] *= left;
        data[1] *= right;
        data += 2;
        count--;
    }
}

void AdjustAudioBalanceForPCM16Bit(int16_t *data, uint64_t len, float left, float right)
{
    uint64_t count = len / 2 / 2;
    // first number 2: stereo audio has 2 channels
    // second number 2: the bit depth of PCM16Bit is 16 bits (2 bytes)

    while (count > 0) {
        // the number 2 is the count of stereo audio channels
        data[0] *= left;
        data[1] *= right;
        data += 2;
        count--;
    }
}

void AdjustAudioBalanceForPCM24Bit(uint8_t *data, uint64_t len, float left, float right)
{
    uint64_t count = len / STEREO_CHANNEL_COUNT / 3; // 3: the bit depth of PCM24Bit is 24 bits (3 bytes)

    while (count > 0) {
        uint32_t leftData = (static_cast<uint32_t>(data[DATA_INDEX_2]) << BIT_16) |
            (static_cast<uint32_t>(data[DATA_INDEX_1]) << BIT_8) |
            (static_cast<uint32_t>(data[DATA_INDEX_0]));
        int32_t leftTemp = static_cast<int32_t>(leftData << BIT_8);
        leftTemp *= left;
        leftData = static_cast<uint32_t>(leftTemp) >> BIT_8;
        data[DATA_INDEX_0] = static_cast<uint8_t>(leftData);
        data[DATA_INDEX_1] = static_cast<uint8_t>(leftData >> BIT_8);
        data[DATA_INDEX_2] = static_cast<uint8_t>(leftData >> BIT_16);

        uint32_t rightData = (static_cast<uint32_t>(data[DATA_INDEX_5]) << BIT_16) |
            (static_cast<uint32_t>(data[DATA_INDEX_4]) << BIT_8) |
            (static_cast<uint32_t>(data[DATA_INDEX_3]));
        int32_t rightTemp = static_cast<int32_t>(rightData << BIT_8);
        rightTemp *= right;
        rightData = static_cast<uint32_t>(rightTemp) >> BIT_8;
        data[DATA_INDEX_3] = static_cast<uint8_t>(rightData);
        data[DATA_INDEX_4] = static_cast<uint8_t>(rightData >> BIT_8);
        data[DATA_INDEX_5] = static_cast<uint8_t>(rightData >> BIT_16);
        data += 6; // 6: 2 channels, 24 bits (3 bytes), 2 * 3 = 6
        count--;
    }
}

void AdjustAudioBalanceForPCM32Bit(int32_t *data, uint64_t len, float left, float right)
{
    uint64_t count = len / 2 / 4;
    // first number 2: stereo audio has 2 channels
    // second number 4: the bit depth of PCM32Bit is 32 bits (4 bytes)

    while (count > 0) {
        // the number 2 is the count of stereo audio channels
        data[0] *= left;
        data[1] *= right;
        data += 2;
        count--;
    }
}

uint32_t Read24Bit(const uint8_t *p)
{
    return ((uint32_t) p[BIT_DEPTH_TWO] << BIT_16) | ((uint32_t) p[1] << BIT_8) | ((uint32_t) p[0]);
}

void Write24Bit(uint8_t *p, uint32_t u)
{
    p[BIT_DEPTH_TWO] = (uint8_t) (u >> BIT_16);
    p[1] = static_cast<uint8_t>(u >> BIT_8);
    p[0] = static_cast<uint8_t>(u);
}

void ConvertFrom24BitToFloat(unsigned n, const uint8_t *a, float *b)
{
    for (; n > 0; n--) {
        int32_t s = Read24Bit(a) << BIT_8;
        *b = s * (1.0f / (1U << (BIT_32 - 1)));
        a += OFFSET_BIT_24;
        b++;
    }
}

void ConvertFrom32BitToFloat(unsigned n, const int32_t *a, float *b)
{
    for (; n > 0; n--) {
        *(b++) = *(a++) * (1.0f / (1U << (BIT_32 - 1)));
    }
}

int16_t ConvertSampleToS16(const uint8_t *samplePtr, AudioSampleFormat format)
{
    if (samplePtr == nullptr) {
        return 0;
    }
    switch (format) {
        case SAMPLE_U8: {
            uint8_t u8 = *samplePtr;
            return static_cast<int16_t>((static_cast<int32_t>(u8) - UINT8_MID_VALUE) << BIT_8);
        }
        case SAMPLE_S16LE: {
            return *reinterpret_cast<const int16_t*>(samplePtr);
        }
        case SAMPLE_S24LE: {
            uint32_t value = samplePtr[DATA_INDEX_0] | (samplePtr[DATA_INDEX_1] << BIT_8) |
                (samplePtr[DATA_INDEX_2] << BIT_16);
            int32_t s24 = (static_cast<int32_t>(value) << BIT_8) >> BIT_8;
            return static_cast<int16_t>(s24 >> BIT_8);
        }
        case SAMPLE_S32LE: {
            int32_t s32 = *reinterpret_cast<const int32_t*>(samplePtr);
            return static_cast<int16_t>((static_cast<double>(s32) / INT32_MAX) * INT16_MAX);
        }
        case SAMPLE_F32LE: {
            float f32 = *reinterpret_cast<const float*>(samplePtr);
            float capped = CapMax(f32);
            return static_cast<int16_t>(capped * INT16_MAX);
        }
        default:
            return 0;
    }
}

void ConvertSampleFromS16(int16_t s16Sample, uint8_t *outputPtr, AudioSampleFormat format)
{
    if (outputPtr == nullptr) {
        return;
    }
    switch (format) {
        case SAMPLE_U8: {
            int32_t temp = (s16Sample >> BIT_8) + UINT8_MID_VALUE;
            *outputPtr = static_cast<uint8_t>(std::max(0, std::min(static_cast<int32_t>(UINT8_MAX), temp)));
            break;
        }
        case SAMPLE_S16LE: {
            *reinterpret_cast<int16_t*>(outputPtr) = s16Sample;
            break;
        }
        case SAMPLE_S24LE: {
            int32_t s24 = static_cast<int32_t>(s16Sample) << BIT_8;
            outputPtr[DATA_INDEX_0] = s24 & 0xFF;
            outputPtr[DATA_INDEX_1] = (s24 >> BIT_8) & 0xFF;
            outputPtr[DATA_INDEX_2] = (s24 >> BIT_16) & 0xFF;
            break;
        }
        case SAMPLE_S32LE: {
            int32_t s32 = static_cast<int32_t>((static_cast<double>(s16Sample) / INT16_MAX) * INT32_MAX);
            *reinterpret_cast<int32_t*>(outputPtr) = s32;
            break;
        }
        case SAMPLE_F32LE: {
            float f32 = static_cast<float>(s16Sample) * (1.0f / (1 << (BIT_16 - 1)));
            *reinterpret_cast<float*>(outputPtr) = f32;
            break;
        }
        default:
            break;
    }
}

void ConvertBufferToS16(const uint8_t *input, uint32_t samples, int16_t *output, AudioSampleFormat format)
{
    if (input == nullptr || output == nullptr || samples == 0) {
        return;
    }
    uint32_t bytesPerSample = PcmFormatToBits(format);
    for (uint32_t i = 0; i < samples; i++) {
        output[i] = ConvertSampleToS16(input + i * bytesPerSample, format);
    }
}

void ConvertBufferFromS16(const int16_t *input, uint32_t samples, uint8_t *output, AudioSampleFormat format)
{
    if (input == nullptr || output == nullptr || samples == 0) {
        return;
    }
    uint32_t bytesPerSample = PcmFormatToBits(format);
    for (uint32_t i = 0; i < samples; i++) {
        ConvertSampleFromS16(input[i], output + i * bytesPerSample, format);
    }
}

float CapMax(float v)
{
    float value = v;
    if (v >= 1.0f) {
        value = 1.0f - FLOAT_EPS;
    } else if (v <= -1.0f) {
        value = -1.0f + FLOAT_EPS;
    }
    return value;
}

void ConvertFromFloatTo24Bit(unsigned n, const float *a, uint8_t *b)
{
    for (; n > 0; n--) {
        float tmp = *a++;
        float v = CapMax(tmp) * (1U << (BIT_32 - 1));
        Write24Bit(b, (static_cast<int32_t>(v)) >> BIT_8);
        b += OFFSET_BIT_24;
    }
}

void ConvertFromFloatTo32Bit(unsigned n, const float *a, int32_t *b)
{
    for (; n > 0; n--) {
        float tmp = *a++;
        float v = CapMax(tmp) * (1U << (BIT_32 - 1));
        *(b++) = static_cast<int32_t>(v);
    }
}

float UpdateMaxAmplitude(ConvertHdiFormat adapterFormat, char *frame, uint64_t replyBytes)
{
    switch (adapterFormat) {
        case SAMPLE_U8_C: {
            return CalculateMaxAmplitudeForPCM8Bit(reinterpret_cast<int8_t *>(frame), replyBytes);
        }
        case SAMPLE_S16_C: {
            return CalculateMaxAmplitudeForPCM16Bit(reinterpret_cast<int16_t *>(frame),
                (replyBytes / sizeof(int16_t)));
        }
        case SAMPLE_S24_C: {
            return CalculateMaxAmplitudeForPCM24Bit(frame, (replyBytes / 3)); // 3 bytes
        }
        case SAMPLE_S32_C: {
            return CalculateMaxAmplitudeForPCM32Bit(reinterpret_cast<int32_t *>(frame),
                (replyBytes / sizeof(int32_t)));
        }
        default: {
            AUDIO_INFO_LOG("getMaxAmplitude: Unsupported audio format: %{public}d", adapterFormat);
            return 0;
        }
    }
}

float CalculateMaxAmplitudeForPCM8Bit(int8_t *frame, uint64_t nSamples)
{
    int curMaxAmplitude = 0;
    for (uint32_t i = nSamples; i > 0; --i) {
        int8_t value = *frame++;
        if (value < 0) {
            value = -value;
        }
        if (curMaxAmplitude < value) {
            curMaxAmplitude = value;
        }
    }
    return float(curMaxAmplitude) / SCHAR_MAX;
}

float CalculateMaxAmplitudeForPCM16Bit(int16_t *frame, uint64_t nSamples)
{
    int curMaxAmplitude = 0;
    for (uint32_t i = nSamples; i > 0; --i) {
        int16_t value = *frame++;
        if (value < 0) {
            value = -value;
        }
        if (curMaxAmplitude < value) {
            curMaxAmplitude = value;
        }
    }
    return float(curMaxAmplitude) / SHRT_MAX;
}

float CalculateMaxAmplitudeForPCM24Bit(char *frame, uint64_t nSamples)
{
    int curMaxAmplitude = 0;
    for (uint32_t i = 0; i < nSamples; ++i) {
        char *curPos = frame + (i * 3); // 3 bytes
        int curValue = 0;
        for (int j = 0; j < 3; ++j) { // 3 bytes
            curValue += (*(curPos + j) << (BIT_8 * j));
        }
        if (curValue < 0) {
            curValue = -curValue;
        }
        if (curMaxAmplitude < curValue) {
            curMaxAmplitude = curValue;
        }
    }
    return float(curMaxAmplitude) / MAX_VALUE_OF_SIGNED_24_BIT;
}

float CalculateMaxAmplitudeForPCM32Bit(int32_t *frame, uint64_t nSamples)
{
    int curMaxAmplitude = 0;
    for (uint32_t i = nSamples; i > 0; --i) {
        int32_t value = *frame++;
        if (value < 0) {
            if (value == INT32_MIN) {
                value = INT32_MAX;
            } else {
                value = -value;
            }
        }

        if (curMaxAmplitude < value) {
            curMaxAmplitude = value;
        }
    }
    return float(curMaxAmplitude) / static_cast<float>(INT_MAX);
}

template <typename T>
bool StringConverter(const std::string &str, T &result)
{
    if (str == "-0") {
        result = 0;
        return true;
    }
    auto [ptr, ec] = std::from_chars(str.data(), str.data() + str.size(), result);
    return ec == std::errc{} && ptr == str.data() + str.size();
}

template bool StringConverter(const std::string &str, uint64_t &result);
template bool StringConverter(const std::string &str, uint32_t &result);
template bool StringConverter(const std::string &str, int32_t &result);
template bool StringConverter(const std::string &str, uint16_t &result);
template bool StringConverter(const std::string &str, uint8_t &result);
template bool StringConverter(const std::string &str, int8_t &result);

bool StringConverterFloat(const std::string &str, float &result)
{
    char *end = nullptr;
    errno = 0;
    result = std::strtof(str.c_str(), &end);
    return end != str.c_str() && *end == '\0' && errno == 0;
}

bool SetSysPara(const std::string &key, int32_t value)
{
    auto res = SetParameter(key.c_str(), std::to_string(value).c_str());
    if (res < 0) {
        AUDIO_WARNING_LOG("SetSysPara fail, key:%{public}s res:%{public}d", key.c_str(), res);
        return false;
    }
    AUDIO_INFO_LOG("SetSysPara %{public}d success.", value);
    return true;
}

template <typename T>
bool GetSysPara(const char *key, T &value)
{
    CHECK_AND_RETURN_RET_LOG(key != nullptr, false, "key is nullptr");
    char paraValue[30] = {0}; // 30 for system parameter
    auto res = GetParameter(key, "-1", paraValue, sizeof(paraValue));

    CHECK_AND_RETURN_RET_LOG(res > 0, false, "GetSysPara fail, key:%{public}s res:%{public}d", key, res);
    AUDIO_DEBUG_LOG("key:%{public}s value:%{public}s", key, paraValue);
    std::stringstream valueStr;
    valueStr << paraValue;
    valueStr >> value;
    return true;
}

template bool GetSysPara(const char *key, int32_t &value);
template bool GetSysPara(const char *key, uint32_t &value);
template bool GetSysPara(const char *key, int64_t &value);
template bool GetSysPara(const char *key, std::string &value);

std::map<std::string, std::string> DumpFileUtil::g_lastPara = {};

FILE *DumpFileUtil::OpenDumpFileInner(std::string para, std::string fileName, AudioDumpFileType fileType)
{
    std::string filePath;
    switch (fileType) {
        case AUDIO_APP:
            filePath = DUMP_APP_DIR + fileName;
            break;
        case OTHER_NATIVE_SERVICE:
            filePath = DUMP_SERVICE_DIR + fileName;
            break;
        case AUDIO_PULSE:
            filePath = DUMP_PULSE_DIR + fileName;
            break;
        default:
            AUDIO_ERR_LOG("Invalid AudioDumpFileType");
            break;
    }
    std::string dumpPara;
    FILE *dumpFile = nullptr;
    bool res = GetSysPara(para.c_str(), dumpPara);
    if (!res || dumpPara.empty()) {
        AUDIO_INFO_LOG("%{public}s is not set, dump audio is not required", para.c_str());
        g_lastPara[para] = dumpPara;
        return dumpFile;
    }
    AUDIO_DEBUG_LOG("%{public}s = %{public}s", para.c_str(), dumpPara.c_str());
    if (dumpPara == "w") {
        dumpFile = fopen(filePath.c_str(), "wb+");
        CHECK_AND_RETURN_RET_LOG(dumpFile != nullptr, dumpFile,
            "Error opening pcm dump file:%{public}s", filePath.c_str());
    } else if (dumpPara == "a") {
        dumpFile = fopen(filePath.c_str(), "ab+");
        CHECK_AND_RETURN_RET_LOG(dumpFile != nullptr, dumpFile,
            "Error opening pcm dump file:%{public}s", filePath.c_str());
    }
    if (dumpFile != nullptr) {
        AUDIO_INFO_LOG("Dump file path: %{public}s", filePath.c_str());
    }
    g_lastPara[para] = dumpPara;
    return dumpFile;
}

void DumpFileUtil::WriteDumpFile(FILE *dumpFile, void *buffer, size_t bufferSize)
{
    if (dumpFile == nullptr) {
        return;
    }
    CHECK_AND_RETURN_LOG(buffer != nullptr, "Invalid write param");
    size_t writeResult = fwrite(buffer, 1, bufferSize, dumpFile);
    CHECK_AND_RETURN_LOG(writeResult == bufferSize, "Failed to write the file.");
}

void DumpFileUtil::CloseDumpFile(FILE **dumpFile)
{
    if (*dumpFile) {
        fclose(*dumpFile);
        *dumpFile = nullptr;
    }
}

void DumpFileUtil::ChangeDumpFileState(std::string para, FILE **dumpFile, std::string filePath)
{
    CHECK_AND_RETURN_LOG(*dumpFile != nullptr, "Invalid file para");
    CHECK_AND_RETURN_LOG(g_lastPara[para] == "w" || g_lastPara[para] == "a", "Invalid input para");
    std::string dumpPara;
    bool res = GetSysPara(para.c_str(), dumpPara);
    if (!res || dumpPara.empty()) {
        AUDIO_WARNING_LOG("get %{public}s fail", para.c_str());
    }
    if (g_lastPara[para] == "w" && dumpPara == "w") {
        return;
    }
    CloseDumpFile(dumpFile);
    OpenDumpFile(para, filePath, dumpFile);
}

void DumpFileUtil::ChangeDumpFileState(const std::string &para, FILE **dumpFile, const std::string &filePath,
    AudioDumpFileType fileType)
{
    CHECK_AND_RETURN_LOG(*dumpFile != nullptr, "Invalid file para");
    CHECK_AND_RETURN_LOG(g_lastPara[para] == "w" || g_lastPara[para] == "a", "Invalid input para");
    std::string dumpPara;
    bool res = GetSysPara(para.c_str(), dumpPara);
    if (!res || dumpPara.empty()) {
        AUDIO_WARNING_LOG("get %{public}s fail", para.c_str());
    }
    if (g_lastPara[para] == "w" && dumpPara == "w") {
        return;
    }
    CloseDumpFile(dumpFile);
    OpenDumpFile(para, filePath, dumpFile, fileType);
}

void DumpFileUtil::OpenDumpFile(const std::string &para, const std::string &fileName, FILE **file,
    AudioDumpFileType fileType)
{
    if (*file != nullptr) {
        DumpFileUtil::ChangeDumpFileState(para, file, fileName, fileType);
        return;
    }
    *file = DumpFileUtil::OpenDumpFileInner(para, fileName, fileType);
}

std::string DumpFileUtil::GetMetadataServerDumpFileName(const std::string &halName, int32_t sourceType,
    int64_t timestamp)
{
    return halName + "_metadata_" + std::to_string(sourceType) + "_" + std::to_string(timestamp) + ".bin";
}

std::string DumpFileUtil::GetMetadataClientDumpFileName(uint32_t sessionId)
{
    return std::to_string(sessionId) + "_cap_client_metadata.bin";
}

void DumpFileUtil::OpenDumpFile(std::string para, std::string fileName, FILE **file)
{
    if (*file != nullptr) {
        DumpFileUtil::ChangeDumpFileState(para, file, fileName);
        return;
    }

    if (para == DUMP_SERVER_PARA) {
        *file = DumpFileUtil::OpenDumpFileInner(para, fileName, AUDIO_PULSE);
    } else {
        *file = DumpFileUtil::OpenDumpFileInner(para, fileName, AUDIO_APP);
        if (*file == nullptr) {
            *file = DumpFileUtil::OpenDumpFileInner(para, fileName, OTHER_NATIVE_SERVICE);
        }
    }
}

void CloseFd(int fd)
{
    // log stdin, stdout, stderr.
    if (fd == STDIN_FILENO || fd == STDOUT_FILENO || fd == STDERR_FILENO) {
        AUDIO_WARNING_LOG("special fd: %{public}d will be closed", fd);
    }
    int tmpFd = fd;
    close(fd);
    AUDIO_DEBUG_LOG("fd: %{public}d closed successfuly!", tmpFd);
}

static void MemcpyToI32FromI16(int16_t *src, int32_t *dst, size_t count)
{
    for (size_t i = 0; i < count; i++) {
        *(dst + i) = static_cast<int32_t>(*(src + i));
    }
}

static void MemcpyToI32FromI24(uint8_t *src, int32_t *dst, size_t count)
{
    for (size_t i = 0; i < count; i++) {
        uint8_t *tmp = src + 3 * i; // 3 is byte size of SAMPLE_S24LE;
        *(dst + i) = static_cast<int32_t>(tmp[2] << (2 * sizeof(uint8_t))) |
            static_cast<int32_t>(tmp[1] << sizeof(uint8_t)) | static_cast<int32_t>(tmp[0]);
    }
}

static void MemcpyToI32FromF32(float *src, int32_t *dst, size_t count)
{
    for (size_t i = 0; i < count; i++) {
        *(dst + i) = static_cast<int32_t>(*(src + i));
    }
}

bool NearZero(int16_t number)
{
    return number >= -DETECTED_ZERO_THRESHOLD && number <= DETECTED_ZERO_THRESHOLD;
}

std::string GetTime()
{
    struct timeval tv;
    struct timezone tz;
    struct tm *t;
    gettimeofday(&tv, &tz);
    t = localtime(&tv.tv_sec);
    if (t == nullptr) {
        return "";
    }

    int64_t mSec = static_cast<int64_t>(tv.tv_usec / AUDIO_MS_PER_SECOND);

    // 2025-06-22-21:22:07:666
    char timeBuf[TIME_TEXT_LENGTH] = {0};
    int ret = sprintf_s(timeBuf, sizeof(timeBuf), "%04d-%02d-%02d-%02d:%02d:%02d:%03d", (YEAR_BASE + t->tm_year),
        (1 + t->tm_mon), t->tm_mday, t->tm_hour, t->tm_min, t->tm_sec, mSec);
    if (ret < 0) {
        return "";
    }

    std::string curTime(timeBuf);
    return curTime;
}

std::string GetField(const std::string &src, const char* field, const char sep)
{
    auto str = std::string(field) + '=';
    auto pos = src.find(str);
    CHECK_AND_RETURN_RET(pos != std::string::npos, "");
    pos += str.length();
    auto end = src.find(sep, pos);
    return end == std::string::npos ? src.substr(pos) : src.substr(pos, end - pos);
}

int32_t GetFormatByteSize(int32_t format)
{
    int32_t formatByteSize;
    switch (format) {
        case SAMPLE_S16LE:
            formatByteSize = 2; // size is 2
            break;
        case SAMPLE_S24LE:
            formatByteSize = 3; // size is 3
            break;
        case SAMPLE_S32LE:
            formatByteSize = 4; // size is 4
            break;
        case SAMPLE_F32LE:
            formatByteSize = 4; // size is 4
            break;
        default:
            formatByteSize = 2; // size is 2
            break;
    }
    return formatByteSize;
}

bool SignalDetectAgent::CheckAudioData(uint8_t *buffer, size_t bufferLen)
{
    CHECK_AND_RETURN_RET_LOG(formatByteSize_ != 0, false, "LatencyMeas checkAudioData failed, "
        "formatByteSize_ %{public}d", formatByteSize_);
    frameCountIgnoreChannel_ = bufferLen / static_cast<uint32_t>(formatByteSize_);
    if (cacheAudioData_.capacity() < frameCountIgnoreChannel_) {
        cacheAudioData_.clear();
        cacheAudioData_.reserve(frameCountIgnoreChannel_);
    }
    int32_t *cache = cacheAudioData_.data();
    if (sampleFormat_ == SAMPLE_S32LE) {
        int32_t ret = memcpy_s(cache, sizeof(int32_t) * cacheAudioData_.capacity(), buffer, bufferLen);
        CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, false, "LatencyMeas checkAudioData failed, dstSize "
            "%{public}zu, srcSize %{public}zu", sizeof(int32_t) * cacheAudioData_.capacity(), bufferLen);
    } else if (sampleFormat_ == SAMPLE_F32LE) {
        float *cp = reinterpret_cast<float*>(buffer);
        MemcpyToI32FromF32(cp, cache, frameCountIgnoreChannel_);
    } else if (sampleFormat_ == SAMPLE_S24LE) {
        MemcpyToI32FromI24(buffer, cache, frameCountIgnoreChannel_);
    } else {
        int16_t *cp = reinterpret_cast<int16_t*>(buffer);
        MemcpyToI32FromI16(cp, cache, frameCountIgnoreChannel_);
    }
    if (DetectSignalData(cache, frameCountIgnoreChannel_)) {
        ResetDetectResult();
        return true;
    }
    return false;
}

bool SignalDetectAgent::DetectSignalData(int32_t *buffer, size_t bufferLen)
{
    std::string curTime = GetTime();
    uint32_t rightZeroSignal = 0;
    int32_t currentPeakIndex = -1;
    int32_t currentPeakSignal = SHRT_MIN;
    bool hasNoneZero = false;
    size_t frameCount = bufferLen / static_cast<size_t>(channels_);
    for (size_t index = 0; index < frameCount; index++) {
        int32_t tempMax = SHRT_MIN;
        int32_t tempMin = SHRT_MAX;
        for (uint32_t channel = 0; channel < static_cast<uint32_t>(channels_); channel++) {
            int32_t temp = buffer[index * static_cast<uint32_t>(channels_) + channel];
            tempMax = temp > tempMax ? temp : tempMax;
            tempMin = temp < tempMin ? temp : tempMin;
        }
        if (!NearZero(tempMax) || !NearZero(tempMin)) {
            rightZeroSignal = index + 1;
            hasNoneZero = true;
            if (currentPeakIndex == -1 || tempMax > currentPeakSignal) {
                currentPeakIndex = static_cast<int32_t>(index);
                currentPeakSignal = tempMax;
            }
        }
    }
    if (!hasNoneZero) {
        blankPeriod_ += static_cast<int32_t>(frameCount);
    } else {
        if (!hasFirstNoneZero_) {
            lastPeakBufferTime_ = curTime;
            hasFirstNoneZero_ = true;
        }
        if (currentPeakSignal > lastPeakSignal_) {
            lastPeakSignal_ = currentPeakSignal;
            lastPeakSignalPos_ = currentPeakIndex;
        }
        blankHaveOutput_ = false;
        blankPeriod_ = static_cast<int32_t>(frameCount - rightZeroSignal);
    }
    int32_t thresholdBlankPeriod = BLANK_THRESHOLD_MS * sampleRate_ / MILLISECOND_PER_SECOND;
    if (blankPeriod_ > thresholdBlankPeriod) {
        return !blankHaveOutput_;
    }
    return false;
}

void SignalDetectAgent::ResetDetectResult()
{
    blankHaveOutput_ = true;
    hasFirstNoneZero_ = false;
    lastPeakSignal_ = SHRT_MIN;
    signalDetected_ = true;
    dspTimestampGot_ = false;
    return;
}

bool AudioLatencyMeasurement::MockPcmData(uint8_t *buffer, size_t bufferLen)
{
    memset_s(buffer, bufferLen, 0, bufferLen);
    int16_t *signal = signalData_.get();
    size_t newlyMocked = bufferLen * MILLISECOND_PER_SECOND /
        static_cast<size_t>(channelCount_ * sampleRate_ * formatByteSize_);
    mockedTime_ += newlyMocked;
    if (mockedTime_ >= MOCK_INTERVAL) {
        mockedTime_ = 0;
        if (format_ == SAMPLE_S32LE) {
            MemcpyToI32FromI16(signal, reinterpret_cast<int32_t*>(buffer), SIGNAL_DATA_SIZE);
        } else {
            int32_t ret = memcpy_s(buffer, bufferLen, signal, SIGNAL_DATA_SIZE * sizeof(uint8_t));
            CHECK_AND_RETURN_RET_LOG(ret == SUCCESS, false, "LatencyMeas mockPcmData failed, dstSize "
                "%{public}zu, srcSize %{public}zu", bufferLen, SIGNAL_DATA_SIZE * sizeof(uint8_t));
        }
        return true;
    }
    return false;
}

AudioLatencyMeasurement::AudioLatencyMeasurement(const int32_t &sampleRate,
                                                 const int32_t &channelCount, const int32_t &sampleFormat,
                                                 const std::string &appName, const uint32_t &sessionId)
    :format_(sampleFormat),
     sampleRate_(sampleRate),
     channelCount_(channelCount),
     sessionId_(sessionId),
     appName_(appName)
{
    std::string appToMock = "com.example.null";
    GetSysPara("persist.multimedia.apptomock", appToMock);
    AUDIO_INFO_LOG("LatencyMeas appName:%{public}s, appToMock:%{public}s, g_sessionId:%{public}u",
        appName.c_str(), appToMock.c_str(), g_sessionToMock);
    if (appToMock == appName && g_sessionToMock == 0) {
        mockThisStream_ = true;
        g_sessionToMock = sessionId;
    }
    formatByteSize_ = GetFormatByteSize(sampleFormat);
    InitSignalData();
}

AudioLatencyMeasurement::~AudioLatencyMeasurement()
{
    if (mockThisStream_ && g_sessionToMock == sessionId_) {
        g_sessionToMock = 0;
    }
}

void AudioLatencyMeasurement::InitSignalData()
{
    signalData_ = std::make_unique<int16_t[]>(SIGNAL_DATA_SIZE);
    memset_s(signalData_.get(), SIGNAL_DATA_SIZE, 0, SIGNAL_DATA_SIZE);
    const int16_t channels = 2; // 2 channels
    const int16_t samplePerChannel = SIGNAL_DATA_SIZE / channels;
    int16_t *signalBuffer = signalData_.get();
    for (int16_t index = 0; index < samplePerChannel; index++) {
        signalBuffer[index * channels] = SIGNAL_THRESHOLD + static_cast<int16_t>(sinf(2.0f *
            static_cast<float>(M_PI) * index / samplePerChannel) * (SHRT_MAX - SIGNAL_THRESHOLD));
        for (int16_t k = 1; k < channels; k++) {
            signalBuffer[channels * index + k] = signalBuffer[channels * index];
        }
    }
    AUDIO_INFO_LOG("LatencyMeas signalData inited");
    return;
}

bool AudioLatencyMeasurement::CheckIfEnabled()
{
    int32_t latencyMeasure = -1;
    GetSysPara("persist.multimedia.audiolatency", latencyMeasure);
    return (latencyMeasure == 1);
}

LatencyMonitor& LatencyMonitor::GetInstance()
{
    static LatencyMonitor latencyMonitor_;
    return latencyMonitor_;
}

void LatencyMonitor::UpdateClientTime(bool isRenderer, std::string &timestamp)
{
    std::lock_guard lock(mutex_);
    if (isRenderer) {
        rendererMockTime_ = timestamp;
    } else {
        capturerDetectedTime_ = timestamp;
    }
}

void LatencyMonitor::UpdateRendererInServerTime(std::string &timestamp)
{
    std::lock_guard lock(mutex_);
    rendererInServerDetectedTime_ = timestamp;
}

void LatencyMonitor::UpdateSinkOrSourceTime(bool isRenderer, std::string &timestamp)
{
    std::lock_guard lock(mutex_);
    if (isRenderer) {
        sinkDetectedTime_ = timestamp;
    } else {
        sourceDetectedTime_ = timestamp;
    }
}

void LatencyMonitor::UpdateDspTime(std::string timestamp)
{
    std::lock_guard lock(mutex_);
    dspDetectedTime_ = timestamp;
}

void LatencyMonitor::ShowTimestamp(bool isRenderer)
{
    std::lock_guard lock(mutex_);
    if (extraStrLen_ == 0) {
        extraStrLen_ = dspDetectedTime_.find("20");
    }
    if (isRenderer) {
        if (dspDetectedTime_.length() == 0) {
            AUDIO_ERR_LOG("LatencyMeas GetExtraParameter failed!");
            AUDIO_INFO_LOG("LatencyMeas RendererMockTime:%{public}s, RendererInServerDetectedTime:%{public}s, "
                           "SinkDetectedTime:%{public}s", rendererMockTime_.c_str(),
                rendererInServerDetectedTime_.c_str(), sinkDetectedTime_.c_str());
            AUTO_CTRACE("LatencyMeas RendererMockTime:%s, RendererInServerDetectedTime:%s, SinkDetectedTime:%s",
                rendererMockTime_.c_str(), rendererInServerDetectedTime_.c_str(), sinkDetectedTime_.c_str());
            return;
        }
        dspBeforeSmartPa_ = dspDetectedTime_.substr(extraStrLen_, DATE_LENGTH);
        dspAfterSmartPa_ = dspDetectedTime_.substr(extraStrLen_ + DATE_LENGTH + 1 +
            extraStrLen_, DATE_LENGTH);
        AUDIO_INFO_LOG("LatencyMeas RendererMockTime:%{public}s, RendererInServerDetectedTime:%{public}s, "
                       "SinkDetectedTime:%{public}s, DspBeforeSmartPa:%{public}s, DspAfterSmartPa:%{public}s",
            rendererMockTime_.c_str(), rendererInServerDetectedTime_.c_str(), sinkDetectedTime_.c_str(),
            dspBeforeSmartPa_.c_str(), dspAfterSmartPa_.c_str());
        AUTO_CTRACE("LatencyMeas RendererMockTime:%s, RendererInServerDetectedTime:%s, SinkDetectedTime:%s, "
                       "DspBeforeSmartPa:%s, DspAfterSmartPa:%s", rendererMockTime_.c_str(),
            rendererInServerDetectedTime_.c_str(), sinkDetectedTime_.c_str(),
            dspBeforeSmartPa_.c_str(), dspAfterSmartPa_.c_str());
    } else {
        AUDIO_INFO_LOG("renderer mock time %{public}s", rendererMockTime_.c_str());
        if (dspDetectedTime_.length() == 0) {
            AUDIO_ERR_LOG("LatencyMeas GetExtraParam failed!");
            AUDIO_INFO_LOG("LatencyMeas CapturerDetectedTime:%{public}s, SourceDetectedTime:%{public}s",
                capturerDetectedTime_.c_str(), sourceDetectedTime_.c_str());
            AUTO_CTRACE("LatencyMeas CapturerDetectedTime:%s, SourceDetectedTime:%s",
                capturerDetectedTime_.c_str(), sourceDetectedTime_.c_str());
            return;
        }
        dspMockTime_ = dspDetectedTime_.substr(extraStrLen_ + DATE_LENGTH + extraStrLen_ + 1 +
            DATE_LENGTH + extraStrLen_ + 1, DATE_LENGTH);
        AUDIO_INFO_LOG("LatencyMeas CapturerDetectedTime:%{public}s, SourceDetectedTime:%{public}s, "
                       "DspMockTime:%{public}s", capturerDetectedTime_.c_str(), sourceDetectedTime_.c_str(),
                       dspMockTime_.c_str());
        AUTO_CTRACE("LatencyMeas CapturerDetectedTime:%s, SourceDetectedTime:%s, "
                       "DspMockTime:%s", capturerDetectedTime_.c_str(), sourceDetectedTime_.c_str(),
                       dspMockTime_.c_str());
    }
}

void LatencyMonitor::ShowBluetoothTimestamp()
{
    std::lock_guard lock(mutex_);
    AUDIO_INFO_LOG("LatencyMeas RendererMockTime:%{public}s, RendererInServerDetectedTime:%{public}s, "
                   "BTSinkDetectedTime:%{public}s", rendererMockTime_.c_str(),
        rendererInServerDetectedTime_.c_str(), sinkDetectedTime_.c_str());
    AUTO_CTRACE("LatencyMeas RendererMockTime:%s, RendererInServerDetectedTime:%s, BTSinkDetectedTime:%s",
        rendererMockTime_.c_str(), rendererInServerDetectedTime_.c_str(), sinkDetectedTime_.c_str());
}

const std::string AudioInfoDumpUtils::GetStreamName(AudioStreamType streamType)
{
    std::string name;
    std::unordered_map<AudioStreamType, std::string> map = STREAM_TYPE_NAME_MAP;
    auto it = map.find(streamType);
    if (it != map.end()) {
        name = it->second;
    } else {
        name = "UNKNOWN";
    }

    const std::string streamName = name;
    return streamName;
}

const std::string AudioInfoDumpUtils::GetDeviceTypeName(DeviceType deviceType)
{
    std::string device;
    auto it = DEVICE_TYPE_NAME_MAP.find(deviceType);
    if (it != DEVICE_TYPE_NAME_MAP.end()) {
        device = it->second;
    } else {
        device = "UNKNOWN";
    }

    const std::string deviceTypeName = device;
    return deviceTypeName;
}

const std::string AudioInfoDumpUtils::GetConnectTypeName(ConnectType connectType)
{
    std::string connectName;
    switch (connectType) {
        case OHOS::AudioStandard::CONNECT_TYPE_LOCAL:
            connectName = "LOCAL";
            break;
        case OHOS::AudioStandard::CONNECT_TYPE_DISTRIBUTED:
            connectName = "REMOTE";
            break;
        default:
            connectName = "UNKNOWN";
            break;
    }
    const std::string connectTypeName = connectName;
    return connectTypeName;
}

const std::string AudioInfoDumpUtils::GetSourceName(SourceType sourceType)
{
    std::string name;
    switch (sourceType) {
        case SOURCE_TYPE_INVALID:
            name = "INVALID";
            break;
        case SOURCE_TYPE_MIC:
            name = "MIC";
            break;
        case SOURCE_TYPE_CAMCORDER:
            name = "CAMCORDER";
            break;
        case SOURCE_TYPE_VOICE_RECOGNITION:
            name = "VOICE_RECOGNITION";
            break;
        case SOURCE_TYPE_ULTRASONIC:
            name = "ULTRASONIC";
            break;
        case SOURCE_TYPE_VOICE_COMMUNICATION:
            name = "VOICE_COMMUNICATION";
            break;
        case SOURCE_TYPE_WAKEUP:
            name = "WAKEUP";
            break;
        case SOURCE_TYPE_UNPROCESSED:
            name = "SOURCE_TYPE_UNPROCESSED";
            break;
        case SOURCE_TYPE_LIVE:
            name = "SOURCE_TYPE_LIVE";
            break;
        case SOURCE_TYPE_UNPROCESSED_VOICE_ASSISTANT:
            name = "SOURCE_TYPE_UNPROCESSED_VOICE_ASSISTANT";
            break;
        case SOURCE_TYPE_INTERPHONE:
            name = "INTERPHONE";
            break;
        default:
            name = "UNKNOWN";
    }

    const std::string sourceName = name;
    return sourceName;
}

const std::string AudioInfoDumpUtils::GetDeviceVolumeTypeName(DeviceVolumeType deviceType)
{
    std::string device;
    switch (deviceType) {
        case EARPIECE_VOLUME_TYPE:
            device = "EARPIECE";
            break;
        case SPEAKER_VOLUME_TYPE:
            device = "SPEAKER";
            break;
        case HEADSET_VOLUME_TYPE:
            device = "HEADSET";
            break;
        default:
            device = "UNKNOWN";
    }

    const std::string deviceTypeName = device;
    return deviceTypeName;
}

bool VolumeUtils::isPCVolumeEnable_ = false;
bool VolumeUtils::isVolumeFixEnable_ = false;

std::unordered_map<AudioStreamType, AudioVolumeType> VolumeUtils::defaultVolumeMap_ = {
    {STREAM_VOICE_CALL, STREAM_VOICE_CALL},
    {STREAM_VOICE_COMMUNICATION, STREAM_VOICE_CALL},
    {STREAM_VOICE_CALL_ASSISTANT, STREAM_VOICE_CALL_ASSISTANT},

    {STREAM_RING, STREAM_RING},
    {STREAM_VOICE_RING, STREAM_RING},

    {STREAM_SYSTEM, STREAM_NOTIFICATION},
    {STREAM_NOTIFICATION, STREAM_NOTIFICATION},
    {STREAM_SYSTEM_ENFORCED, STREAM_NOTIFICATION},
    {STREAM_DTMF, STREAM_NOTIFICATION},

    {STREAM_MUSIC, STREAM_MUSIC},
    {STREAM_MEDIA, STREAM_MUSIC},
    {STREAM_MOVIE, STREAM_MUSIC},
    {STREAM_GAME, STREAM_MUSIC},
    {STREAM_SPEECH, STREAM_MUSIC},
#ifdef FEATURE_AUDIO_ZONE_VOLUME
    {STREAM_NAVIGATION, STREAM_NAVIGATION},
#else
    {STREAM_NAVIGATION, STREAM_MUSIC},
#endif
    {STREAM_VOICE_MESSAGE, STREAM_MUSIC},

    {STREAM_VOICE_ASSISTANT, STREAM_VOICE_ASSISTANT},
    {STREAM_ALARM, STREAM_ALARM},
    {STREAM_ACCESSIBILITY, STREAM_ACCESSIBILITY},
    {STREAM_ULTRASONIC, STREAM_ULTRASONIC},
    {STREAM_ALL, STREAM_ALL},
    {STREAM_APP, STREAM_APP},
#ifdef MULTI_ALARM_LEVEL
    {STREAM_ANNOUNCEMENT, STREAM_ANNOUNCEMENT},
    {STREAM_EMERGENCY, STREAM_EMERGENCY},
#endif
};

std::unordered_map<AudioStreamType, AudioVolumeType> VolumeUtils::audioPCVolumeMap_ = {
    {STREAM_VOICE_CALL, STREAM_MUSIC},
    {STREAM_VOICE_CALL_ASSISTANT, STREAM_VOICE_CALL_ASSISTANT},
    {STREAM_VOICE_MESSAGE, STREAM_MUSIC},
    {STREAM_VOICE_ASSISTANT, STREAM_MUSIC},
    {STREAM_VOICE_COMMUNICATION, STREAM_MUSIC},
    {STREAM_DTMF, STREAM_MUSIC},
    {STREAM_MUSIC, STREAM_MUSIC},
    {STREAM_MEDIA, STREAM_MUSIC},
    {STREAM_MOVIE, STREAM_MUSIC},
    {STREAM_GAME, STREAM_MUSIC},
    {STREAM_SPEECH, STREAM_MUSIC},
    {STREAM_RECORDING, STREAM_MUSIC},
    {STREAM_NAVIGATION, STREAM_MUSIC},
    {STREAM_ACCESSIBILITY, STREAM_MUSIC},
    {STREAM_ALL, STREAM_ALL},

    {STREAM_RING, STREAM_MUSIC},
    {STREAM_VOICE_RING, STREAM_MUSIC},
    {STREAM_ALARM, STREAM_MUSIC},

    {STREAM_SYSTEM, STREAM_SYSTEM},
    {STREAM_NOTIFICATION, STREAM_SYSTEM},
    {STREAM_SYSTEM_ENFORCED, STREAM_SYSTEM},

    {STREAM_ULTRASONIC, STREAM_ULTRASONIC},
    {STREAM_APP, STREAM_APP},

#ifdef MULTI_ALARM_LEVEL
    {STREAM_ANNOUNCEMENT, STREAM_ANNOUNCEMENT},
    {STREAM_EMERGENCY, STREAM_EMERGENCY}
#endif
};

std::unordered_map<AudioVolumeType, std::set<StreamUsage>> VolumeUtils::defaultVolumeToStreamUsageMap_ = {
    {STREAM_VOICE_CALL, {
        STREAM_USAGE_VOICE_COMMUNICATION,
        STREAM_USAGE_VIDEO_COMMUNICATION,
        STREAM_USAGE_VOICE_MODEM_COMMUNICATION,
        STREAM_USAGE_INTERPHONE,
        STREAM_USAGE_VOICE_TRANSFER_COMMUNICATION}},
    {STREAM_VOICE_CALL_ASSISTANT, {
        STREAM_USAGE_VOICE_CALL_ASSISTANT}},
    {STREAM_RING, {
        STREAM_USAGE_RINGTONE,
        STREAM_USAGE_VOICE_RINGTONE,
        STREAM_USAGE_VOICE_TRANSFER_RINGTONE}},
    {STREAM_NOTIFICATION, {
        STREAM_USAGE_SYSTEM,
        STREAM_USAGE_NOTIFICATION,
        STREAM_USAGE_ENFORCED_TONE,
        STREAM_USAGE_DTMF}},
#ifdef FEATURE_AUDIO_ZONE_VOLUME
    {STREAM_MUSIC, {
        STREAM_USAGE_UNKNOWN,
        STREAM_USAGE_MUSIC,
        STREAM_USAGE_MOVIE,
        STREAM_USAGE_AUDIOBOOK,
        STREAM_USAGE_GAME,
        STREAM_USAGE_VOICE_MESSAGE}},
    {STREAM_NAVIGATION, {
        STREAM_USAGE_NAVIGATION}},
#else
    {STREAM_MUSIC, {
        STREAM_USAGE_UNKNOWN,
        STREAM_USAGE_MUSIC,
        STREAM_USAGE_MOVIE,
        STREAM_USAGE_AUDIOBOOK,
        STREAM_USAGE_GAME,
        STREAM_USAGE_NAVIGATION,
        STREAM_USAGE_VOICE_MESSAGE}},
#endif
    {STREAM_VOICE_ASSISTANT, {
        STREAM_USAGE_VOICE_ASSISTANT}},
    {STREAM_ALARM, {
        STREAM_USAGE_ALARM}},
    {STREAM_ACCESSIBILITY, {
        STREAM_USAGE_ACCESSIBILITY}},
    {STREAM_ULTRASONIC, {
        STREAM_USAGE_ULTRASONIC}},
#ifdef MULTI_ALARM_LEVEL
    {STREAM_ANNOUNCEMENT, {
        STREAM_USAGE_ANNOUNCEMENT}},
    {STREAM_EMERGENCY, {
        STREAM_USAGE_EMERGENCY}}
#endif
};

std::unordered_map<AudioVolumeType, std::set<StreamUsage>> VolumeUtils::pcVolumeToStreamUsageMap_ = {
    {STREAM_MUSIC, {
        STREAM_USAGE_UNKNOWN,
        STREAM_USAGE_MUSIC,
        STREAM_USAGE_MOVIE,
        STREAM_USAGE_GAME,
        STREAM_USAGE_AUDIOBOOK,
        STREAM_USAGE_VOICE_MESSAGE,
        STREAM_USAGE_VOICE_COMMUNICATION,
        STREAM_USAGE_VIDEO_COMMUNICATION,
        STREAM_USAGE_VOICE_ASSISTANT,
        STREAM_USAGE_ALARM,
        STREAM_USAGE_RINGTONE,
        STREAM_USAGE_DTMF,
        STREAM_USAGE_ACCESSIBILITY,
        STREAM_USAGE_NAVIGATION,
        STREAM_USAGE_VOICE_MODEM_COMMUNICATION,
        STREAM_USAGE_VOICE_RINGTONE}},
    {STREAM_SYSTEM, {
        STREAM_USAGE_SYSTEM,
        STREAM_USAGE_NOTIFICATION,
        STREAM_USAGE_ENFORCED_TONE}},
    {STREAM_ULTRASONIC, {
        STREAM_USAGE_ULTRASONIC}},
    {STREAM_VOICE_CALL_ASSISTANT, {
        STREAM_USAGE_VOICE_CALL_ASSISTANT
    }},
#ifdef MULTI_ALARM_LEVEL
    {STREAM_ANNOUNCEMENT, {
        STREAM_USAGE_ANNOUNCEMENT}},
    {STREAM_EMERGENCY, {
        STREAM_USAGE_EMERGENCY}}
#endif
};

std::unordered_map<StreamUsage, AudioStreamType> VolumeUtils::streamUsageMap_ = {
    {STREAM_USAGE_UNKNOWN, STREAM_MUSIC},
    {STREAM_USAGE_MUSIC, STREAM_MUSIC},
    {STREAM_USAGE_VOICE_COMMUNICATION, STREAM_VOICE_COMMUNICATION},
    {STREAM_USAGE_INTERPHONE, STREAM_VOICE_COMMUNICATION},
    {STREAM_USAGE_VOICE_ASSISTANT, STREAM_VOICE_ASSISTANT},
    {STREAM_USAGE_ALARM, STREAM_ALARM},
    {STREAM_USAGE_VOICE_MESSAGE, STREAM_VOICE_MESSAGE},
    {STREAM_USAGE_RINGTONE, STREAM_RING},
    {STREAM_USAGE_NOTIFICATION, STREAM_NOTIFICATION},
    {STREAM_USAGE_ACCESSIBILITY, STREAM_ACCESSIBILITY},
    {STREAM_USAGE_MOVIE, STREAM_MOVIE},
    {STREAM_USAGE_GAME, STREAM_GAME},
    {STREAM_USAGE_AUDIOBOOK, STREAM_SPEECH},
    {STREAM_USAGE_NAVIGATION, STREAM_NAVIGATION},
    {STREAM_USAGE_VIDEO_COMMUNICATION, STREAM_VOICE_COMMUNICATION},
    {STREAM_USAGE_SYSTEM, STREAM_SYSTEM},
    {STREAM_USAGE_ENFORCED_TONE, STREAM_SYSTEM_ENFORCED},
    {STREAM_USAGE_DTMF, STREAM_DTMF},
    {STREAM_USAGE_VOICE_MODEM_COMMUNICATION, STREAM_VOICE_CALL},
    {STREAM_USAGE_VOICE_TRANSFER_COMMUNICATION, STREAM_VOICE_CALL},
    {STREAM_USAGE_VOICE_RINGTONE, STREAM_VOICE_RING},
    {STREAM_USAGE_VOICE_TRANSFER_RINGTONE, STREAM_VOICE_RING},
    {STREAM_USAGE_VOICE_CALL_ASSISTANT, STREAM_VOICE_CALL_ASSISTANT},
    {STREAM_USAGE_ULTRASONIC, STREAM_ULTRASONIC},
#ifdef MULTI_ALARM_LEVEL
    {STREAM_USAGE_ANNOUNCEMENT, STREAM_ANNOUNCEMENT},
    {STREAM_USAGE_EMERGENCY, STREAM_EMERGENCY},
#endif
};

std::unordered_set<AudioVolumeType> VolumeUtils::audioVolumeTypeSet_ = {
    STREAM_RING,
    STREAM_MUSIC,
    STREAM_VOICE_CALL,
    STREAM_VOICE_ASSISTANT,
    STREAM_ALARM,
    STREAM_SYSTEM,
    STREAM_ACCESSIBILITY,
    STREAM_ULTRASONIC,
    STREAM_NOTIFICATION,
    STREAM_NAVIGATION,
#ifdef MULTI_ALARM_LEVEL
    STREAM_ANNOUNCEMENT,
    STREAM_EMERGENCY,
#endif
    STREAM_ALL,
};

static const std::map<AudioStreamType, StreamUsage> STREAMTYPE_TO_USAGE_MAP = {
    {STREAM_MUSIC, STREAM_USAGE_MUSIC},
    {STREAM_VOICE_CALL, STREAM_USAGE_VOICE_COMMUNICATION},
    {STREAM_VOICE_CALL_ASSISTANT, STREAM_USAGE_VOICE_CALL_ASSISTANT},
    {STREAM_VOICE_ASSISTANT, STREAM_USAGE_VOICE_ASSISTANT},
    {STREAM_ALARM, STREAM_USAGE_ALARM},
    {STREAM_VOICE_MESSAGE, STREAM_USAGE_VOICE_MESSAGE},
    {STREAM_RING, STREAM_USAGE_RINGTONE},
    {STREAM_NOTIFICATION, STREAM_USAGE_NOTIFICATION},
    {STREAM_ACCESSIBILITY, STREAM_USAGE_ACCESSIBILITY},
    {STREAM_SYSTEM, STREAM_USAGE_SYSTEM},
    {STREAM_MOVIE, STREAM_USAGE_MOVIE},
    {STREAM_GAME, STREAM_USAGE_GAME},
    {STREAM_SPEECH, STREAM_USAGE_AUDIOBOOK},
    {STREAM_NAVIGATION, STREAM_USAGE_NAVIGATION},
    {STREAM_DTMF, STREAM_USAGE_DTMF},
    {STREAM_SYSTEM_ENFORCED, STREAM_USAGE_ENFORCED_TONE},
    {STREAM_ULTRASONIC, STREAM_USAGE_ULTRASONIC},
    {STREAM_VOICE_RING, STREAM_USAGE_VOICE_RINGTONE},
#ifdef MULTI_ALARM_LEVEL
    {STREAM_ANNOUNCEMENT, STREAM_USAGE_ANNOUNCEMENT},
    {STREAM_EMERGENCY, STREAM_USAGE_EMERGENCY},
#endif
};

static const std::map<std::string, HdiAdapterType> HALNAME_TO_TYPE_MAP = {
    {"primary", HDI_ADAPTER_TYPE_PRIMARY},
    {"a2dp", HDI_ADAPTER_TYPE_A2DP},
    {"usb", HDI_ADAPTER_TYPE_USB},
    {"hdmi", HDI_ADAPTER_TYPE_HDMI},
    {"dp", HDI_ADAPTER_TYPE_DP},
    {"remote", HDI_ADAPTER_TYPE_REMOTE},
    {"hearing_aid", HDI_ADAPTER_TYPE_HEARING_AID},
    {"accessory", HDI_ADAPTER_TYPE_ACCESSORY},
    {"sle", HDI_ADAPTER_TYPE_SLE},
    {"va", HDI_ADAPTER_TYPE_VA},
};

std::unordered_map<AudioStreamType, AudioVolumeType>& VolumeUtils::GetVolumeMap()
{
    if (isPCVolumeEnable_) {
        return audioPCVolumeMap_;
    } else {
        return defaultVolumeMap_;
    }
}

void VolumeUtils::SetPCVolumeEnable(const bool& isPCVolumeEnable)
{
    isPCVolumeEnable_ = isPCVolumeEnable;
}

bool VolumeUtils::IsPCVolumeEnable()
{
    return isPCVolumeEnable_;
}

void VolumeUtils::SetVolumeFixEnable(const bool& isVolumeFixEnable)
{
    isVolumeFixEnable_ = isVolumeFixEnable;
}

bool VolumeUtils::IsVolumeFixEnable()
{
    return isVolumeFixEnable_;
}

AudioVolumeType VolumeUtils::GetVolumeTypeFromStreamType(AudioStreamType streamType)
{
    std::unordered_map<AudioStreamType, AudioVolumeType>& map = GetVolumeMap();
    auto it = map.find(streamType);
    if (it != map.end()) {
        return it->second;
    }
    return STREAM_MUSIC;
}

AudioVolumeType VolumeUtils::GetVolumeTypeFromStreamUsage(StreamUsage streamUsage)
{
    auto it = streamUsageMap_.find(streamUsage);
    if (it != streamUsageMap_.end()) {
        return GetVolumeTypeFromStreamType(it->second);
    }
    return STREAM_MUSIC;
}

std::map<AudioVolumeType, std::vector<StreamUsage>> VolumeUtils::streamToStreamUsageMap_ = {
    {STREAM_RING, {STREAM_USAGE_VOICE_RINGTONE, STREAM_USAGE_VOICE_TRANSFER_RINGTONE}},
    {STREAM_NOTIFICATION, {STREAM_USAGE_NOTIFICATION}},
    {STREAM_VOICE_CALL, {STREAM_USAGE_VOICE_MODEM_COMMUNICATION, STREAM_USAGE_VOICE_COMMUNICATION,
        STREAM_USAGE_INTERPHONE, STREAM_USAGE_VOICE_TRANSFER_COMMUNICATION}},
    {STREAM_VOICE_ASSISTANT, {STREAM_USAGE_VOICE_ASSISTANT}},
    {STREAM_ALARM, {STREAM_USAGE_ALARM}},
    {STREAM_ACCESSIBILITY, {STREAM_USAGE_ACCESSIBILITY}},
    {STREAM_SYSTEM, {STREAM_USAGE_SYSTEM}},
    {STREAM_ULTRASONIC, {STREAM_USAGE_ULTRASONIC}},
    {STREAM_MUSIC, {STREAM_USAGE_MUSIC}},
#ifdef MULTI_ALARM_LEVEL
    {STREAM_ANNOUNCEMENT, {STREAM_USAGE_ANNOUNCEMENT}},
    {STREAM_EMERGENCY, {STREAM_USAGE_EMERGENCY}},
#endif

#ifdef FEATURE_AUDIO_ZONE_VOLUME
    {STREAM_NAVIGATION, {STREAM_USAGE_NAVIGATION}},
#endif
};

std::vector<StreamUsage> VolumeUtils::GetStreamUsageByVolumeTypeForFetchDevice(AudioVolumeType volumeType)
{
    auto it = streamToStreamUsageMap_.find(volumeType);
    if (it != streamToStreamUsageMap_.end()) {
        return it->second;
    }
    return {STREAM_USAGE_MUSIC};
}

std::set<StreamUsage> VolumeUtils::GetOverlapStreamUsageSet(const std::set<StreamUsage> &streamUsages,
    AudioVolumeType volumeType)
{
    std::set<StreamUsage>& tempSet = GetStreamUsageSetForVolumeType(volumeType);
    std::set<StreamUsage> overlapSet;
    std::set_intersection(streamUsages.begin(), streamUsages.end(), tempSet.begin(), tempSet.end(),
        std::inserter(overlapSet, overlapSet.begin()));
    return overlapSet;
}

std::vector<AudioVolumeType> VolumeUtils::GetSupportedAudioVolumeTypes()
{
    std::vector<AudioVolumeType> result = {};
    std::unordered_set<AudioVolumeType> volumeTypeSet = audioVolumeTypeSet_;
    for (auto it = volumeTypeSet.begin(); it != volumeTypeSet.end(); ++it) {
        result.push_back(*it);
    }
    return result;
}

std::vector<StreamUsage> VolumeUtils::GetStreamUsagesByVolumeType(AudioVolumeType audioVolumeType)
{
    std::vector<StreamUsage> result = {};
    std::set<StreamUsage> streamUsageSet = GetStreamUsageSetForVolumeType(audioVolumeType);
    for (auto it = streamUsageSet.begin(); it != streamUsageSet.end(); ++it) {
        result.push_back(*it);
    }
    return result;
}

std::set<StreamUsage>& VolumeUtils::GetStreamUsageSetForVolumeType(AudioVolumeType volumeType)
{
    static std::set<StreamUsage> emptySet;
    if (isPCVolumeEnable_) {
        return pcVolumeToStreamUsageMap_.count(volumeType) ? pcVolumeToStreamUsageMap_[volumeType] : emptySet;
    } else {
        return defaultVolumeToStreamUsageMap_.count(volumeType) ? defaultVolumeToStreamUsageMap_[volumeType] : emptySet;
    }
}

int32_t VolumeUtils::VolumeDegreeToLevel(int32_t degree, int32_t maxLevel)
{
    CHECK_AND_RETURN_RET_LOG(degree >= VOLUME_DEGREE_ZERO && degree <= MAX_VOLUME_DEGREE && maxLevel > 0,
        -1, "invalid input, degree:%{public}d, maxLevel:%{public}d", degree, maxLevel);

    if (degree == VOLUME_DEGREE_ZERO) {
        return VOLUME_LEVEL_ZERO;
    }

    if (degree == MAX_VOLUME_DEGREE) {
        return maxLevel;
    }

    int32_t level = (degree - 1) * (maxLevel - 1) / (MAX_VOLUME_DEGREE - VOLUME_DEGREE_ZERO - 1) + 1;
    return level;
}

int32_t VolumeUtils::VolumeLevelToDegree(int32_t level, int32_t maxLevel)
{
    int32_t divider = maxLevel - 1;
    CHECK_AND_RETURN_RET_LOG(level >= VOLUME_LEVEL_ZERO && level <= maxLevel && divider > 0,
        -1, "invalid input, level:%{public}d, maxLevel:%{public}d", level, maxLevel);

    if (level == VOLUME_LEVEL_ZERO) {
        return VOLUME_DEGREE_ZERO;
    }

    if (level == maxLevel) {
        return MAX_VOLUME_DEGREE;
    }

    int32_t degree = ((level * 2 - 1) * (MAX_VOLUME_DEGREE - VOLUME_DEGREE_ZERO - 1) / divider + 1) / 2;
    return degree;
}

void VolumeUtils::InitLevelToDegreeMap(int32_t maxLevel)
{
    for (int32_t i = VOLUME_DEGREE_ZERO; i <= MAX_VOLUME_DEGREE; i++) {
        int32_t level = VolumeDegreeToLevel(i, maxLevel);
        levelToDegreeMap_[maxLevel][level] = i;
    }
}

int32_t VolumeUtils::GetVolumeLevelMaxDegree(int32_t level, int32_t maxLevel)
{
    int32_t divider = maxLevel - 1;
    CHECK_AND_RETURN_RET_LOG(level >= VOLUME_LEVEL_ZERO && level <= maxLevel && divider > 0,
        -1, "invalid input, level:%{public}d, maxLevel:%{public}d", level, maxLevel);
    if (level == VOLUME_LEVEL_ZERO) {
        return VOLUME_DEGREE_ZERO;
    }
    if (level == maxLevel) {
        return MAX_VOLUME_DEGREE;
    }
    if (levelToDegreeMap_.find(maxLevel) == levelToDegreeMap_.end()) {
        InitLevelToDegreeMap(maxLevel);
    }
    auto innerMap = levelToDegreeMap_[maxLevel];
    CHECK_AND_RETURN_RET_LOG(innerMap.find(level) != innerMap.end(),
        -1, "level degree map not init");
    return innerMap[level];
}

VolumeScale VolumeScale::Refresh()
{
    if (volumeDegree_ == -1) {
        volumeDegree_ = VolumeUtils::VolumeLevelToDegree(volumeLevel_, maxVolumeLevel_);
    }

    if (volumeDegree_ == -1) {
        AUDIO_WARNING_LOG("refresh failed, maxVolumeLevel: %{public}d", maxVolumeLevel_);
    }
    return *this;
}

VolumeScale VolumeScale::ResetVolumeDegree()
{
    AUDIO_INFO_LOG("Reset the volume degree to the baseline value of the volume level %{public}d", volumeLevel_);
    volumeDegree_ = VolumeUtils::VolumeLevelToDegree(volumeLevel_, maxVolumeLevel_);
    return *this;
}

VolumeScale VolumeScale::SetVolumeLevelAndResetDegree(int32_t volumeLevel)
{
    AUDIO_INFO_LOG("Set volume level to %{public}d and reset volume degree to the baseline value", volumeLevel);
    volumeLevel_ = volumeLevel;
    volumeDegree_ = VolumeUtils::VolumeLevelToDegree(volumeLevel_, maxVolumeLevel_);
    return *this;
}

VolumeScale VolumeScale::Adjust(const VolumeScale &volume)
{
    if (volume.volumeLevel_ == volumeLevel_) {
        int32_t oldVal = volumeDegree_;
        if (valueType_ == VolumeKeyType::LEVEL) {
            volumeDegree_ = volume.volumeDegree_;
        }

        if (volumeDegree_ != oldVal) {
            AUDIO_WARNING_LOG("volumeDegree, old: %{public}d, new: %{public}d", oldVal, volumeDegree_);
        }
    }
    Refresh();
    return *this;
}

VolumeScale VolumeScale::Update(const VolumeScale &volume)
{
    if (volume.VolumeLevel() != volumeLevel_) {
        *this = volume;
    }
    Refresh();
    return *this;
}

bool VolumeScale::IsVolumeDegreeValid(int32_t min, int32_t max)
{
    CHECK_AND_RETURN_RET_LOG((volumeDegree_ == -1) || (volumeDegree_ >= min && volumeDegree_ <= max), false,
        "volumeDegree:%{public}d not in range:[%{public}d, %{public}d]",
        volumeDegree_, min, max);
    return true;
}

StreamUsage AudioTypeUtils::GetStreamUsageByStreamType(AudioStreamType streamType)
{
    auto it = STREAMTYPE_TO_USAGE_MAP.find(streamType);
    if (it != STREAMTYPE_TO_USAGE_MAP.end()) {
        return it->second;
    }
    return STREAM_USAGE_UNKNOWN;
}

HdiAdapterType AudioTypeUtils::HalNameToType(std::string halName)
{
    auto it = HALNAME_TO_TYPE_MAP.find(halName);
    if (it != HALNAME_TO_TYPE_MAP.end()) {
        return it->second;
    }
    return HDI_ADAPTER_TYPE_PRIMARY;
}

std::string GetEncryptStr(const std::string &src)
{
    if (src.empty()) {
        return std::string("");
    }

    size_t strLen = src.length();
    std::string dst;

    if (strLen < MIN_LEN) {
        // src: abcdef
        // dst: *bcdef
        dst = '*' + src.substr(FIRST_CHAR, strLen - FIRST_CHAR);
    } else {
        // src: 00:00:00:00:00:00
        // dst: 00**********00:00
        dst = src.substr(0, HEAD_STR_LEN);
        std::string tempStr(strLen - HEAD_STR_LEN - TAIL_STR_LEN, '*');
        dst += tempStr;
        dst += src.substr(strLen - TAIL_STR_LEN, TAIL_STR_LEN);
    }

    return dst;
}

std::string Hide(const std::string &str)
{
    CHECK_AND_RETURN_RET(str.length() >= VISIBLE_LEN + VISIBLE_LEN, "*");
    return str.substr(0, VISIBLE_LEN) + "*" + str.substr(str.length() - VISIBLE_LEN);
}

std::string ConvertNetworkId(const std::string &networkId)
{
    if (!networkId.empty() && networkId != LOCAL_NETWORK_ID) {
        return REMOTE_NETWORK_ID;
    }

    return networkId;
}

uint32_t GenerateUniqueID(AudioHdiUniqueIDBase base, uint32_t offset)
{
    return base + offset * UNIQUE_ID_INTERVAL;
}

AudioDump& AudioDump::GetInstance()
{
    static AudioDump mAudioDump;
    return mAudioDump;
}

void AudioDump::SetVersionType(const std::string& versionType)
{
    versionType_ = versionType;
}

std::string AudioDump::GetVersionType()
{
    return versionType_;
}

bool IsHWDecodingType(AudioEncodingType type)
{
    return HWDECODING_TYPES.count(type);
}

const std::unordered_map<AudioEncodingType, std::string> g_EncodingTypeToStringMap = {
    {ENCODING_PCM, "PCM"},
    {ENCODING_AUDIOVIVID, "AUDIOVIVID"},
    {ENCODING_EAC3, "EAC3"},
    {ENCODING_AC3, "AC3"},
    {ENCODING_TRUE_HD, "TRUE_HD"},
    {ENCODING_DTS_HD, "DTS_HD"},
    {ENCODING_DTS_X, "DTS_X"},
    {ENCODING_AUDIOVIVID_DIRECT, "AUDIOVIVID_DIRECT"},
    {ENCODING_AUDIOVIVID_3DA_DIRECT, "AUDIOVIVID_3DA_DIRECT"}
};

std::string EncodingTypeStr(AudioEncodingType type)
{
    auto it = g_EncodingTypeToStringMap.find(type);
    if (it == g_EncodingTypeToStringMap.end()) {
        return "INVALID";
    }
    return it->second;
}

int32_t CheckSupportedParams(const AudioStreamInfo &info)
{
    CHECK_AND_RETURN_RET_LOG(!NotContain(AUDIO_SUPPORTED_SAMPLING_RATES, info.samplingRate),
        ERR_INVALID_PARAM, "samplingRate not supported");
    CHECK_AND_RETURN_RET_LOG(!NotContain(RENDERER_SUPPORTED_CHANNELS, info.channels),
        ERR_INVALID_PARAM, "channels not supported");
    CHECK_AND_RETURN_RET_LOG(!NotContain(AUDIO_SUPPORTED_FORMATS, info.format),
        ERR_INVALID_PARAM, "format not supported");
    CHECK_AND_RETURN_RET_LOG(!NotContain(AUDIO_SUPPORTED_ENCODING_TYPES, info.encoding),
        ERR_INVALID_PARAM, "encoding not supported");
    CHECK_AND_RETURN_RET_LOG(!NotContain(RENDERER_SUPPORTED_CHANNELLAYOUTS, info.channelLayout),
        ERR_INVALID_PARAM, "channelLayout not supported");
    return SUCCESS;
}

std::vector<std::map<AudioInterrupt, int32_t>> ToIpcInterrupts(
    const std::list<std::pair<AudioInterrupt, AudioFocuState>> &from)
{
    std::vector<std::map<AudioInterrupt, int32_t>> ipcInterrupts;
    for (const auto &pair : from) {
        std::map<AudioInterrupt, int32_t> mapEntry;
        mapEntry[pair.first] = static_cast<int32_t>(pair.second);
        ipcInterrupts.push_back(mapEntry);
    }
    return ipcInterrupts;
}

std::list<std::pair<AudioInterrupt, AudioFocuState>> FromIpcInterrupts(
    const std::vector<std::map<AudioInterrupt, int32_t>> &from)
{
    std::list<std::pair<AudioInterrupt, AudioFocuState>> interrupts;
    for (const auto &map : from) {
        for (const auto &entry : map) {
            interrupts.push_back(std::make_pair(entry.first, static_cast<AudioFocuState>(entry.second)));
        }
    }
    return interrupts;
}

uint32_t PcmFormatToBits(AudioSampleFormat format)
{
    switch (format) {
        case SAMPLE_U8:
            return 1; // 1 byte
        case SAMPLE_S16LE:
            return 2; // 2 byte
        case SAMPLE_S24LE:
            return 3; // 3 byte
        case SAMPLE_S32LE:
            return 4; // 4 byte
        case SAMPLE_F32LE:
            return 4; // 4 byte
        default:
            return 2; // 2 byte
    }
}

static std::unordered_map<AudioSampleFormat, std::string> g_formatToStringMap = {
    {SAMPLE_U8, "s8"},
    {SAMPLE_S16LE, "s16le"},
    {SAMPLE_S24LE, "s24le"},
    {SAMPLE_S32LE, "s32le"},
    {SAMPLE_F32LE, "f32le"}
};
std::string ConvertToStringForFormat(const AudioSampleFormat format)
{
    std::string formatStr = "s16le";
    auto it = g_formatToStringMap.find(format);
    if (it != g_formatToStringMap.end()) {
        formatStr = it->second;
    }
    return formatStr;
}

std::string ConvertToStringForSampleRate(const AudioSamplingRate sampleRate)
{
    return std::to_string(static_cast<int32_t>(sampleRate));
}

std::string ConvertToStringForChannel(const AudioChannel channel)
{
    return std::to_string(static_cast<int32_t>(channel));
}

uint8_t* ReallocVectorBufferAndClear(std::vector<uint8_t> &buffer, const size_t bufLength)
{
    buffer.assign(bufLength, 0);
    return buffer.data();
}

std::string GenerateAppsUidStr(std::unordered_set<int32_t> appsUid)
{
    std::ostringstream uidStream;
    uidStream << "AppInfo=";
    bool first = true;
    for (const auto &uid : appsUid) {
        if (!first) {
            uidStream << ";";
        }
        uidStream << "0," << uid;
        first = false;
    }
    return uidStream.str();
}

std::string GenerateAppsTokenIdStr(std::unordered_set<uint32_t> appsTokenId)
{
    std::ostringstream tokenIdStream;
    tokenIdStream << "TokenIds=";
    bool first = true;
    for (const auto &tokenId : appsTokenId) {
        tokenIdStream << (first ? "" : ";");
        tokenIdStream << tokenId;
        first = false;
    }
    return tokenIdStream.str();
}

float ConvertAudioRenderRateToSpeed(AudioRendererRate renderRate)
{
    float speed = 1.0f;
    switch (renderRate) {
        case RENDER_RATE_NORMAL:
            speed = 1.0f;
            break;
        case RENDER_RATE_DOUBLE:
            speed = 2.0f;
            break;
        case RENDER_RATE_HALF:
            speed = 0.5f;
            break;
        default:
            speed = 1.0f;
    }
    return speed;
}

uint64_t HexStrToNum(const std::string &str)
{
    char *endPtr = nullptr;
    uint64_t num = std::strtoull(str.c_str(), &endPtr, BASE_HEX);
    return endPtr != nullptr && *endPtr == '\0' ? num : 0;
}

void BindBigAndMidCore()
{
    cpu_set_t cpuSet;
    CPU_ZERO(&cpuSet);
    int32_t cpuNum = sysconf(_SC_NPROCESSORS_CONF);
    for (int32_t i = MID_CORE_START; i < cpuNum; i++) {
        CPU_SET(i, &cpuSet); // bind to mid cores
    }
    int32_t result = sched_setaffinity(gettid(), sizeof(cpu_set_t), &cpuSet);
    CHECK_AND_CALL_FUNC_RETURN(result == 0,
        HILOG_COMM_ERROR("[BindBigAndMidCore] Set target cpu failed, ret: %{public}d", result));
    AUDIO_INFO_LOG("Bind pid: %{public}d, tid: %{public}d to big and mid cores success", getpid(), gettid());
}

bool IsUltraFastStreamAndRoute(uint8_t ultraFastFlag)
{
    return ultraFastFlag == (ULTRA_REQUESTED | ULTRA_IMPLEMENTED);
}
} // namespace AudioStandard
} // namespace OHOS

#ifdef __cplusplus
extern "C" {
#endif

struct CTrace {
    explicit CTrace(const char *traceName) : trace(OHOS::AudioStandard::Trace(traceName)) {};
    OHOS::AudioStandard::Trace trace;
};

CTrace *GetAndStart(const char *traceName)
{
    std::unique_ptr<CTrace> cTrace = std::make_unique<CTrace>(traceName);

    return cTrace.release();
}

void EndCTrace(CTrace *cTrace)
{
    if (cTrace != nullptr) {
        cTrace->trace.End();
    }
}

void CTraceCount(const char *traceName, int64_t count)
{
    OHOS::AudioStandard::Trace::Count(traceName, count);
}

void CallEndAndClear(CTrace **cTrace)
{
    if (cTrace != nullptr && *cTrace != nullptr) {
        EndCTrace(*cTrace);
        delete *cTrace;
        *cTrace = nullptr;
    }
}

bool IsInnerCapSinkName(char *pattern)
{
    size_t patternLength = strlen(pattern);
    if (patternLength > MAX_MEM_MALLOC_SIZE) {
        return false;
    }
    char *patternCopy = (char*)malloc(patternLength + 1);
    if (patternCopy == nullptr) {
        return false;
    }
    if (strcpy_s(patternCopy, patternLength + 1, pattern) != 0) {
        free(patternCopy);
        return false;
    }
    char *firstPart = strtok(patternCopy, "_");
    bool result = false;
    if (firstPart != nullptr && strcmp(firstPart, SINK_NAME_INNER_CAPTURER) == 0) {
        result = true;
    }
    free(patternCopy);
    return result;
}

#ifdef __cplusplus
}
#endif
