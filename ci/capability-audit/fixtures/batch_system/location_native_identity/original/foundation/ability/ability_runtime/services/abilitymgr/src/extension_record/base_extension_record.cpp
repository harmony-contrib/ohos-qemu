/*
 * Copyright (c) 2025 Huawei Device Co., Ltd.
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

#include "base_extension_record.h"

#include <singleton.h>

#include "ability_manager_service.h"
#include "ability_util.h"
#include "ams_configuration_parameter.h"
#include "connection_state_manager.h"
#include "global_constant.h"
#include "hitrace_meter.h"
#include "res_sched_util.h"
#include "ui_extension_wrapper.h"

namespace OHOS {
namespace AAFwk {
using namespace OHOS::AbilityRuntime::GlobalConstant;
const int HALF_TIMEOUT = 2;

BaseExtensionRecord::BaseExtensionRecord(const Want &want, const AppExecFwk::AbilityInfo &abilityInfo,
    const AppExecFwk::ApplicationInfo &applicationInfo, int requestCode)
    : AbilityRecord(want, abilityInfo, applicationInfo, requestCode) {}

std::shared_ptr<BaseExtensionRecord> BaseExtensionRecord::CreateBaseExtensionRecord(
    const AbilityRequest &abilityRequest)
{
    auto abilityRecord = std::make_shared<BaseExtensionRecord>(abilityRequest.want, abilityRequest.abilityInfo,
        abilityRequest.appInfo, abilityRequest.requestCode);
    abilityRecord->Init(abilityRequest);
    if (abilityRequest.abilityInfo.extensionAbilityType == AppExecFwk::ExtensionAbilityType::APP_SERVICE &&
        abilityRequest.extensionProcessMode == AppExecFwk::ExtensionProcessMode::TYPE) {
        std::string processName = abilityRequest.abilityInfo.bundleName + ":" + abilityRequest.abilityInfo.name;
        abilityRecord->SetProcessName(processName);
    }
    return abilityRecord;
}

AbilityRecordType BaseExtensionRecord::GetAbilityRecordType()
{
    return AbilityRecordType::EXTENSION_ABILITY;
}

std::shared_ptr<BaseExtensionRecord> BaseExtensionRecord::TransferToExtensionRecordBase(
    const std::shared_ptr<AbilityRecord> &abilityRecord)
{
    if (abilityRecord == nullptr) {
        return nullptr;
    }
    if (abilityRecord->GetAbilityRecordType() == AbilityRecordType::EXTENSION_ABILITY) {
        return std::static_pointer_cast<BaseExtensionRecord>(abilityRecord);
    }
    return nullptr;
}

void BaseExtensionRecord::AddConnectRecordToList(const std::shared_ptr<ConnectionRecord> &connRecord)
{
    CHECK_POINTER(connRecord);
    std::lock_guard guard(connRecordListMutex_);
    auto it = std::find(connRecordList_.begin(), connRecordList_.end(), connRecord);
    // found it
    if (it != connRecordList_.end()) {
        TAG_LOGD(AAFwkTag::ABILITYMGR, "Found it in list, so no need to add same connection");
        return;
    }
    // no found then add new connection to list
    TAG_LOGD(AAFwkTag::ABILITYMGR, "No found in list, so add new connection to list");
    connRecordList_.push_back(connRecord);
}

std::list<std::shared_ptr<ConnectionRecord>> BaseExtensionRecord::GetConnectRecordList() const
{
    std::lock_guard guard(connRecordListMutex_);
    return connRecordList_;
}

void BaseExtensionRecord::RemoveConnectRecordFromList(const std::shared_ptr<ConnectionRecord> &connRecord)
{
    CHECK_POINTER(connRecord);
    std::lock_guard guard(connRecordListMutex_);
    connRecordList_.remove(connRecord);
    if (connRecordList_.empty()) {
        isConnected = false;
    }
}

std::shared_ptr<ConnectionRecord> BaseExtensionRecord::GetConnectingRecord() const
{
    std::lock_guard guard(connRecordListMutex_);
    auto connect =
        std::find_if(connRecordList_.begin(), connRecordList_.end(), [](std::shared_ptr<ConnectionRecord> record) {
            return record->GetConnectState() == ConnectionState::CONNECTING;
        });
    return (connect != connRecordList_.end()) ? *connect : nullptr;
}

std::list<std::shared_ptr<ConnectionRecord>> BaseExtensionRecord::GetConnectingRecordList()
{
    std::lock_guard guard(connRecordListMutex_);
    std::list<std::shared_ptr<ConnectionRecord>> connectingList;
    for (auto record : connRecordList_) {
        if (record && record->GetConnectState() == ConnectionState::CONNECTING) {
            connectingList.push_back(record);
        }
    }
    return connectingList;
}

std::shared_ptr<ConnectionRecord> BaseExtensionRecord::GetDisconnectingRecord() const
{
    std::lock_guard guard(connRecordListMutex_);
    auto connect =
        std::find_if(connRecordList_.begin(), connRecordList_.end(), [](std::shared_ptr<ConnectionRecord> record) {
            return record->GetConnectState() == ConnectionState::DISCONNECTING;
        });
    return (connect != connRecordList_.end()) ? *connect : nullptr;
}

size_t BaseExtensionRecord::GetConnectedListSize()
{
    std::lock_guard guard(connRecordListMutex_);
    return std::count_if(connRecordList_.begin(), connRecordList_.end(), [](std::shared_ptr<ConnectionRecord> record) {
        return record && record->GetConnectState() == ConnectionState::CONNECTED;
    });
}

bool BaseExtensionRecord::IsConnectListEmpty()
{
    std::lock_guard guard(connRecordListMutex_);
    return connRecordList_.empty();
}

bool BaseExtensionRecord::NeedConnectAfterCommand()
{
    return !IsConnectListEmpty() && !isConnected;
}

size_t BaseExtensionRecord::GetConnectingListSize()
{
    std::lock_guard guard(connRecordListMutex_);
    return std::count_if(connRecordList_.begin(), connRecordList_.end(), [](std::shared_ptr<ConnectionRecord> record) {
        return record && record->GetConnectState() == ConnectionState::CONNECTING;
    });
}

uint32_t BaseExtensionRecord::GetInProgressRecordCount()
{
    std::lock_guard guard(connRecordListMutex_);
    uint32_t count = 0;
    for (auto record : connRecordList_) {
        if (record && (record->GetConnectState() == ConnectionState::CONNECTING ||
            record->GetConnectState() == ConnectionState::CONNECTED)) {
            count++;
        }
    }
    return count;
}

void BaseExtensionRecord::DisconnectAbility()
{
    HITRACE_METER_NAME(HITRACE_TAG_ABILITY_MANAGER, __PRETTY_FUNCTION__);
    const auto &abilityInfo = GetAbilityInfo();
    TAG_LOGI(AAFwkTag::SERVICE_EXT, "DisconnectAbility, bundle:%{public}s, ability:%{public}s.",
        abilityInfo.applicationInfo.bundleName.c_str(), abilityInfo.name.c_str());
    CHECK_POINTER(lifecycleDeal_);

    lifecycleDeal_->DisconnectAbility(GetWant());

    bool isPerConnectionType = (abilityInfo.extensionAbilityType == AppExecFwk::ExtensionAbilityType::UI_SERVICE ||
        abilityInfo.extensionAbilityType == AppExecFwk::ExtensionAbilityType::AGENT);
    if (!isPerConnectionType || GetInProgressRecordCount() == 0) {
        isConnected = false;
    }
}

void BaseExtensionRecord::DisconnectAbilityWithWant(const Want &want)
{
    HITRACE_METER_NAME(HITRACE_TAG_ABILITY_MANAGER, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::SERVICE_EXT, "DisconnectAbilityWithWant:%{public}s.", GetAbilityInfo().name.c_str());
    CHECK_POINTER(lifecycleDeal_);
    lifecycleDeal_->DisconnectAbility(want);
    if (GetInProgressRecordCount() == 0) {
        isConnected = false;
    }
}

void BaseExtensionRecord::DumpService(std::vector<std::string> &info, bool isClient) const
{
    std::vector<std::string> params;
    DumpService(info, params, isClient);
}

void BaseExtensionRecord::DumpService(std::vector<std::string> &info, std::vector<std::string> &params,
    bool isClient) const
{
    info.emplace_back("      AbilityRecord ID #" + std::to_string(GetRecordId()) + "   state #" +
                      AbilityRecord::ConvertAbilityState(GetAbilityState()) + "   start time [" +
                      std::to_string(GetStartTime()) + "]");
    info.emplace_back("      main name [" + GetAbilityInfo().name + "]");
    info.emplace_back("      bundle name [" + GetAbilityInfo().bundleName + "]");
    bool isUIExtension = UIExtensionWrapper::IsUIExtension(GetAbilityInfo().extensionAbilityType);
    if (isUIExtension) {
        info.emplace_back("      ability type [UIEXTENSION]");
    } else {
        if (GetAbilityInfo().extensionAbilityType == AppExecFwk::ExtensionAbilityType::UI_SERVICE) {
            info.emplace_back("      ability type [UI_SERVICE]");
            info.emplace_back("      windowConfig windowType [" +
                std::to_string(GetAbilityWindowConfig().windowType) + "]");
            info.emplace_back("      windowConfig windowId [" +
                std::to_string(GetAbilityWindowConfig().windowId) + "]");
        } else {
            info.emplace_back("      ability type [SERVICE]");
        }
    }
    info.emplace_back("      app state #" + AbilityRecord::ConvertAppState(GetAppState()));

    std::string isKeepAlive = GetKeepAlive() ? "true" : "false";
    info.emplace_back("        isKeepAlive: " + isKeepAlive);
    if (IsLauncherRoot()) {
        info.emplace_back("      can restart num #" + std::to_string(GetRestartCount()));
    }
    decltype(connRecordList_) connRecordListCpy;
    {
        std::lock_guard guard(connRecordListMutex_);
        connRecordListCpy = connRecordList_;
    }

    info.emplace_back("      Connections: " + std::to_string(connRecordListCpy.size()));
    for (auto &&conn : connRecordListCpy) {
        if (conn) {
            conn->Dump(info);
        }
    }
    // add dump client info
    DumpClientInfo(info, params, isClient);
    DumpUIExtensionRootHostInfo(info);
    DumpUIExtensionPid(info, isUIExtension);
}

void BaseExtensionRecord::DumpUIExtensionRootHostInfo(std::vector<std::string> &info) const
{
    if (!UIExtensionWrapper::IsUIExtension(GetAbilityInfo().extensionAbilityType)) {
        // Dump host info only for uiextension.
        return;
    }

    sptr<IRemoteObject> token = GetToken();
    if (token == nullptr) {
        TAG_LOGE(AAFwkTag::ABILITYMGR, "null token");
        return;
    }

    UIExtensionHostInfo hostInfo;
    auto ret = IN_PROCESS_CALL(AAFwk::AbilityManagerClient::GetInstance()->GetUIExtensionRootHostInfo(token, hostInfo));
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::ABILITYMGR, "failed: %{public}d", ret);
        return;
    }

    std::string dumpInfo = "      root host bundle name [" + hostInfo.elementName_.GetBundleName() + "]";
    info.emplace_back(dumpInfo);
    dumpInfo = "      root host module name [" + hostInfo.elementName_.GetModuleNameRef() + "]";
    info.emplace_back(dumpInfo);
    dumpInfo = "      root host ability name [" + hostInfo.elementName_.GetAbilityName() + "]";
    info.emplace_back(dumpInfo);
}

void BaseExtensionRecord::DumpUIExtensionPid(std::vector<std::string> &info, bool isUIExtension) const
{
    if (!isUIExtension) {
        TAG_LOGD(AAFwkTag::ABILITYMGR, "Not ui extension type.");
        return;
    }

    auto appScheduler = DelayedSingleton<AppScheduler>::GetInstance();
    if (appScheduler == nullptr) {
        TAG_LOGE(AAFwkTag::ABILITYMGR, "null appScheduler");
        return;
    }
    AppExecFwk::RunningProcessInfo processInfo;
    appScheduler->GetRunningProcessInfoByToken(GetToken(), processInfo);
    info.emplace_back("      pid: " + std::to_string(processInfo.pid_));
}

void BaseExtensionRecord::ConnectAbilityWithWant(const Want &want)
{
    TAG_LOGD(AAFwkTag::SERVICE_EXT, "Connect ability.");
    CHECK_POINTER(lifecycleDeal_);
    if (isConnected) {
        TAG_LOGW(AAFwkTag::SERVICE_EXT, "state err");
    }
    lifecycleDeal_->ConnectAbility(want);
    isConnected = true;
}

void BaseExtensionRecord::ConnectAbility()
{
    TAG_LOGI(AAFwkTag::SERVICE_EXT, "ConnectAbility");
    Want want = GetWant();
    UpdateDmsCallerInfo(want);
    ConnectAbilityWithWant(want);
}

void BaseExtensionRecord::SetConnRemoteObject(const sptr<IRemoteObject> &remoteObject)
{
    connRemoteObject_ = remoteObject;
}

sptr<IRemoteObject> BaseExtensionRecord::GetConnRemoteObject() const
{
    return connRemoteObject_;
}

void BaseExtensionRecord::SetClientPid(pid_t clientPid)
{
    clientPid_ = clientPid;
}

pid_t BaseExtensionRecord::GetClientPid() const
{
    return clientPid_;
}

void BaseExtensionRecord::SetIsInProcess(bool isInProcess)
{
    isInProcess_ = isInProcess;
}

bool BaseExtensionRecord::IsInProcess() const
{
    return isInProcess_;
}

void BaseExtensionRecord::SetRequestId(const std::string &requestId)
{
    requestId_ = requestId;
}

std::string BaseExtensionRecord::GetRequestId() const
{
    return requestId_;
}

void BaseExtensionRecord::PostUIExtensionAbilityTimeoutTask(uint32_t messageId)
{
    if (IsDebug()) {
        return;
    }
    int32_t recordId = GetRecordId();
    TAG_LOGD(AAFwkTag::ABILITYMGR, "post timeout %{public}d, id %{public}d", messageId, recordId);
    switch (messageId) {
        case AbilityManagerService::LOAD_TIMEOUT_MSG: {
            uint32_t timeout = static_cast<uint32_t>(
                AmsConfigurationParameter::GetInstance().GetAppStartTimeoutTime()) *
                static_cast<uint32_t>(LOAD_TIMEOUT_MULTIPLE);
            SendEvent(AbilityManagerService::LOAD_HALF_TIMEOUT_MSG, timeout / HALF_TIMEOUT, recordId, true);
            SendEvent(AbilityManagerService::LOAD_TIMEOUT_MSG, timeout, recordId, true);
            break;
        }
        case AbilityManagerService::FOREGROUND_TIMEOUT_MSG: {
            uint32_t timeout = static_cast<uint32_t>(
                AmsConfigurationParameter::GetInstance().GetAppStartTimeoutTime()) *
                static_cast<uint32_t>(FOREGROUND_TIMEOUT_MULTIPLE);
            if (InsightIntentExecuteParam::IsInsightIntentExecute(GetWant())) {
                timeout = static_cast<uint32_t>(
                    AmsConfigurationParameter::GetInstance().GetAppStartTimeoutTime()) *
                    static_cast<uint32_t>(INSIGHT_INTENT_TIMEOUT_MULTIPLE);
            }
            SendEvent(AbilityManagerService::FOREGROUND_HALF_TIMEOUT_MSG, timeout / HALF_TIMEOUT, recordId, true);
            SendEvent(AbilityManagerService::FOREGROUND_TIMEOUT_MSG, timeout, recordId, true);
            ResSchedUtil::GetInstance().ReportLoadingEventToRss(LoadingStage::FOREGROUND_BEGIN, GetPid(), GetUid(),
                timeout, GetAbilityRecordId());
            break;
        }
        default: {
            break;
        }
    }
}
} // namespace AAFwk
} // namespace OHOS