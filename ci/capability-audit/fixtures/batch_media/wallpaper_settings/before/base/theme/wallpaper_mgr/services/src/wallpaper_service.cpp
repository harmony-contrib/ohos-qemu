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
#include "wallpaper_service.h"

#include <fcntl.h>
#include <sys/prctl.h>
#include <sys/sendfile.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <thread>

#include "cJSON.h"
#include "color.h"
#include "color_picker.h"
#include "config_policy_utils.h"
#include "dump_helper.h"
#include "effect_errors.h"
#include "file_ex.h"
#include "hilog_wrapper.h"
#include "hitrace_meter.h"
#include "image_packer.h"
#include "image_source.h"
#include "image_type.h"
#include "mem_mgr_client.h"
#include "mem_mgr_proxy.h"
#include "memory_guard.h"
#include "parameter.h"
#include "pixel_map.h"
#include "scene_board_judgement.h"
#include "system_ability_definition.h"
#include "tokenid_kit.h"
#include "wallpaper_common.h"
#include "wallpaper_common_event_manager.h"
#include "wallpaper_manager_common_info.h"
#include "wallpaper_service_cb_proxy.h"

#ifndef THEME_SERVICE
#include "ability_manager_client.h"
#include "wallpaper_extension_ability_death_recipient.h"
#endif

