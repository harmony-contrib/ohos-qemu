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

#ifndef BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_SERVICES_REMINDER_INCLUDE_REMINDER_AGENT_SERVICE_H
#define BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_SERVICES_REMINDER_INCLUDE_REMINDER_AGENT_SERVICE_H

#include <mutex>
#include <memory>
#include <vector>

#include "ffrt.h"
#include "reminder_agent_service_stub.h"

namespace OHOS::Notification {
class ReminderAgentService final : public ReminderAgentServiceStub,
    public std::enable_shared_from_this<ReminderAgentService> {
public:
    ~ReminderAgentService() override = default;

    /**
     * @brief Get the instance of service.
     *
     * @return Returns the instance.
     */
    static sptr<ReminderAgentService> GetInstance();

    /**
     * @brief Publishes a reminder request.
     *
     * @param reminder Identifies the reminder request that needs to be published.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode PublishReminder(const ReminderRequest& reminder, int32_t& reminderId) override;

    /**
     * @brief Updates a reminder request.
     *
     * @param reminderId Identifies the reminder id that needs to be updated.
     * @param reminder Identifies the reminder request that needs to be updated.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode UpdateReminder(const int32_t reminderId, const ReminderRequest& reminder) override;

    /**
     * @brief Cancel a reminder request.
     *
     * @param reminderId Identifies the reminder id that needs to be canceled.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode CancelReminder(const int32_t reminderId) override;

    /**
     * @brief Cancel all reminder requests.
     *
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode CancelAllReminders() override;

    /**
     * @brief Dismiss the currently displayed alert and only remove it from the Notification Center.
     *
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode CancelReminderOnDisplay(const int32_t reminderId) override;

    /**
     * @brief Get all valid reminder requests.
     *
     * @param reminders Identifies the list of all valid reminder requests.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode GetValidReminders(std::vector<ReminderRequestAdaptation>& reminders) override;

    /**
     * @brief Add exclude date for reminder.
     *
     * @param reminderId Identifies the reminder id.
     * @param date Identifies the exclude date.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode AddExcludeDate(const int32_t reminderId, const int64_t date) override;

    /**
     * @brief Clear exclude date for reminder.
     *
     * @param reminderId Identifies the reminder id.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode DelExcludeDates(const int32_t reminderId) override;

    /**
     * @brief Get exclude date for reminder.
     *
     * @param reminderId Identifies the reminder id.
     * @param dates Identifies the exclude dates.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode GetExcludeDates(const int32_t reminderId, std::vector<int64_t>& dates) override;

    /**
     * @brief Register reminder state.
     *
     * @param object Identifies the callback.
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode RegisterReminderState(const sptr<IRemoteObject>& object) override;

    /**
     * @brief UnRegister reminder state.
     *
     * @return Returns ERR_OK on success, others on failure.
     */
    ErrCode UnRegisterReminderState() override;

    /**
     * @brief Post unload services task.
     */
    void TryPostDelayUnloadTask(const int64_t delayTime);

private:
    ReminderAgentService() = default;
    DISALLOW_COPY_AND_MOVE(ReminderAgentService);

    void TryUnloadService();
    void ChangeReminderAgentLoadConfig(const int8_t reminderAgentState);

    /**
     * @brief Create reminder request pointer.
     */
    sptr<ReminderRequest> CreateReminderRequest(const ReminderRequest& reminder);

    /**
     * @brief Init reminder info.
     */
    ErrCode InitReminderRequest(sptr<ReminderRequest>& reminder, const std::string& bundle,
        const int32_t callingUid);

    /**
     * @brief Check reminder permission.
     */
    bool CheckReminderPermission();

    /**
     * @brief Check caller is sysytem app.
     */
    bool IsSystemApp();

private:
    std::mutex unloadMutex_;  // for tryUnloadTask_
    ffrt::task_handle tryUnloadTask_ {nullptr};
    static std::mutex instanceMutex_;  // for instance_
    static sptr<ReminderAgentService> instance_;
    int8_t reminderAgentState_ {-1};
};
}  // namespace OHOS::Notification

#endif  // BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_SERVICES_REMINDER_INCLUDE_REMINDER_AGENT_SERVICE_H
