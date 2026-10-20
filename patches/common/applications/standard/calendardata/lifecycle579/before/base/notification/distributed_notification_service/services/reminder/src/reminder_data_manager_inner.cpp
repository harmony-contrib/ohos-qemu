/*
 * Copyright (c) 2024-2025 Huawei Device Co., Ltd.
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

#include "reminder_data_manager.h"

#include "ans_log_wrapper.h"
#include "ans_convert_enum.h"
#include "ans_trace_wrapper.h"

#include "reminder_utils.h"
#include "reminder_request_calendar.h"
#include "reminder_datashare_helper.h"
#include "reminder_calendar_share_table.h"

#include "ipc_skeleton.h"
#include "notification_helper.h"
#include "data_share_permission.h"
#include "ability_manager_client.h"
#include "in_process_call_wrapper.h"
#ifdef HAS_HISYSEVENT_PART
#include <sys/statfs.h>
#include "hisysevent.h"
#include "directory_ex.h"
#endif
#ifdef PLAYER_FRAMEWORK_ENABLE
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include "vibrator_agent.h"
#endif

namespace OHOS {
namespace Notification {
namespace {
constexpr int32_t ALL_SA_READY_FLAG = 2;  // bundle service and ability service ready.
// The maximum number of applications that can be displayed at a same time
constexpr int32_t ONE_HAP_MAX_NUMBER_SHOW_AT_SAME_TIME = 10;
// The maximum number of applications that can be displayed
constexpr int32_t ONE_HAP_MAX_NUMBER_SHOW_AT_ONCE = 30;
// The maximum number of system that can be displayed at a time
constexpr int32_t TOTAL_MAX_NUMBER_SHOW_AT_ONCE = 500;
// The maximun number of system that can be start extension count
constexpr int32_t TOTAL_MAX_NUMBER_START_EXTENSION = 100;
constexpr int32_t CONNECT_EXTENSION_INTERVAL = 100;
static constexpr uint64_t VIBRATION_PERIOD = (uint64_t)1000 * 1000;  // 1000us
static constexpr int32_t CONNECT_EXTENSION_MAX_RETRY_TIMES = 3;
}

static uint64_t GetRemainPartitionSize(const std::string& partitionName)
{
#ifdef HAS_HISYSEVENT_PART
    struct statfs stat;
    if (statfs(partitionName.c_str(), &stat) != 0) {
        return -1;
    }
    uint64_t blockSize = stat.f_bsize;
    uint64_t freeSize = stat.f_bfree * blockSize;
    constexpr double units = 1024.0;
    return freeSize/(units * units);
#else
    return 0;
#endif
}

static std::vector<uint64_t> GetFileOrFolderSize(const std::vector<std::string>& paths)
{
    std::vector<uint64_t> folderSize;
#ifdef HAS_HISYSEVENT_PART
    for (auto path : paths) {
        folderSize.emplace_back(OHOS::GetFolderSize(path));
    }
#endif
    return folderSize;
}

bool ReminderDataManager::IsSystemReady()
{
    return saReadyFlag_ >= ALL_SA_READY_FLAG;
}

bool ReminderDataManager::IsActionButtonDataShareValid(const sptr<ReminderRequest>& reminder,
    const uint32_t callerTokenId)
{
    auto actionButtonMap = reminder->GetActionButtons();
    for (auto it = actionButtonMap.begin(); it != actionButtonMap.end(); ++it) {
        ReminderRequest::ActionButtonInfo& buttonInfo = it->second;
        if (buttonInfo.dataShareUpdate == nullptr) {
            continue;
        }
        if (buttonInfo.dataShareUpdate->uri.empty()) {
            continue;
        }
        Uri uri(buttonInfo.dataShareUpdate->uri);
        auto ret = DataShare::DataSharePermission::VerifyPermission(callerTokenId, uri, false);
        if (ret != DataShare::E_OK) {
            ANSR_LOGE("publish failed, DataSharePermission::VerifyPermission return error[%{public}d],",
                static_cast<int32_t>(ret));
            return false;
        }
    }
    return true;
}

void ReminderDataManager::HandleAutoDeleteReminder(const int32_t notificationId, const int32_t uid,
    const int64_t autoDeletedTime)
{
    ANSR_LOGD("called");
    std::vector<sptr<ReminderRequest>> showedReminder;
    {
        std::lock_guard<std::mutex> lock(ReminderDataManager::SHOW_MUTEX);
        showedReminder = showedReminderVector_;
    }
    for (auto reminder : showedReminder) {
        if (reminder == nullptr) {
            continue;
        }

        if (reminder->GetUid() != uid || notificationId != reminder->GetNotificationId() ||
            reminder->GetAutoDeletedTime() != autoDeletedTime) {
            continue;
        }
        CloseReminder(reminder, true);
        UpdateAppDatabase(reminder, ReminderRequest::ActionButtonType::CLOSE);
        CheckNeedNotifyStatus(reminder, ReminderRequest::ActionButtonType::CLOSE);
    }
    StartRecentReminder();
}

void ReminderDataManager::OnBundleMgrServiceStart()
{
    saReadyFlag_.fetch_add(1);
}

void ReminderDataManager::OnAbilityMgrServiceStart()
{
    saReadyFlag_.fetch_add(1);
}

bool ReminderDataManager::GetCustomRingFileDesc(const sptr<ReminderRequest>& reminder,
    Global::Resource::ResourceManager::RawFileDescriptor& desc)
{
    // obtains the resource manager
    soundResource_ = GetResourceMgr(reminder->GetBundleName(), reminder->GetUid());
    if (soundResource_ == nullptr) {
        ANSR_LOGE("null soundResource");
        return false;
    }
    auto result = soundResource_->GetRawFileDescriptor(reminder->GetCustomRingUri(), desc);
    if (result != Global::Resource::SUCCESS) {
        ANSR_LOGE("GetRawFileDescriptor fail[%{public}d].", static_cast<int32_t>(result));
        return false;
    }
    return true;
}

void ReminderDataManager::CloseCustomRingFileDesc(const int32_t reminderId, const std::string& customRingUri)
{
    if (soundResource_ == nullptr) {
        ANSR_LOGE("null soundResource");
        return;
    }
    auto result = soundResource_->CloseRawFileDescriptor(customRingUri);
    if (result != Global::Resource::SUCCESS) {
        ANSR_LOGE("CloseRawFileDescriptor fail[%{public}d]", static_cast<int32_t>(result));
    }
    ANSR_LOGI("reminderId:[%{public}d]", reminderId);
    soundResource_ = nullptr;
}

void ReminderDataManager::ReportSysEvent(const sptr<ReminderRequest>& reminder)
{
#ifdef HAS_HISYSEVENT_PART
    std::string event = "ALARM_TRIGGER";
    std::string bundleName = reminder->GetBundleName();
    int32_t uid = reminder->GetUid();
    int32_t type = static_cast<int32_t>(reminder->GetReminderType());
    int32_t repeat = static_cast<int32_t>(reminder->IsRepeat());
    uint64_t triggerTime = reminder->GetTriggerTimeInMilli();
    int32_t ringTime = static_cast<int32_t>(reminder->GetRingDuration());
    HiSysEventWrite(HiviewDFX::HiSysEvent::Domain::NOTIFICATION, event, HiviewDFX::HiSysEvent::EventType::STATISTIC,
        "UID", uid, "NAME", bundleName, "TYPE", type, "REPEAT", repeat, "TRIGGER_TIME", triggerTime,
        "RING_TIME", ringTime);
#endif
}

bool ReminderDataManager::CheckShowLimit(ShowLimit& limits, sptr<ReminderRequest>& reminder)
{
    if (limits.totalCount > TOTAL_MAX_NUMBER_SHOW_AT_ONCE) {
        ANSR_LOGE("The max number of displays that can be displayed at a time has been reached.");
        return false;
    }
    int32_t uid = reminder->GetUid();
    std::string key = std::to_string(uid) + "_" + std::to_string(reminder->GetTriggerTimeInMilli());
    auto iter = limits.timeLimits.find(key);
    if (iter == limits.timeLimits.end()) {
        limits.timeLimits.emplace(key, 1);
    } else {
        if (iter->second > ONE_HAP_MAX_NUMBER_SHOW_AT_SAME_TIME) {
            ANSR_LOGE("The max number of displays that can be shown at the same time in "
                "a single app[%{public}s] has been reached", reminder->GetBundleName().c_str());
            return false;
        }
        ++iter->second;
    }
    auto bundleIter = limits.bundleLimits.find(uid);
    if (bundleIter == limits.bundleLimits.end()) {
        limits.bundleLimits.emplace(uid, 1);
    } else {
        if (bundleIter->second > ONE_HAP_MAX_NUMBER_SHOW_AT_ONCE) {
            ANSR_LOGE("The max number of displays that can be displayed in a single app[%{public}s] has been reached",
                reminder->GetBundleName().c_str());
            return false;
        }
        ++bundleIter->second;
    }
    ++limits.totalCount;
    return true;
}

void ReminderDataManager::OnDataShareInsertOrDelete()
{
    LoadShareReminders();
    std::vector<sptr<ReminderRequest>> immediatelyReminders;
    std::vector<sptr<ReminderRequest>> extensionReminders;
    CheckReminderTime(immediatelyReminders, extensionReminders);
    ShowLimit limits;
    HandleImmediatelyShow(immediatelyReminders, limits, false, false);
    StartRecentReminder();
}

void ReminderDataManager::OnDataShareUpdate(const std::map<std::string, sptr<ReminderRequest>>& reminders)
{
    UpdateShareReminders(reminders);
}

void ReminderDataManager::UpdateShareReminders(const std::map<std::string, sptr<ReminderRequest>>& reminders)
{
    std::lock_guard<std::mutex> locker(ReminderDataManager::MUTEX);
    for (auto it = reminderVector_.begin(); it != reminderVector_.end(); ++it) {
        if (!(*it)->IsShare() || (*it)->GetReminderType() != ReminderRequest::ReminderType::CALENDAR) {
            continue;
        }
        int32_t reminderId = (*it)->GetReminderId();
        std::string identifier = (*it)->GetIdentifier();
        auto iter = reminders.find(identifier);
        if (iter == reminders.end()) {
            continue;
        }
        ReminderRequestCalendar* calendar = static_cast<ReminderRequestCalendar*>((*it).GetRefPtr());
        calendar->Copy(iter->second);
        if ((*it)->IsShowing()) {
            ShowReminder((*it), false, false, false, true);
        }
    }
}

void ReminderDataManager::AsyncStartExtensionAbility(const sptr<ReminderRequest> &reminder, int32_t times,
    const int8_t type, int32_t& count)
{
    auto manager = ReminderDataManager::GetInstance();
    if (manager == nullptr) {
        ANSR_LOGE("null manager");
        return;
    }
    if (!manager->IsSystemReady()) {
        ANSR_LOGE("bundle service or ability service not ready.");
        return;
    }
    if (!reminder->IsSystemApp()) {
        ANSR_LOGE("Start extension ability failed, is not system app");
        return;
    }
    if (count > TOTAL_MAX_NUMBER_START_EXTENSION) {
        ANSR_LOGE("The maximum number of start extension has been reached.");
        return;
    }
    ++count;
    times--;
    bool ret = ReminderDataManager::StartExtensionAbility(reminder, type);
    if (!ret && times > 0 && serviceQueue_ != nullptr) {
        ANSR_LOGD("StartExtensionAbilty failed, reminder times: %{public}d", times);
        ffrt::task_attr taskAttr;
        taskAttr.delay(CONNECT_EXTENSION_INTERVAL);
        auto callback = [reminder, times, type]() {
            int32_t count = 0;
            ReminderDataManager::AsyncStartExtensionAbility(reminder, times, type, count);
        };
        serviceQueue_->submit(callback, taskAttr);
    }
}

void ReminderDataManager::UpdateReminderFromDb(const std::vector<sptr<ReminderRequest>>& remindersFromDb)
{
    std::map<int32_t, sptr<ReminderRequest>> reminders;
    for (const auto& reminder : remindersFromDb) {
        reminders[reminder->GetReminderId()] = reminder;
    }
    // Only alerts that do not exist in memory are processed
    for (const auto& reminder : reminderVector_) {
        if (reminder->IsShare()) {
            continue;
        }
        int32_t reminderId = reminder->GetReminderId();
        auto iter = reminders.find(reminderId);
        if (iter != reminders.end()) {
            reminders.erase(iter);
        }
    }
    // new reminder
    for (auto& each : reminders) {
        reminderVector_.push_back(each.second);
    }
}

ErrCode ReminderDataManager::UpdateReminder(const sptr<ReminderRequest>& reminder, const int32_t callingUid)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    sptr<ReminderRequest> reminderOld = FindReminderRequestLocked(reminder->GetReminderId(), false);
    bool existInMemory = true;
    if (nullptr != reminderOld) {
        if (!CheckIsSameApp(reminderOld, callingUid)) {
            ANSR_LOGW("Not find the reminder due to not match");
            return ERR_REMINDER_NOT_EXIST;
        }
        if (reminderOld->IsShowing()) {
            ANSR_LOGW("Reminder already showing, update reminder failed.");
            return ERR_REMINDER_NOT_EXIST;
        }
    } else {
        existInMemory = false;
        std::lock_guard<std::mutex> lock(ReminderDataManager::MUTEX);
        if (!store_->IsReminderExist(reminder->GetReminderId(), reminder->GetCreatorUid())) {
            ANSR_LOGW("Reminder not find, update reminder failed.");
            return ERR_REMINDER_NOT_EXIST;
        }
    }
    uint32_t callerTokenId = IPCSkeleton::GetCallingTokenID();
    if (callerTokenId == 0) {
        ANSR_LOGE("pushlish failed, callerTokenId is 0");
        return ERR_REMINDER_CALLER_TOKEN_INVALID;
    }
    if (!IsActionButtonDataShareValid(reminder, callerTokenId)) {
        return ERR_REMINDER_DATA_SHARE_PERMISSION_DENIED;
    }

    UpdateAndSaveReminderLocked(reminder, existInMemory);
    queue_->submit([this, reminder]() {
        StartRecentReminder();
    });
    return ERR_OK;
}

ErrCode ReminderDataManager::CancelReminderOnDisplay(const int32_t reminderId, const int32_t callingUid)
{
    ANSR_LOGI("cancel showing reminder id: %{public}d", reminderId);
    sptr<ReminderRequest> target;
    {
        std::lock_guard<std::mutex> locker(ReminderDataManager::SHOW_MUTEX);
        for (auto it = showedReminderVector_.begin(); it != showedReminderVector_.end(); ++it) {
            sptr<ReminderRequest> reminder = (*it);
            if (reminder->IsShare()) {
                continue;
            }
            if (reminder->GetReminderId() != reminderId) {
                continue;
            }
            if (reminder->GetCreatorUid() != callingUid) {
                continue;
            }
            target = reminder;
            showedReminderVector_.erase(it);
            break;
        }
    }
    if (target == nullptr) {
        return ERR_REMINDER_NOT_EXIST;
    }
    std::lock_guard<std::mutex> locker(cancelMutex_);
    if (activeReminderId_ == reminderId) {
        std::lock_guard<std::mutex> locker(ReminderDataManager::MUTEX);
        StopTimerLocked(TimerType::TRIGGER_TIMER);
    }
    if (alertingReminderId_ == reminderId) {
        StopSoundAndVibrationLocked(target);
        StopTimerLocked(TimerType::ALERTING_TIMER);
    }
    CancelNotification(target);
    target->OnStop();
    StartRecentReminder();
    return ERR_OK;
}

ErrCode ReminderDataManager::RegisterReminderState(const int32_t uid, const sptr<IRemoteObject>& object)
{
    if (notifyManager_ == nullptr) {
        return ERR_NO_INIT;
    }
    notifyManager_->RegisterNotify(uid, object);
    queue_->submit([uid]() {
        ReminderDataManager::GetInstance()->NotifyReminderState(uid);
    });
    return ERR_OK;
}

ErrCode ReminderDataManager::UnRegisterReminderState(const int32_t uid)
{
    if (notifyManager_ == nullptr) {
        return ERR_NO_INIT;
    }
    notifyManager_->UnRegisterNotify(uid);
    return ERR_OK;
}

void ReminderDataManager::UpdateAndSaveReminderLocked(const sptr<ReminderRequest>& reminder, const bool isInMemory)
{
    std::lock_guard<std::mutex> lock(ReminderDataManager::MUTEX);
    if (reminder->GetTriggerTimeInMilli() == ReminderRequest::INVALID_LONG_LONG_VALUE) {
        ANSR_LOGW("now publish reminder is expired. reminder is =%{public}s", reminder->Dump().c_str());
        reminder->SetExpired(true);
    }
    if (isInMemory) {
        for (auto it = reminderVector_.begin(); it != reminderVector_.end(); ++it) {
            if (reminder->GetReminderId() == (*it)->GetReminderId() && !(*it)->IsShare()) {
                *it = reminder;
                break;
            }
        }
    } else {
        reminderVector_.push_back(reminder);
    }
    store_->UpdateOrInsert(reminder);
}

void ReminderDataManager::SetActiveReminder(const sptr<ReminderRequest> &reminder)
{
    if (reminder == nullptr) {
        // activeReminder_ should not be set with null as it point to actual object.
        activeReminderId_ = -1;
        activeTriggerTime_ = 0;
    } else {
        activeReminderId_ = reminder->GetReminderId();
        activeTriggerTime_ = reminder->GetTriggerTimeInMilli();
        std::lock_guard<std::mutex> locker(ReminderDataManager::ACTIVE_MUTEX);
        activeReminder_ = reminder;
    }
    ANSR_LOGD("Set activeReminderId=%{public}d", activeReminderId_.load());
}

void ReminderDataManager::SetAlertingReminder(const sptr<ReminderRequest> &reminder)
{
    if (reminder == nullptr) {
        // alertingReminder_ should not be set with null as it point to actual object.
        alertingReminderId_ = -1;
        alertingIdIsShared_ = false;
    } else {
        alertingReminderId_ = reminder->GetReminderId();
        alertingIdIsShared_ = reminder->IsShare();
        alertingReminder_ = reminder;
    }
}

ErrCode ReminderDataManager::CancelReminderToDb(const int32_t reminderId, const int32_t callingUid)
{
    if (store_ == nullptr) {
        ANSR_LOGE("null store");
        return ERR_REMINDER_NOT_EXIST;
    }
    std::lock_guard<std::mutex> lock(ReminderDataManager::MUTEX);
    if (!store_->IsReminderExist(reminderId, callingUid)) {
        ANSR_LOGE("Not find reminder[%{public}d] in db.", reminderId);
        return ERR_REMINDER_NOT_EXIST;
    }
    store_->Delete(reminderId);
    return ERR_OK;
}

bool ReminderDataManager::IsAllowedNotify(const sptr<ReminderRequest> &reminder) const
{
    if (reminder == nullptr) {
        return false;
    }
    bool isAllowed = false;
    NotificationBundleOption bundleOption(reminder->GetBundleName(), reminder->GetUid());
    ErrCode errCode = IN_PROCESS_CALL(NotificationHelper::IsAllowedNotify(bundleOption, isAllowed));
    if (errCode != ERR_OK) {
        ANSR_LOGE("Failed to call IsAllowedNotify, errCode=%{public}d", errCode);
        return false;
    }
    return isAllowed;
}

void ReminderDataManager::ReportTimerEvent(const int64_t targetTime, const bool isSysTimeChanged)
{
#ifdef HAS_HISYSEVENT_PART
    if (targetTime == 0) {
        return;
    }
    constexpr int64_t deviation = 1000 * 60;  // 1min
    int64_t now = GetCurrentTime();
    if ((now - targetTime) <= deviation) {
        return;
    }
    std::string event = "REMINDER_TIMER_ERROR";
    uint8_t errorCode = isSysTimeChanged ? 0 : 1;
    HiSysEventWrite(HiviewDFX::HiSysEvent::Domain::NOTIFICATION, event, HiviewDFX::HiSysEvent::EventType::STATISTIC,
        "TARGET_TIME", targetTime, "TRIGGER_TIME", now, "ERROR_CODE", errorCode);
#endif
}

void ReminderDataManager::ReportUserDataSizeEvent()
{
#ifdef HAS_HISYSEVENT_PART
    std::vector<std::string> paths = {
        "/data/service/el1/public/notification/"
    };
    uint64_t remainPartitionSize = GetRemainPartitionSize("/data");
    std::vector<uint64_t> folderSize = GetFileOrFolderSize(paths);
    HiSysEventWrite(HiviewDFX::HiSysEvent::Domain::FILEMANAGEMENT, "USER_DATA_SIZE",
        HiviewDFX::HiSysEvent::EventType::STATISTIC,
        "COMPONENT_NAME", "resource_schedule_service",
        "PARTITION_NAME", "/data",
        "REMAIN_PARTITION_SIZE", remainPartitionSize,
        "FILE_OR_FOLDER_PATH", paths,
        "FILE_OR_FOLDER_SIZE", folderSize);
#endif
}

bool ReminderDataManager::IsInDoNotDisturbMode(const int32_t userId)
{
#ifdef PLAYER_FRAMEWORK_ENABLE
    constexpr const char* USER_SETINGS_DATA_SECURE_URI =
        "datashare:///com.ohos.settingsdata/entry/settingsdata/USER_SETTINGSDATA_SECURE_";
    constexpr const char* FOCUS_MODE_ENABLE_URI = "?Proxy=true&key=focus_mode_enable";
    constexpr const char* FOCUS_MODE_ENABLE = "focus_mode_enable";
    std::string uriStr = USER_SETINGS_DATA_SECURE_URI + std::to_string(userId) + FOCUS_MODE_ENABLE_URI;
    Uri enableUri(uriStr);
    std::string enable;
    bool ret = ReminderDataShareHelper::GetInstance().Query(enableUri, FOCUS_MODE_ENABLE, enable);
    if (!ret) {
        ANSR_LOGE("Query focus mode enable failed.");
        return true;
    }
    if (enable.compare("1") == 0) {
        ANSR_LOGI("Currently not is do not disurb mode.");
        return true;
    }
#endif
    return false;
}

bool ReminderDataManager::CheckSoundConfig(const bool isInDoNotDisturbMode, const int32_t isSilentEnabled,
    const uint32_t slotFlag)
{
#ifdef PLAYER_FRAMEWORK_ENABLE
    if (isInDoNotDisturbMode) {
        return false;
    }
    if (isSilentEnabled == static_cast<int32_t>(NotificationConstant::SWITCH_STATE::USER_MODIFIED_ON) ||
        isSilentEnabled == static_cast<int32_t>(NotificationConstant::SWITCH_STATE::SYSTEM_DEFAULT_ON)) {
        ANSR_LOGW("The application has enabled silent notifications.");
        return false;
    }
    uint32_t closeSoundFlag = static_cast<uint32_t>(
        NotificationNapi::NotificationControlFlagStatus::NOTIFICATION_STATUS_CLOSE_SOUND);
    if (!(slotFlag & closeSoundFlag)) {
        ANSR_LOGE("Application sound flag is close.");
        return false;
    }
#endif
    return true;
}

void ReminderDataManager::StartVibration()
{
#ifdef PLAYER_FRAMEWORK_ENABLE
    if (!isVibration_) {
        return;
    }
    Sensors::SetUsage(VibratorUsage::USAGE_NOTIFICATION);
    Sensors::PlayVibratorCustom(vibrationFd_, 0, vibrationFileSize_);
    ffrt::task_attr taskAttr;
    taskAttr.delay(VIBRATION_PERIOD);
    auto callback = [this]() {
        std::lock_guard<std::mutex> lock(alertMutex_);
        StartVibration();
    };
    serviceQueue_->submit(callback, taskAttr);
#endif
}

bool ReminderDataManager::GetSettingsData(const int32_t userId)
{
#ifdef PLAYER_FRAMEWORK_ENABLE
    constexpr const char* USER_SETINGS_DATA_URI =
        "datashare:///com.ohos.settingsdata/entry/settingsdata/USER_SETTINGSDATA_";
    constexpr const char* VIBRATE_ENABLE_URI = "?Proxy=true&key=hw_vibrate_when_ringing";
    constexpr const char* VIBRATE_ENABLE = "hw_vibrate_when_ringing";
    std::string uriStr = USER_SETINGS_DATA_URI + std::to_string(userId) + VIBRATE_ENABLE_URI;
    Uri enableUri(uriStr);
    std::string enable = "1";  // settingsdata default value
    bool ret = ReminderDataShareHelper::GetInstance().Query(enableUri, VIBRATE_ENABLE, enable);
    if (!ret) {
        ANSR_LOGE("Query vibrate enable failed.");
        return false;
    }
    if (enable.compare("0") == 0) {
        ANSR_LOGI("Vibrate enable value is 0.");
        return false;
    }
#endif
    return true;
}

bool ReminderDataManager::CheckVibrationConfig(const int32_t userId, const bool isInDoNotDisturbMode,
    const int32_t isSilentEnabled, const uint32_t slotFlag)
{
#ifdef PLAYER_FRAMEWORK_ENABLE
    // 免打扰开关
    if (isInDoNotDisturbMode) {
        return false;
    }
    // 静默通知开关
    if (isSilentEnabled == static_cast<int32_t>(NotificationConstant::SWITCH_STATE::USER_MODIFIED_ON) ||
        isSilentEnabled == static_cast<int32_t>(NotificationConstant::SWITCH_STATE::SYSTEM_DEFAULT_ON)) {
        ANSR_LOGW("The application has enabled silent notifications.");
        return false;
    }
    // 响铃时振动开关
    bool vibrateSettingEnable = GetSettingsData(userId);
    if (!vibrateSettingEnable) {
        return false;
    }
    // 振动配置信息
    if (systemSoundClient_ == nullptr) {
        return false;
    }
    Media::ToneHapticsSettings settings;
    systemSoundClient_->GetToneHapticsSettings(nullptr, Media::ToneHapticsType::NOTIFICATION, settings);
    if (settings.mode == Media::ToneHapticsMode::NONE) {
        ANSR_LOGE("System vibration flag is close.");
        return false;
    }
    uint32_t closeVibrationFlag = static_cast<uint32_t>(
        NotificationNapi::NotificationControlFlagStatus::NOTIFICATION_STATUS_CLOSE_VIBRATION);
    if (!(slotFlag & closeVibrationFlag)) {
        ANSR_LOGE("Application vibration flag is close.");
        return false;
    }
    vibrationFd_ = open(settings.hapticsUri.c_str(), O_RDONLY);
    if (vibrationFd_ == -1) {
        ANSR_LOGE("Open vibration file failed.");
        return false;
    }
    struct stat statbuf = {0};
    if (fstat(vibrationFd_, &statbuf) != 0) {
        ANSR_LOGE("Get vibration file size failed.");
        close(vibrationFd_);
        vibrationFd_ = -1;
        return false;
    }
    vibrationFileSize_ = statbuf.st_size;
#endif
    return true;
}

int32_t ReminderDataManager::ConvertRingChannel(ReminderRequest::RingChannel channel)
{
    switch (channel) {
        case ReminderRequest::RingChannel::ALARM:
            return static_cast<int32_t>(AudioStandard::StreamUsage::STREAM_USAGE_ALARM);
        case ReminderRequest::RingChannel::MEDIA:
            return static_cast<int32_t>(AudioStandard::StreamUsage::STREAM_USAGE_MEDIA);
        case ReminderRequest::RingChannel::NOTIFICATION:
            return static_cast<int32_t>(AudioStandard::StreamUsage::STREAM_USAGE_NOTIFICATION);
        default:
            return static_cast<int32_t>(AudioStandard::StreamUsage::STREAM_USAGE_ALARM);
    }
}

void ReminderDataManager::HandleExtensionReminder(std::vector<sptr<ReminderRequest>>& extensionReminders,
    const int8_t type)
{
    int32_t count = 0;
    for (auto& reminder : extensionReminders) {
        ReminderDataManager::AsyncStartExtensionAbility(reminder, CONNECT_EXTENSION_MAX_RETRY_TIMES, type, count);
    }
}

bool ReminderDataManager::StartExtensionAbility(const sptr<ReminderRequest> &reminder, const int8_t type)
{
    ANSR_LOGD("called");
    if (reminder->GetReminderType() == ReminderRequest::ReminderType::CALENDAR) {
        ReminderRequestCalendar* calendar = static_cast<ReminderRequestCalendar*>(reminder.GetRefPtr());
        std::shared_ptr<ReminderRequest::WantAgentInfo> wantInfo = calendar->GetRRuleWantAgentInfo();
        if (wantInfo != nullptr && wantInfo->pkgName.size() != 0 && wantInfo->abilityName.size() != 0) {
            AAFwk::Want want;
            want.SetElementName(wantInfo->pkgName, wantInfo->abilityName);
            want.SetParam(ReminderRequest::PARAM_REMINDER_ID, reminder->GetReminderId());
            want.SetParam("PULL_TYPE", type);
            int32_t result = IN_PROCESS_CALL(
                AAFwk::AbilityManagerClient::GetInstance()->StartExtensionAbility(want, nullptr));
            if (result != ERR_OK) {
                ANSR_LOGE("failed[%{public}d]", result);
                return false;
            }
        }
    }
    return true;
}

void ReminderDataManager::CheckAndCloseShareReminder(const sptr<ReminderRequest>& reminder)
{
    if (!reminder->IsShare()) {
        return;
    }
    constexpr int64_t interval = 24 * 60 * 60 * 1000;
    std::lock_guard<std::mutex> locker(ReminderDataManager::MUTEX);
    for (auto vit = reminderVector_.begin(); vit != reminderVector_.end(); vit++) {
        sptr<ReminderRequest> tarReminder = *vit;
        if (tarReminder == nullptr) {
            continue;
        }
        if (!tarReminder->IsShare()) {
            continue;
        }
        if (tarReminder->GetIdentifier() == reminder->GetIdentifier()) {
            continue;
        }
        if (tarReminder->GetNotificationId() != reminder->GetNotificationId()) {
            continue;
        }
        int64_t diff = static_cast<int64_t>(tarReminder->GetOriTriggerTimeInMilli())
            - static_cast<int64_t>(reminder->GetOriTriggerTimeInMilli());
        if (diff > 0 && diff < interval) {
            tarReminder->SetExpired(true);
            tarReminder->SetStateToInActive();
            ReminderDataShareHelper::GetInstance().Update(tarReminder->GetIdentifier(),
                ReminderCalendarShareTable::STATE_DISMISSED);
            ANSR_LOGI("Cancel reminder[%{public}d] by same notificationId and close button",
                tarReminder->GetReminderId());
        }
    }
    StopTimerLocked(TimerType::TRIGGER_TIMER);
}

void ReminderDataManager::CollapseNotificationPanel()
{
    EventFwk::Want want;
    want.SetAction("sceneboard.event.HIDE_DROPDOWN_WINDOW");
    want.SetParam("Code", 0);
    EventFwk::CommonEventData eventData(want);
    EventFwk::CommonEventManager::PublishCommonEvent(eventData);
}

std::shared_ptr<ReminderNotifyManager> ReminderDataManager::GetNotifyManager()
{
    return notifyManager_;
}

void ReminderDataManager::NotifyReminderState(const int32_t uid)
{
    if (notifyManager_ == nullptr) {
        return;
    }
    std::vector<ReminderState> states = store_->QueryState(uid);
    notifyManager_->NotifyReminderState(uid, states);
    store_->DeleteState(uid);
}
}
}
