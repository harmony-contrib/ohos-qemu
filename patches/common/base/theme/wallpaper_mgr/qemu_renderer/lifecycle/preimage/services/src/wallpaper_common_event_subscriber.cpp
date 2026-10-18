/*
 * Copyright (C) 2022 Huawei Device Co., Ltd.
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

#include "hilog_wrapper.h"
#include "wallpaper_common_event_subscriber.h"
#include "wallpaper_service.h"

namespace OHOS {
namespace WallpaperMgrService {

void WallpaperCommonEventSubscriber::OnReceiveEvent(const OHOS::EventFwk::CommonEventData &data)
{
    HILOG_INFO("WallpaperCommonEvent::OnReceiveEvent.");
    auto want = data.GetWant();
    std::string action = want.GetAction();
    if (action == EventFwk::CommonEventSupport::COMMON_EVENT_USER_ADDED) {
        wallpaperService_.OnInitUser(data.GetCode());
    } else if (action == EventFwk::CommonEventSupport::COMMON_EVENT_USER_REMOVED) {
        wallpaperService_.OnRemovedUser(data.GetCode());
    } else if (action == EventFwk::CommonEventSupport::COMMON_EVENT_USER_SWITCHED) {
        wallpaperService_.OnSwitchedUser(data.GetCode());
    }
}

CommonEventSubscribeInfo WallpaperCommonEventSubscriber::CreateSubscriberInfo()
{
    OHOS::EventFwk::MatchingSkills matchingSkills;
    matchingSkills.AddEvent(EventFwk::CommonEventSupport::COMMON_EVENT_USER_ADDED);
    matchingSkills.AddEvent(EventFwk::CommonEventSupport::COMMON_EVENT_USER_REMOVED);
    matchingSkills.AddEvent(EventFwk::CommonEventSupport::COMMON_EVENT_USER_SWITCHED);
    return CommonEventSubscribeInfo(matchingSkills);
}
} // namespace WallpaperMgrService
} // namespace OHOS