namespace OHOS {
namespace WallpaperMgrService {
REGISTER_SYSTEM_ABILITY_BY_ID(WallpaperService, WALLPAPER_MANAGER_SERVICE_ID, true);

using namespace OHOS::Media;
using namespace OHOS::MiscServices;
using namespace OHOS::Security::AccessToken;
using namespace OHOS::AccountSA;

constexpr const char *WALLPAPER_SYSTEM_ORIG = "wallpaper_system_orig";
constexpr const char *WALLPAPER_HOME = "wallpaper_home";
constexpr const char *WALLPAPER_LOCK_ORIG = "wallpaper_lock_orig";
constexpr const char *WALLPAPER_LOCK = "wallpaper_lock";
constexpr const char *LIVE_WALLPAPER_SYSTEM_ORIG = "live_wallpaper_system_orig";
constexpr const char *LIVE_WALLPAPER_LOCK_ORIG = "live_wallpaper_lock_orig";
constexpr const char *CUSTOM_WALLPAPER_LOCK = "custom_lock.zip";
constexpr const char *CUSTOM_WALLPAPER_SYSTEM = "custom_system.zip";
constexpr const char *OHOS_WALLPAPER_BUNDLE_NAME = "com.ohos.launcher";
constexpr const char *SHOW_SYSTEM_SCREEN = "SHOW_SYSTEMSCREEN";
constexpr const char *SHOW_LOCK_SCREEN = "SHOW_LOCKSCREEN";
constexpr const char *SYSTEM_RES_TYPE = "SystemResType";
constexpr const char *LOCKSCREEN_RES_TYPE = "LockScreenResType";
constexpr const char *WALLPAPER_CHANGE = "wallpaperChange";
constexpr const char *COLOR_CHANGE = "colorChange";
constexpr const char *SCENEBOARD_BUNDLE_NAME = "com.ohos.sceneboard";

constexpr const char *WALLPAPER_USERID_PATH = "/data/service/el1/public/wallpaper/";
constexpr const char *WALLPAPER_SYSTEM_DIRNAME = "system";
constexpr const char *WALLPAPER_TMP_DIRNAME = "fwsettmp";
constexpr const char *WALLPAPER_LOCKSCREEN_DIRNAME = "lockscreen";
constexpr const char *WALLPAPER_DEFAULT_FILEFULLPATH = "/system/etc/wallpaperdefault.jpeg";
constexpr const char *WALLPAPER_DEFAULT_LOCK_FILEFULLPATH = "/system/etc/wallpaperlockdefault.jpeg";
constexpr const char *WALLPAPER_CROP_PICTURE = "crop_file";
constexpr const char *RESOURCE_PATH = "resource/themes/theme/";
constexpr const char *DEFAULT_PATH = "default/";
constexpr const char *MANIFEST = "manifest.json";
constexpr const char *RES = "resources/";
constexpr const char *HOME = "home/";
constexpr const char *LOCK = "lock/";
constexpr const char *BASE = "base/";
constexpr const char *LAND_PATH = "land/";
constexpr const char *HOME_UNFOLDED = "home/unfolded/";
constexpr const char *HOME_UNFOLDED2 = "home/unfolded2/";
constexpr const char *LOCK_UNFOLDED = "lock/unfolded/";
constexpr const char *LOCK_UNFOLDED2 = "lock/unfolded2/";
constexpr const char *IMAGE = "image";
constexpr const char *SRC = "src";
constexpr const char *NORMAL_LAND_WALLPAPER_HOME = "normal_land_wallpaper_home";
constexpr const char *UNFOLD1_PORT_WALLPAPER_HOME = "unfold1_port_wallpaper_home";
constexpr const char *UNFOLD1_LAND_WALLPAPER_HOME = "unfold1_land_wallpaper_home";
constexpr const char *UNFOLD2_PORT_WALLPAPER_HOME = "unfold2_port_wallpaper_home";
constexpr const char *UNFOLD2_LAND_WALLPAPER_HOME = "unfold2_land_wallpaper_home";
constexpr const char *NORMAL_LAND_WALLPAPER_LOCK = "normal_land_wallpaper_lock";
constexpr const char *UNFOLD1_PORT_WALLPAPER_LOCK = "unfold1_port_wallpaper_lock";
constexpr const char *UNFOLD1_LAND_WALLPAPER_LOCK = "unfold1_land_wallpaper_lock";
constexpr const char *UNFOLD2_PORT_WALLPAPER_LOCK = "unfold2_port_wallpaper_lock";
constexpr const char *UNFOLD2_LAND_WALLPAPER_LOCK = "unfold2_land_wallpaper_lock";
constexpr int64_t INIT_INTERVAL = 10000L;
constexpr int64_t DELAY_TIME = 1000L;
constexpr int64_t QUERY_USER_ID_INTERVAL = 300L;
constexpr int32_t FOO_MAX_LEN = 52428800;
constexpr int32_t MAX_RETRY_TIMES = 20;
constexpr int32_t QUERY_USER_MAX_RETRY_TIMES = 100;
constexpr int32_t DEFAULT_WALLPAPER_ID = -1;
constexpr int32_t DEFAULT_USER_ID = 0;
constexpr int32_t MAX_VIDEO_SIZE = 104857600;
constexpr int32_t OPTION_QUALITY = 100;
constexpr int32_t COMPRESSION_RATIO = 8;
constexpr int32_t MIN_SIZE = 64;

#ifndef THEME_SERVICE
constexpr int32_t CONNECT_EXTENSION_INTERVAL = 100;
constexpr int32_t DEFAULT_VALUE = -1;
constexpr int32_t CONNECT_EXTENSION_MAX_RETRY_TIMES = 50;
#endif

std::shared_ptr<AppExecFwk::EventHandler> WallpaperService::serviceHandler_;

WallpaperService::WallpaperService(int32_t systemAbilityId, bool runOnCreate)
    : SystemAbility(systemAbilityId, runOnCreate), WallpaperServiceStub(true),
      state_(ServiceRunningState::STATE_NOT_START)
{
}

WallpaperService::WallpaperService() : WallpaperServiceStub(true), state_(ServiceRunningState::STATE_NOT_START)
{
}

WallpaperService::~WallpaperService()
{
}

int32_t WallpaperService::Init()
{
    InitQueryUserId(QUERY_USER_MAX_RETRY_TIMES);
    bool ret = Publish(this);
    if (!ret) {
        HILOG_ERROR("Publish failed!");
        ReporterFault(FaultType::SERVICE_FAULT, FaultCode::SF_SERVICE_UNAVAILABLE);
        return -1;
    }
    HILOG_INFO("Publish success.");
    state_.store(ServiceRunningState::STATE_RUNNING);
#ifndef THEME_SERVICE
    StartExtensionAbility(CONNECT_EXTENSION_MAX_RETRY_TIMES);
#endif
    return NO_ERROR;
}

void WallpaperService::OnStart()
{
    HILOG_INFO("Enter OnStart.");
    MemoryGuard cacheGuard;
    if (state_.load() == ServiceRunningState::STATE_RUNNING) {
        HILOG_ERROR("WallpaperService is already running.");
        return;
    }
    InitData();
    InitServiceHandler();
    AddSystemAbilityListener(COMMON_EVENT_SERVICE_ID);
    AddSystemAbilityListener(MEMORY_MANAGER_SA_ID);
    auto cmd = std::make_shared<Command>(std::vector<std::string>({ "-all" }), "Show all",
        [this](const std::vector<std::string> &input, std::string &output) -> bool {
            output.append(
                "WallpaperExtensionAbility\t: ExtensionInfo{" + std::string(OHOS_WALLPAPER_BUNDLE_NAME) + "}\n");
            return true;
        });
    DumpHelper::GetInstance().RegisterCommand(cmd);
    if (Init() != NO_ERROR) {
        auto callback = [=]() { Init(); };
        serviceHandler_->PostTask(callback, INIT_INTERVAL);
        HILOG_ERROR("Init failed. Try again 10s later.");
    }
    return;
}

void WallpaperService::OnAddSystemAbility(int32_t systemAbilityId, const std::string &deviceId)
{
    HILOG_INFO("OnAddSystemAbility systemAbilityId:%{public}d added!", systemAbilityId);
    if (systemAbilityId == COMMON_EVENT_SERVICE_ID) {
        int32_t times = 0;
        RegisterSubscriber(times);
    } else if (systemAbilityId == MEMORY_MANAGER_SA_ID) {
        int32_t pid = getpid();
        Memory::MemMgrClient::GetInstance().NotifyProcessStatus(pid, 1, 1, WALLPAPER_MANAGER_SERVICE_ID);
    }
}

void WallpaperService::RegisterSubscriber(int32_t times)
{
    MemoryGuard cacheGuard;
    times++;
    bool subRes = false;
    {
        std::lock_guard<std::mutex> lock(subscriberMutex_);
        subscriber_ = std::make_shared<WallpaperCommonEventSubscriber>(*this);
        subRes = OHOS::EventFwk::CommonEventManager::SubscribeCommonEvent(subscriber_);
    }
    if (!subRes && times <= MAX_RETRY_TIMES) {
        HILOG_INFO("RegisterSubscriber failed!");
        auto callback = [this, times]() { RegisterSubscriber(times); };
        serviceHandler_->PostTask(callback, DELAY_TIME);
    }
}

void WallpaperService::InitServiceHandler()
{
    HILOG_INFO("InitServiceHandler started.");
    if (serviceHandler_ != nullptr) {
        HILOG_ERROR("InitServiceHandler already init.");
        return;
    }
    std::shared_ptr<AppExecFwk::EventRunner> runner =
        AppExecFwk::EventRunner::Create("WallpaperService", AppExecFwk::ThreadMode::FFRT);
    serviceHandler_ = std::make_shared<AppExecFwk::EventHandler>(runner);
}

void WallpaperService::OnStop()
{
    HILOG_INFO("OnStop started.");
    if (state_.load() != ServiceRunningState::STATE_RUNNING) {
        HILOG_ERROR("WallpaperService is not already running.");
        return;
    }
    serviceHandler_ = nullptr;
#ifndef THEME_SERVICE
    connection_ = nullptr;
#endif
    {
        std::lock_guard<std::mutex> lock(remoteObjectMutex_);
        recipient_ = nullptr;
        extensionRemoteObject_ = nullptr;
    }
    {
        std::lock_guard<std::mutex> lock(subscriberMutex_);
        if (subscriber_ != nullptr) {
            bool unSubscribeResult = OHOS::EventFwk::CommonEventManager::UnSubscribeCommonEvent(subscriber_);
            subscriber_ = nullptr;
            HILOG_INFO("UnregisterSubscriber end, unSubscribeResult = %{public}d", unSubscribeResult);
        }
    }
    state_.store(ServiceRunningState::STATE_NOT_START);
    int32_t pid = getpid();
    Memory::MemMgrClient::GetInstance().NotifyProcessStatus(pid, 1, 0, WALLPAPER_MANAGER_SERVICE_ID);
}

void WallpaperService::InitData()
{
    HILOG_INFO("WallpaperService::initData --> start.");
    wallpaperId_ = DEFAULT_WALLPAPER_ID;
    int32_t userId = DEFAULT_USER_ID;
    systemWallpaperMap_.Clear();
    lockWallpaperMap_.Clear();
    wallpaperTmpFullPath_ = std::string(WALLPAPER_USERID_PATH) + std::string(WALLPAPER_TMP_DIRNAME);
    wallpaperCropPath_ = std::string(WALLPAPER_USERID_PATH) + std::string(WALLPAPER_CROP_PICTURE);
    {
        std::lock_guard<std::mutex> lock(wallpaperColorMtx_);
        systemWallpaperColor_ = 0;
        lockWallpaperColor_ = 0;
    }
    currentUserId_ = userId;
    {
        std::lock_guard<std::mutex> autoLock(listenerMapMutex_);
        wallpaperEventMap_.clear();
    }
    appBundleName_ = SCENEBOARD_BUNDLE_NAME;
    InitUserDir(userId);
    UpdataWallpaperMap(userId, WALLPAPER_SYSTEM);
    UpdataWallpaperMap(userId, WALLPAPER_LOCKSCREEN);
    LoadWallpaperState();
    ClearRedundantFile(userId, WALLPAPER_SYSTEM, WALLPAPER_SYSTEM_ORIG);
    ClearRedundantFile(userId, WALLPAPER_LOCKSCREEN, WALLPAPER_LOCK_ORIG);
}

#ifndef THEME_SERVICE
void WallpaperService::AddWallpaperExtensionDeathRecipient(const sptr<IRemoteObject> &remoteObject)
{
    if (remoteObject != nullptr) {
        std::lock_guard<std::mutex> lock(remoteObjectMutex_);
        IPCObjectProxy *proxy = reinterpret_cast<IPCObjectProxy *>(remoteObject.GetRefPtr());
        if (recipient_ == nullptr) {
            recipient_ = sptr<IRemoteObject::DeathRecipient>(new WallpaperExtensionAbilityDeathRecipient(*this));
        }
        if (proxy != nullptr && !proxy->IsObjectDead()) {
            HILOG_INFO("get remoteObject succeed.");
            proxy->AddDeathRecipient(recipient_);
            extensionRemoteObject_ = remoteObject;
        }
    }
}
#endif

void WallpaperService::RemoveExtensionDeathRecipient()
{
    std::lock_guard<std::mutex> lock(remoteObjectMutex_);
    if (extensionRemoteObject_ != nullptr && recipient_ != nullptr) {
        HILOG_INFO("Remove Extension DeathRecipient.");
        extensionRemoteObject_->RemoveDeathRecipient(recipient_);
        recipient_ = nullptr;
        extensionRemoteObject_ = nullptr;
    }
}

void WallpaperService::InitQueryUserId(int32_t times)
{
    times--;
    bool ret = InitUsersOnBoot();
    if (!ret && times > 0) {
        HILOG_DEBUG("InitQueryUserId failed!");
        auto callback = [this, times]() { InitQueryUserId(times); };
        serviceHandler_->PostTask(callback, QUERY_USER_ID_INTERVAL);
    }
}

#ifndef THEME_SERVICE
void WallpaperService::StartExtensionAbility(int32_t times)
{
    times--;
    bool ret = ConnectExtensionAbility();
    if (!ret && times > 0 && serviceHandler_ != nullptr) {
        HILOG_ERROR("StartExtensionAbilty failed, remainder of the times: %{public}d", times);
        auto callback = [this, times]() { StartExtensionAbility(times); };
        serviceHandler_->PostTask(callback, CONNECT_EXTENSION_INTERVAL);
    }
}
#endif

bool WallpaperService::InitUsersOnBoot()
{
    std::vector<AccountSA::OsAccountInfo> osAccountInfos;
    ErrCode errCode = AccountSA::OsAccountManager::QueryAllCreatedOsAccounts(osAccountInfos);
    if (errCode != ERR_OK || osAccountInfos.empty()) {
        HILOG_ERROR("Query all created userIds failed, errCode:%{public}d", errCode);
        return false;
    }
    for (const auto &osAccountInfo : osAccountInfos) {
        int32_t userId = osAccountInfo.GetLocalId();
        HILOG_INFO("InitUsersOnBoot Current userId: %{public}d", userId);
        InitUserDir(userId);
        UpdataWallpaperMap(userId, WALLPAPER_SYSTEM);
        UpdataWallpaperMap(userId, WALLPAPER_LOCKSCREEN);
        ClearRedundantFile(userId, WALLPAPER_SYSTEM, WALLPAPER_SYSTEM_ORIG);
        ClearRedundantFile(userId, WALLPAPER_LOCKSCREEN, WALLPAPER_LOCK_ORIG);
    }
    return true;
}

void WallpaperService::ClearRedundantFile(int32_t userId, WallpaperType wallpaperType, std::string fileName)
{
    HILOG_DEBUG("ClearRedundantFile Current userId: %{public}d", userId);
    std::string wallpaperFilePath = GetWallpaperDir(userId, wallpaperType) + "/" + fileName;
    FileDeal::DeleteFile(wallpaperFilePath);
}

void WallpaperService::OnInitUser(int32_t userId)
{
    if (userId < 0) {
        HILOG_ERROR("userId error, userId = %{public}d", userId);
        return;
    }
    std::string userDir = WALLPAPER_USERID_PATH + std::to_string(userId);
    if (FileDeal::IsFileExist(userDir)) {
        std::lock_guard<std::mutex> lock(mtx_);
        if (!FileDeal::DeleteDir(userDir, true)) {
            HILOG_ERROR("Force remove user directory path failed, errno %{public}d", errno);
            return;
        }
    }
    if (!InitUserDir(userId)) {
        return;
    }
    UpdataWallpaperMap(userId, WALLPAPER_SYSTEM);
    UpdataWallpaperMap(userId, WALLPAPER_LOCKSCREEN);
    HILOG_INFO("OnInitUser success, userId = %{public}d", userId);
}

bool WallpaperService::InitUserDir(int32_t userId)
{
    std::string userDir = WALLPAPER_USERID_PATH + std::to_string(userId);
    if (!FileDeal::Mkdir(userDir)) {
        HILOG_ERROR("Failed to create destination path, userId:%{public}d", userId);
        return false;
    }
    std::string wallpaperSystemFilePath = userDir + "/" + WALLPAPER_SYSTEM_DIRNAME;
    if (!FileDeal::Mkdir(wallpaperSystemFilePath)) {
        HILOG_ERROR("Failed to create destination wallpaper system path, userId:%{public}d, type:%{public}s.", userId,
            WALLPAPER_SYSTEM_DIRNAME);
        return false;
    }
    std::string wallpaperLockScreenFilePath = userDir + "/" + WALLPAPER_LOCKSCREEN_DIRNAME;
    if (!FileDeal::Mkdir(wallpaperLockScreenFilePath)) {
        HILOG_ERROR("Failed to create destination wallpaper lockscreen path, userId:%{public}d, type:%{public}s.",
            userId, WALLPAPER_LOCKSCREEN_DIRNAME);
        return false;
    }
    return true;
}

bool WallpaperService::RestoreUserResources(int32_t userId, WallpaperData &wallpaperData, WallpaperType wallpaperType)
{
    if (!FileDeal::DeleteDir(GetWallpaperDir(userId, wallpaperType), false)) {
        HILOG_ERROR("delete resources failed, userId:%{public}d, wallpaperType:%{public}d.", userId, wallpaperType);
        return false;
    }
    std::string wallpaperPath = GetWallpaperDir(userId, wallpaperType);
    wallpaperData = GetWallpaperDefaultPath(wallpaperType);
    wallpaperData.userId = userId;
    wallpaperData.allowBackup = true;
    wallpaperData.resourceType = PICTURE;
    wallpaperData.wallpaperId = DEFAULT_WALLPAPER_ID;
    wallpaperData.liveWallpaperFile =
        wallpaperPath + "/"
        + (wallpaperType == WALLPAPER_SYSTEM ? LIVE_WALLPAPER_SYSTEM_ORIG : LIVE_WALLPAPER_LOCK_ORIG);
    wallpaperData.customPackageUri =
        wallpaperPath + "/" + (wallpaperType == WALLPAPER_SYSTEM ? CUSTOM_WALLPAPER_SYSTEM : CUSTOM_WALLPAPER_LOCK);
    if (wallpaperData.wallpaperFile.empty()) {
        HILOG_ERROR("get default path failed, userId:%{public}d, wallpaperType:%{public}d.", userId, wallpaperType);
        return false;
    }
    HILOG_INFO("Restore user resources end.");
    return true;
}

WallpaperData WallpaperService::GetWallpaperDefaultPath(WallpaperType wallpaperType)
{
    WallpaperData wallpaperData;
    std::string manifest = MANIFEST;
    std::string res = RES;
    std::string base = BASE;
    std::string land = LAND_PATH;
    if (wallpaperType == WallpaperType::WALLPAPER_SYSTEM) {
        wallpaperData.wallpaperFile = GetWallpaperPathInJson(HOME + manifest, HOME + base + res);
        wallpaperData.normalLandFile = GetWallpaperPathInJson(HOME + base + land + manifest, HOME + base + land + res);
        wallpaperData.unfoldedOnePortFile = GetWallpaperPathInJson(HOME_UNFOLDED + manifest, HOME_UNFOLDED + res);
        wallpaperData.unfoldedOneLandFile =
            GetWallpaperPathInJson(HOME_UNFOLDED + land + manifest, HOME_UNFOLDED + land + res);
        wallpaperData.unfoldedTwoPortFile = GetWallpaperPathInJson(HOME_UNFOLDED2 + manifest, HOME_UNFOLDED2 + res);
        wallpaperData.unfoldedTwoLandFile =
            GetWallpaperPathInJson(HOME_UNFOLDED2 + land + manifest, HOME_UNFOLDED2 + land + res);
    } else {
        wallpaperData.wallpaperFile = GetWallpaperPathInJson(LOCK + manifest, LOCK + base + res);
        wallpaperData.normalLandFile = GetWallpaperPathInJson(LOCK + base + land + manifest, LOCK + base + land + res);
        wallpaperData.unfoldedOnePortFile = GetWallpaperPathInJson(LOCK_UNFOLDED + manifest, LOCK_UNFOLDED + res);
        wallpaperData.unfoldedOneLandFile =
            GetWallpaperPathInJson(LOCK_UNFOLDED + land + manifest, LOCK_UNFOLDED + land + res);
        wallpaperData.unfoldedTwoPortFile = GetWallpaperPathInJson(LOCK_UNFOLDED2 + manifest, LOCK_UNFOLDED2 + res);
        wallpaperData.unfoldedTwoLandFile =
            GetWallpaperPathInJson(LOCK_UNFOLDED2 + land + manifest, LOCK_UNFOLDED2 + land + res);
    }
    if (wallpaperData.wallpaperFile.empty()) {
        wallpaperData.wallpaperFile = (wallpaperType == WallpaperType::WALLPAPER_SYSTEM)
                                          ? WALLPAPER_DEFAULT_FILEFULLPATH
                                          : WALLPAPER_DEFAULT_LOCK_FILEFULLPATH;
    }
    return wallpaperData;
}
void WallpaperService::OnRemovedUser(int32_t userId)
{
    if (userId < 0) {
        HILOG_ERROR("userId error, userId = %{public}d", userId);
        return;
    }
    ClearWallpaperLocked(userId, WALLPAPER_SYSTEM);
    ClearWallpaperLocked(userId, WALLPAPER_LOCKSCREEN);
    std::string userDir = WALLPAPER_USERID_PATH + std::to_string(userId);
    std::lock_guard<std::mutex> lock(mtx_);
    if (!FileDeal::DeleteDir(userDir, true)) {
        HILOG_ERROR("Force remove user directory path failed, errno %{public}d", errno);
    }
    HILOG_INFO("OnRemovedUser end, userId = %{public}d", userId);
}

void WallpaperService::OnSwitchedUser(int32_t userId)
{
    if (userId < 0) {
        HILOG_ERROR("userId error, userId = %{public}d", userId);
        return;
    }
    if (userId == currentUserId_) {
        HILOG_ERROR("userId not switch, userId = %{public}d", userId);
        return;
    }
    currentUserId_ = userId;
    RemoveExtensionDeathRecipient();
#ifndef THEME_SERVICE
    ConnectExtensionAbility();
#endif
    std::string userDir = WALLPAPER_USERID_PATH + std::to_string(userId);
    if (!FileDeal::IsFileExist(userDir)) {
        HILOG_INFO("User file is not exist, userId = %{public}d", userId);
        InitUserDir(userId);
        UpdataWallpaperMap(userId, WALLPAPER_SYSTEM);
        UpdataWallpaperMap(userId, WALLPAPER_LOCKSCREEN);
    }
    LoadWallpaperState();
    SendWallpaperChangeEvent(userId, WALLPAPER_SYSTEM);
    SendWallpaperChangeEvent(userId, WALLPAPER_LOCKSCREEN);
    SaveColor(userId, WALLPAPER_SYSTEM);
    SaveColor(userId, WALLPAPER_LOCKSCREEN);
    HILOG_INFO("OnSwitchedUser end, newUserId = %{public}d", userId);
}

std::string WallpaperService::GetWallpaperDir(int32_t userId, WallpaperType wallpaperType)
{
    std::string userIdPath = WALLPAPER_USERID_PATH + std::to_string(userId);
    std::string wallpaperFilePath;
    if (wallpaperType == WALLPAPER_SYSTEM) {
        wallpaperFilePath = userIdPath + "/" + WALLPAPER_SYSTEM_DIRNAME;
    } else if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        wallpaperFilePath = userIdPath + "/" + WALLPAPER_LOCKSCREEN_DIRNAME;
    }
    return wallpaperFilePath;
}

bool WallpaperService::GetFileNameFromMap(int32_t userId, WallpaperType wallpaperType, std::string &filePathName)
{
    auto iterator = wallpaperType == WALLPAPER_SYSTEM ? systemWallpaperMap_.Find(userId)
                                                      : lockWallpaperMap_.Find(userId);
    if (!iterator.first) {
        HILOG_ERROR("system wallpaper already cleared.");
        return false;
    }
    HILOG_DEBUG("GetFileNameFromMap resourceType : %{public}d", static_cast<int32_t>(iterator.second.resourceType));
    switch (iterator.second.resourceType) {
        case PICTURE:
            filePathName = iterator.second.wallpaperFile;
            break;
        case VIDEO:
            filePathName = iterator.second.liveWallpaperFile;
            break;
        case DEFAULT:
            filePathName = iterator.second.wallpaperFile;
            break;
        case PACKAGE:
            filePathName = iterator.second.customPackageUri;
            break;
        default:
            filePathName = "";
            break;
    }
    return filePathName != "";
}

bool WallpaperService::GetPictureFileName(int32_t userId, WallpaperType wallpaperType, std::string &filePathName)
{
    auto iterator = wallpaperType == WALLPAPER_SYSTEM ? systemWallpaperMap_.Find(userId)
                                                      : lockWallpaperMap_.Find(userId);
    if (!iterator.first) {
        HILOG_INFO("WallpaperType:%{public}d, WallpaperMap not found userId: %{public}d", wallpaperType, userId);
        OnInitUser(userId);
        iterator = wallpaperType == WALLPAPER_SYSTEM ? systemWallpaperMap_.Find(userId)
                                                     : lockWallpaperMap_.Find(userId);
    }
    filePathName = iterator.second.wallpaperFile;
    HILOG_INFO("GetPictureFileName filePathName : %{public}s", FileDeal::ToBeAnonymous(filePathName).c_str());
    return filePathName != "";
}

int32_t WallpaperService::MakeWallpaperIdLocked()
{
    HILOG_INFO("MakeWallpaperIdLocked start.");
    if (wallpaperId_ == INT32_MAX) {
        wallpaperId_ = DEFAULT_WALLPAPER_ID;
    }
    return ++wallpaperId_;
}

void WallpaperService::UpdataWallpaperMap(int32_t userId, WallpaperType wallpaperType)
{
    HILOG_INFO("updata wallpaperMap.");
    std::string wallpaperPath = GetWallpaperDir(userId, wallpaperType);
    std::string wallpaperFilePath =
        wallpaperPath + "/" + (wallpaperType == WALLPAPER_SYSTEM ? WALLPAPER_HOME : WALLPAPER_LOCK);
    ConcurrentMap<int32_t, WallpaperData> &wallpaperMap = [&]() -> ConcurrentMap<int32_t, WallpaperData>& {
        if (wallpaperType == WALLPAPER_SYSTEM) {
            return systemWallpaperMap_;
        } else {
            return lockWallpaperMap_;
        }
    }();
    auto wallpaperData = GetWallpaperDefaultPath(wallpaperType);
    wallpaperData.userId = userId;
    wallpaperData.allowBackup = true;
    wallpaperData.resourceType = PICTURE;
    wallpaperData.wallpaperId = DEFAULT_WALLPAPER_ID;
    wallpaperData.liveWallpaperFile =
        wallpaperPath + "/"
        + (wallpaperType == WALLPAPER_SYSTEM ? LIVE_WALLPAPER_SYSTEM_ORIG : LIVE_WALLPAPER_LOCK_ORIG);
    wallpaperData.customPackageUri =
        wallpaperPath + "/" + (wallpaperType == WALLPAPER_SYSTEM ? CUSTOM_WALLPAPER_SYSTEM : CUSTOM_WALLPAPER_LOCK);
    if (FileDeal::IsFileExist(wallpaperFilePath)) {
        wallpaperData.wallpaperFile = GetExistFilePath(
            wallpaperPath + "/" + (wallpaperType == WALLPAPER_SYSTEM ? WALLPAPER_HOME : WALLPAPER_LOCK));
        wallpaperData.normalLandFile = GetExistFilePath(
            wallpaperPath + "/"
            + (wallpaperType == WALLPAPER_SYSTEM ? NORMAL_LAND_WALLPAPER_HOME : NORMAL_LAND_WALLPAPER_LOCK));
        wallpaperData.unfoldedOnePortFile = GetExistFilePath(
            wallpaperPath + "/"
            + (wallpaperType == WALLPAPER_SYSTEM ? UNFOLD1_PORT_WALLPAPER_HOME : UNFOLD1_PORT_WALLPAPER_LOCK));
        wallpaperData.unfoldedOneLandFile = GetExistFilePath(
            wallpaperPath + "/"
            + (wallpaperType == WALLPAPER_SYSTEM ? UNFOLD1_LAND_WALLPAPER_HOME : UNFOLD1_LAND_WALLPAPER_LOCK));
        wallpaperData.unfoldedTwoPortFile = GetExistFilePath(
            wallpaperPath + "/"
            + (wallpaperType == WALLPAPER_SYSTEM ? UNFOLD2_PORT_WALLPAPER_HOME : UNFOLD2_PORT_WALLPAPER_LOCK));
        wallpaperData.unfoldedTwoLandFile = GetExistFilePath(
            wallpaperPath + "/"
            + (wallpaperType == WALLPAPER_SYSTEM ? UNFOLD2_LAND_WALLPAPER_HOME : UNFOLD2_LAND_WALLPAPER_LOCK));
    }
    wallpaperMap.InsertOrAssign(userId, wallpaperData);
}

ErrCode WallpaperService::GetColors(int32_t wallpaperType, std::vector<uint64_t> &colors)
{
    if (wallpaperType == WALLPAPER_SYSTEM) {
        std::lock_guard<std::mutex> lock(wallpaperColorMtx_);
        colors.emplace_back(systemWallpaperColor_);
    } else if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        std::lock_guard<std::mutex> lock(wallpaperColorMtx_);
        colors.emplace_back(lockWallpaperColor_);
    }
    HILOG_INFO("GetColors Service End.");
    return NO_ERROR;
}

