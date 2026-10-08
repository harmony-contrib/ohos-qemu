/*
 * Copyright (C) 2025 Huawei Device Co., Ltd.
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

#define MLOG_TAG "MediaLibraryFaCardOperations"

#include "medialibrary_facard_operations.h"

#include "medialibrary_object_utils.h"
#include "result_set_utils.h"
#include "media_facard_photos_column.h"
#include "result_set_utils.h"
#include "ability_manager_client.h"
#include "ffrt_inner.h"
 
using namespace OHOS::DataShare;
using ChangeType = OHOS::DataShare::DataShareObserver::ChangeType;
using namespace std;
using namespace OHOS::NativeRdb;
 
namespace OHOS {
namespace Media {
std::mutex MediaLibraryFaCardOperations::mutex_;
const std::string_view MEDIA_LIBRARY_PROXY_URI = "datashareproxy://com.ohos.medialibrary.medialibrarydata";
const std::string_view CLOUD_SYNC_PROXY_URI = "datashareproxy://com.huawei.hmos.clouddrive/sync_switch";

const std::string_view ASSET_URI_PREFIX = "file://media/";
const std::string_view CLOUD_SYNC_SWITCH_URI_PREFIX = "datashareproxy://";

static unordered_map<string, unordered_set<string>> g_uriMapFormIds;
static unordered_map<string, unordered_set<string>> g_formIdMapUris;

static unordered_map<string, std::shared_ptr<CardAssetUriObserver>> g_formAssetObserversMap;
static unordered_map<string, sptr<FaCloudSyncSwitchObserver>> g_formCloudSyncObserversMap;

static std::map<ChangeType, int> changeTypeMap = {
    { ChangeType::INSERT, 0 },
    { ChangeType::DELETE, 1 },
    { ChangeType::UPDATE, 2 },
    { ChangeType::OTHER, 3 },
    { ChangeType::INVAILD, 4 },
};
 
bool CardAssetUriObserver::isTaskPosted = false;
std::mutex CardAssetUriObserver::mtx;
std::unordered_set<
    CardAssetUriObserver::AssetChangeInfo,
    CardAssetUriObserver::AssetChangeInfoHash> CardAssetUriObserver::assetChanges;

bool FaCloudSyncSwitchObserver::isTaskPosted = false;
std::mutex FaCloudSyncSwitchObserver::mtx;
std::unordered_set<
    FaCloudSyncSwitchObserver::CloudSyncChangeInfo,
    FaCloudSyncSwitchObserver::CloudSyncChangeInfoHash> FaCloudSyncSwitchObserver::cloudSyncChanges;
// LCOV_EXCL_START
std::map<std::string, std::vector<std::string>> MediaLibraryFaCardOperations::GetUris()
{
    MediaLibraryCommand queryFaCardCmd(OperationObject::TAB_FACARD_PHOTO, OperationType::QUERY);
    std::map<std::string, std::vector<std::string>> resultMap;
    auto uniStore = MediaLibraryUnistoreManager::GetInstance().GetRdbStore();
    if (uniStore == nullptr) {
        MEDIA_ERR_LOG("UniStore is nullptr");
        return resultMap;
    }
    vector<string> columns = {
        TabFaCardPhotosColumn::FACARD_PHOTOS_ASSET_URI,
        TabFaCardPhotosColumn::FACARD_PHOTOS_FORM_ID
    };
    auto queryResult = uniStore->Query(queryFaCardCmd, columns);
    if (queryResult == nullptr) {
        MEDIA_ERR_LOG("Failed to query assetUris!");
        return resultMap;
    }
    while (queryResult->GoToNextRow() == NativeRdb::E_OK) {
        string assetUri = GetStringVal(TabFaCardPhotosColumn::FACARD_PHOTOS_ASSET_URI, queryResult);
        string formId = GetStringVal(TabFaCardPhotosColumn::FACARD_PHOTOS_FORM_ID, queryResult);
        resultMap[formId].push_back(assetUri);
    }
    return resultMap;
}
 
static string GetStringObject(MediaLibraryCommand &cmd, const string &columnName)
{
    ValueObject valueObject;
    ValuesBucket values = cmd.GetValueBucket();
    string value;
    if (values.GetObject(columnName, valueObject)) {
        valueObject.GetString(value);
        return value;
    }
    return "";
}

void CardAssetUriObserver::PostAssetChangeTask()
{
    if (!CardAssetUriObserver::isTaskPosted) {
        CardAssetUriObserver::isTaskPosted = true;
        thread([]() {
            MEDIA_DEBUG_LOG("CardAssetUriObserver task start");
            const int DELAY_MILLISECONDS = 2000;
            this_thread::sleep_for(chrono::milliseconds(DELAY_MILLISECONDS));
            std::lock_guard<std::mutex> lock(CardAssetUriObserver::mtx);
            std::vector<std::string> assetChangeUris;
            std::vector<int> assetChangeTypes;
            for (const auto& change : CardAssetUriObserver::assetChanges) {
                assetChangeUris.push_back(change.assetChangeUri);
                MEDIA_DEBUG_LOG("change.assetChangeUri = %{public}s", change.assetChangeUri.c_str());
                assetChangeTypes.push_back(change.assetChangeType);
                MEDIA_DEBUG_LOG("change.assetChangeType = %{public}d", change.assetChangeType);
            }
            AAFwk::Want want;
            want.SetElementName("com.huawei.hmos.photos", "FACardServiceAbility");
            want.SetParam("assetChangeUris", assetChangeUris);
            want.SetParam("assetChangeTypes", assetChangeTypes);
            int32_t userId = -1;
            auto result = AAFwk::AbilityManagerClient::GetInstance()->StartExtensionAbility(
                want, nullptr, userId, AppExecFwk::ExtensionAbilityType::SERVICE);
            CardAssetUriObserver::assetChanges.clear();
            CardAssetUriObserver::isTaskPosted = false;
            MEDIA_DEBUG_LOG("CardAssetUriObserver task end");
        }).detach();
    }
}

void FaCloudSyncSwitchObserver::PostAssetChangeTask()
{
    if (!FaCloudSyncSwitchObserver::isTaskPosted) {
        FaCloudSyncSwitchObserver::isTaskPosted = true;
        thread([]() {
            MEDIA_INFO_LOG("FaCloudSyncSwitchObserver task start");
            const int DELAY_MILLISECONDS = 2000;
            this_thread::sleep_for(chrono::milliseconds(DELAY_MILLISECONDS));
            std::lock_guard<std::mutex> lock(FaCloudSyncSwitchObserver::mtx);
            std::vector<std::string> assetChangeUris;
            std::vector<int> assetChangeTypes;
            for (const auto& change : FaCloudSyncSwitchObserver::cloudSyncChanges) {
                assetChangeUris.push_back(change.cloudSyncChangeUri);
                assetChangeTypes.push_back(change.cloudSyncChangeType);
                MEDIA_INFO_LOG("change.assetChangeUri = %{public}s, change.assetChangeType = %{public}d",
                    change.cloudSyncChangeUri.c_str(), change.cloudSyncChangeType);
            }
            AAFwk::Want want;
            want.SetElementName("com.huawei.hmos.photos", "FACardServiceAbility");
            want.SetParam("assetChangeUris", assetChangeUris);
            want.SetParam("assetChangeTypes", assetChangeTypes);
            int32_t userId = -1;
            auto result = AAFwk::AbilityManagerClient::GetInstance()->StartExtensionAbility(
                want, nullptr, userId, AppExecFwk::ExtensionAbilityType::SERVICE);
            FaCloudSyncSwitchObserver::cloudSyncChanges.clear();
            FaCloudSyncSwitchObserver::isTaskPosted = false;
            MEDIA_INFO_LOG("FaCloudSyncSwitchObserver task end");
        }).detach();
    }
}

void CardAssetUriObserver::OnChange(const ChangeInfo &changeInfo)
{
    if (changeTypeMap.find(changeInfo.changeType_) != changeTypeMap.end()) {
        std::lock_guard<std::mutex> lock(CardAssetUriObserver::mtx);
        MEDIA_DEBUG_LOG("OnChange assetChangeUri = %{public}s", assetChangeUri.c_str());
        MEDIA_DEBUG_LOG("OnChange assetChangeType = %{public}d", static_cast<int>(changeInfo.changeType_));
        CardAssetUriObserver::assetChanges.insert(
            AssetChangeInfo(assetChangeUri, static_cast<int>(changeInfo.changeType_)));

        PostAssetChangeTask();
    }
}

void FaCloudSyncSwitchObserver::OnChange()
{
    std::lock_guard<std::mutex> lock(FaCloudSyncSwitchObserver::mtx);
    const int CLOUD_SYNC_TYPE = 3;
    MEDIA_INFO_LOG("OnChange assetChangeUri = %{public}s, assetChangeType = %{public}d", cloudSyncChangeUri.c_str(),
        static_cast<int>(CLOUD_SYNC_TYPE));
    FaCloudSyncSwitchObserver::cloudSyncChanges.insert(
        CloudSyncChangeInfo(cloudSyncChangeUri, static_cast<int>(CLOUD_SYNC_TYPE)));

    PostAssetChangeTask();
}

void MediaLibraryFaCardOperations::RegisterObserver(const std::string &formId, const std::string &registerUri)
{
    MEDIA_INFO_LOG("formId: %{public}s, registerUri: %{public}s", formId.c_str(), registerUri.c_str());
    if (formId.empty() || registerUri.empty()) {
        MEDIA_ERR_LOG("parameter is null");
        return;
    }
    bool isAssetUri = (registerUri.find(ASSET_URI_PREFIX) == 0);
    if (!isAssetUri && (registerUri.find(CLOUD_SYNC_SWITCH_URI_PREFIX) != 0)) {
        MEDIA_ERR_LOG("registerUri is inValid: %{public}s", registerUri.c_str());
        return;
    }
    lock_guard<mutex> lock(mutex_);
    g_formIdMapUris[formId].emplace(registerUri);
    auto &formIds = g_uriMapFormIds[registerUri];
    if (!formIds.empty()) {
        MEDIA_WARN_LOG("registerUri: %{public}s has been registered", registerUri.c_str());
        formIds.emplace(formId);
        return;
    }
    formIds.emplace(formId);

    Uri notifyUri(registerUri);
    CreateOptions options;
    options.enabled_ = true;
    if (isAssetUri) {
        auto cardAssetUriObserver = std::make_shared<CardAssetUriObserver>(registerUri);
        CHECK_AND_RETURN_LOG(cardAssetUriObserver != nullptr, "cardAssetUriObserver is nullptr");
        auto dataShareHelper = DataShare::DataShareHelper::Creator(string(MEDIA_LIBRARY_PROXY_URI), options);
        CHECK_AND_RETURN_LOG(dataShareHelper != nullptr, "dataShareHelper is nullptr");
        dataShareHelper->RegisterObserverExt(notifyUri, cardAssetUriObserver, true);
        g_formAssetObserversMap.emplace(registerUri, cardAssetUriObserver);
    } else {
        sptr<FaCloudSyncSwitchObserver> cloudSwitchObserver(new (std::nothrow) FaCloudSyncSwitchObserver(registerUri));
        CHECK_AND_RETURN_LOG(cloudSwitchObserver != nullptr, "cloudSwitchObserver is nullptr");
        auto dataShareHelper = DataShare::DataShareHelper::Creator(string(CLOUD_SYNC_PROXY_URI), options);
        CHECK_AND_RETURN_LOG(dataShareHelper != nullptr, "dataShareHelper is nullptr");
        dataShareHelper->RegisterObserver(notifyUri, cloudSwitchObserver);
        g_formCloudSyncObserversMap.emplace(registerUri, cloudSwitchObserver);
    }
}

void MediaLibraryFaCardOperations::UnregisterObserver(const std::string &formId)
{
    MEDIA_INFO_LOG("formId: %{public}s", formId.c_str());
    CHECK_AND_RETURN_LOG(!formId.empty(), "formId is empty");
    lock_guard<mutex> lock(mutex_);
    auto formIdMapUrisIt = g_formIdMapUris.find(formId);
    CHECK_AND_RETURN_WARN_LOG(
        formIdMapUrisIt != g_formIdMapUris.end(), "formId: %{public}s has been unregistered", formId.c_str());
    CreateOptions options;
    options.enabled_ = true;
    auto libHelper = DataShare::DataShareHelper::Creator(string(MEDIA_LIBRARY_PROXY_URI), options);
    CHECK_AND_RETURN_LOG(libHelper != nullptr, "libHelper is nullptr");
    auto syncHelper = DataShare::DataShareHelper::Creator(string(CLOUD_SYNC_PROXY_URI), options);
    CHECK_AND_RETURN_LOG(syncHelper != nullptr, "syncHelper is nullptr");
    for (const auto &uri : formIdMapUrisIt->second) {
        if (g_uriMapFormIds.count(uri)) {
            g_uriMapFormIds[uri].erase(formId);
            if (!g_uriMapFormIds[uri].empty()) {
                MEDIA_WARN_LOG("uri: %{public}s has been registered for other formId, current formId: %{public}s",
                    uri.c_str(),
                    formId.c_str());
                continue;
            }
        }
        g_uriMapFormIds.erase(uri);
        Uri notifyUri(uri);
        if (uri.find(ASSET_URI_PREFIX) == 0) {
            auto it = g_formAssetObserversMap.find(uri);
            CHECK_AND_CONTINUE_ERR_LOG(
                it != g_formAssetObserversMap.end(), "uri: %{public}s, cardAssetUriObserver not find", uri.c_str());
            if (it->second != nullptr) {
                libHelper->UnregisterObserverExt(notifyUri, it->second);
            } else {
                MEDIA_ERR_LOG("uri: %{public}s, cardAssetUriObserver is nullptr", uri.c_str());
            }
            g_formAssetObserversMap.erase(it);
        } else {
            auto it = g_formCloudSyncObserversMap.find(uri);
            CHECK_AND_CONTINUE_ERR_LOG(
                it != g_formCloudSyncObserversMap.end(), "uri: %{public}s, cloudSwitchObserver not find", uri.c_str());
            if (it->second != nullptr) {
                syncHelper->UnregisterObserver(notifyUri, it->second);
            } else {
                MEDIA_ERR_LOG("uri: %{public}s, cloudSwitchObserver is nullptr", uri.c_str());
            }
            g_formCloudSyncObserversMap.erase(it);
        }
    }
    g_formIdMapUris.erase(formIdMapUrisIt);
}

int32_t MediaLibraryFaCardOperations::HandleStoreGalleryFormOperation(MediaLibraryCommand &cmd)
{
    auto rdbStore = MediaLibraryUnistoreManager::GetInstance().GetRdbStore();
    if (rdbStore == nullptr) {
        return E_HAS_DB_ERROR;
    }
    int64_t outRowId = -1;
    int32_t errCode = rdbStore->Insert(cmd, outRowId);
    if (errCode != NativeRdb::E_OK || outRowId < 0) {
        MEDIA_ERR_LOG("Insert into db failed, errCode = %{public}d", errCode);
        return E_HAS_DB_ERROR;
    }
    string formId = GetStringObject(cmd, TabFaCardPhotosColumn::FACARD_PHOTOS_FORM_ID);
    MEDIA_DEBUG_LOG("formId = %{public}s", formId.c_str());
    string assetRegisterUri = GetStringObject(cmd, TabFaCardPhotosColumn::FACARD_PHOTOS_ASSET_URI);
    MEDIA_DEBUG_LOG("assetRegisterUri = %{public}s", assetRegisterUri.c_str());
    MediaLibraryFaCardOperations::RegisterObserver(formId, assetRegisterUri);
    return static_cast<int32_t>(outRowId);
}
 
int32_t MediaLibraryFaCardOperations::HandleRemoveGalleryFormOperation(NativeRdb::RdbPredicates &rdbPredicate)
{
    string formId = rdbPredicate.GetWhereArgs()[0];
    MediaLibraryFaCardOperations::UnregisterObserver(formId);
    return MediaLibraryRdbStore::Delete(rdbPredicate);
}

void MediaLibraryFaCardOperations::InitRegisterObserver()
{
    MEDIA_INFO_LOG("enter InitRegisterObserver");
    const int INIT_NUM = 0;
    const int END_NUM = 10;
    const int DELAY_NUM = 100;
    int cnt = INIT_NUM;
    std::map<std::string, std::vector<std::string>> urisMap = MediaLibraryFaCardOperations::GetUris();
    for (const auto& pair : urisMap) {
        const std::string& formId = pair.first;
        MEDIA_DEBUG_LOG("InitRegisterObserver formId = %{public}s", formId.c_str());
        const std::vector<std::string>& uris = pair.second;
        MEDIA_DEBUG_LOG("InitRegisterObserver uris.size = %{public}zu", uris.size());
        for (const std::string& uri : uris) {
            MediaLibraryFaCardOperations::RegisterObserver(formId, uri);
            MEDIA_DEBUG_LOG("InitRegisterObserver uri = %{public}s", uri.c_str());
            cnt ++;
            if (cnt == END_NUM) {
                cnt = INIT_NUM;
                std::this_thread::sleep_for(std::chrono::milliseconds(DELAY_NUM));
            }
        }
    }
}

void MediaLibraryFaCardOperations::InitFaCard()
{
    ffrt::submit([]() { MediaLibraryFaCardOperations::InitRegisterObserver(); });
}
// LCOV_EXCL_STOP
} // namespace Media
} // namespace OHOS