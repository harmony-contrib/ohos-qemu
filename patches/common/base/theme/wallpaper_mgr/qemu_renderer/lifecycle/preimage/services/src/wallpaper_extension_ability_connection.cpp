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
#include "hilog_wrapper.h"
#include "wallpaper_extension_ability_connection.h"
#include "wallpaper_service.h"

namespace OHOS {
namespace WallpaperMgrService {
using namespace AAFwk;

void WallpaperExtensionAbilityConnection::OnAbilityConnectDone(
    const AppExecFwk::ElementName &element, const sptr<IRemoteObject> &remoteObject, int32_t resultCode)
{
    HILOG_INFO("on ability connected.");
    wallpaperService_.AddWallpaperExtensionDeathRecipient(remoteObject);
}

void WallpaperExtensionAbilityConnection::OnAbilityDisconnectDone(
    const AppExecFwk::ElementName &element, int32_t resultCode)
{
    HILOG_INFO("on ability disconnected.");
}
} // namespace WallpaperMgrService
} // namespace OHOS