ErrCode WallpaperService::GetColorsV9(int32_t wallpaperType, std::vector<uint64_t> &colors)
{
    if (!IsSystemApp()) {
        HILOG_ERROR("CallingApp is not SystemApp.");
        return E_NOT_SYSTEM_APP;
    }
    return GetColors(wallpaperType, colors);
}

ErrCode WallpaperService::GetFile(int32_t wallpaperType, int &wallpaperFd)
{
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_GET_WALLPAPER)) {
        HILOG_ERROR("GetPixelMap no get permission!");
        return E_NO_PERMISSION;
    }
    if (wallpaperType != static_cast<int32_t>(WALLPAPER_LOCKSCREEN)
        && wallpaperType != static_cast<int32_t>(WALLPAPER_SYSTEM)) {
        return E_PARAMETERS_INVALID;
    }
    auto type = static_cast<WallpaperType>(wallpaperType);
    int32_t userId = QueryActiveUserId();
    HILOG_INFO("QueryCurrentOsAccount userId: %{public}d", userId);
    ErrorCode ret = GetImageFd(userId, type, wallpaperFd);
    HILOG_INFO("GetImageFd fd:%{public}d, ret:%{public}d", wallpaperFd, ret);
    return ret;
}

bool WallpaperService::CompareColor(const uint64_t &localColor, const ColorManager::Color &color)
{
    std::lock_guard<std::mutex> lock(wallpaperColorMtx_);
    return localColor == color.PackValue();
}

bool WallpaperService::SaveColor(int32_t userId, WallpaperType wallpaperType)
{
    uint32_t errorCode = 0;
    OHOS::Media::SourceOptions opts;
    opts.formatHint = "image/jpeg";
    std::string pathName;
    if (!GetPictureFileName(userId, wallpaperType, pathName)) {
        return false;
    }
    std::unique_ptr<OHOS::Media::ImageSource> imageSource =
        OHOS::Media::ImageSource::CreateImageSource(pathName, opts, errorCode);
    if (errorCode != 0 || imageSource == nullptr) {
        HILOG_ERROR("CreateImageSource failed!");
        return false;
    }
    OHOS::Media::DecodeOptions decodeOpts;
    OHOS::Media::ImageInfo imageInfo;
    imageSource->GetImageInfo(imageInfo);
    int32_t height = imageInfo.size.height;
    int32_t width = imageInfo.size.width;
    if (height >= MIN_SIZE || width >= MIN_SIZE) {
        decodeOpts.desiredSize = {width / COMPRESSION_RATIO, height / COMPRESSION_RATIO};
    }
    std::unique_ptr<PixelMap> wallpaperPixelMap = imageSource->CreatePixelMap(decodeOpts, errorCode);
    if (errorCode != 0 || wallpaperPixelMap == nullptr) {
        HILOG_ERROR("CreatePixelMap failed!");
        return false;
    }
    auto colorPicker = Rosen::ColorPicker::CreateColorPicker(std::move(wallpaperPixelMap), errorCode);
    if (errorCode != 0) {
        HILOG_ERROR("CreateColorPicker failed!");
        return false;
    }
    auto color = ColorManager::Color();
    uint32_t ret = colorPicker->GetMainColor(color);
    if (ret != Rosen::SUCCESS) {
        HILOG_ERROR("GetMainColor failed ret is : %{public}d", ret);
        return false;
    }
    OnColorsChange(wallpaperType, color);
    return true;
}

ErrCode WallpaperService::SetWallpaper(int fd, int32_t wallpaperType, int32_t length)
{
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER)) {
        HILOG_ERROR("SetWallpaper no set permission.");
        return E_NO_PERMISSION;
    }
    StartAsyncTrace(HITRACE_TAG_MISC, "SetWallpaper", static_cast<int32_t>(TraceTaskId::SET_WALLPAPER));
    ErrorCode wallpaperErrorCode = SetWallpaper(fd, wallpaperType, length, PICTURE);
    FinishAsyncTrace(HITRACE_TAG_MISC, "SetWallpaper", static_cast<int32_t>(TraceTaskId::SET_WALLPAPER));
    close(fd);
    return wallpaperErrorCode;
}

ErrCode WallpaperService::SetWallpaperByPixelMap(const WallpaperRawData &wallpaperRawdata, int32_t wallpaperType)
{
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER)) {
        HILOG_ERROR("SetWallpaper no set permission.");
        return E_NO_PERMISSION;
    }
    auto *rawData = (uint8_t *)wallpaperRawdata.data;
    if (rawData == nullptr) {
        HILOG_ERROR("rawData is nullptr!");
        return E_FILE_ERROR;
    }
    std::vector<uint8_t> VectorPixelMap(rawData, rawData + wallpaperRawdata.size);
    if (VectorPixelMap.size() == 0) {
        HILOG_ERROR("VectorPixelMap  is nullptr!");
        return E_FILE_ERROR;
    }
    std::shared_ptr<OHOS::Media::PixelMap> pixelMap = std::shared_ptr<PixelMap>(PixelMap::DecodeTlv(VectorPixelMap));
    if (pixelMap == nullptr) {
        HILOG_ERROR("pixelMap is nullptr");
        return E_FILE_ERROR;
    }
    StartAsyncTrace(HITRACE_TAG_MISC, "SetWallpaper", static_cast<int32_t>(TraceTaskId::SET_WALLPAPER));
    ErrorCode wallpaperErrorCode = SetWallpaperByPixelMap(pixelMap, wallpaperType, PICTURE);
    FinishAsyncTrace(HITRACE_TAG_MISC, "SetWallpaper", static_cast<int32_t>(TraceTaskId::SET_WALLPAPER));
    return wallpaperErrorCode;
}

ErrCode WallpaperService::SetWallpaperV9(int fd, int32_t wallpaperType, int32_t length)
{
    if (!IsSystemApp()) {
        HILOG_ERROR("CallingApp is not SystemApp.");
        close(fd);
        return E_NOT_SYSTEM_APP;
    }
    return SetWallpaper(fd, wallpaperType, length);
}

ErrCode WallpaperService::SetWallpaperV9ByPixelMap(const WallpaperRawData &wallpaperRawdata, int32_t wallpaperType)
{
    if (!IsSystemApp()) {
        HILOG_INFO("CallingApp is not SystemApp.");
        return E_NOT_SYSTEM_APP;
    }
    return SetWallpaperByPixelMap(wallpaperRawdata, wallpaperType);
}

ErrorCode WallpaperService::SetWallpaperBackupData(
    int32_t userId, WallpaperResourceType resourceType, const std::string &uriOrPixelMap, WallpaperType wallpaperType)
{
    HILOG_INFO("set wallpaper and backup data Start.");
    if (!OHOS::FileExists(uriOrPixelMap)) {
        return E_DEAL_FAILED;
    }
    if (!FileDeal::DeleteDir(GetWallpaperDir(userId, wallpaperType), false)) {
        return E_DEAL_FAILED;
    }
    WallpaperData wallpaperData;
    bool ret = GetWallpaperSafeLocked(userId, wallpaperType, wallpaperData);
    if (!ret) {
        HILOG_ERROR("GetWallpaperSafeLocked failed!");
        return E_DEAL_FAILED;
    }
    if (resourceType == PICTURE || resourceType == DEFAULT) {
        wallpaperData.wallpaperFile = GetWallpaperDir(userId, wallpaperType) + "/"
                                      + (wallpaperType == WALLPAPER_SYSTEM ? WALLPAPER_HOME : WALLPAPER_LOCK);
    }
    wallpaperData.resourceType = resourceType;
    wallpaperData.wallpaperId = MakeWallpaperIdLocked();
    std::string wallpaperFile;
    WallpaperService::GetWallpaperFile(resourceType, wallpaperData, wallpaperFile);
    {
        std::lock_guard<std::mutex> lock(mtx_);
        if (!FileDeal::CopyFile(uriOrPixelMap, wallpaperFile)) {
            HILOG_ERROR("CopyFile failed!");
            FileDeal::DeleteFile(uriOrPixelMap);
            return E_DEAL_FAILED;
        }
        if (!FileDeal::DeleteFile(uriOrPixelMap)) {
            return E_DEAL_FAILED;
        }
    }
    if (!SaveWallpaperState(userId, wallpaperType, resourceType)) {
        HILOG_ERROR("Save wallpaper state failed!");
        return E_DEAL_FAILED;
    }
    if (wallpaperType == WALLPAPER_SYSTEM) {
        systemWallpaperMap_.InsertOrAssign(userId, wallpaperData);
    } else if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        lockWallpaperMap_.InsertOrAssign(userId, wallpaperData);
    }
    if (!SendWallpaperChangeEvent(userId, wallpaperType)) {
        HILOG_ERROR("Send wallpaper state failed!");
        return E_DEAL_FAILED;
    }
    return NO_ERROR;
}

void WallpaperService::GetWallpaperFile(
    WallpaperResourceType resourceType, const WallpaperData &wallpaperData, std::string &wallpaperFile)
{
    switch (resourceType) {
        case PICTURE:
            wallpaperFile = wallpaperData.wallpaperFile;
            break;
        case DEFAULT:
            wallpaperFile = wallpaperData.wallpaperFile;
            break;
        case VIDEO:
            wallpaperFile = wallpaperData.liveWallpaperFile;
            break;
        case PACKAGE:
            wallpaperFile = wallpaperData.customPackageUri;
            break;
        default:
            HILOG_ERROR("Non-existent error type!");
            break;
    }
}

