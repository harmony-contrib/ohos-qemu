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

#ifndef BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_SERVICES_REMINDER_INCLUDE_REMINDER_DATA_MANAGER_H
#define BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_SERVICES_REMINDER_INCLUDE_REMINDER_DATA_MANAGER_H

#include <map>
#include <vector>

#include "ans_inner_errors.h"
#include "reminder_store.h"
#include "reminder_request.h"
#include "reminder_timer_info.h"
#include "reminder_notify_manager.h"
#include "reminder_request_adaptation.h"

#include "app_mgr_interface.h"
#include "time_service_client.h"
#include "datashare_predicates.h"
#include "datashare_values_bucket.h"
#ifdef PLAYER_FRAMEWORK_ENABLE
#include "player.h"
#include "system_sound_manager.h"
#endif

namespace OHOS {
namespace Notification {
class ReminderDataManager final {
public:
    ReminderDataManager();
    ~ReminderDataManager();

    ReminderDataManager(ReminderDataManager &other) = delete;
    ReminderDataManager& operator = (const ReminderDataManager &other) = delete;

    /**
     * @brief Cancels all the reminders relative to the bundle option.
     *
     * @param packageName Indicates the package name.
     * @param userId Indicates the user id which the bundle belong to.
     * @param uid Indicates the uid which the bundle belong to.
     * @param isUninstallApp Is it an app uninstall event.
     * @return ERR_OK if success, else not.
     */
    ErrCode CancelAllReminders(const std::string& packageName, const int32_t userId, const int32_t uid,
        const bool isUninstallApp = false);

    /**
     * @brief Cancels the target reminder relative to the reminder id and bundle option.
     *
     * @param reminderId Indicates the reminder id.
     * @param bundleOption Indicates the bundle option.
     * @return ERR_OK if success, else not.
     */
    ErrCode CancelReminder(const int32_t &reminderId, const int32_t callingUid);

    /**
     * @brief Dismiss the currently displayed alert and only remove it from the Notification Center.
     *
     * @param reminderId Indicates the reminder id.
     * @param callingUid Indicates the uid.
     * @return ERR_OK if success, else not.
     */
    ErrCode CancelReminderOnDisplay(const int32_t reminderId, const int32_t callingUid);

    sptr<ReminderRequest> CheckExcludeDateParam(const int32_t reminderId,
        const int32_t callingUid);

    /**
     * @brief Add exclude date for reminder
     *
     * @param reminderId Identifies the reminders id.
     * @param date exclude date
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode AddExcludeDate(const int32_t reminderId, const int64_t date,
        const int32_t callingUid);

    /**
     * @brief Clear exclude date for reminder
     *
     * @param reminderId Identifies the reminders id.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode DelExcludeDates(const int32_t reminderId, const int32_t callingUid);

    /**
     * @brief Get exclude date for reminder
     *
     * @param reminderId Identifies the reminders id.
     * @param dates exclude dates
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode GetExcludeDates(const int32_t reminderId, const int32_t callingUid,
        std::vector<int64_t>& dates);

    /**
     * @brief Register reminder state.
     *
     * @param uid Identifies the uid
     * @param object Identifies the callback.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode RegisterReminderState(const int32_t uid, const sptr<IRemoteObject>& object);

    /**
     * @brief UnRegister reminder state.
     *
     * @param uid Identifies the uid
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode UnRegisterReminderState(const int32_t uid);

    /**
     * @brief Close the target reminder which is showing on panel.
     *        This is manul operation by user: 1.Click close button of the reminder, 2.remove reminder notification.
     *
     * @param want Want information that transferred when the event trigger by user.
     * @param cancelNotification Indicates whether need to cancel notification or not.
     */
    void CloseReminder(const OHOS::EventFwk::Want &want, bool cancelNotification, bool isButtonClick = true);

    /**
     * Obtains the single instance.
     *
     * @return Single instance of ReminderDataManager.
     */
    static std::shared_ptr<ReminderDataManager> GetInstance();
    static std::shared_ptr<ReminderDataManager> InitInstance();

    /**
     * Obtains all the valid reminders (which are not expired) relative to the bundle option.
     *
     * @param bundleOption Indicates the bundle option.
     * @param[out] reminders return the valid reminders.
     */
    void GetValidReminders(
        const int32_t callingUid, std::vector<ReminderRequestAdaptation> &reminders);

