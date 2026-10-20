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

#define LOG_TAG "datashare_stub"

#include "datashare_stub.h"

#include <cinttypes>

#include "accesstoken_kit.h"
#include "data_ability_observer_interface.h"
#include "datashare_itypes_utils.h"
#include "datashare_log.h"
#include "hiview_datashare.h"
#include "ipc_skeleton.h"
#include "ipc_types.h"
#include "ishared_result_set.h"
#include "datashare_operation_statement.h"
#include "unistd.h"
#include "string_ex.h"
#include "bundle_mgr_helper.h"
#include "datashare_errno.h"

using namespace OHOS::DistributedShare::DataShare;
namespace OHOS {
namespace DataShare {
using namespace OHOS::Security::AccessToken;
constexpr int DEFAULT_NUMBER = -1;
constexpr int PERMISSION_ERROR_NUMBER = -2;
DataShareStub::DataShareStub()
{
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_GET_FILE_TYPES)] = &DataShareStub::CmdGetFileTypes;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_OPEN_FILE)] = &DataShareStub::CmdOpenFile;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_OPEN_FILE_WITH_ERR_CODE)] =
        &DataShareStub::CmdOpenFileWithErrCode;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_OPEN_RAW_FILE)] = &DataShareStub::CmdOpenRawFile;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_INSERT)] = &DataShareStub::CmdInsert;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_UPDATE)] = &DataShareStub::CmdUpdate;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_DELETE)] = &DataShareStub::CmdDelete;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_QUERY)] = &DataShareStub::CmdQuery;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_GET_TYPE)] = &DataShareStub::CmdGetType;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_BATCH_INSERT)] = &DataShareStub::CmdBatchInsert;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_REGISTER_OBSERVER)] =
        &DataShareStub::CmdRegisterObserver;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_UNREGISTER_OBSERVER)] =
        &DataShareStub::CmdUnregisterObserver;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_NOTIFY_CHANGE)] = &DataShareStub::CmdNotifyChange;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_NORMALIZE_URI)] = &DataShareStub::CmdNormalizeUri;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_DENORMALIZE_URI)] =
        &DataShareStub::CmdDenormalizeUri;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_EXECUTE_BATCH)] = &DataShareStub::CmdExecuteBatch;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_INSERT_EXT)] = &DataShareStub::CmdInsertExt;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_BATCH_UPDATE)] = &DataShareStub::CmdBatchUpdate;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_INSERT_EX)] = &DataShareStub::CmdInsertEx;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_UPDATE_EX)] = &DataShareStub::CmdUpdateEx;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_DELETE_EX)] = &DataShareStub::CmdDeleteEx;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_REGISTER_OBSERVEREXT_PROVIDER)] =
        &DataShareStub::CmdRegisterObserverExtProvider;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_UNREGISTER_OBSERVEREXT_PROVIDER)] =
        &DataShareStub::CmdUnregisterObserverExtProvider;
    stubFuncMap_[static_cast<uint32_t>(IDataShareInterfaceCode::CMD_NOTIFY_CHANGEEXT_PROVIDER)] =
        &DataShareStub::CmdNotifyChangeExtProvider;
}

DataShareStub::~DataShareStub()
{
    stubFuncMap_.clear();
}

