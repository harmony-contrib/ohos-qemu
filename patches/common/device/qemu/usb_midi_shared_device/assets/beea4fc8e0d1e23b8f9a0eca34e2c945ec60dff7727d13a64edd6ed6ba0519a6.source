/*
 * Copyright (c) 2025 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#define MLOG_TAG "MediaMtpServicemanager"

#include <thread>

#include "media_mtp_manager.h"
#include "media_log.h"
#include "media_mtp_service_manager.h"
#include "media_mtp_subscriber.h"
#include "parameter.h"
#include "parameters.h"
#include "usb_srv_client.h"
#include "usb_srv_support.h"

#define USB_FUNTION_HDC     (1 << 2)
#define USB_FUNTION_MTP     (1 << 3)
#define USB_FUNTION_PTP     (1 << 4)
#define USB_FUNTION_STORAGE     (1 << 9)
//LCOV_EXCL_START
namespace OHOS {
namespace Media {
namespace {
    static std::mutex mutex_;
    std::atomic<bool> isMtpServiceRunning = false;
    const std::string KEY_CUST = "const.cust.custPath";
    const std::string CUST_DEFAULT = "phone";
    const std::string CUST_TOBBASIC = "tobbasic";
    const std::string CUST_HWIT = "hwit";
    const char *MTP_SERVER_DISABLE = "persist.edm.mtp_server_disable";
}

MediaMtpManager &MediaMtpManager::GetInstance()
{
    static MediaMtpManager instance;
    return instance;
}

void MediaMtpManager::Init()
{
    std::thread([]() {
        MEDIA_INFO_LOG("MediaMtpManager Init");
        // IT管控 PC - tobasic/hwit 不启动MTP服务 start
        std::string cust = OHOS::system::GetParameter(KEY_CUST, CUST_DEFAULT);
        bool cond = (cust.find(CUST_TOBBASIC) != std::string::npos || cust.find(CUST_HWIT) != std::string::npos);
        CHECK_AND_RETURN_INFO_LOG(!cond, "MediaMtpManager Init Return cust = [%{public}s]", cust.c_str());
        // IT管控 PC - tobasic/hwit 不启动MTP服务 end
        bool result = MediaMtpSubscriber::Subscribe();
        MEDIA_INFO_LOG("MediaMtpManager Subscribe result = %{public}d", result);
        // param 监听注册
        MediaMtpManager::GetInstance().RegisterMtpParamListener();

        int32_t funcs = 0;
        int ret = OHOS::USB::UsbSrvClient::GetInstance().GetCurrentFunctions(funcs);
        MEDIA_INFO_LOG("MediaMtpManager Init GetCurrentFunctions = %{public}d ret = %{public}d", funcs, ret);
        CHECK_AND_RETURN_LOG(ret == 0, "GetCurrentFunctions failed");
        uint32_t unsignedfuncs = static_cast<uint32_t>(funcs);
        if (unsignedfuncs & USB::UsbSrvSupport::Function::FUNCTION_MTP) {
            std::string param(MTP_SERVER_DISABLE);
            bool mtpDisable = system::GetBoolParameter(param, false);
            if (mtpDisable) {
                MEDIA_INFO_LOG("MediaMtpManager Init MTP Manager persist.edm.mtp_server_disable = true");
            } else {
                MEDIA_INFO_LOG("MediaMtpManager Init USB MTP connected");
                MediaMtpServiceManager::StartMtpService(MtpMode::MTP_MODE);
            }
            return;
        }
        if (unsignedfuncs & USB::UsbSrvSupport::Function::FUNCTION_PTP) {
            MediaMtpServiceManager::StartMtpService(MtpMode::PTP_MODE);
            return;
        }
        if (unsignedfuncs & USB::UsbSrvSupport::Function::FUNCTION_HDC) {
            MediaMtpServiceManager::StopMtpService();
        }
        MEDIA_INFO_LOG("MediaMtpManager Init success end");
    }).detach();
}

void MediaMtpManager::Stop()
{
    MediaMtpManager::GetInstance().RemoveMtpParamListener();
}

void MediaMtpManager::RegisterMtpParamListener()
{
    MEDIA_INFO_LOG("RegisterMTPParamListener");
    WatchParameter(MTP_SERVER_DISABLE, OnMtpParamDisableChanged, this);
}

void MediaMtpManager::RemoveMtpParamListener()
{
    MEDIA_INFO_LOG("RemoveMtpParamListener");
    RemoveParameterWatcher(MTP_SERVER_DISABLE, OnMtpParamDisableChanged, this);
}

void MediaMtpManager::OnMtpParamDisableChanged(const char *key, const char *value, void *context)
{
    std::lock_guard<std::mutex> lock(mutex_);
    bool cond = (key == nullptr || value == nullptr);
    CHECK_AND_RETURN_LOG(!cond, "OnMtpParamDisableChanged return invalid value");
    MEDIA_INFO_LOG("OnMTPParamDisable, key = %{public}s, value = %{public}s", key, value);
    CHECK_AND_RETURN_INFO_LOG(strcmp(key, MTP_SERVER_DISABLE) == 0, "event key mismatch");
    std::string param(MTP_SERVER_DISABLE);
    bool mtpDisable = system::GetBoolParameter(param, false);
    if (!mtpDisable) {
        int32_t funcs = 0;
        int ret = OHOS::USB::UsbSrvClient::GetInstance().GetCurrentFunctions(funcs);
        MEDIA_INFO_LOG("OnMtpparamDisableChanged GetCurrentFunction = %{public}d ret = %{public}d", funcs, ret);
        CHECK_AND_RETURN_INFO_LOG(ret != 0, "OnMtpparamDisableChanged GetCurrentFunction failed");
        uint32_t unsignedFuncs = static_cast<uint32_t>(funcs);
        if (unsignedFuncs && static_cast<bool>(USB::UsbSrvSupport::Function::FUNCTION_MTP)) {
            MediaMtpServiceManager::StartMtpService(MtpMode::MTP_MODE);
            return;
        }
    } else {
        MEDIA_INFO_LOG("MTP Manager not init");
        int32_t currentFunctions_ = USB_FUNTION_STORAGE;
        int ret = OHOS::USB::UsbSrvClient::GetInstance().GetCurrentFunctions(currentFunctions_);
        if (ret == 0) {
            currentFunctions_ = static_cast<uint32_t>(currentFunctions_) & (~USB_FUNTION_MTP) & (~USB_FUNTION_PTP);
            currentFunctions_ = currentFunctions_ == 0 ? USB_FUNTION_STORAGE : currentFunctions_;
            MEDIA_INFO_LOG("start to execute disconnect task");
            // 调用内核接口，将MTP或PTP端口切换为HDC接口
            OHOS::USB::UsbSrvClient::GetInstance().SetCurrentFunctions(currentFunctions_);
        }
        MediaMtpServiceManager::StopMtpService();
    }
}
} // namespace Media
} // namespace OHOS
//LCOV_EXCL_STOP