WallpaperResourceType WallpaperService::GetResType(int32_t userId, WallpaperType wallpaperType)
{
    if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        auto iterator = lockWallpaperMap_.Find(userId);
        if (iterator.first) {
            return iterator.second.resourceType;
        }
    } else if (wallpaperType == WALLPAPER_SYSTEM) {
        auto iterator = systemWallpaperMap_.Find(userId);
        if (iterator.first) {
            return iterator.second.resourceType;
        }
    }
    return WallpaperResourceType::DEFAULT;
}

ErrCode WallpaperService::SendEvent(const std::string &eventType)
{
    HILOG_INFO("Send event start.");
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER)) {
        HILOG_ERROR("Send event not set permission!");
        return E_NO_PERMISSION;
    }

    int32_t userId = QueryActiveUserId();
    WallpaperType wallpaperType;
    WallpaperData data;
    if (eventType == SHOW_SYSTEM_SCREEN) {
        wallpaperType = WALLPAPER_SYSTEM;
    } else if (eventType == SHOW_LOCK_SCREEN) {
        wallpaperType = WALLPAPER_LOCKSCREEN;
    } else {
        HILOG_ERROR("Event type error!");
        return E_PARAMETERS_INVALID;
    }

    if (!GetWallpaperSafeLocked(userId, wallpaperType, data)) {
        HILOG_ERROR("Get wallpaper safe locked failed!");
        return E_PARAMETERS_INVALID;
    }
    std::string uri;
    GetFileNameFromMap(userId, WALLPAPER_SYSTEM, uri);
    WallpaperChanged(wallpaperType, data.resourceType, uri);
    return NO_ERROR;
}

bool WallpaperService::SendWallpaperChangeEvent(int32_t userId, WallpaperType wallpaperType)
{
    WallpaperData wallpaperData;
    if (!GetWallpaperSafeLocked(userId, wallpaperType, wallpaperData)) {
        HILOG_ERROR("GetWallpaperSafeLocked failed!");
        return false;
    }
    shared_ptr<WallpaperCommonEventManager> wallpaperCommonEventManager = make_shared<WallpaperCommonEventManager>();
    if (wallpaperType == WALLPAPER_SYSTEM) {
        HILOG_INFO("Send wallpaper system setting message.");
        wallpaperCommonEventManager->SendWallpaperSystemSettingMessage(wallpaperData.resourceType);
    } else if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        HILOG_INFO("Send wallpaper lock setting message.");
        wallpaperCommonEventManager->SendWallpaperLockSettingMessage(wallpaperData.resourceType);
    }
    {
        HILOG_INFO("SetWallpaperBackupData callbackProxy_->OnCall start.");
        std::lock_guard<std::mutex> lock(callbackProxyMutex_);
        if (callbackProxy_ != nullptr
            && (wallpaperData.resourceType == PICTURE || wallpaperData.resourceType == DEFAULT)) {
            callbackProxy_->OnCall(wallpaperType);
        }
    }
    std::string uri;
    WallpaperChanged(wallpaperType, wallpaperData.resourceType, uri);
    return true;
}

ErrCode WallpaperService::SetVideo(int fd, int32_t wallpaperType, int32_t length)
{
    if (!IsSystemApp()) {
        HILOG_ERROR("current app is not SystemApp.");
        close(fd);
        return E_NOT_SYSTEM_APP;
    }
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER)) {
        HILOG_ERROR("SetWallpaper no set permission.");
        return E_NO_PERMISSION;
    }
    StartAsyncTrace(HITRACE_TAG_MISC, "SetVideo", static_cast<int32_t>(TraceTaskId::SET_VIDEO));
    ErrorCode wallpaperErrorCode = SetWallpaper(fd, wallpaperType, length, VIDEO);
    FinishAsyncTrace(HITRACE_TAG_MISC, "SetVideo", static_cast<int32_t>(TraceTaskId::SET_VIDEO));
    close(fd);
    return wallpaperErrorCode;
}

ErrCode WallpaperService::SetCustomWallpaper(int fd, int32_t type, int32_t length)
{
    if (!IsSystemApp()) {
        HILOG_ERROR("current app is not SystemApp.");
        close(fd);
        return E_NOT_SYSTEM_APP;
    }
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER)) {
        close(fd);
        return E_NO_PERMISSION;
    }
    if (type != static_cast<int32_t>(WALLPAPER_LOCKSCREEN) && type != static_cast<int32_t>(WALLPAPER_SYSTEM)) {
        close(fd);
        return E_PARAMETERS_INVALID;
    }
    StartAsyncTrace(HITRACE_TAG_MISC, "SetCustomWallpaper", static_cast<int32_t>(TraceTaskId::SET_CUSTOM_WALLPAPER));
    int32_t userId = QueryActiveUserId();
    WallpaperType wallpaperType = static_cast<WallpaperType>(type);
    WallpaperData wallpaperData;
    if (!GetWallpaperSafeLocked(userId, wallpaperType, wallpaperData)) {
        HILOG_ERROR("GetWallpaper data failed!");
        close(fd);
        return E_DEAL_FAILED;
    }
    if (!Rosen::SceneBoardJudgement::IsSceneBoardEnabled()) {
        close(fd);
        HILOG_ERROR("SceneBoard is not Enabled.");
        return E_NO_PERMISSION;
    }
    if (!SaveWallpaperState(userId, wallpaperType, PACKAGE)) {
        HILOG_ERROR("Save wallpaper state failed!");
        close(fd);
        return E_DEAL_FAILED;
    }
    ErrorCode wallpaperErrorCode = SetWallpaper(fd, wallpaperType, length, PACKAGE);
    wallpaperData.resourceType = PACKAGE;
    wallpaperData.wallpaperId = MakeWallpaperIdLocked();
    if (wallpaperType == WALLPAPER_SYSTEM) {
        systemWallpaperMap_.InsertOrAssign(userId, wallpaperData);
    } else if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        lockWallpaperMap_.InsertOrAssign(userId, wallpaperData);
    }
    if (!SendWallpaperChangeEvent(userId, wallpaperType)) {
        HILOG_ERROR("Send wallpaper state failed!");
        close(fd);
        return E_DEAL_FAILED;
    }
    FinishAsyncTrace(HITRACE_TAG_MISC, "SetCustomWallpaper", static_cast<int32_t>(TraceTaskId::SET_CUSTOM_WALLPAPER));
    close(fd);
    return wallpaperErrorCode;
}

ErrCode WallpaperService::GetPixelMap(int32_t wallpaperType, int32_t &size, int &fd)
{
    HILOG_INFO("WallpaperService::getPixelMap start.");
    if (!IsSystemApp()) {
        HILOG_ERROR("CallingApp is not SystemApp.");
        return E_NOT_SYSTEM_APP;
    }
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_GET_WALLPAPER)) {
        HILOG_ERROR("GetPixelMap no get permission!");
        return E_NO_PERMISSION;
    }
    if (wallpaperType != static_cast<int32_t>(WALLPAPER_LOCKSCREEN)
        && wallpaperType != static_cast<int32_t>(WALLPAPER_SYSTEM)) {
        return E_PARAMETERS_INVALID;
    }
    auto type = static_cast<WallpaperType>(wallpaperType);
    int32_t userId = QueryActiveUserId();
    HILOG_INFO("QueryCurrentOsAccount userId: %{public}d", userId);
    // current user's wallpaper is live video, not image
    WallpaperResourceType resType = GetResType(userId, type);
    if (resType != PICTURE && resType != DEFAULT) {
        HILOG_ERROR("Current user's wallpaper is live video, not image.");
        size = 0; // 0: empty file size
        fd = -1;  // -1: invalid file description
        return NO_ERROR;
    }
    ErrorCode ret = GetImageSize(userId, type, size);
    if (ret != NO_ERROR) {
        HILOG_ERROR("GetImageSize failed!");
        return ret;
    }
    ret = GetImageFd(userId, type, fd);
    if (ret != NO_ERROR) {
        HILOG_ERROR("GetImageFd failed!");
        return ret;
    }
    return NO_ERROR;
}

ErrCode WallpaperService::GetPixelMapV9(int32_t wallpaperType, int32_t &size, int &fd)
{
    return GetPixelMap(wallpaperType, size, fd);
}

int32_t WallpaperService::GetWallpaperId(int32_t wallpaperType)
{
    HILOG_INFO("WallpaperService::GetWallpaperId --> start.");
    int32_t iWallpaperId = -1;
    int32_t userId = QueryActiveUserId();
    HILOG_INFO("QueryCurrentOsAccount userId: %{public}d", userId);
    if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        auto iterator = lockWallpaperMap_.Find(userId);
        if (iterator.first) {
            iWallpaperId = iterator.second.wallpaperId;
        }
    } else if (wallpaperType == WALLPAPER_SYSTEM) {
        auto iterator = systemWallpaperMap_.Find(userId);
        if (iterator.first) {
            iWallpaperId = iterator.second.wallpaperId;
        }
    }
    HILOG_INFO("WallpaperService::GetWallpaperId --> end ID[%{public}d]", iWallpaperId);
    return iWallpaperId;
}

ErrCode WallpaperService::IsChangePermitted(bool &isChangePermitted)
{
    HILOG_INFO("IsChangePermitted wallpaper Start.");
    isChangePermitted = CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER);
    return NO_ERROR;
}

ErrCode WallpaperService::IsOperationAllowed(bool &isOperationAllowed)
{
    HILOG_INFO("IsOperationAllowed wallpaper Start.");
    isOperationAllowed = CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER);
    return NO_ERROR;
}

ErrCode WallpaperService::ResetWallpaper(int32_t wallpaperType)
{
    HILOG_INFO("reset wallpaper Start.");
    bool permissionSet = CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER);
    if (!permissionSet) {
        HILOG_ERROR("reset wallpaper no set permission!");
        return E_NO_PERMISSION;
    }
    if (wallpaperType != static_cast<int32_t>(WALLPAPER_LOCKSCREEN)
        && wallpaperType != static_cast<int32_t>(WALLPAPER_SYSTEM)) {
        HILOG_ERROR("wallpaperType = %{public}d type not support ", wallpaperType);
        return E_PARAMETERS_INVALID;
    }
    WallpaperType type = static_cast<WallpaperType>(wallpaperType);
    int32_t userId = QueryActiveUserId();
    HILOG_INFO("QueryCurrentOsAccount userId: %{public}d", userId);
    if (!CheckUserPermissionById(userId)) {
        return E_USER_IDENTITY_ERROR;
    }
    ErrorCode wallpaperErrorCode = SetDefaultDataForWallpaper(userId, type);
    HILOG_INFO(" Set default data result[%{public}d]", wallpaperErrorCode);
    return wallpaperErrorCode;
}

ErrCode WallpaperService::ResetWallpaperV9(int32_t wallpaperType)
{
    if (!IsSystemApp()) {
        HILOG_ERROR("CallingApp is not SystemApp.");
        return E_NOT_SYSTEM_APP;
    }
    return ResetWallpaper(wallpaperType);
}

ErrorCode WallpaperService::SetDefaultDataForWallpaper(int32_t userId, WallpaperType wallpaperType)
{
    WallpaperData wallpaperData;
    if (!GetWallpaperSafeLocked(userId, wallpaperType, wallpaperData)) {
        return E_DEAL_FAILED;
    }
    if (!RestoreUserResources(userId, wallpaperData, wallpaperType)) {
        HILOG_ERROR("RestoreUserResources error!");
        return E_DEAL_FAILED;
    }
    if (!SaveWallpaperState(userId, wallpaperType, DEFAULT)) {
        HILOG_ERROR("Save wallpaper state failed!");
        return E_DEAL_FAILED;
    }
    wallpaperData.wallpaperId = DEFAULT_WALLPAPER_ID;
    wallpaperData.resourceType = DEFAULT;
    wallpaperData.allowBackup = true;
    if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        lockWallpaperMap_.InsertOrAssign(userId, wallpaperData);
    } else if (wallpaperType == WALLPAPER_SYSTEM) {
        systemWallpaperMap_.InsertOrAssign(userId, wallpaperData);
    }
    if (!SendWallpaperChangeEvent(userId, wallpaperType)) {
        HILOG_ERROR("Send wallpaper state failed!");
        return E_DEAL_FAILED;
    }
    SaveColor(userId, wallpaperType);
    return NO_ERROR;
}

ErrCode WallpaperService::On(const std::string &type, const sptr<IWallpaperEventListener> &listener)
{
    HILOG_DEBUG("WallpaperService::On in.");
    if (listener == nullptr) {
        HILOG_ERROR("WallpaperService::On listener is null.");
        return E_DEAL_FAILED;
    }
    if (type == WALLPAPER_CHANGE && !IsSystemApp()) {
        HILOG_ERROR("current app is not SystemApp.");
        return E_NOT_SYSTEM_APP;
    }
    std::lock_guard<std::mutex> autoLock(listenerMapMutex_);
    wallpaperEventMap_[type].insert_or_assign(IPCSkeleton::GetCallingTokenID(), listener);
    return NO_ERROR;
}

ErrCode WallpaperService::Off(const std::string &type, const sptr<IWallpaperEventListener> &listener)
{
    HILOG_DEBUG("WallpaperService::Off in.");
    (void)listener;
    if (type == WALLPAPER_CHANGE && !IsSystemApp()) {
        HILOG_ERROR("current app is not SystemApp.");
        return E_NOT_SYSTEM_APP;
    }
    std::lock_guard<std::mutex> autoLock(listenerMapMutex_);
    auto iter = wallpaperEventMap_.find(type);
    if (iter != wallpaperEventMap_.end()) {
        auto it = iter->second.find(IPCSkeleton::GetCallingTokenID());
        if (it != iter->second.end()) {
            it->second = nullptr;
            iter->second.erase(it);
        }
    }
    return NO_ERROR;
}