    /**
     * @brief Inits and recovery data from database.
     */
    void Init();

    void InitUserId();

    /**
     * @brief Check all reminders, Whether an immediate reminder is needed;
     * whether a pull up service extension is required.
     * Use when powering on and changing the system time.
     */
    void CheckReminderTime(std::vector<sptr<ReminderRequest>>& immediatelyReminders,
        std::vector<sptr<ReminderRequest>>& extensionReminders);

    /**
     * @brief Register configuration observer, the listening system language is changed.
     */
    bool RegisterConfigurationObserver();

    void OnUserRemove(const int32_t& userId);

    /**
     * @brief Notify UNLOCK_SCREEN event.
     */
    void OnUnlockScreen();

    /**
     * @brief Bundle manager service start.
     */
    void OnBundleMgrServiceStart();

    /**
     * @brief Ability manager service start.
     */
    void OnAbilityMgrServiceStart();

    void OnUserSwitch(const int32_t& userId);

    /**
     * Publishs a scheduled reminder.
     *
     * @param reminder Indicates the reminder.
     * @param bundleOption Indicates bundle option the reminder belongs to.
     * @return ERR_OK if success, else not.
     */
    ErrCode PublishReminder(const sptr<ReminderRequest> &reminder,
        const int32_t callingUid);

    /**
     * Updates a scheduled reminder.
     *
     * @param reminder Indicates the reminder.
     * @param callingUid Indicates uid the reminder belongs to.
     * @return ERR_OK if success, else not.
     */
    ErrCode UpdateReminder(const sptr<ReminderRequest> &reminder, const int32_t callingUid);

    /**
     * @brief Refresh all reminders when date/time or timeZone of device changed by user.
     *
     * @param type Indicates it is triggered by dateTime change or timeZone change.
     */
    void RefreshRemindersDueToSysTimeChange(uint8_t type);

    bool ShouldAlert(const sptr<ReminderRequest> &reminder) const;

    /**
     * @brief Show the reminder.
     *
     * @param isSysTimeChanged Indicates it is triggered as dateTime changed by user or not.
     * @param want Which contains the given reminder.
     */
    void ShowActiveReminder(const EventFwk::Want &want);

    /**
     * @brief Snooze the reminder by manual.
     * 1) Snooze the trigger time to the next.
     * 2) Update the notification(Update notification lable/content...; Stop audio player and vibrator)
     * 3) Show the notification dialog in the SystemUI
     * 4) Start a new reminder, which is recent one now.
     *
     * @param want Which contains the given reminder.
     */
    void SnoozeReminder(const OHOS::EventFwk::Want &want);

    /**
     * Starts the recent reminder timing.
     */
    void StartRecentReminder();

    /**
     * Handle custom button click event.
     */
    void HandleCustomButtonClick(const OHOS::EventFwk::Want &want);

    /**
     * Handle click notification, no button.
     */
    void ClickReminder(const OHOS::EventFwk::Want &want);

    /**
     * @brief Load reminder event.
     */
    void OnLoadReminderEvent();

    /**
     * @brief Load reminder event for ffrt.
     */
    void OnLoadReminderInFfrt();

    /**
     * @brief datashare notify, share reminder insert or delete.
     */
    void OnDataShareInsertOrDelete();

    /**
     * @brief datashare notify, share reminder update.
     */
    void OnDataShareUpdate(const std::map<std::string, sptr<ReminderRequest>>& reminders);

    /**
     * Handle auto delete time
     */
    void HandleAutoDeleteReminder(const int32_t notificationId, const int32_t uid, const int64_t autoDeletedTime);

    /**
     * @brief Terminate the alerting reminder.
     *
     * 1. Stop sound and vibrate.
     * 2. Stop the alerting timer.
     * 3. Update the reminder state.
     * 4. Update the display content of the notification.
     *
     * @param want Which contains the given reminder.
     */
    void TerminateAlerting(const OHOS::EventFwk::Want &want);
    void TerminateAlerting();

    /**
     * @brief Update reminders based on the system language.
     *
     * Update action button title.
     */
    void UpdateReminderLanguageLocked(const int32_t uid, const std::vector<sptr<ReminderRequest>>& reminders);

