/*
 * Copyright (C) 2024 Huawei Device Co., Ltd.
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

#include "dataobs_mgr_client.h"
#include "datashare_ext_ability_context.h"
#include "number_identity_datashare_stub_impl.h"
#include "number_identity_errors.h"
#include "number_identity_log_wrapper.h"
#include "download_file_ability.h"
#include "number_identity_rdb_helper.h"

namespace OHOS {
namespace DataShare {
using DataObsMgrClient = OHOS::AAFwk::DataObsMgrClient;
using namespace OHOS::Telephony;

const int32_t INVALID_DATA = -1;

int NumberIdentityDataShareStubImpl::Insert(const Uri &uri, const DataShareValuesBucket &value)
{
    return NUMBER_IDENTITY_ERROR;
}

int NumberIdentityDataShareStubImpl::Update(const Uri &uri, const DataSharePredicates &predicates,
    const DataShareValuesBucket &value)
{
    NUMBER_IDENTITY_LOGD("update begin.");
    auto extension = GetOwner(uri);
    if (extension == nullptr) {
        NUMBER_IDENTITY_LOGE("Update failed, extension is null.");
        return NUMBER_IDENTITY_ERROR;
    }
    int result = extension->Update(uri, predicates, value);
    if (result != NUMBER_IDENTITY_ERR_SUCCESS) {
        NUMBER_IDENTITY_LOGE("Update fail.");
        return NUMBER_IDENTITY_ERROR;
    }
    NUMBER_IDENTITY_LOGD("Update end.");
    return NUMBER_IDENTITY_ERR_SUCCESS;
}

int NumberIdentityDataShareStubImpl::Delete(const Uri &uri, const DataSharePredicates &predicates)
{
    NUMBER_IDENTITY_LOGI("Delete begin.");
    auto extension = GetOwner(uri);
    if (extension == nullptr) {
        NUMBER_IDENTITY_LOGE("Delete failed, extension is null.");
        return NO_ROW_AFFECTED;
    }
    int rows = extension->Delete(uri, predicates);
    NUMBER_IDENTITY_LOGI("Delete end.");
    return rows;
}

std::shared_ptr<DataShareResultSet> NumberIdentityDataShareStubImpl::Query(const Uri &uri,
    const DataSharePredicates &predicates, std::vector<std::string> &columns, DatashareBusinessError &businessError)
{
    NUMBER_IDENTITY_LOGD("Query begin.");
    auto extension = GetOwner(uri);
    if (extension == nullptr) {
        NUMBER_IDENTITY_LOGE("Query failed, extension is null.");
        return nullptr;
    }
    auto resultSet = extension->Query(uri, predicates, columns, businessError);
    NUMBER_IDENTITY_LOGD("Query end.");
    return resultSet;
}

int NumberIdentityDataShareStubImpl::BatchInsert(const Uri &uri, const std::vector<DataShareValuesBucket> &values)
{
    NUMBER_IDENTITY_LOGI("BatchInsert begin, got %{public}lu record(s).", values.size());
    auto extension = GetOwner(uri);
    if (extension == nullptr) {
        NUMBER_IDENTITY_LOGE("BatchInsert failed, extension is null.");
        return NO_ROW_AFFECTED;
    }
    auto affectedRows = extension->BatchInsert(uri, values);
    NUMBER_IDENTITY_LOGI("BatchInsert end.");
    return affectedRows;
}

void NumberIdentityDataShareStubImpl::SetNumberLocationAbility(std::shared_ptr<DataShareExtAbility> extension)
{
    std::lock_guard<std::mutex> lock(setNumberLocationMutex_);
    numberLocationAbility_ = extension;
}

std::shared_ptr<DataShareExtAbility> NumberIdentityDataShareStubImpl::GetNumberLocationAbility()
{
    std::lock_guard<std::mutex> lock(setNumberLocationMutex_);
    return numberLocationAbility_;
}

void NumberIdentityDataShareStubImpl::SetDownloadFileAbility(std::shared_ptr<DataShareExtAbility> extension)
{
    std::lock_guard<std::mutex> lock(downloadFileMutex_);
    downloadFileAbility_ = extension;
}

std::shared_ptr<DataShareExtAbility> NumberIdentityDataShareStubImpl::GetDownloadFileAbility()
{
    std::lock_guard<std::mutex> lock(downloadFileMutex_);
    return downloadFileAbility_;
}

void NumberIdentityDataShareStubImpl::SetNumberMarkAbility(std::shared_ptr<DataShareExtAbility> extension)
{
    std::lock_guard<std::mutex> lock(numberMarkMutex_);
    numberMarkAbility_ = extension;
}

std::shared_ptr<DataShareExtAbility> NumberIdentityDataShareStubImpl::GetNumberMarkAbility()
{
    std::lock_guard<std::mutex> lock(numberMarkMutex_);
    return numberMarkAbility_;
}

std::shared_ptr<DataShareExtAbility> NumberIdentityDataShareStubImpl::GetOwner(const Uri &uri)
{
    OHOS::Uri uriTemp = uri;
    std::string path = uriTemp.GetPath();
    NUMBER_IDENTITY_LOGD("GetOwner uri: %{public}s", path.c_str());
    if (path.find("com.ohos.numberlocationability") != std::string::npos) {
        NUMBER_IDENTITY_LOGD("return numberLocationAbility");
        return GetNumberLocationAbility();
    }
    if (path.find("com.ohos.downloadfileability") != std::string::npos) {
        NUMBER_IDENTITY_LOGD("return downloadFileAbility_");
        return GetDownloadFileAbility();
    }
    if (path.find("com.ohos.numbermarkability") != std::string::npos) {
        NUMBER_IDENTITY_LOGD("return numberMarkAbility_");
        return GetNumberMarkAbility();
    }
    NUMBER_IDENTITY_LOGE("URI %{public}s no owner matched!", path.c_str());
    return nullptr;
}

std::vector<std::string> NumberIdentityDataShareStubImpl::GetFileTypes(
    const Uri &uri, const std::string &mimeTypeFilter)
{
    NUMBER_IDENTITY_LOGI("GetFileTypes not supported.");
    std::vector<std::string> result;
    return result;
}

int NumberIdentityDataShareStubImpl::OpenFile(const Uri &uri, const std::string &mode)
{
    NUMBER_IDENTITY_LOGI("OpenFile not supported.");
    return INVALID_DATA;
}

int NumberIdentityDataShareStubImpl::OpenRawFile(const Uri &uri, const std::string &mode)
{
    NUMBER_IDENTITY_LOGI("OpenRawFile not supported.");
    return INVALID_DATA;
}

std::string NumberIdentityDataShareStubImpl::GetType(const Uri &uri)
{
    NUMBER_IDENTITY_LOGI("GetType not supported.");
    return "";
}

bool NumberIdentityDataShareStubImpl::RegisterObserver(
    const Uri &uri, const sptr<AAFwk::IDataAbilityObserver> &dataObserver)
{
    return false;
}

bool NumberIdentityDataShareStubImpl::UnregisterObserver(const Uri &uri,
    const sptr<AAFwk::IDataAbilityObserver> &dataObserver)
{
    return false;
}

bool NumberIdentityDataShareStubImpl::NotifyChange(const Uri &uri)
{
    return false;
}

Uri NumberIdentityDataShareStubImpl::NormalizeUri(const Uri &uri)
{
    NUMBER_IDENTITY_LOGI("NormalizeUri not supported.");
    return uri;
}

Uri NumberIdentityDataShareStubImpl::DenormalizeUri(const Uri &uri)
{
    NUMBER_IDENTITY_LOGI("DenormalizeUri not supported.");
    return uri;
}
} // namespace DataShare
} // namespace OHOS