ErrCode WallpaperService::RegisterWallpaperCallback(
    const sptr<IWallpaperCallback> &wallpaperCallback, bool &registerWallpaperCallback)
{
    HILOG_INFO("  WallpaperService::RegisterWallpaperCallback.");
    std::lock_guard<std::mutex> lock(callbackProxyMutex_);
    if (!IsSystemApp()) {
        HILOG_ERROR("current app is not SystemApp.");
        registerWallpaperCallback = false;
        return E_NOT_SYSTEM_APP;
    }
    callbackProxy_ = wallpaperCallback;
    registerWallpaperCallback = true;
    return NO_ERROR;
}

bool WallpaperService::GetWallpaperSafeLocked(int32_t userId, WallpaperType wallpaperType, WallpaperData &wallpaperData)
{
    HILOG_DEBUG("GetWallpaperSafeLocked start.");
    auto iterator = wallpaperType == WALLPAPER_SYSTEM ? systemWallpaperMap_.Find(userId)
                                                      : lockWallpaperMap_.Find(userId);
    if (!iterator.first) {
        HILOG_INFO("No Lock wallpaper?  Not tracking for lock-only");
        UpdataWallpaperMap(userId, wallpaperType);
        iterator = wallpaperType == WALLPAPER_SYSTEM ? systemWallpaperMap_.Find(userId)
                                                     : lockWallpaperMap_.Find(userId);
        if (!iterator.first) {
            HILOG_ERROR("Fail to get wallpaper data");
            return false;
        }
    }
    wallpaperData = iterator.second;
    ClearnWallpaperDataFile(wallpaperData);
    return true;
}

void WallpaperService::ClearWallpaperLocked(int32_t userId, WallpaperType wallpaperType)
{
    HILOG_INFO("Clear wallpaper Start.");
    auto iterator = wallpaperType == WALLPAPER_SYSTEM ? systemWallpaperMap_.Find(userId)
                                                      : lockWallpaperMap_.Find(userId);
    if (!iterator.first) {
        HILOG_ERROR("Lock wallpaper already cleared.");
        return;
    }
    if (!iterator.second.wallpaperFile.empty() || !iterator.second.liveWallpaperFile.empty()) {
        if (wallpaperType == WALLPAPER_LOCKSCREEN) {
            lockWallpaperMap_.Erase(userId);
        } else if (wallpaperType == WALLPAPER_SYSTEM) {
            systemWallpaperMap_.Erase(userId);
        }
    }
}

bool WallpaperService::CheckCallingPermission(const std::string &permissionName)
{
    AccessTokenID callerToken = IPCSkeleton::GetCallingTokenID();
    int32_t result = AccessTokenKit::VerifyAccessToken(callerToken, permissionName);
    if (result != TypePermissionState::PERMISSION_GRANTED) {
        HILOG_ERROR("Check permission failed!");
        return false;
    }
    return true;
}

void WallpaperService::ReporterFault(FaultType faultType, FaultCode faultCode)
{
    FaultMsg msg;
    msg.faultType = faultType;
    msg.errorCode = faultCode;
    ReportStatus nRet;
    if (faultType == FaultType::SERVICE_FAULT) {
        msg.moduleName = "WallpaperService";
        nRet = FaultReporter::ReportServiceFault(msg);
    } else {
        nRet = FaultReporter::ReportRuntimeFault(msg);
    }

    if (nRet == ReportStatus::SUCCESS) {
        HILOG_INFO("ReporterFault success.");
    } else {
        HILOG_ERROR("ReporterFault failed!");
    }
}

int32_t WallpaperService::Dump(int32_t fd, const std::vector<std::u16string> &args)
{
    std::vector<std::string> argsStr;
    for (auto item : args) {
        argsStr.emplace_back(Str16ToStr8(item));
    }

    if (DumpHelper::GetInstance().Dispatch(fd, argsStr)) {
        HILOG_ERROR("DumpHelper Dispatch failed!");
        return 0;
    }
    return 1;
}

#ifndef THEME_SERVICE
bool WallpaperService::ConnectExtensionAbility()
{
    HILOG_DEBUG("ConnectAdapter.");
    MemoryGuard cacheGuard;
    AAFwk::Want want;
    want.SetElementName(OHOS_WALLPAPER_BUNDLE_NAME, "WallpaperExtAbility");
    ErrCode errCode = AAFwk::AbilityManagerClient::GetInstance()->Connect();
    if (errCode != ERR_OK) {
        HILOG_ERROR("connect ability server failed errCode=%{public}d", errCode);
        return false;
    }
    if (connection_ == nullptr) {
        connection_ = new WallpaperExtensionAbilityConnection(*this);
    }
    auto ret = AAFwk::AbilityManagerClient::GetInstance()->ConnectExtensionAbility(want, connection_, DEFAULT_VALUE);
    HILOG_INFO("ConnectExtensionAbility errCode=%{public}d", ret);
    return ret;
}
#endif

bool WallpaperService::IsSystemApp()
{
    HILOG_INFO("IsSystemApp start.");
    uint64_t tokenId = IPCSkeleton::GetCallingFullTokenID();
    return TokenIdKit::IsSystemAppByFullTokenID(tokenId);
}

bool WallpaperService::IsNativeSa()
{
    HILOG_INFO("IsNativeSa start.");
    AccessTokenID tokenId = IPCSkeleton::GetCallingTokenID();
    return AccessTokenKit::GetTokenTypeFlag(tokenId) == TypeATokenTypeEnum::TOKEN_NATIVE;
}

ErrorCode WallpaperService::GetImageFd(int32_t userId, WallpaperType wallpaperType, int32_t &fd)
{
    HILOG_INFO("WallpaperService::GetImageFd start.");
    std::string filePathName;
    if (!GetFileNameFromMap(userId, wallpaperType, filePathName)) {
        return E_DEAL_FAILED;
    }
    if (GetResType(userId, wallpaperType) == WallpaperResourceType::PACKAGE) {
        HILOG_INFO("The current wallpaper is a custom wallpaper");
        return NO_ERROR;
    }
    {
        std::lock_guard<std::mutex> lock(mtx_);
        fd = open(filePathName.c_str(), O_RDONLY, S_IREAD);
    }
    if (fd < 0) {
        HILOG_ERROR("Open file failed, errno %{public}d", errno);
        ReporterFault(FaultType::LOAD_WALLPAPER_FAULT, FaultCode::RF_FD_INPUT_FAILED);
        return E_DEAL_FAILED;
    }
    fdsan_exchange_owner_tag(fd, 0, WP_DOMAIN);
    HILOG_INFO("fd = %{public}d", fd);
    return NO_ERROR;
}

ErrorCode WallpaperService::GetImageSize(int32_t userId, WallpaperType wallpaperType, int32_t &size)
{
    HILOG_INFO("WallpaperService::GetImageSize start.");
    std::string filePathName;
    HILOG_INFO("userId = %{public}d", userId);
    if (!GetPictureFileName(userId, wallpaperType, filePathName)) {
        return E_DEAL_FAILED;
    }

    if (!OHOS::FileExists(filePathName)) {
        HILOG_ERROR("file is not exist.");
        return E_NOT_FOUND;
    }
    std::lock_guard<std::mutex> lock(mtx_);
    FILE *fd = fopen(filePathName.c_str(), "rb");
    if (fd == nullptr) {
        HILOG_ERROR("fopen file failed, errno %{public}d", errno);
        return E_FILE_ERROR;
    }
    int32_t fend = fseek(fd, 0, SEEK_END);
    long length = ftell(fd);
    int32_t fset = fseek(fd, 0, SEEK_SET);
    if (length <= 0 || length > INT32_MAX || fend != 0 || fset != 0) {
        HILOG_ERROR("ftell file failed or fseek file failed, errno %{public}d", errno);
        fclose(fd);
        return E_FILE_ERROR;
    }
    size = static_cast<int32_t>(length);
    fclose(fd);
    return NO_ERROR;
}

int32_t WallpaperService::QueryActiveUserId()
{
    std::vector<int32_t> ids;
    ErrCode errCode = AccountSA::OsAccountManager::QueryActiveOsAccountIds(ids);
    if (errCode != ERR_OK || ids.empty()) {
        HILOG_ERROR("Query active userid failed, errCode: %{public}d,", errCode);
        return DEFAULT_USER_ID;
    }
    return ids[0];
}

bool WallpaperService::CheckUserPermissionById(int32_t userId)
{
    OsAccountInfo osAccountInfo;
    ErrCode errCode = OsAccountManager::QueryOsAccountById(userId, osAccountInfo);
    if (errCode != ERR_OK) {
        HILOG_ERROR("Query os account info failed, errCode: %{public}d", errCode);
        return false;
    }
    HILOG_INFO("osAccountInfo GetType: %{public}d", static_cast<int32_t>(osAccountInfo.GetType()));
    if (osAccountInfo.GetType() == OsAccountType::GUEST) {
        HILOG_ERROR("The guest does not have permissions.");
        return false;
    }
    return true;
}

ErrorCode WallpaperService::SetWallpaper(
    int32_t fd, int32_t wallpaperType, int32_t length, WallpaperResourceType resourceType)
{
    int32_t userId = QueryActiveUserId();
    HILOG_INFO("QueryCurrentOsAccount userId: %{public}d", userId);
    if (!CheckUserPermissionById(userId)) {
        return E_USER_IDENTITY_ERROR;
    }
    ErrorCode errCode = CheckValid(wallpaperType, length, resourceType);
    if (errCode != NO_ERROR) {
        return errCode;
    }
    std::string uri = wallpaperTmpFullPath_;
    char *paperBuf = new (std::nothrow) char[length]();
    if (paperBuf == nullptr) {
        return E_NO_MEMORY;
    }
    {
        std::lock_guard<std::mutex> lock(mtx_);
        if (read(fd, paperBuf, length) <= 0) {
            HILOG_ERROR("read fd failed!");
            delete[] paperBuf;
            return E_DEAL_FAILED;
        }
        mode_t mode = S_IRUSR | S_IWUSR;
        int32_t fdw = open(uri.c_str(), O_WRONLY | O_CREAT, mode);
        if (fdw < 0) {
            HILOG_ERROR("Open wallpaper tmpFullPath failed, errno %{public}d", errno);
            delete[] paperBuf;
            return E_DEAL_FAILED;
        }
        fdsan_exchange_owner_tag(fdw, 0, WP_DOMAIN);
        if (write(fdw, paperBuf, length) <= 0) {
            HILOG_ERROR("Write to fdw failed, errno %{public}d", errno);
            ReporterFault(FaultType::SET_WALLPAPER_FAULT, FaultCode::RF_DROP_FAILED);
            delete[] paperBuf;
            fdsan_close_with_tag(fdw, WP_DOMAIN);
            return E_DEAL_FAILED;
        }
        delete[] paperBuf;
        fdsan_close_with_tag(fdw, WP_DOMAIN);
    }
    WallpaperType type = static_cast<WallpaperType>(wallpaperType);
    ErrorCode wallpaperErrorCode = SetWallpaperBackupData(userId, resourceType, uri, type);
    if (resourceType == PICTURE) {
        SaveColor(userId, type);
    }
    return wallpaperErrorCode;
}

ErrorCode WallpaperService::SetWallpaperByPixelMap(
    std::shared_ptr<OHOS::Media::PixelMap> pixelMap, int32_t wallpaperType, WallpaperResourceType resourceType)
{
    if (pixelMap == nullptr) {
        HILOG_ERROR("pixelMap is nullptr");
        return E_FILE_ERROR;
    }
    int32_t userId = QueryActiveUserId();
    HILOG_INFO("QueryCurrentOsAccount userId: %{public}d", userId);
    if (!CheckUserPermissionById(userId)) {
        return E_USER_IDENTITY_ERROR;
    }
    std::string uri = wallpaperTmpFullPath_;
    ErrorCode errCode = WritePixelMapToFile(pixelMap, uri, wallpaperType, resourceType);
    if (errCode != NO_ERROR) {
        HILOG_ERROR("WritePixelMapToFile failed!");
        return errCode;
    }
    WallpaperType type = static_cast<WallpaperType>(wallpaperType);
    ErrorCode wallpaperErrorCode = SetWallpaperBackupData(userId, resourceType, uri, type);
    if (resourceType == PICTURE) {
        SaveColor(userId, type);
    }
    return wallpaperErrorCode;
}

ErrorCode WallpaperService::WritePixelMapToFile(std::shared_ptr<OHOS::Media::PixelMap> pixelMap,
    std::string wallpaperTmpFullPath, int32_t wallpaperType, WallpaperResourceType resourceType)
{
    if (pixelMap == nullptr) {
        HILOG_ERROR("pixelMap is nullptr");
        return E_FILE_ERROR;
    }
    std::stringbuf stringBuf;
    std::ostream ostream(&stringBuf);
    int32_t mapSize = WritePixelMapToStream(pixelMap, ostream);
    if (mapSize <= 0) {
        HILOG_ERROR("WritePixelMapToStream failed!");
        return E_WRITE_PARCEL_ERROR;
    }
    ErrorCode errCode = CheckValid(wallpaperType, mapSize, resourceType);
    if (errCode != NO_ERROR) {
        HILOG_ERROR("CheckValid failed!");
        return errCode;
    }
    char *buffer = new (std::nothrow) char[mapSize]();
    if (buffer == nullptr) {
        HILOG_ERROR("buffer failed!");
        return E_NO_MEMORY;
    }
    stringBuf.sgetn(buffer, mapSize);
    {
        std::lock_guard<std::mutex> lock(mtx_);
        mode_t mode = S_IRUSR | S_IWUSR;
        int32_t fdw = open(wallpaperTmpFullPath.c_str(), O_WRONLY | O_CREAT, mode);
        if (fdw < 0) {
            HILOG_ERROR("Open wallpaper tmpFullPath failed, errno %{public}d", errno);
            delete[] buffer;
            return E_DEAL_FAILED;
        }
        fdsan_exchange_owner_tag(fdw, 0, WP_DOMAIN);
        if (write(fdw, buffer, mapSize) <= 0) {
            HILOG_ERROR("Write to fdw failed, errno %{public}d", errno);
            ReporterFault(FaultType::SET_WALLPAPER_FAULT, FaultCode::RF_DROP_FAILED);
            delete[] buffer;
            fdsan_close_with_tag(fdw, WP_DOMAIN);
            return E_DEAL_FAILED;
        }
        delete[] buffer;
        fdsan_close_with_tag(fdw, WP_DOMAIN);
    }
    return NO_ERROR;
}