    /**
     * @brief System language change
     */
    void OnLanguageChanged();

    /**
     * @brief When OnRemoveSystemAbility occurs.
     */
    void OnRemoveAppMgr();

    /**
     * @brief Whether the device is ready or not.
     */
    bool IsSystemReady();

    int32_t QueryActiveReminderCount();

    void StartLoadTimer();

    /**
     * @brief When the device boot complete, need delay for 5 seconds,
     * then load the reminder.
     */
    void InitShareReminders(const bool registerObserver);

    /**
     * @brief Get notify manager.
     */
    std::shared_ptr<ReminderNotifyManager> GetNotifyManager();

    /**
     * @brief After the application registration callback, send all data.
     */
    void NotifyReminderState(const int32_t uid);

    static constexpr uint8_t TIME_ZONE_CHANGE = 0;
    static constexpr uint8_t DATE_TIME_CHANGE = 1;

private:
    enum class TimerType : uint8_t {
        TRIGGER_TIMER,
        ALERTING_TIMER
    };

    struct ShowLimit {
        // Limit on the number of single applications at the same time.
        std::unordered_map<std::string, int32_t> timeLimits;
        // Notification limit for a single app.
        std::unordered_map<int32_t, int32_t> bundleLimits;
        // Total number of notifications displayed at one time.
        int32_t totalCount {0};
        // Whether to play custom ringtones.
        bool isAlerting {false};
        bool checkIsShowing {true};
    };

    static std::shared_ptr<ffrt::queue> serviceQueue_;

    /**
     * Add reminder to showed reminder vector.
     *
     * @param reminder Indicates the showed reminder.
     */
    void AddToShowedReminders(const sptr<ReminderRequest> &reminder);

    void CancelAllReminders(const int32_t userId);

    /**
     * @brief Check the update conditions.
     *
     * @param reminder Indicates the showed reminder.
     * @param actionButtonType Button type of the button.
     * @param actionButtonMap Button map.
     * @return True if check successful.
     */
    bool CheckUpdateConditions(const sptr<ReminderRequest> &reminder,
        const ReminderRequest::ActionButtonType &actionButtonType,
        const std::map<ReminderRequest::ActionButtonType, ReminderRequest::ActionButtonInfo> &actionButtonMap);

    /**
     * @brief update app database.
     *
     * @param reminder Indicates the showed reminder.
     * @param actionButtonType Button type of the button.
     */
    void UpdateAppDatabase(const sptr<ReminderRequest> &reminder,
        const ReminderRequest::ActionButtonType &actionButtonType);

    /**
     * @brief generate Predicates for dataShare.
     *
     * @param predicates find fields from database.
     * @param equalToVector Split from dataShareUpdate->equaleTo.
     */
    void GenPredicates(DataShare::DataSharePredicates &predicates, const std::vector<std::string> &equalToVector);

    /**
     * @brief generate ValuesBucket for dataShare.
     *
     * @param valuesBucket update fields at database.
     * @param valuesBucketVector Split from dataShareUpdate->valuesBucket.
     */
    void GenValuesBucket(DataShare::DataShareValuesBucket &valuesBucket,
        const std::vector<std::string> &valuesBucketVector);

    /**
     * @brief get bundleName from uri.
     *
     * @param dstBundleName The package name required to update the database.
     * @param uri Database address.
     */
    void GenDstBundleName(std::string &dstBundleName, const std::string &uri) const;

    /**
     * @brief Cancels all the reminders of the target bundle or user.
     *
     * @param packageName Indicates the packageName need to cancel.
     * @param userId Indicates the userId to cancel.
     */
    void CancelRemindersImplLocked(const std::string& bundleName,
        const int32_t userId, const int32_t uid, bool isCancelAllPackage = false);

    /**
     * @brief Close reminders with the same group id.
     *
     * @param oldReminderId Indicates the reminderId that are currently bing showed.
     * @param packageName Indicates the packageName need to cancel.
     * @param groupId Indicates the group id to cancel.
     */
    void CloseRemindersByGroupId(const int32_t &oldReminderId, const std::string &packageName,
        const std::string &groupId);