int DataShareStub::OnRemoteRequest(uint32_t code, MessageParcel& data, MessageParcel& reply,
    MessageOption& option)
{
    std::u16string descriptor = DataShareStub::GetDescriptor();
    std::u16string remoteDescriptor = data.ReadInterfaceToken();
    if (descriptor != remoteDescriptor) {
        LOG_INFO("local descriptor is not equal to remote, localDescriptor = %{public}s, remoteDescriptor = %{public}s",
            Str16ToStr8(descriptor).c_str(), Str16ToStr8(remoteDescriptor).c_str());
        return ERR_INVALID_STATE;
    }

    const auto &itFunc = stubFuncMap_.find(code);
    auto start = std::chrono::steady_clock::now();
    int32_t ret = 0;
    bool isCodeValid = false;
    if (itFunc != stubFuncMap_.end()) {
        isCodeValid = true;
        ret = (this->*(itFunc->second))(data, reply);
    } else if (code == static_cast<uint32_t>(IDataShareInterfaceCode::CMD_USER_DEFINE_FUNC)) {
        isCodeValid = true;
        ret = CmdUserDefineFunc(data, reply, option);
    }
    if (isCodeValid) {
        auto finish = std::chrono::steady_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(finish - start);
        if (duration >= TIME_THRESHOLD) {
            auto callingPid = IPCSkeleton::GetCallingPid();
            int64_t milliseconds = duration.count();
            LOG_ERROR("extension time over, code:%{public}u callingPid:%{public}d, cost:%{public}" PRIi64 "ms",
                code, callingPid, milliseconds);
        }
        return ret;
    }
    LOG_DEBUG("remote request unhandled: %{public}d", code);
    return IPCObjectStub::OnRemoteRequest(code, data, reply, option);
}

bool DataShareStub::VerifyPermissionAndUri(std::string uri, uint32_t tokenId)
{
    DataShareNonSilentConfig config = GetConfig();
    size_t pos = uri.find('?');
    std::string pureUri = (pos != std::string::npos) ? uri.substr(0, pos) : uri;

    for (const auto& record : config.records) {
        if (record.uri != pureUri) {
            continue;
        }
        if (!record.readPermission.empty()) {
            auto status = AccessTokenKit::VerifyAccessToken(tokenId, record.readPermission);
            if (status == PermissionState::PERMISSION_GRANTED) {
                return true;
            }
        }
        if (!record.writePermission.empty()) {
            auto status = AccessTokenKit::VerifyAccessToken(tokenId, record.writePermission);
            if (status == PermissionState::PERMISSION_GRANTED) {
                return true;
            }
        }
    }
    return false;
}

void DataShareStub::ReportOpenFileUsage(const std::string &funcName, const std::string &mode)
{
    static std::string providerBundleName = []() {
        auto bmsHelper = DelayedSingleton<AppExecFwk::BundleMgrHelper>::GetInstance();
        if (bmsHelper != nullptr) {
            AppExecFwk::BundleInfo bundleInfo;
            int32_t ret = bmsHelper->GetBundleInfoForSelf(
                static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_APPLICATION) |
                static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_SIGNATURE_INFO), bundleInfo);
            if (ret == E_OK) {
                return bundleInfo.applicationInfo.bundleName;
            }
        }
        return std::string();
    }();

    uint32_t callingTokenId = IPCSkeleton::GetCallingTokenID();
    DataShareFaultInfo faultInfo{
        HiViewFaultAdapter::OPEN_FILE_USED,
        providerBundleName, "", "", funcName, 0,
        "mode=" + mode + ",callingTokenId=" + std::to_string(callingTokenId)
    };
    HiViewFaultAdapter::ReportDataFault(faultInfo);
}

