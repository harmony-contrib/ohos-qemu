/*
 * Copyright (c) 2021-2025 Huawei Device Co., Ltd.
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

#include "reminder_agent_service.h"

#include "reminder_data_manager.h"
#include "reminder_request_alarm.h"
#include "reminder_request_timer.h"
#include "reminder_notify_manager.h"
#include "reminder_request_calendar.h"
#include "reminder_bundle_manager_helper.h"

#include "ffrt_inner.h"
#include "tokenid_kit.h"
#include "ipc_skeleton.h"
#include "accesstoken_kit.h"
#include "ans_log_wrapper.h"
#include "ans_trace_wrapper.h"
#include "ans_inner_errors.h"
#include "os_account_manager.h"
#include "notification_helper.h"
#include "in_process_call_wrapper.h"

#include <file_ex.h>

namespace OHOS::Notification {
namespace {
constexpr int8_t REMINDER_AGENT_SERVICE_LOAD_STATE = 1;
constexpr int8_t REMINDER_AGENT_SERVICE_UNLOAD_STATE = 0;
constexpr int32_t REMINDER_AGENT_SERVICE_ID = 3204;
constexpr int64_t UNLOAD_TASK_DELAY_TIME = 60 * 1000 * 1000;  // 60s, ut: microsecond
constexpr const char* REMINDER_AGENT_SERVICE_CONFIG_PATH =
    "/data/service/el1/public/notification/reminder_agent_service_config";
}

std::mutex ReminderAgentService::instanceMutex_;
sptr<ReminderAgentService> ReminderAgentService::instance_;

sptr<ReminderAgentService> ReminderAgentService::GetInstance()
{
    std::lock_guard<std::mutex> locker(instanceMutex_);
    if (instance_ == nullptr) {
        instance_ = new (std::nothrow) ReminderAgentService();
        if (instance_ == nullptr) {
            ANSR_LOGE("Failed to create ReminderAgentService instance.");
            return nullptr;
        }
    }
    return instance_;
}

ErrCode ReminderAgentService::PublishReminder(const ReminderRequest& reminder, int32_t& reminderId)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    sptr<ReminderRequest> tarReminder = CreateReminderRequest(reminder);
    if (nullptr == tarReminder) {
        ANSR_LOGE("CreateReminderRequest is nullptr.");
        return ERR_REMINDER_INVALID_PARAM;
    }
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    int32_t callingUid = IPCSkeleton::GetCallingUid();
    std::string bundleName = ReminderBundleManagerHelper::GetInstance().GetBundleNameByUid(callingUid);
    bool isAllowUseReminder = false;
#ifdef NOTIFICATION_MULTI_FOREGROUND_USER
    int32_t userId = SUBSCRIBE_USER_INIT;
    AccountSA::OsAccountManager::GetOsAccountLocalIdFromUid(callingUid, userId);
    NotificationHelper::AllowUseReminder(bundleName, userId, isAllowUseReminder);
#else
    NotificationHelper::AllowUseReminder(bundleName, isAllowUseReminder);
#endif
    if (!isAllowUseReminder) {
        ANSR_LOGW("The number of reminders exceeds the limit[0].");
        return ERR_REMINDER_NUMBER_OVERLOAD;
    }
    ErrCode ret = InitReminderRequest(tarReminder, bundleName, callingUid);
    if (ret != ERR_OK) {
        return ret;
    }
    NotificationBundleOption bundleOption(tarReminder->GetBundleName(), tarReminder->GetUid());
    bool allowedNotify = false;
    ret = IN_PROCESS_CALL(NotificationHelper::IsAllowedNotify(bundleOption, allowedNotify));
    if (!tarReminder->IsSystemApp() && (ret != ERR_OK || !allowedNotify)) {
        ANSR_LOGW("The application does not request enable notification.");
        return ERR_REMINDER_NOTIFICATION_NOT_ENABLE;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    ret = rdm->PublishReminder(tarReminder, callingUid);
    if (ret == ERR_OK) {
        reminderId = tarReminder->GetReminderId();
        ChangeReminderAgentLoadConfig(REMINDER_AGENT_SERVICE_LOAD_STATE);
    }
    return ret;
}

ErrCode ReminderAgentService::UpdateReminder(const int32_t reminderId, const ReminderRequest& reminder)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    sptr<ReminderRequest> tarReminder = CreateReminderRequest(reminder);
    if (nullptr == tarReminder) {
        ANSR_LOGE("CreateReminderRequest is nullptr.");
        return ERR_REMINDER_INVALID_PARAM;
    }
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    int32_t callingUid = IPCSkeleton::GetCallingUid();
    std::string bundleName = ReminderBundleManagerHelper::GetInstance().GetBundleNameByUid(callingUid);
    ErrCode ret = InitReminderRequest(tarReminder, bundleName, callingUid);
    if (ret != ERR_OK) {
        return ret;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    tarReminder->SetReminderId(reminderId);
    ret = rdm->UpdateReminder(tarReminder, callingUid);
    return ret;
}

ErrCode ReminderAgentService::CancelReminder(const int32_t reminderId)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    ErrCode ret = rdm->CancelReminder(reminderId, IPCSkeleton::GetCallingUid());
    return ret;
}

ErrCode ReminderAgentService::CancelAllReminders()
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    int32_t callingUid = IPCSkeleton::GetCallingUid();
    std::string bundleName = ReminderBundleManagerHelper::GetInstance().GetBundleNameByUid(callingUid);
    int32_t userId = -1;
    AccountSA::OsAccountManager::GetOsAccountLocalIdFromUid(callingUid, userId);
    ErrCode ret = rdm->CancelAllReminders(bundleName, userId, callingUid);
    return ret;
}

ErrCode ReminderAgentService::CancelReminderOnDisplay(const int32_t reminderId)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    ErrCode ret = rdm->CancelReminderOnDisplay(reminderId, IPCSkeleton::GetCallingUid());
    return ret;
}

ErrCode ReminderAgentService::GetValidReminders(std::vector<ReminderRequestAdaptation>& reminders)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    reminders.clear();
    rdm->GetValidReminders(IPCSkeleton::GetCallingUid(), reminders);
    return ERR_OK;
}

ErrCode ReminderAgentService::AddExcludeDate(const int32_t reminderId, const int64_t date)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    ErrCode ret = rdm->AddExcludeDate(reminderId, date, IPCSkeleton::GetCallingUid());
    return ret;
}

ErrCode ReminderAgentService::DelExcludeDates(const int32_t reminderId)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    ErrCode ret = rdm->DelExcludeDates(reminderId, IPCSkeleton::GetCallingUid());
    return ret;
}

ErrCode ReminderAgentService::GetExcludeDates(const int32_t reminderId, std::vector<int64_t>& dates)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        return ERR_NO_INIT;
    }
    ErrCode ret = rdm->GetExcludeDates(reminderId, IPCSkeleton::GetCallingUid(), dates);
    return ret;
}

ErrCode ReminderAgentService::RegisterReminderState(const sptr<IRemoteObject>& object)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    if (!CheckReminderPermission()) {
        ANSR_LOGE("Failed to check permission: ohos.permission.PUBLISH_AGENT_REMINDER.");
        return ERR_REMINDER_PERMISSION_DENIED;
    }
    auto rdm = ReminderDataManager::GetInstance();
    if (rdm == nullptr) {
        return ERR_NO_INIT;
    }
    return rdm->RegisterReminderState(IPCSkeleton::GetCallingUid(), object);
}

ErrCode ReminderAgentService::UnRegisterReminderState()
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    ANSR_LOGD("called");
    auto rdm = ReminderDataManager::GetInstance();
    if (rdm == nullptr) {
        return ERR_NO_INIT;
    }
    return rdm->UnRegisterReminderState(IPCSkeleton::GetCallingUid());
}

void ReminderAgentService::TryPostDelayUnloadTask(const int64_t delayTime)
{
    std::lock_guard<std::mutex> locker(unloadMutex_);
    if (nullptr != tryUnloadTask_) {
        ffrt::skip(tryUnloadTask_);
    }
    tryUnloadTask_ = ffrt::submit_h([]() {
        ReminderAgentService::GetInstance()->TryUnloadService();
    }, {}, {}, ffrt::task_attr().delay(delayTime));
}

void ReminderAgentService::TryUnloadService()
{
    std::lock_guard<std::mutex> locker(unloadMutex_);
    auto rdm = ReminderDataManager::GetInstance();
    if (nullptr == rdm) {
        tryUnloadTask_ = nullptr;
        return;
    }
    int32_t reminderCount = rdm->QueryActiveReminderCount();
    if (reminderCount > 0) {
        tryUnloadTask_ = nullptr;
        return;
    }
    ANSR_LOGD("called");
    ChangeReminderAgentLoadConfig(REMINDER_AGENT_SERVICE_UNLOAD_STATE);
    auto samgrProxy = SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager();
    if (samgrProxy == nullptr) {
        ANSR_LOGE("null samgrProxy");
        tryUnloadTask_ = nullptr;
        return;
    }
    int32_t ret = samgrProxy->UnloadSystemAbility(REMINDER_AGENT_SERVICE_ID);
    if (ret != ERR_OK) {
        ANSR_LOGE("Failed to unload system ability.");
    }
    tryUnloadTask_ = nullptr;
}

void ReminderAgentService::ChangeReminderAgentLoadConfig(const int8_t reminderAgentState)
{
    if (reminderAgentState_ != reminderAgentState) {
        OHOS::SaveStringToFile(REMINDER_AGENT_SERVICE_CONFIG_PATH, std::to_string(reminderAgentState), true);
        reminderAgentState_ = reminderAgentState;
    }
}

sptr<ReminderRequest> ReminderAgentService::CreateReminderRequest(const ReminderRequest& reminder)
{
    sptr<ReminderRequest> tarReminder = nullptr;
    switch (reminder.GetReminderType()) {
        case ReminderRequest::ReminderType::TIMER: {
            ANSR_LOGI("Publish timer.");
            ReminderRequestTimer& timer = (ReminderRequestTimer&)reminder;
            tarReminder = new (std::nothrow) ReminderRequestTimer(timer);
            break;
        }
        case ReminderRequest::ReminderType::ALARM: {
            ANSR_LOGI("Publish alarm.");
            ReminderRequestAlarm& alarm = (ReminderRequestAlarm&)reminder;
            tarReminder = new (std::nothrow) ReminderRequestAlarm(alarm);
            break;
        }
        case ReminderRequest::ReminderType::CALENDAR: {
            ANSR_LOGI("Publish calendar.");
            ReminderRequestCalendar& calendar = (ReminderRequestCalendar&)reminder;
            tarReminder = new (std::nothrow) ReminderRequestCalendar(calendar);
            break;
        }
        default: {
            ANSR_LOGW("Unknown reminder type.");
            break;
        }
    }
    return tarReminder;
}

ErrCode ReminderAgentService::InitReminderRequest(sptr<ReminderRequest>& reminder,
    const std::string& bundle, const int32_t callingUid)
{
    if (reminder->GetWantAgentInfo() == nullptr || reminder->GetMaxScreenWantAgentInfo() == nullptr) {
        ANSR_LOGE("WantAgentInfo or MaxScreenWantAgentInfo is nullptr.");
        return ERR_REMINDER_INVALID_PARAM;
    }
    std::string wantAgentName = reminder->GetWantAgentInfo()->pkgName;
    std::string maxWantAgentName = reminder->GetMaxScreenWantAgentInfo()->pkgName;
    if (wantAgentName != maxWantAgentName && wantAgentName != "" && maxWantAgentName != "") {
        ANSR_LOGE("WantAgentName[%{public}s] is not same to maxWantAgentName[%{public}s].",
            wantAgentName.c_str(), maxWantAgentName.c_str());
        return ERR_REMINDER_INVALID_PARAM;
    }
    int32_t userId = -1;
    if (AccountSA::OsAccountManager::GetOsAccountLocalIdFromUid(callingUid, userId) != ERR_OK) {
        ANSR_LOGE("Failed to get user id by uid.");
        return ERR_REMINDER_INVALID_PARAM;
    }
    std::string bundleName = bundle;
    int32_t uid = callingUid;
    if (wantAgentName != bundle && wantAgentName != "") {
        bundleName = wantAgentName;
        uid = ReminderBundleManagerHelper::GetInstance().GetDefaultUidByBundleName(bundleName, userId);
    } else if (maxWantAgentName != bundle && maxWantAgentName != "") {
        bundleName = maxWantAgentName;
        uid = ReminderBundleManagerHelper::GetInstance().GetDefaultUidByBundleName(bundleName, userId);
    }
    // Only system applications can proxy other applications to send notifications
    bool isSystemApp = IsSystemApp();
    if (bundleName != bundle && !isSystemApp) {
        ANSR_LOGE("Only system applications can proxy other applications to send notifications.");
        return ERR_REMINDER_INVALID_PARAM;
    }
    reminder->SetSystemApp(isSystemApp);
    reminder->InitUserId(userId);
    reminder->InitBundleName(bundleName);
    reminder->InitCreatorBundleName(bundle);
    reminder->InitCreatorUid(callingUid);
    reminder->InitUid(uid);
    return ERR_OK;
}

bool ReminderAgentService::CheckReminderPermission()
{
    Security::AccessToken::AccessTokenID callerToken = IPCSkeleton::GetCallingTokenID();
    ErrCode ret = Security::AccessToken::AccessTokenKit::VerifyAccessToken(
        callerToken, "ohos.permission.PUBLISH_AGENT_REMINDER");
    return ret == Security::AccessToken::PermissionState::PERMISSION_GRANTED;
}

bool ReminderAgentService::IsSystemApp()
{
    Security::AccessToken::AccessTokenID tokenId = IPCSkeleton::GetCallingTokenID();
    Security::AccessToken::ATokenTypeEnum type = Security::AccessToken::AccessTokenKit::GetTokenTypeFlag(tokenId);
    if (type != Security::AccessToken::ATokenTypeEnum::TOKEN_HAP) {
        return false;
    }
    uint64_t fullTokenId = IPCSkeleton::GetCallingFullTokenID();
    return Security::AccessToken::TokenIdKit::IsSystemAppByFullTokenID(fullTokenId);
}
}  // namespace OHOS::Notification