    /**
     * Cancels the notification relative to the reminder.
     *
     * @param reminder Indicates the reminder.
     */
    void CancelNotification(const sptr<ReminderRequest> &reminder) const;

    /**
     * Check whether the number limit of reminders if exceeded.
     *
     * @param bundleName Indicates the target bundle.
     * @return true if number limit is exceeded.
     */
    bool CheckReminderLimitExceededLocked(const int32_t callingUid,
        const sptr<ReminderRequest>& reminder) const;
    void CloseReminder(const sptr<ReminderRequest> &reminder, bool cancelNotification);

    /**
     * Create a information for timer, such as timer type, repeat policy, interval and want agent.
     *
     * @param type Indicates the timer type.
     * @param reminderRequest Indicates the reminder request.
     * @return pointer of ReminderTimerInfo.
     */
    std::shared_ptr<ReminderTimerInfo> CreateTimerInfo(TimerType type,
        const sptr<ReminderRequest> &reminderRequest) const;
    void InitTimerInfo(std::shared_ptr<ReminderTimerInfo> &timerInfo,
        const sptr<ReminderRequest> &reminderRequest, TimerType reminderType) const;

    /**
     * Find the reminder from reminderVector_ by reminder id.
     *
     * @param reminderId Indicates the reminder id.
     * @param isShare Indicates the reminder datashare flag.
     * @return pointer of reminder request or nullptr.
     */
    sptr<ReminderRequest> FindReminderRequestLocked(const int32_t reminderId, const bool isShare);

    /**
     * Obtains the recent reminder which is not expired from reminder vector.
     *
     * The expired reminders will be removed from reminderVector_ and notificationBundleOptionMap_.
     *
     * @return pointer of reminder object.
     */
    sptr<ReminderRequest> GetRecentReminder();

    void HandleImmediatelyShow(std::vector<sptr<ReminderRequest>>& showImmediately, ShowLimit& limits,
        const bool isSysTimeChanged, const bool isSlienceNotification, size_t index = 0);
    void HandleExtensionReminder(std::vector<sptr<ReminderRequest>> &extensionReminders, const int8_t type);

    /**
     * @brief Refresh the reminder due to date/time or timeZone change by user.
     *
     * @param type Indicates it is date/time change or timeZone change.
     * @param reminder Indicates the target reminder.
     * @return sptr<ReminderRequest> Returns the target reminder if it is need to show immediately, otherwise nullptr.
     */
    sptr<ReminderRequest> HandleRefreshReminder(const uint8_t &type, sptr<ReminderRequest> &reminder);

    /**
     * @brief Handles all the reminders that have the same notification id and belong to same application
     *        with the current reminder. Unset the state of "showing".
     *
     * @param reminder Indicates the current reminder.
     */
    void HandleSameNotificationIdShowing(const sptr<ReminderRequest> reminder);

    bool HandleSysTimeChange(const sptr<ReminderRequest> reminder) const;

    /**
     * @brief Judge the two reminders is belong to the same application or not.
     *
     * @param bundleOption Indicates the bundleOption of first reminder.
     * @param other Indicates the bundleOption of second reminder.
     * @return true if the two reminders belong to the same application.
     */
    bool IsBelongToSameApp(const int32_t uidSrc, const int32_t uidTar) const;
    bool CheckIsSameApp(const sptr<ReminderRequest> &reminder, const int32_t callingUid) const;

    /**
     * @brief Judges whether the reminder is matched with the bundleOption or userId.
     *
     * @param reminder Indicates the target reminder.
     * @param packageName Indicates the package name.
     * @param userId Indicates the user id.
     * @param uid Indicates the uid.
     * @return true If the reminder is matched with the bundleOption or userId.
     */
    bool IsMatched(const sptr<ReminderRequest> &reminder, const int32_t userId, const int32_t uid,
        bool isCancelAllPackage = false) const;

    /**
     * @brief Judges whether the reminder is matched with the packageName or groupId.
     *
     * @param reminder Indicates the target reminder.
     * @param packageName Indicates the package name.
     * @param groupId Indicates the group id.
     * @return true If the reminder is matched with the packageName and groupId.
     */
    bool IsMatchedForGroupIdAndPkgName(const sptr<ReminderRequest> &reminder, const std::string &packageName,
        const std::string &groupId) const;

