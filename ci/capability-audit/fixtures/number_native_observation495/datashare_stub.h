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

#ifndef DATASHARE_STUB_H
#define DATASHARE_STUB_H

#include <iremote_stub.h>
#include <map>

#include "datashare_business_error.h"
#include "datashare_errno.h"
#include "datashare_sa_provider_info.h"
#include "idatashare.h"

namespace OHOS {
namespace DataShare {
class DataShareStub : public IRemoteStub<IDataShare> {
public:
    DataShareStub();
    ~DataShareStub();
    int OnRemoteRequest(uint32_t code, MessageParcel &data, MessageParcel &reply, MessageOption &option) override;
    /**
     * Not configuring read and write permissions is considered as not allowing other processes to access,
     * and the visitors are only allowed to create a data share if they have at least one of the permissions
    */
    bool VerifyPermissionAndUri(std::string uri, uint32_t tokenId);
    virtual DataShareNonSilentConfig GetConfig();
private:
    ErrCode CmdGetFileTypes(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdOpenFile(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdOpenFileWithErrCode(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdOpenRawFile(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdInsert(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdUpdate(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdDelete(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdQuery(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdGetType(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdBatchInsert(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdRegisterObserver(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdUnregisterObserver(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdNotifyChange(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdNormalizeUri(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdDenormalizeUri(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdExecuteBatch(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdInsertExt(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdBatchUpdate(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdInsertEx(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdUpdateEx(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdDeleteEx(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdUserDefineFunc(MessageParcel &data, MessageParcel &reply, MessageOption &option);
    ErrCode CmdRegisterObserverExtProvider(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdUnregisterObserverExtProvider(MessageParcel &data, MessageParcel &reply);
    ErrCode CmdNotifyChangeExtProvider(MessageParcel &data, MessageParcel &reply);
    ErrCode OpenFileInner(MessageParcel &data, MessageParcel &reply, int &fd);

    virtual int ExecuteBatch(const std::vector<OperationStatement> &statements, ExecResultSet &result) override;
    virtual int InsertExt(const Uri &uri, const DataShareValuesBucket &value, std::string &result) override;
    virtual int BatchUpdate(const UpdateOperations &operations, std::vector<BatchUpdateResult> &results) override;
    virtual std::pair<int32_t, int32_t> InsertEx(const Uri &uri, const DataShareValuesBucket &value) override;
    virtual std::pair<int32_t, int32_t> UpdateEx(const Uri &uri, const DataSharePredicates &predicates,
        const DataShareValuesBucket &value) override;
    virtual std::pair<int32_t, int32_t> DeleteEx(const Uri &uri, const DataSharePredicates &predicates) override;
    virtual int32_t UserDefineFunc(
        MessageParcel &data, MessageParcel &reply, MessageOption &option) override;
    // default return true, need override by users
    virtual int RegisterObserverExtProvider(const Uri &uri, const sptr<AAFwk::IDataAbilityObserver> &dataObserver,
        bool isDescendants, RegisterOption option) override;
    // default return true, need override by users
    virtual int UnregisterObserverExtProvider(const Uri &uri,
        const sptr<AAFwk::IDataAbilityObserver> &dataObserver) override;
    // default return true, need override by users
    virtual int NotifyChangeExtProvider(const ChangeInfo &changeInfo) override;

    /**
     * @brief Report OpenFile/OpenRawFile usage via HiSysEvent.
     *
     * Records the provider's bundleName, caller's token ID, and open mode
     * to HiSysEvent for instrumentation. Does not block or validate permissions.
     *
     * @param funcName Calling function name (e.g. __func__ gives "OpenFileInner").
     * @param mode Open mode string (e.g. "r", "w", "rw").
     */
    void ReportOpenFileUsage(const std::string &funcName, const std::string &mode);

    using RequestFuncType = int (DataShareStub::*)(MessageParcel &data, MessageParcel &reply);
    std::map<uint32_t, RequestFuncType> stubFuncMap_;
    static constexpr int VALUEBUCKET_MAX_COUNT = 3000;
    static constexpr std::chrono::milliseconds TIME_THRESHOLD = std::chrono::milliseconds(500);
};
} // namespace DataShare
} // namespace OHOS
#endif // DATASHARE_STUB_H