int64_t WallpaperService::WritePixelMapToStream(
    std::shared_ptr<OHOS::Media::PixelMap> pixelMap, std::ostream &outputStream)
{
    if (pixelMap == nullptr) {
        HILOG_ERROR("pixelMap is nullptr");
        return 0;
    }
    OHOS::Media::ImagePacker imagePacker;
    OHOS::Media::PackOption option;
    option.format = "image/jpeg";
    option.quality = OPTION_QUALITY;
    option.numberHint = 1;
    std::set<std::string> formats;
    uint32_t ret = imagePacker.GetSupportedFormats(formats);
    if (ret != 0) {
        HILOG_ERROR("image packer get supported format failed, ret=%{public}u.", ret);
    }

    imagePacker.StartPacking(outputStream, option);
    imagePacker.AddImage(*pixelMap);
    int64_t packedSize = 0;
    imagePacker.FinalizePacking(packedSize);
    HILOG_INFO("FrameWork WritePixelMapToStream End! packedSize=%{public}lld.", static_cast<long long>(packedSize));
    return packedSize;
}

void WallpaperService::OnColorsChange(WallpaperType wallpaperType, const ColorManager::Color &color)
{
    std::vector<uint64_t> colors;
    if (wallpaperType == WALLPAPER_SYSTEM && !CompareColor(systemWallpaperColor_, color)) {
        {
            std::lock_guard<std::mutex> lock(wallpaperColorMtx_);
            systemWallpaperColor_ = color.PackValue();
            colors.emplace_back(systemWallpaperColor_);
        }
        NotifyColorChange(colors, WALLPAPER_SYSTEM);
    } else if (wallpaperType == WALLPAPER_LOCKSCREEN && !CompareColor(lockWallpaperColor_, color)) {
        {
            std::lock_guard<std::mutex> lock(wallpaperColorMtx_);
            lockWallpaperColor_ = color.PackValue();
            colors.emplace_back(lockWallpaperColor_);
        }
        NotifyColorChange(colors, WALLPAPER_LOCKSCREEN);
    }
}

ErrorCode WallpaperService::CheckValid(int32_t wallpaperType, int32_t length, WallpaperResourceType resourceType)
{
    if (wallpaperType != static_cast<int32_t>(WALLPAPER_LOCKSCREEN)
        && wallpaperType != static_cast<int32_t>(WALLPAPER_SYSTEM)) {
        return E_PARAMETERS_INVALID;
    }

    int32_t maxLength = resourceType == VIDEO ? MAX_VIDEO_SIZE : FOO_MAX_LEN;
    if (length <= 0) {
        return E_PARAMETERS_INVALID;
    }
    if (length > maxLength) {
        return E_PICTURE_OVERSIZED;
    }
    return NO_ERROR;
}

bool WallpaperService::WallpaperChanged(
    WallpaperType wallpaperType, WallpaperResourceType resType, const std::string &uri)
{
    std::lock_guard<std::mutex> autoLock(listenerMapMutex_);
    auto it = wallpaperEventMap_.find(WALLPAPER_CHANGE);
    if (it != wallpaperEventMap_.end()) {
        for (auto iter = it->second.begin(); iter != it->second.end(); iter++) {
            if (iter->second == nullptr) {
                continue;
            }
            iter->second->OnWallpaperChange(wallpaperType, resType, uri);
        }
        return true;
    }
    return false;
}

void WallpaperService::NotifyColorChange(const std::vector<uint64_t> &colors, const WallpaperType &wallpaperType)
{
    std::lock_guard<std::mutex> autoLock(listenerMapMutex_);
    auto it = wallpaperEventMap_.find(COLOR_CHANGE);
    if (it != wallpaperEventMap_.end()) {
        for (auto iter = it->second.begin(); iter != it->second.end(); iter++) {
            if (iter->second == nullptr) {
                continue;
            }
            iter->second->OnColorsChange(colors, wallpaperType);
        }
    }
}

bool WallpaperService::SaveWallpaperState(
    int32_t userId, WallpaperType wallpaperType, WallpaperResourceType resourceType)
{
    WallpaperData systemData;
    WallpaperData lockScreenData;
    if (!GetWallpaperSafeLocked(userId, WALLPAPER_SYSTEM, systemData)
        || !GetWallpaperSafeLocked(userId, WALLPAPER_LOCKSCREEN, lockScreenData)) {
        return false;
    }
    cJSON *root = cJSON_CreateObject();
    if (root == nullptr) {
        HILOG_ERROR("create object failed.");
        return false;
    }
    int32_t systemResourceType = (wallpaperType == WALLPAPER_SYSTEM) ? static_cast<int32_t>(resourceType)
                                                                     : static_cast<int32_t>(systemData.resourceType);

    int32_t lockScreenResourceType = (wallpaperType == WALLPAPER_SYSTEM)
                                         ? static_cast<int32_t>(lockScreenData.resourceType)
                                         : static_cast<int32_t>(resourceType);

    if (cJSON_AddNumberToObject(root, SYSTEM_RES_TYPE, systemResourceType) == nullptr
        || cJSON_AddNumberToObject(root, LOCKSCREEN_RES_TYPE, lockScreenResourceType) == nullptr) {
        HILOG_ERROR("add number to object fail.");
        cJSON_Delete(root);
        return false;
    }

    char *json = cJSON_Print(root);
    if (json == nullptr) {
        HILOG_ERROR("write user config file failed. because json content is empty.");
        cJSON_Delete(root);
        return false;
    }
    cJSON_Delete(root);

    if (!WriteWallpapercfgFile(json, userId)) {
        HILOG_ERROR("write wallpapercfg fail.");
        cJSON_free(json);
        return false;
    }
    cJSON_free(json);
    return true;
}

bool WallpaperService::WriteWallpapercfgFile(char *wallpaperJson, int32_t userId)
{
    std::string userPath = WALLPAPER_USERID_PATH + std::to_string(userId) + "/wallpapercfg";
    mode_t mode = S_IRUSR | S_IWUSR;
    int fd = open(userPath.c_str(), O_CREAT | O_WRONLY | O_SYNC, mode);
    if (fd <= 0) {
        HILOG_ERROR("open user config file failed! %{public}d", errno);
        return false;
    }
    fdsan_exchange_owner_tag(fd, 0, WP_DOMAIN);
    ssize_t size = write(fd, wallpaperJson, strlen(wallpaperJson));
    if (size <= 0) {
        HILOG_ERROR("write user config file failed!");
        fdsan_close_with_tag(fd, WP_DOMAIN);
        return false;
    }
    fdsan_close_with_tag(fd, WP_DOMAIN);
    return true;
}

void WallpaperService::LoadWallpaperState()
{
    int32_t userId = QueryActiveUserId();
    std::string userPath = WALLPAPER_USERID_PATH + std::to_string(userId) + "/wallpapercfg";
    int fd = open(userPath.c_str(), O_RDONLY, S_IREAD);
    if (fd <= 0) {
        HILOG_ERROR("open user config file failed!");
        return;
    }
    fdsan_exchange_owner_tag(fd, 0, WP_DOMAIN);
    const size_t len = 255;
    char buf[len] = { 0 };
    ssize_t size = read(fd, buf, len - 1);
    if (size <= 0) {
        HILOG_ERROR("read user config file failed!");
        fdsan_close_with_tag(fd, WP_DOMAIN);
        return;
    }
    buf[size] = '\0';
    fdsan_close_with_tag(fd, WP_DOMAIN);

    if (buf[0] == '\0') {
        return;
    }
    WallpaperData systemData;
    WallpaperData lockScreenData;
    if (!GetWallpaperSafeLocked(userId, WALLPAPER_SYSTEM, systemData)
        || !GetWallpaperSafeLocked(userId, WALLPAPER_LOCKSCREEN, lockScreenData)) {
        return;
    }
    cJSON *root = cJSON_Parse(buf);
    if (root == nullptr) {
        HILOG_ERROR("Failed to parse json.");
        return;
    }
    cJSON *systemResTypeItem = cJSON_GetObjectItemCaseSensitive(root, SYSTEM_RES_TYPE);
    if (systemResTypeItem != nullptr && cJSON_IsNumber(systemResTypeItem)) {
        systemData.resourceType = static_cast<WallpaperResourceType>(systemResTypeItem->valueint);
    }

    cJSON *lockScreenResTypeItem = cJSON_GetObjectItemCaseSensitive(root, LOCKSCREEN_RES_TYPE);
    if (lockScreenResTypeItem != nullptr && cJSON_IsNumber(lockScreenResTypeItem)) {
        lockScreenData.resourceType = static_cast<WallpaperResourceType>(lockScreenResTypeItem->valueint);
    }
    cJSON_Delete(root);
}

std::string WallpaperService::GetDefaultResDir()
{
    std::string resPath;
    CfgFiles *cfgFiles = GetCfgFiles(RESOURCE_PATH);
    if (cfgFiles != nullptr) {
        for (auto &cfgPath : cfgFiles->paths) {
            if (cfgPath != nullptr) {
                HILOG_DEBUG("GetCfgFiles path is :%{public}s", FileDeal::ToBeAnonymous(cfgPath).c_str());
                resPath = cfgPath + std::string(DEFAULT_PATH);
                break;
            }
        }
        FreeCfgFiles(cfgFiles);
    }
    return resPath;
}

std::string WallpaperService::GetWallpaperPathInJson(const std::string manifestName, const std::string filePath)
{
    std::string wallpaperPath;
    std::string resPath = GetDefaultResDir();
    if (resPath.empty() && !FileDeal::IsDirExist(resPath)) {
        HILOG_ERROR("wallpaperDefaultDir get failed!");
        return "";
    }
    std::string manifestFile = resPath + manifestName;
    std::ifstream file(manifestFile);
    if (!file.is_open()) {
        HILOG_ERROR("open fail:%{public}s", FileDeal::ToBeAnonymous(manifestFile).c_str());
        file.close();
        return "";
    }
    std::string content((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    file.close();
    cJSON *root = cJSON_Parse(content.c_str());
    if (root == nullptr) {
        HILOG_ERROR("Failed to parse json.");
        return "";
    }
    cJSON *image = cJSON_GetObjectItemCaseSensitive(root, IMAGE);
    if (image != nullptr && cJSON_IsObject(image)) {
        cJSON *src = cJSON_GetObjectItemCaseSensitive(image, SRC);
        if (src != nullptr && cJSON_IsString(src)) {
            std::string srcValue = src->valuestring;
            cJSON_Delete(root);
            return GetExistFilePath(resPath + filePath + srcValue);
        }
    }
    cJSON_Delete(root);
    HILOG_ERROR("src not exist.");
    return "";
}

std::string WallpaperService::GetExistFilePath(const std::string &filePath)
{
    if (!FileDeal::IsFileExist(filePath)) {
        HILOG_ERROR("path file is not exist! %{public}s", FileDeal::ToBeAnonymous(filePath).c_str());
        return "";
    }
    return filePath;
}

void WallpaperService::CloseVectorFd(const std::vector<int> &fdVector)
{
    for (auto &fd : fdVector) {
        if (fd >= 0) {
            close(fd);
        }
    }
}

void WallpaperService::CloseWallpaperInfoFd(const std::vector<WallpaperPictureInfo> &wallpaperPictureInfo)
{
    for (auto &wallpaperInfo : wallpaperPictureInfo) {
        if (wallpaperInfo.fd >= 0) {
            close(wallpaperInfo.fd);
        }
    }
}

ErrCode WallpaperService::SetAllWallpapers(const WallpaperPictureInfoByParcel &wallpaperPictureInfoByParcel,
    int32_t wallpaperType, const std::vector<int> &fdVector)
{
    StartAsyncTrace(HITRACE_TAG_MISC, "SetAllWallpapers", static_cast<int32_t>(TraceTaskId::SET_ALL_WALLPAPERS));
    std::vector<WallpaperPictureInfo> wallpaperPictureInfo;
    wallpaperPictureInfo = wallpaperPictureInfoByParcel.wallpaperPictureInfo_;
    if (wallpaperPictureInfo.size() != fdVector.size() || fdVector.size() == 0) {
        HILOG_ERROR("wallpaperPictureInfo size = %{public}zu and fdVector size = %{public}zu is inconsistent",
            wallpaperPictureInfo.size(), fdVector.size());
        CloseVectorFd(fdVector);
        return E_DEAL_FAILED;
    }
    for (std::size_t i = 0; i < fdVector.size(); ++i) {
        wallpaperPictureInfo[i].fd = fdVector[i];
    }
    ErrorCode wallpaperErrorCode = SetAllWallpapers(wallpaperPictureInfo, wallpaperType, PICTURE);
    FinishAsyncTrace(HITRACE_TAG_MISC, "SetAllWallpapers", static_cast<int32_t>(TraceTaskId::SET_ALL_WALLPAPERS));
    CloseWallpaperInfoFd(wallpaperPictureInfo);
    return wallpaperErrorCode;
}

ErrorCode WallpaperService::SetAllWallpapers(
    std::vector<WallpaperPictureInfo> allWallpaperInfos, int32_t wallpaperType, WallpaperResourceType resourceType)
{
    StartAsyncTrace(HITRACE_TAG_MISC, "SetAllWallpapers", static_cast<int32_t>(TraceTaskId::SET_ALL_WALLPAPERS));
    if (!IsSystemApp() && !IsNativeSa()) {
        HILOG_ERROR("Is not SystemApp or NativeSA.");
        return E_NOT_SYSTEM_APP;
    }
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_SET_WALLPAPER)) {
        HILOG_ERROR("SetWallpaper no set permission.");
        return E_NO_PERMISSION;
    }
    int32_t userId = QueryActiveUserId();
    HILOG_INFO("SetAllWallpapers userId: %{public}d", userId);
    if (!CheckUserPermissionById(userId)) {
        return E_USER_IDENTITY_ERROR;
    }
    ErrorCode errCode;
    for (auto &wallpaperInfo : allWallpaperInfos) {
        wallpaperInfo.tempPath = std::string(WALLPAPER_USERID_PATH) + GetFoldStateName(wallpaperInfo.foldState) + "_"
                                 + GetRotateStateName(wallpaperInfo.rotateState);
        errCode = CheckValid(wallpaperType, wallpaperInfo.length, resourceType);
        if (errCode != NO_ERROR) {
            return errCode;
        }
        errCode = WriteFdToFile(wallpaperInfo, wallpaperInfo.tempPath);
        if (errCode != NO_ERROR) {
            DeleteTempResource(allWallpaperInfos);
            HILOG_ERROR("WriteFdToFile failed!");
            return errCode;
        }
    }
    WallpaperType type = static_cast<WallpaperType>(wallpaperType);
    std::string wallpaperPath = GetWallpaperDir(userId, type);
    FileDeal::DeleteDir(wallpaperPath, false);
    errCode = UpdateWallpaperData(allWallpaperInfos, userId, type);
    if (errCode != NO_ERROR) {
        HILOG_ERROR("UpdateWallpaperData failed!");
        return errCode;
    }
    SaveColor(userId, type);
    if (!SendWallpaperChangeEvent(userId, type)) {
        HILOG_ERROR("Send wallpaper state failed!");
        return E_DEAL_FAILED;
    }
    FinishAsyncTrace(HITRACE_TAG_MISC, "SetAllWallpapers", static_cast<int32_t>(TraceTaskId::SET_ALL_WALLPAPERS));
    return errCode;
}

