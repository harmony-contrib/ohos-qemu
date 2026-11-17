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

#include "number_location_ability.h"
#include "number_mark_ability.h"
#include "download_file_ability.h"

#include "ability_context.h"
#include "ability_loader.h"
#include "datashare_ext_ability.h"
#include "datashare_predicates.h"
#include "new"
#include "number_identity_datashare_stub_impl.h"
#include "number_identity_errors.h"
#include "number_identity_log_wrapper.h"
#include "number_location_manager.h"
#include "number_location_result_set_bridge.h"
#include "rdb_errno.h"
#include "rdb_utils.h"
#include "uri.h"
#include "utility"

namespace OHOS {
using AbilityRuntime::Extension;
using AbilityRuntime::Runtime;
using AppExecFwk::Ability;
using AppExecFwk::AbilityLoader;
using namespace NativeRdb;
namespace Telephony {

NumberLocationAbility::NumberLocationAbility() : DataShareExtAbility() {}

NumberLocationAbility::~NumberLocationAbility() {}

NumberLocationAbility *NumberLocationAbility::Create()
{
    NUMBER_IDENTITY_LOGD("NumberLocationAbility::Create begin.");
    auto self = new NumberLocationAbility();
    return self;
}

static DataShare::DataShareExtAbility *NumberLocationDataShareCreator(const std::unique_ptr<Runtime> &runtime)
{
    NUMBER_IDENTITY_LOGD("NumberLocationDataShareCreator::%{public}s begin.", __func__);
    return NumberLocationAbility::Create();
}

__attribute__((constructor)) void RegisterDataShareCreator()
{
    NUMBER_IDENTITY_LOGD("NumberLocationDataShareCreator::%{public}s", __func__);
    DataShare::DataShareExtAbility::SetCreator(NumberLocationDataShareCreator);
}

sptr<IRemoteObject> NumberLocationAbility::OnConnect(const AAFwk::Want &want)
{
    NUMBER_IDENTITY_LOGD("NumberLocationAbility::OnConnect");
    Extension::OnConnect(want);
    sptr<DataShare::NumberIdentityDataShareStubImpl> remoteObject =
        new (std::nothrow) DataShare::NumberIdentityDataShareStubImpl();
    if (remoteObject == nullptr) {
        NUMBER_IDENTITY_LOGE("%{public}s No memory allocated for DataShareStubImpl", __func__);
        return nullptr;
    }
    remoteObject->SetNumberLocationAbility(std::static_pointer_cast<NumberLocationAbility>(shared_from_this()));
    std::shared_ptr<NumberMarkAbility> numberMarkAbility(NumberMarkAbility::Create(GetContext()));
    remoteObject->SetNumberMarkAbility(std::static_pointer_cast<NumberMarkAbility>(numberMarkAbility));
    NUMBER_IDENTITY_LOGI("NumberLocationAbility %{public}s end.", __func__);
    std::shared_ptr<DownloadFileAbility> downloadFileAbility(DownloadFileAbility::Create(GetContext()));
    remoteObject->SetDownloadFileAbility(std::static_pointer_cast<DownloadFileAbility>(downloadFileAbility));
    NUMBER_IDENTITY_LOGI("DownloadFileAbility %{public}s end.", __func__);
    return remoteObject->AsObject();
}

void NumberLocationAbility::OnStart(const AppExecFwk::Want &want)
{
    NUMBER_IDENTITY_LOGD("NumberLocationAbility::OnStart");
    Extension::OnStart(want);
}

int NumberLocationAbility::Insert(const Uri &uri, const DataShare::DataShareValuesBucket &value)
{
    return NUMBER_IDENTITY_ERROR;
}

std::shared_ptr<DataShare::DataShareResultSet> NumberLocationAbility::Query(const Uri &uri,
    const DataShare::DataSharePredicates &predicates, std::vector<std::string> &columns,
    DataShare::DatashareBusinessError &businessError)
{
    std::shared_ptr<DataShare::DataShareResultSet> sharedPtrResult = nullptr;
    bool isExactMatch = true;
    if (std::strcmp(columns[0].c_str(), "false") == 0) {
        isExactMatch = false;
    }
    std::vector<std::string> whereList = predicates.GetWhereArgs();
    std::vector<std::string> numberLocations;
    std::string numberlocation = "";
    std::string currentIso = DelayedSingleton<NumberLocationManager>::GetInstance()->GetCountryIso();
    for (auto iter = whereList.begin(); iter != whereList.end(); iter++) {
        numberlocation =
            DelayedSingleton<NumberLocationManager>::GetInstance()->GetNumberLocation(*iter, isExactMatch, currentIso);
        numberLocations.push_back(numberlocation);
    }
    std::shared_ptr<DataShare::ResultSetBridge> resultSet =
        std::make_shared<NumberLocationResultSetBridge>(numberLocations);
    sharedPtrResult = std::make_shared<DataShare::DataShareResultSet>(resultSet);
    return sharedPtrResult;
}

int NumberLocationAbility::Update(
    const Uri &uri, const DataShare::DataSharePredicates &predicates, const DataShare::DataShareValuesBucket &value)
{
    return NUMBER_IDENTITY_ERROR;
}

int NumberLocationAbility::Delete(const Uri &uri, const DataShare::DataSharePredicates &predicates)
{
    return NUMBER_IDENTITY_ERROR;
}
} // namespace Telephony
} // namespace OHOS