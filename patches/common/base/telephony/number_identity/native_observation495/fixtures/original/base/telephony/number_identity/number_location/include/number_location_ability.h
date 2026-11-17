/*
 * Copyright (c) 2021-2022 Huawei Device Co., Ltd.
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

#ifndef NUMBER_LOCATION_DB_ABILITY_H
#define NUMBER_LOCATION_DB_ABILITY_H

#include "__mutex_base"
#include "ability.h"
#include "ability_lifecycle.h"
#include "abs_shared_result_set.h"
#include "datashare_ext_ability.h"
#include "datashare_ext_ability_context.h"
#include "datashare_predicates.h"
#include "iosfwd"
#include "map"
#include "memory"
#include "string"
#include "vector"
#include "want.h"

namespace OHOS {
namespace NativeRdb {
class ResultSet;
class DataAbilityPredicates;
}
namespace Telephony {
class NumberLocationAbility : public DataShare::DataShareExtAbility {
public:
    NumberLocationAbility();
    virtual ~NumberLocationAbility() override;
    static NumberLocationAbility* Create();
    virtual void OnStart(const AppExecFwk::Want &want) override;
    sptr<IRemoteObject> OnConnect(const AAFwk::Want &want) override;
    virtual int Insert(const Uri &uri, const DataShare::DataShareValuesBucket &value) override;
    virtual std::shared_ptr<DataShare::DataShareResultSet> Query(const Uri &uri,
        const DataShare::DataSharePredicates &predicates, std::vector<std::string> &columns,
        DataShare::DatashareBusinessError &businessError) override;
    virtual int Update(const Uri &uri, const DataShare::DataSharePredicates &predicates,
        const DataShare::DataShareValuesBucket &value) override;
    virtual int Delete(const Uri &uri, const DataShare::DataSharePredicates &predicates) override;

private:
    std::mutex lock_;
};
} // namespace Telephony
} // namespace OHOS
#endif // NUMBER_LOCATION_DB_ABILITY_H