    bool IsAllowedNotify(const sptr<ReminderRequest> &reminder) const;

    bool IsReminderAgentReady() const;

    void LoadReminderFromDb();

    void PlaySoundAndVibrationLocked(const sptr<ReminderRequest>& reminder);
    void StopSoundAndVibrationLocked(const sptr<ReminderRequest>& reminder);
    void SetAlertingReminder(const sptr<ReminderRequest>& reminder);
    bool IsInDoNotDisturbMode(const int32_t userId);
    // sound
    std::string GetFullPath(const std::string& path);
    void SetPlayerParam(const sptr<ReminderRequest> reminder);
    bool CheckSoundConfig(const bool isInDoNotDisturbMode, const int32_t isSilentEnabled, const uint32_t slotFlag);
    int32_t ConvertRingChannel(ReminderRequest::RingChannel channel);

    /**
     * @brief Get custom ring file desc.
     */
    bool GetCustomRingFileDesc(const sptr<ReminderRequest>& reminder,
        Global::Resource::ResourceManager::RawFileDescriptor& desc);

    /**
     * @brief Close custom ring file desc.
     */
    void CloseCustomRingFileDesc(const int32_t reminderId, const std::string& customRingUri);

    // vibration
    void StartVibration();
    bool GetSettingsData(const int32_t userId);
    bool CheckVibrationConfig(const int32_t userId, const bool isInDoNotDisturbMode,
        const int32_t isSilentEnabled, const uint32_t slotFlag);

    /**
     * Remove from showed reminder vector.
     *
     * @param reminder Indicates the reminder need to remove.
     */
    void RemoveFromShowedReminders(const sptr<ReminderRequest> &reminder);

    /**
     * @brief Refresh the all reminders due to date/time or timeZone change by user.
     *
     * @param type Indicates it is date/time change or timeZone change.
     * @return reminders that need to show immediately.
     */
    void RefreshRemindersLocked(uint8_t type, std::vector<sptr<ReminderRequest>>& immediatelyReminders,
        std::vector<sptr<ReminderRequest>>& extensionReminders);

    /**
     * Removes the reminder.
     * 1. removes the reminder from reminderVector_ and notificationBundleOptionMap_.
     * 2. cancels the notification.
     *
     * @param reminderId Indicates the reminder id.
     * @param isShare Indicates the reminder datashare flag.
     */
    void RemoveReminderLocked(const int32_t reminderId, const bool isShare);

    /**
     * Resets timer status.
     * 1. Sets timerId_ or timerIdAlerting_ with 0.
     * 2. Sets activeReminderId_ or alertingReminderId with -1.
     *
     * @param type Indicates the timer type.
     */
    void ResetStates(TimerType type);

    void SetActiveReminder(const sptr<ReminderRequest> &reminder);
    void ShowActiveReminderExtendLocked(const uint64_t triggerTime,
        std::vector<sptr<ReminderRequest>>& immediatelyReminders,
        std::vector<sptr<ReminderRequest>>& extensionReminders);
    static bool StartExtensionAbility(const sptr <ReminderRequest> &reminder, const int8_t type);
    static void AsyncStartExtensionAbility(const sptr<ReminderRequest> &reminder,
        int32_t times, const int8_t type, int32_t& count);
    void InitServiceHandler();
    /**
     * @brief Show the reminder on SystemUI.
     *
     * @param reminder Indicates the reminder to show.
     * @param isPlaySound Indicates whether need to play sound.
     * @param isSysTimeChanged Indicates whether it is triggerred as system time changed by user.
     * @param isCloseDefaultSound Indicates whether need to close default sound.
     * @param isSlienceNotification Indicates whether need to slience show notification.
     */
    void ShowReminder(const sptr<ReminderRequest>& reminder, const bool isPlaySound,
        const bool isSysTimeChanged, const bool isCloseDefaultSound, const bool isSlienceNotification);
    void SlienceNotification(const bool isCloseDefaultSound, const bool isSlienceNotification,
        NotificationRequest& notification);

    void SnoozeReminderImpl(sptr<ReminderRequest> &reminder);