ErrorCode WallpaperService::UpdateWallpaperData(
    std::vector<WallpaperPictureInfo> allWallpaperInfos, int32_t userId, WallpaperType wallpaperType)
{
    ErrorCode errCode;
    WallpaperData wallpaperData;
    bool ret = GetWallpaperSafeLocked(userId, wallpaperType, wallpaperData);
    if (!ret) {
        HILOG_ERROR("GetWallpaperSafeLocked failed!");
        return E_DEAL_FAILED;
    }
    ClearnWallpaperDataFile(wallpaperData);
    errCode = SetAllWallpaperBackupData(allWallpaperInfos, userId, wallpaperType, wallpaperData);
    if (errCode != NO_ERROR) {
        DeleteTempResource(allWallpaperInfos);
        HILOG_ERROR("SetAllWallpaperBackupData failed!");
        return errCode;
    }
    wallpaperData.resourceType = PICTURE;
    wallpaperData.wallpaperId = MakeWallpaperIdLocked();
    if (wallpaperType == WALLPAPER_SYSTEM) {
        systemWallpaperMap_.InsertOrAssign(userId, wallpaperData);
    } else if (wallpaperType == WALLPAPER_LOCKSCREEN) {
        lockWallpaperMap_.InsertOrAssign(userId, wallpaperData);
    }
    return NO_ERROR;
}

ErrorCode WallpaperService::WriteFdToFile(WallpaperPictureInfo &wallpaperPictureInfo, std::string &path)
{
    std::lock_guard<std::mutex> lock(mtx_);
    char *wallpaperBuffer = new (std::nothrow) char[wallpaperPictureInfo.length]();
    if (wallpaperBuffer == nullptr) {
        HILOG_ERROR("create wallpaperBuffer failed!");
        return E_NO_MEMORY;
    }
    if (read(wallpaperPictureInfo.fd, wallpaperBuffer, wallpaperPictureInfo.length) <= 0) {
        HILOG_ERROR("read fd failed!");
        delete[] wallpaperBuffer;
        return E_DEAL_FAILED;
    }
    mode_t mode = S_IRUSR | S_IWUSR;
    int32_t fdw = open(path.c_str(), O_WRONLY | O_CREAT, mode);
    if (fdw < 0) {
        HILOG_ERROR("Open wallpaper tmpFullPath failed, errno %{public}d", errno);
        delete[] wallpaperBuffer;
        return E_DEAL_FAILED;
    }
    fdsan_exchange_owner_tag(fdw, 0, WP_DOMAIN);
    if (write(fdw, wallpaperBuffer, wallpaperPictureInfo.length) <= 0) {
        HILOG_ERROR("Write to fdw failed, errno %{public}d", errno);
        ReporterFault(FaultType::SET_WALLPAPER_FAULT, FaultCode::RF_DROP_FAILED);
        delete[] wallpaperBuffer;
        fdsan_close_with_tag(fdw, WP_DOMAIN);
        return E_DEAL_FAILED;
    }
    delete[] wallpaperBuffer;
    fdsan_close_with_tag(fdw, WP_DOMAIN);
    return NO_ERROR;
}

ErrorCode WallpaperService::SetAllWallpaperBackupData(std::vector<WallpaperPictureInfo> allWallpaperInfos,
    int32_t userId, WallpaperType wallpaperType, WallpaperData &wallpaperData)
{
    HILOG_INFO("set All wallpaper and backup data Start.");
    for (auto &wallpaperInfo : allWallpaperInfos) {
        if (!OHOS::FileExists(wallpaperInfo.tempPath)) {
            return E_DEAL_FAILED;
        }
        UpdateWallpaperDataFile(wallpaperInfo, userId, wallpaperType, wallpaperData);
        std::string wallpaperFile = GetWallpaperDataFile(wallpaperInfo, userId, wallpaperType);
        {
            std::lock_guard<std::mutex> lock(mtx_);
            if (!FileDeal::CopyFile(wallpaperInfo.tempPath, wallpaperFile)) {
                HILOG_ERROR("CopyFile failed!");
                FileDeal::DeleteFile(wallpaperInfo.tempPath);
                return E_DEAL_FAILED;
            }
            if (!FileDeal::DeleteFile(wallpaperInfo.tempPath)) {
                return E_DEAL_FAILED;
            }
        }
    }
    return NO_ERROR;
}

void WallpaperService::UpdateWallpaperDataFile(WallpaperPictureInfo &wallpaperPictureInfo, int32_t userId,
    WallpaperType wallpaperType, WallpaperData &wallpaperData)
{
    switch (static_cast<FoldState>(wallpaperPictureInfo.foldState)) {
        case FoldState::NORMAL:
            if (static_cast<RotateState>(wallpaperPictureInfo.rotateState) == RotateState::PORT) {
                wallpaperData.wallpaperFile = GetWallpaperDir(userId, wallpaperType) + "/"
                                              + (wallpaperType == WALLPAPER_SYSTEM ? WALLPAPER_HOME : WALLPAPER_LOCK);
            } else if (static_cast<RotateState>(wallpaperPictureInfo.rotateState) == RotateState::LAND) {
                wallpaperData.normalLandFile = GetWallpaperDataFile(wallpaperPictureInfo, userId, wallpaperType);
            }
            break;

        case FoldState::UNFOLD_1:
            if (static_cast<RotateState>(wallpaperPictureInfo.rotateState) == RotateState::PORT) {
                wallpaperData.unfoldedOnePortFile = GetWallpaperDataFile(wallpaperPictureInfo, userId, wallpaperType);
            } else if (static_cast<RotateState>(wallpaperPictureInfo.rotateState) == RotateState::LAND) {
                wallpaperData.unfoldedOneLandFile = GetWallpaperDataFile(wallpaperPictureInfo, userId, wallpaperType);
            }
            break;

        case FoldState::UNFOLD_2:
            if (static_cast<RotateState>(wallpaperPictureInfo.rotateState) == RotateState::PORT) {
                wallpaperData.unfoldedTwoPortFile = GetWallpaperDataFile(wallpaperPictureInfo, userId, wallpaperType);
            } else if (static_cast<RotateState>(wallpaperPictureInfo.rotateState) == RotateState::LAND) {
                wallpaperData.unfoldedTwoLandFile = GetWallpaperDataFile(wallpaperPictureInfo, userId, wallpaperType);
            }
            break;
        default:
            break;
    }
}

std::string WallpaperService::GetWallpaperDataFile(
    WallpaperPictureInfo &wallpaperPictureInfo, int32_t userId, WallpaperType wallpaperType)
{
    std::string wallpaperTypeName = wallpaperType == WALLPAPER_SYSTEM ? WALLPAPER_HOME : WALLPAPER_LOCK;
    std::string foldStateName = GetFoldStateName(wallpaperPictureInfo.foldState);
    std::string rotateStateName = GetRotateStateName(wallpaperPictureInfo.rotateState);
    if (foldStateName == "normal" && rotateStateName == "port") {
        return GetWallpaperDir(userId, wallpaperType) + "/" + wallpaperTypeName;
    }
    std::string wallpaperFile =
        GetWallpaperDir(userId, wallpaperType) + "/" + foldStateName + "_" + rotateStateName + "_" + wallpaperTypeName;
    return wallpaperFile;
}

void WallpaperService::ClearnWallpaperDataFile(WallpaperData &wallpaperData)
{
    wallpaperData.normalLandFile = "";
    wallpaperData.unfoldedOnePortFile = "";
    wallpaperData.unfoldedOneLandFile = "";
    wallpaperData.unfoldedTwoPortFile = "";
    wallpaperData.unfoldedTwoLandFile = "";
}

ErrCode WallpaperService::GetCorrespondWallpaper(
    int32_t wallpaperType, int32_t foldState, int32_t rotateState, int32_t &size, int &fd)
{
    StartAsyncTrace(
        HITRACE_TAG_MISC, "GetCorrespondWallpaper", static_cast<int32_t>(TraceTaskId::GET_CORRESPOND_WALLPAPER));
    HILOG_DEBUG("WallpaperService::GetCorrespondWallpaper start.");
    if (!IsSystemApp()) {
        HILOG_ERROR("CallingApp is not SystemApp.");
        return E_NOT_SYSTEM_APP;
    }
    if (!CheckCallingPermission(WALLPAPER_PERMISSION_NAME_GET_WALLPAPER)) {
        HILOG_ERROR("GetPixelMap no get permission!");
        return E_NO_PERMISSION;
    }
    if (wallpaperType != static_cast<int32_t>(WALLPAPER_LOCKSCREEN)
        && wallpaperType != static_cast<int32_t>(WALLPAPER_SYSTEM)) {
        return E_PARAMETERS_INVALID;
    }
    auto type = static_cast<WallpaperType>(wallpaperType);
    int32_t userId = QueryActiveUserId();
    HILOG_INFO("QueryCurrentOsAccount userId: %{public}d", userId);
    // current user's wallpaper is live video, not image
    WallpaperResourceType resType = GetResType(userId, type);
    if (resType != PICTURE && resType != DEFAULT) {
        HILOG_ERROR("Current user's wallpaper is live video, not image.");
        size = 0; // 0: empty file size
        fd = -1;  // -1: invalid file description
        return NO_ERROR;
    }
    ErrorCode ret = GetImageSize(userId, type, size, foldState, rotateState);
    if (ret != NO_ERROR) {
        HILOG_ERROR("GetImageSize failed!");
        return ret;
    }
    ret = GetImageFd(userId, type, fd, foldState, rotateState);
    if (ret != NO_ERROR) {
        HILOG_ERROR("GetImageFd failed!");
        return ret;
    }
    return NO_ERROR;
}

ErrorCode WallpaperService::GetImageSize(
    int32_t userId, WallpaperType wallpaperType, int32_t &size, int32_t foldState, int32_t rotateState)
{
    HILOG_DEBUG("WallpaperService::GetImageSize start.");
    std::string filePathName;
    if (!GetWallpaperDataPath(userId, wallpaperType, filePathName, foldState, rotateState)) {
        return E_DEAL_FAILED;
    }
    HILOG_INFO("GetImageSize file: %{public}s", FileDeal::ToBeAnonymous(filePathName).c_str());
    if (!OHOS::FileExists(filePathName)) {
        HILOG_ERROR("file is not exist.");
        return E_NOT_FOUND;
    }
    std::lock_guard<std::mutex> lock(mtx_);
    FILE *fd = fopen(filePathName.c_str(), "rb");
    if (fd == nullptr) {
        HILOG_ERROR("fopen file failed, errno %{public}d", errno);
        return E_FILE_ERROR;
    }
    int32_t fend = fseek(fd, 0, SEEK_END);
    size = ftell(fd);
    int32_t fset = fseek(fd, 0, SEEK_SET);
    if (size <= 0 || fend != 0 || fset != 0) {
        HILOG_ERROR("ftell file failed or fseek file failed, errno %{public}d", errno);
        fclose(fd);
        return E_FILE_ERROR;
    }
    fclose(fd);
    return NO_ERROR;
}

