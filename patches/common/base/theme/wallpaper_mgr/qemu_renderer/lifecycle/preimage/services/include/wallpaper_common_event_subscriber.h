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
#ifndef WALLPAPER_SERVICES_WALLPAPER_COMMON_EVENT_H
#define WALLPAPER_SERVICES_WALLPAPER_COMMON_EVENT_H

#include <string>

#include "common_event_manager.h"
#include "common_event_subscriber.h"
#include "common_event_support.h"

namespace OHOS {
namespace WallpaperMgrService {
using CommonEventSubscriber = OHOS::EventFwk::CommonEventSubscriber;
using CommonEventData = OHOS::EventFwk::CommonEventData;
using CommonEventSubscribeInfo = OHOS::EventFwk::CommonEventSubscribeInfo;
class WallpaperService;

class WallpaperCommonEventSubscriber : public OHOS::EventFwk::CommonEventSubscriber {
public:
    WallpaperCommonEventSubscriber(WallpaperService &wallpaperService)
        : CommonEventSubscriber(CreateSubscriberInfo()), wallpaperService_(wallpaperService)
    {
    }
    ~WallpaperCommonEventSubscriber() = default;

    void OnReceiveEvent(const OHOS::EventFwk::CommonEventData &data) override;

private:
    OHOS::EventFwk::CommonEventSubscribeInfo CreateSubscriberInfo();

    WallpaperService &wallpaperService_;
};
} // namespace WallpaperMgrService
} // namespace OHOS

#endif