    /**
     * Starts timing actually.
     *
     * @param reminderRequest Indicates the reminder.
     * @param type Indicates the timer type.
     */
    void StartTimerLocked(const sptr<ReminderRequest> &reminderRequest, TimerType type);
    void StartTimer(const sptr<ReminderRequest> &reminderRequest, TimerType type);

    uint64_t HandleTriggerTimeInner(const sptr<ReminderRequest> &reminderRequest, TimerType type,
        const sptr<MiscServices::TimeServiceClient> &timer);

    uint64_t HandleAlertingTimeInner(const sptr<ReminderRequest> &reminderRequest, TimerType type,
        const sptr<MiscServices::TimeServiceClient> &timer, time_t now);

    /**
     * @brief Stop the alerting timer and update reminder information.
     *
     * 1. Stop sound and vibrate.
     * 2. Stop the alerting timer.
     *
     * @param reminder Indicates the target reminder.
     */
    void StopAlertingReminder(const sptr<ReminderRequest> &reminder);

    /**
     * Stops timing.
     *
     * @param type Indicates the timer type.
     */
    void StopTimer(TimerType type);
    void StopTimerLocked(TimerType type);

    /**
     * @brief Terminate the alerting reminder.
     *
     * 1. Stop sound and vibrate.
     * 2. Stop the alerting timer.
     * 3. Update the reminder state.
     * 4. Update the display content of the notification.
     *
     * @param reminder Indicates the reminder.
     * @param reason Indicates the description information.
     */
    void TerminateAlerting(const sptr<ReminderRequest> &reminder, const std::string &reason);

    /**
     * @brief Assign unique reminder id and save reminder in memory.
     *
     * @param reminder Indicates a reminder.
     */
    void UpdateAndSaveReminderLocked(const sptr<ReminderRequest> &reminder);
    void UpdateAndSaveReminderLocked(const sptr<ReminderRequest>& reminder, const bool isInMemory);

    static bool cmp(sptr<ReminderRequest> &reminderRequest, sptr<ReminderRequest> &other);

    /**
     * @brief Connect App Manager to get the current foreground application.
     */
    bool ConnectAppMgr();

    /**
     * @brief Check need to notify the application, if the current foreground application
     *     is the creator of the reminder, notify the application of the reminder status
     *     change; otherwise, do not noitfy.
     *
     * @param reminder Indicates a reminder.
     * @param buttonType The type of button clicked by the user.
     */
    void CheckNeedNotifyStatus(const sptr<ReminderRequest> &reminder,
        const ReminderRequest::ActionButtonType buttonType);

    /**
     * @brief Check action button data share permission
    */
    bool IsActionButtonDataShareValid(const sptr<ReminderRequest>& reminder,
        const uint32_t callerTokenId);

    /**
     * @brief Get resource manager by bundlename and uid.
     */
    std::shared_ptr<Global::Resource::ResourceManager> GetResourceMgr(const std::string& bundleName,
        const int32_t uid);

    /**
     * @brief report event to dfx
     */
    void ReportSysEvent(const sptr<ReminderRequest>& reminder);
    void ReportTimerEvent(const int64_t targetTime, const bool isSysTimeChanged);
    void ReportUserDataSizeEvent();

    /**
     * @brief Create load reminder timer.
     */
    uint64_t CreateTimer(const sptr<MiscServices::TimeServiceClient>& timer);

    /**
     * @brief Load reminder from datashare.
     */
    void LoadShareReminders();

    /**
     * @brief Load reminder from datashare.
     */
    void UpdateShareReminders(const std::map<std::string, sptr<ReminderRequest>>& reminders);

    /**
     * @brief Single reminder display limit check.
     *
     * @param limits Limit on the number of single applications at the same time.
     * @param bundleLimits Notification limit for a single app.
     * @param totalCount Total number of notifications displayed at one time.
     */
    bool CheckShowLimit(ShowLimit& limits, sptr<ReminderRequest>& reminder);

    void UpdateReminderFromDb(const std::vector<sptr<ReminderRequest>>& remindersFromDb);
    ErrCode CancelReminderToDb(const int32_t reminderId, const int32_t callingUid);

    /**
     * @brief Synchronously close shared reminders with the same notificationId within the next 24 hours.
     *
     * When the user clicks the "close" button for a shared reminder, this function locates
     * other reminders that are:
     *  - shared reminder
     *  - have the same notificationId, and
     *  - scheduled to trigger within the next 24 hours (relative to the current system time).
     */
    void CheckAndCloseShareReminder(const sptr<ReminderRequest>& reminder);

