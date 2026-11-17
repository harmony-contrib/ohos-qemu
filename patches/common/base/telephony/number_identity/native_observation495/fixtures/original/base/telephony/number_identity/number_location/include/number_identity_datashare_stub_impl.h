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

#ifndef DATASHARE_STUB_IMPL_H
#define DATASHARE_STUB_IMPL_H

#include "datashare_stub.h"
#include "datashare_ext_ability.h"

namespace OHOS {
namespace DataShare {
class NumberIdentityDataShareStubImpl : public DataShareStub {
public:
    NumberIdentityDataShareStubImpl() {}
    virtual ~NumberIdentityDataShareStubImpl() {};

    int Insert(const Uri &uri, const DataShareValuesBucket &value) override;
    int Update(const Uri &uri, const DataSharePredicates &predicates,
        const DataShareValuesBucket &value) override;
    int Delete(const Uri &uri, const DataSharePredicates &predicates) override;
    std::shared_ptr<DataShareResultSet> Query(const Uri &uri, const DataSharePredicates &predicates,
        std::vector<std::string> &columns, DatashareBusinessError &businessError) override;
    int BatchInsert(const Uri &uri, const std::vector<DataShareValuesBucket> &values) override;

    std::vector<std::string> GetFileTypes(const Uri &uri, const std::string &mimeTypeFilter) override;
    int OpenFile(const Uri &uri, const std::string &mode) override;
    int OpenRawFile(const Uri &uri, const std::string &mode) override;
    std::string GetType(const Uri &uri) override;
    bool RegisterObserver(const Uri &uri, const sptr<AAFwk::IDataAbilityObserver> &dataObserver) override;
    bool UnregisterObserver(const Uri &uri, const sptr<AAFwk::IDataAbilityObserver> &dataObserver) override;
    bool NotifyChange(const Uri &uri) override;
    Uri NormalizeUri(const Uri &uri) override;
    Uri DenormalizeUri(const Uri &uri) override;

    void SetNumberLocationAbility(std::shared_ptr<DataShareExtAbility> extension);
    void SetDownloadFileAbility(std::shared_ptr<DataShareExtAbility> extension);
    void SetNumberMarkAbility(std::shared_ptr<DataShareExtAbility> extension);

private:
    std::shared_ptr<DataShareExtAbility> GetNumberLocationAbility();
    std::shared_ptr<DataShareExtAbility> GetDownloadFileAbility();
    std::shared_ptr<DataShareExtAbility> GetNumberMarkAbility();
    std::shared_ptr<DataShareExtAbility> GetOwner(const Uri &uri);
private:
    std::mutex setNumberLocationMutex_;
    std::mutex downloadFileMutex_;
    std::mutex numberMarkMutex_;
    std::shared_ptr<DataShareExtAbility> numberLocationAbility_ = nullptr;
    std::shared_ptr<DataShareExtAbility> downloadFileAbility_ = nullptr;
    std::shared_ptr<DataShareExtAbility> numberMarkAbility_ = nullptr;
    std::shared_ptr<DataShareExtAbility> yellowPageAbility_ = nullptr;
};
} // namespace DataShare
} // namespace OHOS
#endif // DATASHARE_STUB_IMPL_H