ErrorCode WallpaperService::GetImageFd(
    int32_t userId, WallpaperType wallpaperType, int32_t &fd, int32_t foldState, int32_t rotateState)
{
    HILOG_DEBUG("WallpaperService::GetImageFd start.");
    std::string filePathName;
    if (!GetWallpaperDataPath(userId, wallpaperType, filePathName, foldState, rotateState)) {
        return E_DEAL_FAILED;
    }
    if (GetResType(userId, wallpaperType) == WallpaperResourceType::PACKAGE) {
        HILOG_INFO("The current wallpaper is a custom wallpaper");
        return NO_ERROR;
    }
    fd = open(filePathName.c_str(), O_RDONLY, S_IREAD);
    if (fd < 0) {
        HILOG_ERROR("Open file failed, errno %{public}d", errno);
        ReporterFault(FaultType::LOAD_WALLPAPER_FAULT, FaultCode::RF_FD_INPUT_FAILED);
        return E_DEAL_FAILED;
    }
    fdsan_exchange_owner_tag(fd, 0, WP_DOMAIN);
    HILOG_INFO("fd = %{public}d", fd);
    return NO_ERROR;
}

bool WallpaperService::GetWallpaperDataPath(
    int32_t userId, WallpaperType wallpaperType, std::string &filePathName, int32_t foldState, int32_t rotateState)
{
    auto iterator = wallpaperType == WALLPAPER_SYSTEM ? systemWallpaperMap_.Find(userId)
                                                      : lockWallpaperMap_.Find(userId);
    if (!iterator.first) {
        HILOG_INFO("WallpaperType:%{public}d, WallpaperMap not found userId: %{public}d", wallpaperType, userId);
        OnInitUser(userId);
        iterator = wallpaperType == WALLPAPER_SYSTEM ? systemWallpaperMap_.Find(userId)
                                                     : lockWallpaperMap_.Find(userId);
    }
    filePathName = GetWallpaperPath(foldState, rotateState, iterator.second);
    return filePathName != "";
}

std::string WallpaperService::GetWallpaperPath(int32_t foldState, int32_t rotateState, WallpaperData &wallpaperData)
{
    std::string wallpaperFilePath;
    if (foldState == static_cast<int32_t>(FoldState::UNFOLD_2)) {
        if (rotateState == static_cast<int32_t>(RotateState::LAND)) {
            wallpaperFilePath = wallpaperData.unfoldedTwoLandFile;
            if (wallpaperFilePath != "") {
                return wallpaperFilePath;
            }
        }
        wallpaperFilePath = wallpaperData.unfoldedTwoPortFile;
        if (wallpaperFilePath != "") {
            return wallpaperFilePath;
        }
        wallpaperFilePath = wallpaperData.wallpaperFile;
    }
    if (foldState == static_cast<int32_t>(FoldState::UNFOLD_1)) {
        if (rotateState == static_cast<int32_t>(RotateState::LAND)) {
            wallpaperFilePath = wallpaperData.unfoldedOneLandFile;
            if (wallpaperFilePath != "") {
                return wallpaperFilePath;
            }
        }
        wallpaperFilePath = wallpaperData.unfoldedOnePortFile;
        if (wallpaperFilePath != "") {
            return wallpaperFilePath;
        }
        wallpaperFilePath = wallpaperData.wallpaperFile;
    }
    if (foldState == static_cast<int32_t>(FoldState::NORMAL)) {
        if (rotateState == static_cast<int32_t>(RotateState::LAND)) {
            wallpaperFilePath = wallpaperData.normalLandFile;
            if (wallpaperFilePath != "") {
                return wallpaperFilePath;
            }
        }
        wallpaperFilePath = wallpaperData.wallpaperFile;
    }
    return wallpaperFilePath;
}

void WallpaperService::DeleteTempResource(std::vector<WallpaperPictureInfo> &tempResourceFiles)
{
    for (auto &wallpaperFile : tempResourceFiles) {
        FileDeal::DeleteFile(wallpaperFile.tempPath);
    }
}

std::string WallpaperService::GetFoldStateName(FoldState foldState)
{
    std::string foldStateName;
    switch (foldState) {
        case FoldState::NORMAL:
            foldStateName = "normal";
            break;
        case FoldState::UNFOLD_1:
            foldStateName = "unfold1";
            break;
        case FoldState::UNFOLD_2:
            foldStateName = "unfold2";
            break;
        default:
            break;
    }
    return foldStateName;
}

std::string WallpaperService::GetRotateStateName(RotateState rotateState)
{
    std::string rotateStateName;
    switch (rotateState) {
        case RotateState::PORT:
            rotateStateName = "port";
            break;
        case RotateState::LAND:
            rotateStateName = "land";
            break;
        default:
            break;
    }
    return rotateStateName;
}

ErrCode WallpaperService::IsDefaultWallpaperResource(
    int32_t userId, int32_t wallpaperType, bool &isDefaultWallpaperResource)
{
    HILOG_INFO("IsDefaultWallpaperResource start");
    if (wallpaperType == static_cast<int32_t>(WALLPAPER_SYSTEM)) {
        std::string wallpaperSystemPath = std::string(WALLPAPER_USERID_PATH) + std::to_string(userId) + "/"
                                          + std::string(WALLPAPER_SYSTEM_DIRNAME) + "/";
        if (!FileDeal::IsFileExistInDir(wallpaperSystemPath)) {
            HILOG_INFO("System is empty");
            isDefaultWallpaperResource = true;
            return NO_ERROR;
        }
    } else if (wallpaperType == static_cast<int32_t>(WALLPAPER_LOCKSCREEN)) {
        std::string wallpaperLockscreenPath = std::string(WALLPAPER_USERID_PATH) + std::to_string(userId) + "/"
                                              + std::string(WALLPAPER_LOCKSCREEN_DIRNAME) + "/";
        if (!FileDeal::IsFileExistInDir(wallpaperLockscreenPath)) {
            HILOG_INFO("Lockscreen is empty");
            isDefaultWallpaperResource = true;
            return NO_ERROR;
        }
    }
    isDefaultWallpaperResource = false;
    return NO_ERROR;
}

int32_t WallpaperService::CallbackParcel(
    uint32_t code, MessageParcel &data, MessageParcel &reply, MessageOption &option)
{
    switch (static_cast<IWallpaperServiceIpcCode>(code)) {
        case IWallpaperServiceIpcCode::COMMAND_GET_PIXEL_MAP: {
            return GetPixleMapParcel(data, reply, false);
        }
        case IWallpaperServiceIpcCode::COMMAND_GET_PIXEL_MAP_V9: {
            return GetPixleMapParcel(data, reply, true);
        }
        case IWallpaperServiceIpcCode::COMMAND_GET_CORRESPOND_WALLPAPER: {
            return GetCorrespondWallpaperParcel(data, reply);
        }
        case IWallpaperServiceIpcCode::COMMAND_GET_FILE: {
            return GetFileParcel(data, reply);
        }
        case IWallpaperServiceIpcCode::COMMAND_SET_WALLPAPER_BY_PIXEL_MAP: {
            return SetwallpaperByPixelMapParcel(data, reply, false);
        }
        case IWallpaperServiceIpcCode::COMMAND_SET_WALLPAPER_V9_BY_PIXEL_MAP: {
            return SetwallpaperByPixelMapParcel(data, reply, true);
        }
        default:
            return NO_ERROR;
    }
}

int32_t WallpaperService::GetPixleMapParcel(MessageParcel &data, MessageParcel &reply, bool isSystemApi)
{
    std::u16string myDescriptor = WallpaperServiceStub::GetDescriptor();
    std::u16string remoteDescriptor = data.ReadInterfaceToken();
    if (myDescriptor != remoteDescriptor) {
        HILOG_ERROR("Remote descriptor not the same as local descriptor.");
        return E_CHECK_DESCRIPTOR_ERROR;
    }
    int32_t wallpaperType = data.ReadInt32();
    int32_t size;
    int fd = DEFAULT_WALLPAPER_ID;
    ErrCode errCode = E_UNKNOWN;
    if (isSystemApi) {
        errCode = GetPixelMapV9(wallpaperType, size, fd);
    } else {
        errCode = GetPixelMap(wallpaperType, size, fd);
    }
    if (!reply.WriteInt32(errCode)) {
        HILOG_ERROR("WriteInt32 fail!");
        if (fd > DEFAULT_WALLPAPER_ID) {
            fdsan_close_with_tag(fd, WP_DOMAIN);
        }
        return ERR_INVALID_VALUE;
    }
    if (!reply.WriteInt32(size)) {
        HILOG_ERROR("WriteInt32 fail!");
        if (fd > DEFAULT_WALLPAPER_ID) {
            fdsan_close_with_tag(fd, WP_DOMAIN);
        }
        return ERR_INVALID_DATA;
    }
    HILOG_ERROR("getpixelmap fd %{public}d!", fd);
    if (!reply.WriteFileDescriptor(fd)) {
        HILOG_ERROR("WriteFileDescriptor fail!");
        if (fd > DEFAULT_WALLPAPER_ID) {
            fdsan_close_with_tag(fd, WP_DOMAIN);
        }
        return ERR_INVALID_DATA;
    }
    if (fd > DEFAULT_WALLPAPER_ID) {
        fdsan_close_with_tag(fd, WP_DOMAIN);
    }
    if (errCode == NO_ERROR) {
        return E_OK;
    }
    return errCode;
}

int32_t WallpaperService::GetCorrespondWallpaperParcel(MessageParcel &data, MessageParcel &reply)
{
    std::u16string myDescriptor = WallpaperServiceStub::GetDescriptor();
    std::u16string remoteDescriptor = data.ReadInterfaceToken();
    if (myDescriptor != remoteDescriptor) {
        HILOG_ERROR("Remote descriptor not the same as local descriptor.");
        return E_CHECK_DESCRIPTOR_ERROR;
    }
    int32_t wallpaperType = data.ReadInt32();
    int32_t foldState = data.ReadInt32();
    int32_t rotateState = data.ReadInt32();
    int32_t size;
    int fd = DEFAULT_WALLPAPER_ID;
    ErrCode errCode = GetCorrespondWallpaper(wallpaperType, foldState, rotateState, size, fd);
    if (!reply.WriteInt32(errCode)) {
        HILOG_ERROR("WriteInt32 fail!");
        if (fd > DEFAULT_WALLPAPER_ID) {
            fdsan_close_with_tag(fd, WP_DOMAIN);
        }
        return ERR_INVALID_VALUE;
    }
    if (!reply.WriteInt32(size)) {
        HILOG_ERROR("WriteInt32 fail!");
        if (fd > DEFAULT_WALLPAPER_ID) {
            fdsan_close_with_tag(fd, WP_DOMAIN);
        }
        return ERR_INVALID_DATA;
    }
    if (!reply.WriteFileDescriptor(fd)) {
        HILOG_ERROR("WriteFileDescriptor fail!");
        if (fd > DEFAULT_WALLPAPER_ID) {
            fdsan_close_with_tag(fd, WP_DOMAIN);
        }
        return ERR_INVALID_DATA;
    }
    if (fd > DEFAULT_WALLPAPER_ID) {
        fdsan_close_with_tag(fd, WP_DOMAIN);
    }
    if (errCode == NO_ERROR) {
        return E_OK;
    }
    return errCode;
}

int32_t WallpaperService::GetFileParcel(MessageParcel &data, MessageParcel &reply)
{
    std::u16string myDescriptor = WallpaperServiceStub::GetDescriptor();
    std::u16string remoteDescriptor = data.ReadInterfaceToken();
    if (myDescriptor != remoteDescriptor) {
        HILOG_ERROR("Remote descriptor not the same as local descriptor.");
        return E_CHECK_DESCRIPTOR_ERROR;
    }
    int32_t wallpaperType = data.ReadInt32();
    int wallpaperFd = DEFAULT_WALLPAPER_ID;
    ErrCode errCode = GetFile(wallpaperType, wallpaperFd);
    if (!reply.WriteInt32(errCode)) {
        HILOG_ERROR("WriteInt32 fail!");
        if (wallpaperFd > DEFAULT_WALLPAPER_ID) {
            fdsan_close_with_tag(wallpaperFd, WP_DOMAIN);
        }
        return ERR_INVALID_VALUE;
    }
    if (!reply.WriteFileDescriptor(wallpaperFd)) {
        HILOG_ERROR("WriteFileDescriptor fail!");
        if (wallpaperFd > DEFAULT_WALLPAPER_ID) {
            fdsan_close_with_tag(wallpaperFd, WP_DOMAIN);
        }
        return ERR_INVALID_DATA;
    }
    HILOG_ERROR("GetFileParcel fd %{public}d!", wallpaperFd);
    if (wallpaperFd > DEFAULT_WALLPAPER_ID) {
        fdsan_close_with_tag(wallpaperFd, WP_DOMAIN);
    }
    if (errCode == NO_ERROR) {
        return E_OK;
    }
    return errCode;
}

int32_t WallpaperService::SetwallpaperByPixelMapParcel(MessageParcel &data, MessageParcel &reply, bool isSystemApi)
{
    std::u16string myDescriptor = WallpaperServiceStub::GetDescriptor();
    std::u16string remoteDescriptor = data.ReadInterfaceToken();
    if (myDescriptor != remoteDescriptor) {
        HILOG_ERROR("Remote descriptor not the same as local descriptor.");
        return E_CHECK_DESCRIPTOR_ERROR;
    }
    WallpaperRawData wallpaperRawData;
    wallpaperRawData.size = data.ReadUint32();
    if (wallpaperRawData.size <= 0) {
        HILOG_ERROR("ReadUint32 fail!");
        return ERR_INVALID_VALUE;
    }
    wallpaperRawData.data = data.ReadRawData(wallpaperRawData.size);
    int32_t wallpaperType = data.ReadInt32();
    ErrCode errCode = E_UNKNOWN;
    if (isSystemApi) {
        errCode = SetWallpaperV9ByPixelMap(wallpaperRawData, wallpaperType);
    } else {
        errCode = SetWallpaperByPixelMap(wallpaperRawData, wallpaperType);
    }
    if (errCode == NO_ERROR) {
        return E_OK;
    }
    return errCode;
}
} // namespace WallpaperMgrService
} // namespace OHOS