    /**
     * @brief Collapse the notification panel, send event to sceneboard.
     */
    void CollapseNotificationPanel();

   /**
    * Single instance.
    */
    static std::shared_ptr<ReminderDataManager> REMINDER_DATA_MANAGER;

    /**
     * Used for multi-thread synchronise.
     */
    static std::mutex MUTEX;
    static std::mutex SHOW_MUTEX;
    static std::mutex TIMER_MUTEX;
    static std::mutex ACTIVE_MUTEX;
    std::mutex cancelMutex_; // for cancelReminder function

    /**
     * Max number of reminders limit for the whole system.
     */
    static constexpr int16_t MAX_NUM_REMINDER_LIMIT_SYSTEM = 12000;

    /**
     * Max number of reminders limit for one system application.
     */
    static constexpr int16_t MAX_NUM_REMINDER_LIMIT_SYS_APP = 10000;

    /**
     * Max number of reminders limit for one application.
     */
    static constexpr int16_t MAX_NUM_REMINDER_LIMIT_APP = 64;

    bool isReminderAgentReady_ = false;

    // first recv UNLOCK_SCREEN event.
    std::atomic<bool> isScreenUnLocked_ {false};

    /**
     * Vector used to record all the reminders in system.
     */
    std::vector<sptr<ReminderRequest>> reminderVector_;

    /**
     * Vector used to record all the reminders which has been shown on panel.
     */
    std::vector<sptr<ReminderRequest>> showedReminderVector_;

    /**
     * This timer is used to control the triggerTime of next reminder.
     */
    uint64_t timerId_ {0};

    /**
     * This timer is used to control the ringDuration of the alerting reminder.
     */
    std::atomic<uint64_t> timerIdAlerting_ {0};

    /**
     * Indicates the active reminder that timing is taking effect.
     */
    std::atomic<int32_t> activeReminderId_ = -1;
    std::atomic<uint64_t> activeTriggerTime_ = 0;
    sptr<ReminderRequest> activeReminder_ = nullptr;

    /**
     * Indicates the reminder which is playing sound or vibration.
     */
    std::mutex alertMutex_;
    std::atomic<int32_t> alertingReminderId_ = -1;
    std::atomic<bool> alertingIdIsShared_ = false;
    sptr<ReminderRequest> alertingReminder_ = nullptr;
#ifdef PLAYER_FRAMEWORK_ENABLE
    std::shared_ptr<Media::Player> soundPlayer_;
    std::shared_ptr<Media::SystemSoundManager> systemSoundClient_;
    std::shared_ptr<Global::Resource::ResourceManager> soundResource_;
    std::shared_ptr<Global::Resource::ResourceManager> vibrationResource_;
    int32_t soundFd_ {-1};
    int32_t vibrationFd_ {-1};
    int64_t vibrationFileSize_ {-1};
    bool isVibration_ {false};
#endif
    /**
     * Indicates the total count of reminders in system.
     */
    int16_t totalCount_ {0};
    int currentUserId_ {0};
    std::shared_ptr<ReminderStore> store_ = nullptr;

    /**
     * Indicates config change observer for language
     */
    sptr<AppExecFwk::IConfigurationObserver> configChangeObserver_ = nullptr;

    /**
     * Indicates app mananger for get foreground application
     */
    std::mutex appMgrMutex_;
    sptr<AppExecFwk::IAppMgr> appMgrProxy_ = nullptr;

    /**
     * async queue
     */
    std::shared_ptr<ffrt::queue> queue_ = nullptr;

    /**
     * Sa ready flag
     */
    std::atomic<int32_t> saReadyFlag_{ 0 };

    std::mutex timeLoadMutex_;
    uint64_t reminderLoadtimerId_ {0};

    // Last time the calendardata was launched.
    std::atomic<int64_t> lastStartTime_ {0};
    std::shared_ptr<ReminderNotifyManager> notifyManager_;
};
}  // namespace OHOS
}  // namespace Notification
#endif  // BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_SERVICES_REMINDER_INCLUDE_REMINDER_DATA_MANAGER_H