ErrCode DataShareStub::CmdGetFileTypes(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    std::string mimeTypeFilter;
    if (!ITypesUtil::Unmarshal(data, uri, mimeTypeFilter)) {
        LOG_ERROR("Unmarshalling value is nullptr");
        return ERR_INVALID_VALUE;
    }
    if (mimeTypeFilter.empty()) {
        LOG_ERROR("mimeTypeFilter is nullptr");
        return ERR_INVALID_VALUE;
    }
    std::vector<std::string> types = GetFileTypes(uri, mimeTypeFilter);
    if (!ITypesUtil::Marshal(reply, types)) {
        LOG_ERROR("Marshal value is nullptr");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::OpenFileInner(MessageParcel &data, MessageParcel &reply, int &fd)
{
    Uri uri("");
    std::string mode;
    if (!ITypesUtil::Unmarshal(data, uri, mode)) {
        LOG_ERROR("Unmarshalling value is nullptr");
        return ERR_INVALID_VALUE;
    }
    if (mode.empty()) {
        LOG_ERROR("mode is nullptr");
        return ERR_INVALID_VALUE;
    }
    fd = OpenFile(uri, mode);
    return E_OK;
}

ErrCode DataShareStub::CmdOpenFile(MessageParcel &data, MessageParcel &reply)
{
    int fd = -1;
    int ret = OpenFileInner(data, reply, fd);
    if (ret != E_OK) {
        return ret;
    }

    if (fd < 0) {
        return ERR_INVALID_DATA;
    }
    if (!reply.WriteFileDescriptor(fd)) {
        LOG_ERROR("fail to WriteFileDescriptor fd");
        close(fd);
        return ERR_INVALID_VALUE;
    }
    close(fd);
    return E_OK;
}

ErrCode DataShareStub::CmdOpenFileWithErrCode(MessageParcel &data, MessageParcel &reply)
{
    int fd = -1;
    int ret = OpenFileInner(data, reply, fd);
    if (ret != E_OK) {
        return ret;
    }

    if (fd < 0) {
        return fd;
    }
    if (!reply.WriteFileDescriptor(fd)) {
        LOG_ERROR("fail to WriteFileDescriptor fd");
        close(fd);
        return ERR_INVALID_VALUE;
    }
    close(fd);
    return E_OK;
}

ErrCode DataShareStub::CmdOpenRawFile(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    std::string mode;
    if (!ITypesUtil::Unmarshal(data, uri, mode)) {
        LOG_ERROR("Unmarshalling value is nullptr");
        return ERR_INVALID_VALUE;
    }
    int fd = OpenRawFile(uri, mode);
    if (!ITypesUtil::Marshal(reply, fd)) {
        LOG_ERROR("Marshal value is nullptr");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdInsert(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    DataShareValuesBucket value;
    if (!ITypesUtil::Unmarshal(data, uri, value)) {
        LOG_ERROR("Unmarshalling value is nullptr");
        return ERR_INVALID_VALUE;
    }
    int index = Insert(uri, value);
    if (index == DEFAULT_NUMBER) {
        LOG_ERROR("Insert inner error");
        return ERR_INVALID_VALUE;
    } else if (index == PERMISSION_ERROR_NUMBER) {
        LOG_ERROR("Insert permission error");
        return ERR_PERMISSION_DENIED;
    }
    if (!reply.WriteInt32(index)) {
        LOG_ERROR("fail to WriteInt32 index");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdUpdate(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    DataSharePredicates predicates;
    DataShareValuesBucket value;
    if (!ITypesUtil::Unmarshal(data, uri, predicates, value)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return ERR_INVALID_VALUE;
    }
    int index = Update(uri, predicates, value);
    if (index == DEFAULT_NUMBER) {
        LOG_ERROR("Update inner error");
        return ERR_INVALID_VALUE;
    } else if (index == PERMISSION_ERROR_NUMBER) {
        LOG_ERROR("Update permission error");
        return ERR_PERMISSION_DENIED;
    }
    if (!reply.WriteInt32(index)) {
        LOG_ERROR("fail to WriteInt32 index");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdBatchUpdate(OHOS::MessageParcel &data, OHOS::MessageParcel &reply)
{
    UpdateOperations updateOperations;
    if (!ITypesUtil::Unmarshal(data, updateOperations)) {
        LOG_ERROR("Unmarshalling updateOperations is nullptr");
        return ERR_INVALID_VALUE;
    }
    std::vector<BatchUpdateResult> results;
    int ret = BatchUpdate(updateOperations, results);
    if (ret == DEFAULT_NUMBER) {
        LOG_ERROR("BatchUpdate inner error, ret is %{public}d.", ret);
        return ERR_INVALID_VALUE;
    } else if (ret == PERMISSION_ERROR_NUMBER) {
        LOG_ERROR("BatchUpdate permission error");
        return ERR_PERMISSION_DENIED;
    }
    if (!ITypesUtil::Marshal(reply, results)) {
        LOG_ERROR("marshalling updateOperations is failed");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdDelete(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    DataSharePredicates predicates;
    if (!ITypesUtil::Unmarshal(data, uri, predicates)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return ERR_INVALID_VALUE;
    }
    int index = Delete(uri, predicates);
    if (index == DEFAULT_NUMBER) {
        LOG_ERROR("Delete inner error");
        return ERR_INVALID_VALUE;
    } else if (index == PERMISSION_ERROR_NUMBER) {
        LOG_ERROR("Delete permission error");
        return ERR_PERMISSION_DENIED;
    }
    if (!reply.WriteInt32(index)) {
        LOG_ERROR("fail to WriteInt32 index");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdInsertEx(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    DataShareValuesBucket value;
    if (!ITypesUtil::Unmarshal(data, uri, value)) {
        LOG_ERROR("Unmarshalling value is nullptr");
        return E_UNMARSHAL_ERROR;
    }

    auto [errCode, result] = InsertEx(uri, value);
    if (errCode == DEFAULT_NUMBER) {
        LOG_ERROR("Insert inner error");
        return ERR_INVALID_VALUE;
    } else if (errCode == PERMISSION_ERROR_NUMBER) {
        LOG_ERROR("Insert permission error");
        return ERR_PERMISSION_DENIED;
    }

    if (!ITypesUtil::Marshal(reply, errCode, result)) {
        LOG_ERROR("Marshal value is nullptr");
        return E_MARSHAL_ERROR;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdUpdateEx(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    DataSharePredicates predicates;
    DataShareValuesBucket value;
    if (!ITypesUtil::Unmarshal(data, uri, predicates, value)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return E_UNMARSHAL_ERROR;
    }

    auto [errCode, result] = UpdateEx(uri, predicates, value);
    if (errCode == DEFAULT_NUMBER) {
        LOG_ERROR("Update inner error");
        return ERR_INVALID_VALUE;
    } else if (errCode == PERMISSION_ERROR_NUMBER) {
        LOG_ERROR("Update permission error");
        return ERR_PERMISSION_DENIED;
    }

    if (!ITypesUtil::Marshal(reply, errCode, result)) {
        LOG_ERROR("Marshal value is nullptr");
        return E_MARSHAL_ERROR;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdDeleteEx(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    DataSharePredicates predicates;
    if (!ITypesUtil::Unmarshal(data, uri, predicates)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return E_UNMARSHAL_ERROR;
    }
    auto [errCode, result] = DeleteEx(uri, predicates);
    if (errCode == DEFAULT_NUMBER) {
        LOG_ERROR("Delete inner error");
        return ERR_INVALID_VALUE;
    } else if (errCode == PERMISSION_ERROR_NUMBER) {
        LOG_ERROR("Delete permission error");
        return ERR_PERMISSION_DENIED;
    }
    if (!ITypesUtil::Marshal(reply, errCode, result)) {
        LOG_ERROR("Marshal value is nullptr");
        return E_MARSHAL_ERROR;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdQuery(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    DataSharePredicates predicates;
    std::vector<std::string> columns;
    if (!ITypesUtil::Unmarshal(data, uri, columns)) {
        LOG_ERROR("Unmarshalling uri and columns to data failed");
        return ERR_INVALID_VALUE;
    }
    if (!ITypesUtil::UnmarshalPredicates(predicates, data)) {
        LOG_ERROR("Unmarshalling predicates to shared-memory failed");
        return ERR_INVALID_VALUE;
    }
    DatashareBusinessError businessError;
    auto resultSet = Query(uri, predicates, columns, businessError);
    auto result = ISharedResultSet::WriteToParcel(std::move(resultSet), reply);
    reply.WriteInt32(businessError.GetCode());
    reply.WriteString(businessError.GetMessage());
    if (result == nullptr) {
        LOG_ERROR("!resultSet->Marshalling(reply)");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdGetType(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    if (!ITypesUtil::Unmarshal(data, uri)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return ERR_INVALID_VALUE;
    }
    std::string type = GetType(uri);
    if (!reply.WriteString(type)) {
        LOG_ERROR("fail to WriteString type");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdUserDefineFunc(MessageParcel &data, MessageParcel &reply, MessageOption &option)
{
    UserDefineFunc(data, reply, option);
    return E_OK;
}

ErrCode DataShareStub::CmdBatchInsert(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    std::vector<DataShareValuesBucket> values;
    if (!ITypesUtil::Unmarshal(data, uri)) {
        LOG_ERROR("Unmarshalling uri from data failed");
        return ERR_INVALID_VALUE;
    }
    if (!ITypesUtil::UnmarshalValuesBucketVec(values, data)) {
        LOG_ERROR("Unmarshalling DataShareValuesBucket from shared-memory failed");
        return ERR_INVALID_VALUE;
    }
    int ret = BatchInsert(uri, values);
    if (ret == DEFAULT_NUMBER) {
        LOG_ERROR("BatchInsert inner error");
        return ERR_INVALID_VALUE;
    } else if (ret == PERMISSION_ERROR_NUMBER) {
        LOG_ERROR("BatchInsert permission error");
        return ERR_PERMISSION_DENIED;
    }
    if (!reply.WriteInt32(ret)) {
        LOG_ERROR("fail to WriteInt32 ret");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdRegisterObserver(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    sptr<IRemoteObject> observer;
    if (!ITypesUtil::Unmarshal(data, uri, observer)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return ERR_INVALID_VALUE;
    }
    auto obServer = iface_cast<AAFwk::IDataAbilityObserver>(observer);
    if (obServer == nullptr) {
        LOG_ERROR("obServer is nullptr");
        return ERR_INVALID_VALUE;
    }

    bool ret = RegisterObserver(uri, obServer);
    if (!reply.WriteInt32(ret)) {
        LOG_ERROR("fail to WriteInt32 ret");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdUnregisterObserver(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    sptr<IRemoteObject> observer;
    if (!ITypesUtil::Unmarshal(data, uri, observer)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return ERR_INVALID_VALUE;
    }
    auto obServer = iface_cast<AAFwk::IDataAbilityObserver>(observer);
    if (obServer == nullptr) {
        LOG_ERROR("obServer is nullptr");
        return ERR_INVALID_VALUE;
    }

    bool ret = UnregisterObserver(uri, obServer);
    if (!reply.WriteInt32(ret)) {
        LOG_ERROR("fail to WriteInt32 ret");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdNotifyChange(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    if (!ITypesUtil::Unmarshal(data, uri)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return ERR_INVALID_VALUE;
    }

    bool ret = NotifyChange(uri);
    if (!reply.WriteInt32(ret)) {
        LOG_ERROR("fail to WriteInt32 ret");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdRegisterObserverExtProvider(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    sptr<IRemoteObject> observer;
    bool isDescendants = false;
    RegisterOption option;
    if (!ITypesUtil::Unmarshal(data, uri, observer, isDescendants, option)) {
        LOG_ERROR("Unmarshalling uri and observer failed");
        return ERR_INVALID_VALUE;
    }
    auto obServer = iface_cast<AAFwk::IDataAbilityObserver>(observer);
    if (obServer == nullptr) {
        LOG_ERROR("obServer is nullptr");
        return ERR_INVALID_VALUE;
    }

    int ret = RegisterObserverExtProvider(uri, obServer, isDescendants, option);
    if (!reply.WriteInt32(ret)) {
        LOG_ERROR("fail to WriteInt32 ret");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdUnregisterObserverExtProvider(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    sptr<IRemoteObject> observer;
    if (!ITypesUtil::Unmarshal(data, uri, observer)) {
        LOG_ERROR("Unmarshalling uri and observer failed");
        return ERR_INVALID_VALUE;
    }
    auto obServer = iface_cast<AAFwk::IDataAbilityObserver>(observer);
    if (obServer == nullptr) {
        LOG_ERROR("obServer is nullptr");
        return ERR_INVALID_VALUE;
    }

    int ret = UnregisterObserverExtProvider(uri, obServer);
    if (!reply.WriteInt32(ret)) {
        LOG_ERROR("fail to WriteInt32 ret");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdNotifyChangeExtProvider(MessageParcel &data, MessageParcel &reply)
{
    ChangeInfo changeInfo;
    if (!ChangeInfo::Unmarshalling(changeInfo, data)) {
        LOG_ERROR("Failed to unmarshall changeInfo.");
        return ERR_INVALID_VALUE;
    }

    int ret = NotifyChangeExtProvider(changeInfo);
    if (!reply.WriteInt32(ret)) {
        LOG_ERROR("fail to WriteInt32 ret");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdNormalizeUri(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    if (!ITypesUtil::Unmarshal(data, uri)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return ERR_INVALID_VALUE;
    }
    auto ret = NormalizeUri(uri);
    if (!ITypesUtil::Marshal(reply, ret)) {
        LOG_ERROR("Write to message parcel failed!");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdDenormalizeUri(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    if (!ITypesUtil::Unmarshal(data, uri)) {
        LOG_ERROR("Unmarshalling predicates is nullptr");
        return ERR_INVALID_VALUE;
    }

    auto ret = DenormalizeUri(uri);
    if (!ITypesUtil::Marshal(reply, ret)) {
        LOG_ERROR("Write to message parcel failed!");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdExecuteBatch(MessageParcel &data, MessageParcel &reply)
{
    std::vector<OperationStatement> statements;
    ExecResultSet result;
    if (!ITypesUtil::UnmarshalOperationStatementVec(statements, data)) {
        LOG_ERROR("Unmarshalling OperationStatement failed");
        return ERR_INVALID_VALUE;
    }
    auto ret = ExecuteBatch(statements, result);
    if (ret == DEFAULT_NUMBER) {
        LOG_ERROR("ExecuteBatch error");
        return ERR_INVALID_VALUE;
    }
    if (!ITypesUtil::Marshal(reply, result)) {
        LOG_ERROR("fail to write result");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

ErrCode DataShareStub::CmdInsertExt(MessageParcel &data, MessageParcel &reply)
{
    Uri uri("");
    DataShareValuesBucket value;
    if (!ITypesUtil::Unmarshal(data, uri, value)) {
        LOG_ERROR("Unmarshalling value is nullptr");
        return ERR_INVALID_VALUE;
    }
    std::string result;
    int index = InsertExt(uri, value, result);
    if (index == DEFAULT_NUMBER) {
        LOG_ERROR("Insert inner error");
        return ERR_INVALID_VALUE;
    }
    if (!ITypesUtil::Marshal(reply, index, result)) {
        LOG_ERROR("fail to write result");
        return ERR_INVALID_VALUE;
    }
    return E_OK;
}

int DataShareStub::ExecuteBatch(const std::vector<OperationStatement> &statements, ExecResultSet &result)
{
    return 0;
}

int DataShareStub::InsertExt(const Uri &uri, const DataShareValuesBucket &value, std::string &result)
{
    return 0;
}

int DataShareStub::BatchUpdate(const UpdateOperations &operations, std::vector<BatchUpdateResult> &results)
{
    return 0;
}
std::pair<int32_t, int32_t> DataShareStub::InsertEx(const Uri &uri, const DataShareValuesBucket &value)
{
    return std::make_pair(0, 0);
}
std::pair<int32_t, int32_t> DataShareStub::UpdateEx(const Uri &uri, const DataSharePredicates &predicates,
    const DataShareValuesBucket &value)
{
    return std::make_pair(0, 0);
}
std::pair<int32_t, int32_t> DataShareStub::DeleteEx(const Uri &uri, const DataSharePredicates &predicates)
{
    return std::make_pair(0, 0);
}

int32_t DataShareStub::UserDefineFunc(
    MessageParcel &data, MessageParcel &reply, MessageOption &option)
{
    LOG_ERROR("UserDefineFunc excuted.");
    return 0;
}

int DataShareStub::RegisterObserverExtProvider(const Uri &uri, const sptr<AAFwk::IDataAbilityObserver> &dataObserver,
    bool isDescendants, RegisterOption option)
{
    return 0;
}

int DataShareStub::UnregisterObserverExtProvider(const Uri &uri, const sptr<AAFwk::IDataAbilityObserver> &dataObserver)
{
    return 0;
}
int DataShareStub::NotifyChangeExtProvider(const ChangeInfo &changeInfo)
{
    return 0;
}

DataShareNonSilentConfig DataShareStub::GetConfig()
{
    DataShareNonSilentConfig config;
    return config;
}
} // namespace DataShare
} // namespace OHOS