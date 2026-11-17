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

#ifndef WALLPAPER_EXTENSION_ABILITY_CONNECTION_H
#define WALLPAPER_EXTENSION_ABILITY_CONNECTION_H
#include "ability_connect_callback_interface.h"
#include "ability_connect_callback_stub.h"
#include "iremote_object.h"
#include "iremote_stub.h"
#include "nocopyable.h"

namespace OHOS {
namespace WallpaperMgrService {
class WallpaperService;
class WallpaperExtensionAbilityConnection : public AAFwk::AbilityConnectionStub {
public:
    WallpaperExtensionAbilityConnection(WallpaperService &wallpaperService) : wallpaperService_(wallpaperService)
    {
    }
    virtual ~WallpaperExtensionAbilityConnection() = default;

    void OnAbilityConnectDone(
        const AppExecFwk::ElementName &element, const sptr<IRemoteObject> &remoteObject, int32_t resultCode) override;
    void OnAbilityDisconnectDone(const AppExecFwk::ElementName &element, int32_t resultCode) override;

private:
    DISALLOW_COPY_AND_MOVE(WallpaperExtensionAbilityConnection);
    WallpaperService &wallpaperService_;
};
} // namespace WallpaperMgrService
} // namespace OHOS
#endif // WALLPAPER_EXTENSION_ABILITY_CONNECTION_H