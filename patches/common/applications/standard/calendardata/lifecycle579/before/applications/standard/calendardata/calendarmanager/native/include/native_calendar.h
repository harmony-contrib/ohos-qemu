/*
 * Copyright (c) 2023 Huawei Device Co., Ltd.
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

#ifndef NATIVE_CALENDAR_H
#define NATIVE_CALENDAR_H
#include <vector>
#include <set>
#include "calendar_define.h"
#include "event_filter.h"
#include "uri.h"
using Uri = OHOS::Uri;
namespace OHOS::CalendarApi::Native {
class Calendar final {
public:
    Calendar(int id);
    Calendar(CalendarAccount account, int id);
    Calendar(Calendar&& other) : m_account(std::move(other.m_account)), m_id(other.m_id)
    {
    }
    Calendar(const Calendar& other) : m_account(other.m_account), m_id(other.m_id)
    {
    }

    Calendar() = delete;
    ~Calendar() = default;
    Result<int> AddEvent(const Event& event);
    Result<int> AddEvents(const std::vector<Event>& events);
    Result<bool> DeleteEvent(int id);
    Result<int> DeleteEvents(const std::vector<int>& id);
    void DeleteAllEvents();
    Result<bool> UpdateEvent(const Event& event);
    int UpdateEvents(const std::vector<Event>& events);
    CalendarConfig GetConfig();
    Result<bool> SetConfig(const CalendarConfig& config);
    Result<std::vector<Event>> GetEvents(std::shared_ptr<EventFilter> filter,
     const std::vector<string>& eventKey);
    void BatchGetEvents(std::vector<Event> &events, const std::set<string> &resultSetField,
     const std::vector<std::string> &eventIds);
    void GetAttendeesByEventIds(const std::vector<std::string> &ids,
     std::vector<Event> &events);
    void GetRemindersByEventIds(const std::vector<std::string> &ids, std::vector<Event> &events);
    void InsertReminders(int eventId, vector<int> reminders);
    Result<int> AddEventInfo(const Event& event, int channelId);
    Result<std::vector<Event>> QueryEventInstances(int64_t start, int64_t end, const std::vector<int> &ids,
     const std::vector<string>& eventKey);
    void FillEventsInfo(const std::vector<std::string> &eventIds, std::vector<Event> &events,
     const std::set<std::string>& resultSetField);
    CalendarAccount GetAccount() const
    {
        return m_account;
    }
    int GetId() const
    {
        return m_id;
    }
private:
    CalendarAccount m_account = {"", "", std::nullopt};
    CalendarConfig m_config = {true, 0};
    int m_id = 0;
    std::unique_ptr<Uri> m_eventUri = nullptr;
    std::unique_ptr<Uri> m_attendeeUri = nullptr;
    std::unique_ptr<Uri> m_calendarUri = nullptr;
    std::unique_ptr<Uri> m_reminderUrl = nullptr;
    std::unique_ptr<Uri> m_instanceUrl = nullptr;
};
}  // namespace OHOS::Calendar
#endif  //  NATIVE_CALENDAR_H