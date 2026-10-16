/*
 * Copyright (c) 2024 Huawei Device Co., Ltd.
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

#ifndef BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_REMINDER_INCLUDE_REMINDER_CALENDAR_SHARE_TABLE_H
#define BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_REMINDER_INCLUDE_REMINDER_CALENDAR_SHARE_TABLE_H

#include <cstdint>

namespace OHOS::Notification {
class ReminderCalendarShareTable {
public:
    static constexpr const char* ID = "_id";
    static constexpr const char* EVENT_ID = "event_id";
    static constexpr const char* END = "end";
    static constexpr const char* ALARM_TIME = "alarmTime";
    static constexpr const char* STATE = "state";
    static constexpr const char* TITLE = "title";
    static constexpr const char* CONTENT = "content";
    static constexpr const char* WANT_AGENT = "wantAgent";
    static constexpr const char* BUTTONS = "buttons";
    static constexpr const char* SLOT_TYPE = "slotType";
    static constexpr const char* KEEP_HEADSUP = "keepHeadsUp";
    static constexpr const char* IDENTIFIER = "identifier";
    static constexpr const char* TIME_INTERVAL = "timeInterval";
    static constexpr const char* SNOOZE_TIMES = "snoozeTimes";
    static constexpr const char* RING_DURATION = "ringDuration";
    static constexpr const char* SNOOZE_SLOT_TYPE = "snoozeSlotType";
    static constexpr const char* SNOOZE_CONTENT = "snoozeContent";
    static constexpr const char* EXPIRED_CONTENT = "expiredContent";
    static constexpr const char* MAX_SCREEN_WANT_AGENT = "maxScreenWantAgent";
    static constexpr const char* CUSTOM_RING_URI = "customRingUri";
    static constexpr const char* NEED_AGENT = "needAgent";

    static constexpr const char* PROXY = "datashareproxy://com.ohos.calendardata/CalendarAlerts";
    static constexpr const char* NAME = "com.ohos.calendar";
    static constexpr const char* DATA_NAME = "com.ohos.calendardata";
    static constexpr const char* ENTRY = "ReminderCallbackExtAbility";
    static constexpr const char* MAIN_ABILITY = "MainAbility";

    static constexpr const char* PARAM_CALLBACK_TYPE = "CallbackType";

    /**
     * @brief An alert begins in this state when it is first created.
     */
    static constexpr int8_t STATE_SCHEDULED = 0;
    /**
     * @brief After a notification for an alert has been created it should be updated to fired.
     */
    static constexpr int8_t STATE_FIRED = 1;
    /**
     * @brief Once the user has dismissed the notification the alert's state should be set to
     * dismissed so it is not fired again.
     */
    static constexpr int8_t STATE_DISMISSED = 2;

    /**
     * @brief Start calendardata reason: Device start or restart complete.
     */
    static constexpr int8_t START_BY_BOOT_COMPLETE = 0;
    /**
     * @brief Start calendardata reason: Time chage.
     */
    static constexpr int8_t START_BY_TIME_CHANGE = 1;
    /**
     * @brief Start calendardata reason: Time zone chage.
     */
    static constexpr int8_t START_BY_TIMEZONE_CHANGE = 2;
    /**
     * @brief Start calendardata reason: Timer.
     */
    static constexpr int8_t START_BY_NORMAL = 3;
    /**
     * @brief Start calendardata reason: Language change.
     */
    static constexpr int8_t START_BY_LANGUAGE_CHANGE = 4;
};
}  // namespace OHOS::Notification
#endif  // BASE_NOTIFICATION_DISTRIBUTED_NOTIFICATION_SERVICE_REMINDER_INCLUDE_REMINDER_CALENDAR_SHARE_TABLE_H