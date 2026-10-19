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

#include "number_mark_ability.h"

#include "application_info.h"
#include "bundle_mgr_interface.h"
#include "context.h"
#include "continuation_handler.h"
#include "datashare_ext_ability_context.h"
#include "errors.h"
#include "hisysevent.h"
#include "ipc_skeleton.h"
#include "number_identity_database.h"
#include "number_identity_datashare_stub_impl.h"
#include "number_identity_datashare_transform.h"
#include "number_identity_ddl.h"
#include "number_identity_errors.h"
#include "number_identity_hsdr_helper.h"
#include "number_identity_json_helper.h"
#include "number_identity_log_wrapper.h"
#include "number_identity_models.h"
#include "number_identity_rdb_helper.h"
#include "number_identity_settings.h"
#include "number_identity_utils.h"
#include "number_identity_value_bucket_template.h"
#include "number_location_manager.h"
#include "number_mark_caller_info.h"
#include "number_mark_manager.h"
#include "number_mark_result_set_bridge.h"

#include "ability_context.h"
#include "ability_loader.h"
#include "datashare_business_error.h"
#include "datashare_ext_ability.h"
#include "datashare_helper.h"
#include "datashare_predicates.h"
#include "datashare_predicates_def.h"
#include "datashare_predicates_object.h"
#include "datashare_result_set.h"
#include "datashare_values_bucket.h"
#include "extension_manager_client.h"
#include "fix_phone_number.h"
#include "iservice_registry.h"
#include "parameters.h"
#include "rdb_errno.h"
#include "rdb_predicates.h"
#include "rdb_utils.h"
#include "refbase.h"
#include "result_set_bridge.h"
#include "singleton.h"
#include "string_ex.h"
#include "system_ability_definition.h"
#include "telephony_permission.h"
#include "uri.h"
#include "utility"
#include "values_bucket.h"
#include "want.h"

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <future>
#include <memory>
#include <mutex>
#include <new>
#include <optional>
#include <set>
#include <string>
#include <thread>
#include <tuple>
#include <variant>
#include <vector>

#define DATABASE_READ_FAIL_IF_NULL(ptr, businessError, finally)                                                        \
    do {                                                                                                               \
        if ((ptr) == nullptr) {                                                                                        \
            NUMBER_IDENTITY_LOGE(#ptr " is nullptr!");                                                                 \
            SetBusinessError(businessError, NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL);                                   \
            finally;                                                                                                   \
        }                                                                                                              \
    } while (0)

#define HANDLE_BUSINESS_ERROR(msg, errCode, businessError, finally)                                                    \
    do {                                                                                                               \
        HANDLE_ERR(msg, errCode, {                                                                                     \
            SetBusinessError(businessError, errCode);                                                                  \
            finally;                                                                                                   \
        });                                                                                                            \
    } while (0)

#define CHECK_PERMISSION(permission, ret) BOOL_CHECK(CheckPermissionBypassSelf(permission), return (ret))

namespace OHOS {
namespace Telephony {

using AbilityRuntime::Extension;
using namespace NativeRdb;
using namespace OHOS::RdbDataShareAdapter;
using namespace std;
using DataShare::DataShareHelper;

using TransformNumber = function<string(const string &)>;
static constexpr const char *STRANGE_NUMBER_IDENTITY_SETTINGS_KEY = "settings.telephony.number_identity_switch";
static constexpr const char *UPDATE_LIBRARY_TIMESTAMP = "spamshield_update_library_time";
static constexpr const char *ANTIFRAUD_CENTER_SWITCH = "settings.telephony.antifraud_center_switch";
static constexpr const char *ANTIFRAUD_BESTMIND_SWITCH = "settings.telephony.antifraud_bestmind_switch";
static constexpr const char *CALLLOG_URI = "datashare:///com.ohos.calllogability";
static constexpr const char *CALL_SUBSECTION = "datashare:///com.ohos.calllogability/calls/calllog";
static constexpr const char *ANTIFRAUD_CENTER_BUNDLE_NAME = "com.hicorenational.antifraud.hmy";
static constexpr const char *ANTIFRAUD_BESTMIND_BUNDLE_NAME = "com.bestmind.antifraud.hmy";
constexpr const char *CALL_PHONE_NUMBER = "phone_number";
// constexpr const char *CALL_FORMAT_PHONE_NUMBER_TO_E164 = "format_phone_number";
constexpr const char *CALL_MARK_TYPE = "mark_type";
constexpr const char *CALL_ANSWER_STATE = "answer_state";
constexpr const char *CALL_MARK_CONTENT = "mark_content";
constexpr const char *CALL_IS_CLOUD_MARK = "is_cloud_mark";
constexpr const char *CALL_MARK_COUNT = "mark_count";
constexpr const char *CALL_MARK_SOURCE = "mark_source";
constexpr const char *CALL_MARK_SOURCE_FOR_AFS = "5";
constexpr const char *CALL_MARK_SOURCE_NOT_AFS = "3";
constexpr const char *AFS_BUTTON_IS_ON = "1";

constexpr const char API_PREFIX[] = "api/";
constexpr const size_t API_PREFIX_LENGTH = sizeof(API_PREFIX) - 1;
constexpr const char *API_QUERY_VIRTUAL_COLUMN_ORIGINAL_NUMBER = "original_number";
constexpr const char *API_QUERY_VIRTUAL_YELLOW_PAGE_NORMALIZED = "yellow_page_normalized";
constexpr const char *API_QUERY_VIRTUAL_NUMBER_MARK_NORMALIZED = "number_mark_normalized";
constexpr const char *API_PARAM_UPDATE_TIMESTAMP = "update_timestamp";

static inline int SetBusinessError(DatashareBusinessError &businessError, int errCode)
{
    businessError.SetCode(errCode);
    switch (errCode) {
        case DataShare::E_OK:
            break;
        case NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL:
            businessError.SetMessage("Failed to read number identity database.");
            break;
        case NUMBER_IDENTITY_ERR_ARGUMENT_INVALID:
            businessError.SetMessage("Invalid datashare query parameter.");
            break;
        default:
            businessError.SetMessage("other ignore error message.");
            break;
    }
    return errCode;
}

static bool IsValidMark(const NumberMarkModel &numberMark)
{
    // `MarkType::MARK_TYPE_NONE` is not a valid mark.
    // Setting number mark with type `MarkType::MARK_TYPE_NONE` means to delete it.
    return numberMark.MarkType() != MarkType::MARK_TYPE_NONE;
}

static bool IsCloudMark(const NumberMarkModel &numberMark)
{
    return numberMark.is_cloud == 1L && IsValidMark(numberMark);
}

static bool IsUserMark(const NumberMarkModel &numberMark)
{
    return numberMark.is_cloud == 0L && IsValidMark(numberMark);
}

static optional<YellowPageViewModel> FindYellowPageBestMatch(
    const string &phoneNumber, const vector<YellowPageViewModel> &yellowPages)
{
    for (const auto &model : yellowPages) {
        if (model.number.has_value() && model.number.value() == phoneNumber) {
            NUMBER_IDENTITY_LOGI("Got exact match.");
            return model;
        }
    }
    if (auto first = yellowPages.cbegin(); first != yellowPages.cend()) {
        NUMBER_IDENTITY_LOGI("Using first match.");
        return *first;
    }
    return nullopt;
}

NumberMarkAbility::NumberMarkAbility(shared_ptr<DataShareExtAbilityContext> parentContext) : DataShareExtAbility()
{
    if (parentContext == nullptr) {
        NUMBER_IDENTITY_LOGF("parent context is null!");
    }
    parentContext_ = parentContext;
}

NumberMarkAbility::~NumberMarkAbility() {}

NumberMarkAbility *NumberMarkAbility::Create(shared_ptr<DataShareExtAbilityContext> parentContext)
{
    NUMBER_IDENTITY_LOGI("NumberMarkAbility::Create begin.");
    auto self = new NumberMarkAbility(parentContext);
    return self;
}

sptr<IRemoteObject> NumberMarkAbility::OnConnect(const Want &want)
{
    NUMBER_IDENTITY_LOGI("NumberMarkAbility::OnConnect");
    Extension::OnConnect(want);
    sptr<DataShare::NumberIdentityDataShareStubImpl> remoteObject =
        new (std::nothrow) DataShare::NumberIdentityDataShareStubImpl();
    FAIL_IF_NULL(remoteObject, return nullptr);
    remoteObject->SetNumberMarkAbility(std::static_pointer_cast<NumberMarkAbility>(shared_from_this()));
    return remoteObject->AsObject();
}

void NumberMarkAbility::OnStart(const Want &want)
{
    NUMBER_IDENTITY_LOGI("NumberMarkAbility::OnStart");
    Extension::OnStart(want);
}

int NumberMarkAbility::Insert(const Uri &uri, const DataShareValuesBucket &values)
{
    NUMBER_IDENTITY_LOGE("Insert via DataShare is not supported.");
    return NUMBER_IDENTITY_ERR_WRITE_DATA_FAIL;
}

int NumberMarkAbility::BatchInsert(const Uri &uri, const vector<DataShareValuesBucket> &values)
{
    CHECK_PERMISSION(Permission::SET_TELEPHONY_STATE, NUMBER_IDENTITY_ERR_PERMISSION_ERR);
    auto path = GetUriPathName(uri);
    NUMBER_IDENTITY_LOGI("path: %{public}s.", path.c_str());
    if (path == NumberIdentityTables::NUMBER_MARK) {
        return RawBatchInsert(NumberIdentityTables::NUMBER_MARK, values);
    }
    NUMBER_IDENTITY_LOGE("BatchInsert with path %{public}s is not supported.", path.c_str());
    return NUMBER_IDENTITY_ERR_WRITE_DATA_FAIL;
}

int NumberMarkAbility::Delete(const Uri &uri, const DataSharePredicates &predicates)
{
    CHECK_PERMISSION(Permission::SET_TELEPHONY_STATE, NUMBER_IDENTITY_ERR_PERMISSION_ERR);
    auto path = GetUriPathName(uri);
    NUMBER_IDENTITY_LOGI("path: %{public}s.", path.c_str());
    if (path == NumberIdentityTables::NUMBER_MARK) {
        return RawDelete(NumberIdentityTables::NUMBER_MARK, predicates);
    }
    NUMBER_IDENTITY_LOGE("Delete with path %{public}s is not supported.", path.c_str());
    return NUMBER_IDENTITY_ERR_WRITE_DATA_FAIL;
}

int NumberMarkAbility::Update(
    const Uri &uri, const DataSharePredicates &predicates, const DataShareValuesBucket &values)
{
    CHECK_PERMISSION(Permission::SET_TELEPHONY_STATE, NUMBER_IDENTITY_ERR_PERMISSION_ERR);
    auto path = GetUriPathName(uri);
    NUMBER_IDENTITY_LOGI("path: %{public}s.", path.c_str());
    if (path == "number_mark_info") {
        return this->SetNumberMark(values);
    }
    if (path == PropertyKeys::INTELLIGENT_DB_UPDATE_TIMESTAMP) {
        return this->SetIntelligentDBUpdateTimestamp(values);
    }
    NUMBER_IDENTITY_LOGE("Failed to match NumberMarkAbility::Update URI.");
    return NUMBER_IDENTITY_ERR_WRITE_DATA_FAIL;
}

TransformNumber TransformYellowPageNumber = [](const string &number) {
    auto transformed = FixPhoneNumber(number).SubstringFixedPhoneNumber();
    if (number.size() != transformed.size()) {
        NUMBER_IDENTITY_LOGI("number and transformed size is not equal.");
        if (StartsWith(number, "1")) {
            NUMBER_IDENTITY_LOGW("Orignal number is started with 1, area code removal discarded.");
            transformed = number;
        }
    }
    return transformed;
};

TransformNumber TransformNumberMarkNumber = [](const string &number) {
    auto transformed = NumberMarkManager::StandardizationPhoneNum(number);
    NUMBER_IDENTITY_LOGI("TransformNumberMarkNumber number size(%{public}ld), transformed size(%{public}ld)",
        number.size(), transformed.size());
    if (number.size() != transformed.size()) {
        NUMBER_IDENTITY_LOGI("number and transformed size is not equal.");
    }
    return transformed;
};

shared_ptr<DataShareResultSet> NumberMarkAbility::Query(const Uri &uri, const DataSharePredicates &predicates,
    vector<string> &columns, DatashareBusinessError &businessError)
{
    if (OHOS::system::GetParameter("const.global.region", "CN") != "CN") {
        NUMBER_IDENTITY_LOGI("not the chinese version, no need to query markinfo.");
        return nullptr;
    }
    CHECK_PERMISSION(Permission::GET_TELEPHONY_STATE, nullptr);
    static set<string> yellowPageTables = {
        NumberIdentityTables::YELLOW_PAGE,
        NumberIdentityTables::YELLOW_PAGE_PHONE,
        NumberIdentityTables::YELLOW_PAGE_VIEW,
    };
    static set<string> numberMarkTables = {
        NumberIdentityTables::NUMBER_MARK,
        NumberIdentityTables::NUMBER_MARK_EXTRAS,
    };
    static set<string> otherTables = {
        NumberIdentityTables::PROPERTIES,
    };
    auto path = GetUriPathName(uri);
    NUMBER_IDENTITY_LOGI("path: %{public}s.", path.c_str());
    NativeQuery query = [&](const auto &predicates) { return RawQuery(path, predicates, columns, businessError); };
    if (auto tableIter = yellowPageTables.find(path); tableIter != yellowPageTables.end()) {
        StringFieldProxy proxy = {
            .field = YellowPageViewColumns::NUMBER,
            .transform = TransformYellowPageNumber,
            .query = query,
        };
        return proxy.ProxyQuery(predicates);
    }
    if (auto tableIter = numberMarkTables.find(path); tableIter != numberMarkTables.end()) {
        StringFieldProxy proxy = {
            .field = NumberMarkColumns::NUMBER,
            .transform = TransformNumberMarkNumber,
            .query = query,
        };
        return proxy.ProxyQuery(predicates);
    }
    if (auto tableIter = otherTables.find(path); tableIter != otherTables.end()) {
        return this->RawQuery(*tableIter, predicates, columns, businessError);
    }
    if (path == "number_mark_info") {
        return this->QueryNumberMarks(predicates, businessError);
    }
    if (StartsWith(path, API_PREFIX)) {
        return this->APIQuery(uri, predicates, columns, businessError);
    }
    NUMBER_IDENTITY_LOGE("Failed to match NumberMarkAbility::Query URI.");
    SetBusinessError(businessError, NUMBER_IDENTITY_ERR_ARGUMENT_INVALID);
    return nullptr;
}

int NumberMarkAbility::Put(
    const string &table, const DataSharePredicates &predicates, const DataShareValuesBucket &values)
{
    NUMBER_IDENTITY_LOGI("put begin, table: %{public}s.", table.c_str());
    int errCode = E_OK;
    vector<string> columns;
    DatashareBusinessError businessError;
    auto resultSet = RawQuery(table, predicates, columns, businessError);
    errCode = businessError.GetCode();
    if (errCode != NUMBER_IDENTITY_ERR_SUCCESS) {
        NUMBER_IDENTITY_LOGE("BusinessError: %{public}s", businessError.GetMessage().c_str());
        return errCode;
    }
    FAIL_IF_NULL(resultSet, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    int count;
    errCode = resultSet->GetRowCount(count);
    HANDLE_ERR("GetRowCount", errCode, return errCode);
    if (count == 0) {
        errCode = RawInsert(table, values);
    } else {
        errCode = RawUpdate(table, predicates, values);
    }
    return errCode;
}

int NumberMarkAbility::RawInsert(const string &table, const DataShareValuesBucket &values)
{
    NUMBER_IDENTITY_LOGI("RawInsert begin, table: %{public}s.", table.c_str());
    auto db = NumberIdentityDatabase::GetInstance();
    FAIL_IF_NULL(db, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    auto rdbValues = RdbUtils::ToValuesBucket(values);
    return db->Insert(table, rdbValues);
}

int NumberMarkAbility::RawBatchInsert(const string &table, const vector<DataShareValuesBucket> &values)
{
    NUMBER_IDENTITY_LOGI("RawBatchInsert begin, table: %{public}s.", table.c_str());
    auto db = NumberIdentityDatabase::GetInstance();
    FAIL_IF_NULL(db, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    vector<ValuesBucket> rdbValues;
    MapVector<DataShareValuesBucket, ValuesBucket>(values, rdbValues, RdbUtils::ToValuesBucket);
    return db->BatchInsert(table, rdbValues);
}

int NumberMarkAbility::RawDelete(const string &table, const DataSharePredicates &predicates)
{
    NUMBER_IDENTITY_LOGI("RawDelete begin, table: %{public}s.", table.c_str());
    auto db = NumberIdentityDatabase::GetInstance();
    FAIL_IF_NULL(db, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    auto rdbPredicates = RdbUtils::ToPredicates(predicates, table);
    return db->Delete(rdbPredicates);
}

int NumberMarkAbility::RawUpdate(
    const string &table, const DataSharePredicates &predicates, const DataShareValuesBucket &values)
{
    NUMBER_IDENTITY_LOGI("RawUpdate begin, table: %{public}s.", table.c_str());
    auto db = NumberIdentityDatabase::GetInstance();
    FAIL_IF_NULL(db, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    auto rdbPredicates = RdbUtils::ToPredicates(predicates, table);
    auto rdbValues = RdbUtils::ToValuesBucket(values);
    return db->Update(rdbPredicates, rdbValues);
}

shared_ptr<DataShareResultSet> NumberMarkAbility::RawQuery(const string &table, const DataSharePredicates &predicates,
    vector<string> &columns, DatashareBusinessError &businessError)
{
    NUMBER_IDENTITY_LOGI("RawQuery begin");
    auto rdbPredicates = RdbUtils::ToPredicates(predicates, table);
    NUMBER_IDENTITY_LOGI("RawQuery converted");
    auto db = NumberIdentityDatabase::GetInstance();
    DATABASE_READ_FAIL_IF_NULL(db, businessError, return nullptr);
    auto resultSet = db->Query(rdbPredicates, columns);
    DATABASE_READ_FAIL_IF_NULL(resultSet, businessError, return nullptr);
    auto queryResultSet = RdbUtils::ToResultSetBridge(resultSet);
    DATABASE_READ_FAIL_IF_NULL(queryResultSet, businessError, return nullptr);
    auto result = std::make_shared<DataShareResultSet>(queryResultSet);
    DATABASE_READ_FAIL_IF_NULL(result, businessError, return nullptr);
    return result;
}

bool NumberMarkAbility::IsSelfCall()
{
    auto pid = getpid();
    auto callerPid = IPCSkeleton::GetCallingPid();
    bool isSelfCall = pid == callerPid;
    if (isSelfCall) {
        NUMBER_IDENTITY_LOGI("Self call");
    }
    return isSelfCall;
}

bool NumberMarkAbility::CheckPermissionBypassSelf(const string &permission)
{
    if (IsSelfCall()) {
        return true;
    }
    return TelephonyPermission::CheckPermission(permission);
}

shared_ptr<DataShareResultSet> NumberMarkAbility::APIQuery(const Uri &uri, const DataSharePredicates &predicates,
    vector<string> &columns, DatashareBusinessError &businessError)
{
    auto apiPath = GetUriPathName(uri).substr(API_PREFIX_LENGTH);
    NUMBER_IDENTITY_LOGI("APIQuery begin, apiPath: %{public}s.", apiPath.c_str());
    if (apiPath == "process_number") {
        return this->ProcessNumber(predicates, columns, businessError);
    }
    NUMBER_IDENTITY_LOGE("Failed to match api path.");
    return nullptr;
}

static inline void AddAPIQueryEqualToNumber(const OperationItem &item, vector<string> &numbers)
{
    auto number = GetEqualToFieldValue<string>(API_QUERY_VIRTUAL_COLUMN_ORIGINAL_NUMBER, item);
    if (number.has_value()) {
        numbers.emplace_back(number.value());
    }
}

static inline void AddAPIQuerySqlInNumber(const OperationItem &item, vector<string> &numbers)
{
    auto inValues = GetSqlInFieldValues<string>(API_QUERY_VIRTUAL_COLUMN_ORIGINAL_NUMBER, item);
    if (inValues.has_value()) {
        numbers.insert(numbers.end(), inValues->begin(), inValues->end());
    }
}

static inline vector<string> GetAPIQueryNumbers(const DataSharePredicates &predicates)
{
    vector<string> numbers;
    auto operations = predicates.GetOperationList();
    auto p = predicates;
    for (const auto &item : operations) {
        switch (item.operation) {
            case DataShare::OperationType::EQUAL_TO:
                AddAPIQueryEqualToNumber(item, numbers);
                break;
            case DataShare::OperationType::SQL_IN:
                AddAPIQuerySqlInNumber(item, numbers);
                break;
            default:
                break;
        }
    }

    return numbers;
}

enum class ProcessType {
    ORIGINAL_NUMBER,
    YELLOW_PAGE_NORMALIZED,
    NUMBER_MARK_NORMALIZED,
    UNKNOWN,
};

static ProcessType GetProcessType(const string &columnName)
{
    if (columnName == API_QUERY_VIRTUAL_COLUMN_ORIGINAL_NUMBER) {
        return ProcessType::ORIGINAL_NUMBER;
    }
    if (columnName == API_QUERY_VIRTUAL_YELLOW_PAGE_NORMALIZED) {
        return ProcessType::YELLOW_PAGE_NORMALIZED;
    }
    if (columnName == API_QUERY_VIRTUAL_NUMBER_MARK_NORMALIZED) {
        return ProcessType::NUMBER_MARK_NORMALIZED;
    }
    return ProcessType::UNKNOWN;
}

static inline NativeData GetProcessedNumber(const string &number, ProcessType type)
{
    switch (type) {
        case ProcessType::ORIGINAL_NUMBER:
            return number;
        case ProcessType::YELLOW_PAGE_NORMALIZED:
            return TransformYellowPageNumber(number);
        case ProcessType::NUMBER_MARK_NORMALIZED:
            return TransformNumberMarkNumber(number);
        case ProcessType::UNKNOWN:
        default:
            return monostate{};
    }
}

shared_ptr<DataShareResultSet> NumberMarkAbility::ProcessNumber(
    const DataSharePredicates &predicates, vector<string> &columns, DatashareBusinessError &businessError)
{
    auto numbers = GetAPIQueryNumbers(predicates);
    NativeDataSet result;
    result.columnNames = columns;
    LOGI_EXPR(columns);
    vector<ProcessType> types;
    MapVector<string, ProcessType>(columns, types, GetProcessType);
    for (auto number : numbers) {
        NativeRecord record;
        for (auto type : types) {
            record.emplace_back(GetProcessedNumber(number, type));
        }
        result.records.emplace_back(record);
    }
    shared_ptr<ResultSetBridge> bridge = make_shared<NativeDataResultSetBridge>(result);
    return make_shared<DataShareResultSet>(bridge);
}

shared_ptr<DataShareResultSet> NumberMarkAbility::QueryNumberMarks(
    const DataSharePredicates &predicates, DatashareBusinessError &businessError)
{
    NUMBER_IDENTITY_LOGI("QueryNumberMarks begin.");
    auto whereList = predicates.GetWhereArgs();
    vector<NumberMarkInfo> numberMarks;
    int errCode = E_OK;
    for (size_t i = 0, size = whereList.size(); i < size; ++i) {
        const auto &phoneNumber = whereList.at(i);
        NumberMarkInfo markInfo;
        errCode = QueryByPhoneNumber(phoneNumber, markInfo, businessError);
        if (errCode != E_OK) {
            NUMBER_IDENTITY_LOGE("number mark query row %{public}ld failed! errCode = %{public}d", i, errCode);
            // Assign with empty NumberMarkInfo.
            markInfo = NumberMarkInfo();
        };
        numberMarks.emplace_back(markInfo);
    }
    shared_ptr<ResultSetBridge> bridge = std::make_shared<NumberMarkResultSetBridge>(numberMarks);
    NUMBER_IDENTITY_LOGI("QueryNumberMarks end.");
    return std::make_shared<DataShareResultSet>(bridge);
}

int NumberMarkAbility::QueryByPhoneNumber(
    const string &phoneNumber, NumberMarkInfo &markInfo, DatashareBusinessError &businessError)
{
    NUMBER_IDENTITY_LOGI("QueryByPhoneNumber begin.");
    NumberMarkQueryContext context;
    context.phoneNumber = phoneNumber;
    auto &yellowPages = context.dbYellowPages;
    auto &numberMarks = context.dbMarks;
    int errCode = this->QueryLocalYellowPage(phoneNumber, yellowPages, businessError);
    HANDLE_BUSINESS_ERROR("QueryYellowPage", errCode, businessError, return errCode);
    if (auto it = FindYellowPageBestMatch(phoneNumber, yellowPages); it.has_value()) {
        NUMBER_IDENTITY_LOGI("Got %{public}ld Yellow page, 1st = %{public}s", yellowPages.size(), TO_C_STR(it->name));
        markInfo.FromYellowPage(*it);
        return SetBusinessError(businessError, errCode);
    }
    context.numberMarkQueryNumber = TransformNumberMarkNumber(phoneNumber);
    auto &numberMarkQueryPhoneNumber = context.numberMarkQueryNumber;
    errCode = this->QueryLocalNumberMark(numberMarkQueryPhoneNumber, numberMarks, businessError);
    HANDLE_BUSINESS_ERROR("QueryLocalNumberMark", errCode, businessError, return errCode);
    auto mark = find_if(numberMarks.cbegin(), numberMarks.cend(), IsUserMark);
    if (mark != numberMarks.cend()) { // found local user mark:
        NUMBER_IDENTITY_LOGI("Got user number mark: classify = %{public}s", TO_C_STR(mark->classify));
        markInfo.FromNumberMark(*mark);
        return SetBusinessError(businessError, errCode);
    }
    auto token = parentContext_ != nullptr ? parentContext_->GetToken() : nullptr;
    if (!LOGI_EXPR(IsStrangeNumberIdentitySwitchedOn(token))) {
        NUMBER_IDENTITY_LOGI("Switch is off, no local mark found.");
        return E_OK; // Settings not switched on, returns None.
    }
    return errCode;
}

bool NumberMarkAbility::IsStrangeNumberIdentitySwitchedOn(sptr<IRemoteObject> token)
{
    bool isSwitchedOn = false; // default to switched off
    string value;
    auto errCode = GetSettingsData(STRANGE_NUMBER_IDENTITY_SETTINGS_KEY, value, token);
    if (errCode == NUMBER_IDENTITY_ERR_SUCCESS && value == "1") {
        isSwitchedOn = true;
    }
    return isSwitchedOn;
}

int NumberMarkAbility::QueryLocalYellowPage(
    const string &phoneNumber, vector<YellowPageViewModel> &yellowPages, DatashareBusinessError &businessError)
{
    NUMBER_IDENTITY_LOGI("QueryLocalYellowPage start.");
    int errCode = E_OK;
    auto db = NumberIdentityDatabase::GetInstance();
    DATABASE_READ_FAIL_IF_NULL(db, businessError, return NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL);
    RdbPredicates predicates(NumberIdentityTables::YELLOW_PAGE_VIEW);
    auto transformed = TransformYellowPageNumber(phoneNumber);
    if (transformed != phoneNumber) {
        predicates.In(YellowPagePhoneColumns::NUMBER, vector<string>({ transformed, phoneNumber }));
    } else {
        predicates.EqualTo(YellowPageViewColumns::NUMBER, phoneNumber);
    }
    vector<string> columns = {
        YellowPageViewColumns::ID,
        YellowPageViewColumns::NAME,
        YellowPageViewColumns::NUMBER,
        YellowPageViewColumns::PHOTO,
    };
    auto resultSet = db->Query(predicates, columns);
    DATABASE_READ_FAIL_IF_NULL(resultSet, businessError, return NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL);
    int rowCount = 0;
    errCode = resultSet->GetRowCount(rowCount);
    HANDLE_BUSINESS_ERROR("resultSet->GetRowCount", errCode, businessError, return errCode);
    NUMBER_IDENTITY_LOGI("Got %{public}d rows", rowCount);
    for (int i = 0; i < rowCount; ++i) {
        errCode = resultSet->GoToRow(i);
        HANDLE_BUSINESS_ERROR("GoToRow", errCode, businessError, return errCode);
        YellowPageViewModel yellowPage;
        errCode = yellowPage.CreateFromResultSet(*resultSet);
        HANDLE_BUSINESS_ERROR("Create YellowPageViewModel from result set", errCode, businessError, return errCode);
        yellowPages.emplace_back(yellowPage);
    }
    NUMBER_IDENTITY_LOGI("QueryLocalYellowPage end.");
    return errCode;
}

int NumberMarkAbility::QueryLocalNumberMark(
    const string &phoneNumber, vector<NumberMarkModel> &numberMarks, DatashareBusinessError &businessError)
{
    NUMBER_IDENTITY_LOGI("QueryLocalNumberMark begin.");
    int errCode = E_OK;
    auto db = NumberIdentityDatabase::GetInstance();
    DATABASE_READ_FAIL_IF_NULL(db, businessError, return NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL);
    RdbPredicates predicates(NumberIdentityTables::NUMBER_MARK);
    predicates.EqualTo(NumberMarkColumns::NUMBER, phoneNumber);
    vector<string> columns = {
        NumberMarkColumns::ID,
        NumberMarkColumns::NUMBER,
        NumberMarkColumns::NAME,
        NumberMarkColumns::CLASSIFY,
        NumberMarkColumns::MARKED_COUNT,
        NumberMarkColumns::IS_CLOUD,
        NumberMarkColumns::DESCRIPTION,
        NumberMarkColumns::SAVE_TIMESTAMP,
        NumberMarkColumns::SUPPLIER,
        NumberMarkColumns::SUPPLIER_ID,
        NumberMarkColumns::IS_INTELLIGENT_DB,
    };
    auto resultSet = db->Query(predicates, columns);
    DATABASE_READ_FAIL_IF_NULL(resultSet, businessError, return NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL);
    int rowCount = 0;
    errCode = resultSet->GetRowCount(rowCount);
    HANDLE_BUSINESS_ERROR("resultSet->GetRowCount", errCode, businessError, return errCode);
    NUMBER_IDENTITY_LOGI("Got %{public}d rows", rowCount);
    for (int i = 0; i < rowCount; ++i) {
        errCode = resultSet->GoToRow(i);
        HANDLE_BUSINESS_ERROR("GoToRow", errCode, businessError, return errCode);
        NumberMarkModel numberMark;
        errCode = numberMark.CreateFromResultSet(*resultSet);
        HANDLE_BUSINESS_ERROR("Create NumberMarkModel from result set", errCode, businessError, return errCode);
        numberMarks.emplace_back(numberMark);
    }
    SetBusinessError(businessError, errCode);
    NUMBER_IDENTITY_LOGI("QueryLocalNumberMark end.");
    return errCode;
}

int NumberMarkAbility::QueryIntelligentDB(const string &phoneNumber, NumberMarkInfo &markInfo)
{
    NUMBER_IDENTITY_LOGI("QueryIntelligentDB begin.");
    int errCode = E_OK;
    auto db = NumberIdentityDatabase::GetInstance();
    FAIL_IF_NULL(db, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    auto md5 = GenerateMD5(StringBytes(phoneNumber));
    FAIL_IF_NULLOPT(md5, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    auto md5Hex = ToHexString(*md5);
    RdbPredicates predicates(NumberIdentityTables::NUMBER_MARK);
    predicates.EqualTo(NumberMarkColumns::NUMBER, md5Hex)->And()->EqualTo(NumberMarkColumns::IS_INTELLIGENT_DB, true);
    vector<string> columns = {
        NumberMarkColumns::ID,
        NumberMarkColumns::NUMBER,
        NumberMarkColumns::NAME,
        NumberMarkColumns::CLASSIFY,
        NumberMarkColumns::MARKED_COUNT,
        NumberMarkColumns::IS_CLOUD,
        NumberMarkColumns::DESCRIPTION,
        NumberMarkColumns::SAVE_TIMESTAMP,
        NumberMarkColumns::SUPPLIER,
        NumberMarkColumns::SUPPLIER_ID,
        NumberMarkColumns::IS_INTELLIGENT_DB,
    };
    auto resultSet = db->Query(predicates, columns);
    FAIL_IF_NULL(resultSet, return NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL);
    int rowCount = 0;
    errCode = resultSet->GetRowCount(rowCount);
    HANDLE_ERR("GetRowCount", errCode, return errCode);
    if (rowCount == 0) {
        NUMBER_IDENTITY_LOGI("No intelligent DB mark found.");
        return NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL;
    }
    errCode = resultSet->GoToFirstRow();
    HANDLE_ERR("GoToFirstRow", errCode, return errCode);
    NumberMarkModel numberMark;
    errCode = numberMark.CreateFromResultSet(*resultSet);
    HANDLE_ERR("CreateFromResultSet", errCode, return errCode);
    markInfo.FromNumberMark(numberMark);
    NUMBER_IDENTITY_LOGI("Got intelligent db, classify = %{public}s", TO_C_STR(numberMark.classify));
    return errCode;
}

static map<string, tuple<string, MarkType>> markerTypes = {
    {
        "100",
        { "未知", MarkType::MARK_TYPE_NONE },
    },
    {
        "101",
        { "快递送餐", MarkType::MARK_TYPE_EXPRESS },
    },
    {
        "102",
        { "出租司机", MarkType::MARK_TYPE_TAXI },
    },
    {
        "103",
        { "教育培训", MarkType::MARK_TYPE_OTHERS },
    },
    {
        "104",
        { "招聘猎头", MarkType::MARK_TYPE_OTHERS },
    },
    {
        "105",
        { "保险理财", MarkType::MARK_TYPE_INSURANCE },
    },
    {
        "106",
        { "贷款中介", MarkType::MARK_TYPE_OTHERS },
    },
    {
        "107",
        { "房产中介", MarkType::MARK_TYPE_HOUSE_AGENT },
    },
    {
        "108",
        { "广告推销", MarkType::MARK_TYPE_PROMOTE_SALES },
    },
    {
        "109",
        { "骚扰电话", MarkType::MARK_TYPE_CRANK },
    },
    {
        "110",
        { "高风险电话", MarkType::MARK_TYPE_FRAUD },
    },

};

bool NumberMarkAbility::ShouldMarkTypeBeReported(MarkType markType)
{
    switch (markType) {
        case MarkType::MARK_TYPE_NONE:
        case MarkType::MARK_TYPE_OTHERS:
        case MarkType::MARK_TYPE_YELLOW_PAGE:
        case MarkType::MARK_TYPE_ENTERPRISE:
            return false;
        default:
            return true; // Other mark types will be reported to cloud.
    }
}

int NumberMarkAbility::PutOrDeleteNumberMark(const NumberMarkModel &numberMark)
{
    NUMBER_IDENTITY_LOGI("PutOrDeleteNumberMark, classify = %{public}s", TO_C_STR(numberMark.classify));
    int errCode = E_OK;
    auto predicates = numberMark.ToIdentityDataSharePredicates();
    if (!IsValidMark(numberMark)) {
        errCode = RawDelete(NumberIdentityTables::NUMBER_MARK, predicates);
        LOG_IF_ERR(errCode, "RawDelete");
        return errCode;
    }
    auto values = numberMark.ToDataShareValuesBucket();
    // No need to create data models.
    errCode = Put(NumberIdentityTables::NUMBER_MARK, predicates, values);
    LOG_IF_ERR(errCode, "Put");
    return errCode;
}

shared_future<void> g_asyncTask;

int NumberMarkAbility::SetNumberMark(const DataShareValuesBucket &values)
{
    NUMBER_IDENTITY_LOGI("SetNumberMark.");
    int errCode = NUMBER_IDENTITY_ERR_SUCCESS;
    NumberMarkModel rawMark;
    errCode = ParseNumberMark(values, rawMark);
    HANDLE_ERR("ParseNumberMark", errCode, return errCode);
    auto markType = rawMark.MarkType();
    NUMBER_IDENTITY_LOGI("mark type: %{public}d.", markType);
    vector<NumberMarkModel> oldMarks;
    auto convertedMark = rawMark;
    convertedMark.number = TransformNumberMarkNumber(rawMark.number);
    errCode = RunInTransaction("SetLocalNumberMark", [&]() { return SetLocalNumberMark(convertedMark, oldMarks); });
    HANDLE_ERR("SetLocalNumberMark", errCode, return errCode);
    auto callLogMark = rawMark;
    if (!IsValidMark(callLogMark)) {
        auto oldCloudMark = find_if(oldMarks.cbegin(), oldMarks.cend(), IsCloudMark);
        if (oldCloudMark != oldMarks.cend()) {
            NUMBER_IDENTITY_LOGI("Should restore cache, classify = %{public}s", TO_C_STR(oldCloudMark->classify));
            callLogMark = *oldCloudMark;
            callLogMark.number = rawMark.number;
        }
    }
    errCode = UpdateCallLog(callLogMark);
    HANDLE_ERR("UpdateCallLog", errCode, return errCode);
    auto &net = DelayedRefSingleton<NetworkInfo>::GetInstance();
    net.Refresh();
    if (!LOGI_EXPR(net.hasNetWork)) {
        return errCode;
    }
    if (!ShouldMarkTypeBeReported(markType)) {
        NUMBER_IDENTITY_LOGI("Skipped report to cloud.");
        return NUMBER_IDENTITY_ERR_SUCCESS;
    }
    return NUMBER_IDENTITY_ERR_SUCCESS; // Ignore cloud report errors.
}

int NumberMarkAbility::ParseNumberMark(const DataShareValuesBucket &values, NumberMarkModel &numberMark)
{
    NUMBER_IDENTITY_LOGI("ParseNumberMark start.");
    int errCode = NUMBER_IDENTITY_ERR_SUCCESS;
    string stringValue;
    if (!GetFromValueBucket(values, SetNumberMarkParamsFields::phoneNumber, stringValue)) {
        return NUMBER_IDENTITY_ERR_ARGUMENT_INVALID;
    }
    if (stringValue.empty()) {
        NUMBER_IDENTITY_LOGE("phoneNumber is empty.");
        return NUMBER_IDENTITY_ERR_ARGUMENT_INVALID;
    }
    numberMark.number = stringValue;
    int64_t longValue;
    if (!GetFromValueBucket(values, SetNumberMarkParamsFields::markType, longValue)) {
        return NUMBER_IDENTITY_ERR_ARGUMENT_INVALID;
    }
    MarkType markType;
    BOOL_CHECK(GetMarkType(longValue, markType), return NUMBER_IDENTITY_ERR_ARGUMENT_INVALID);
    numberMark.classify = GetClassify(markType);
    if (markType == MarkType::MARK_TYPE_CUSTOM) {
        if (!GetFromValueBucket(values, SetNumberMarkParamsFields::customMarkContent, stringValue)) {
            return NUMBER_IDENTITY_ERR_ARGUMENT_INVALID;
        }
        BOOL_CHECK(!stringValue.empty(), return NUMBER_IDENTITY_ERR_ARGUMENT_INVALID);
        numberMark.name = stringValue;
    }
    numberMark.is_cloud = 0;
    return errCode;
}

int NumberMarkAbility::SetLocalNumberMark(const NumberMarkModel &numberMark, vector<NumberMarkModel> &oldMarks)
{
    int errCode = NUMBER_IDENTITY_ERR_SUCCESS;
    DatashareBusinessError businessError;
    // Query only once, output old marks.
    errCode = QueryLocalNumberMark(numberMark.number, oldMarks, businessError);
    HANDLE_ERR("QueryLocalNumberMark", errCode, return NUMBER_IDENTITY_ERR_READ_DATA_FAIL);
    auto hasUserMark = find_if(oldMarks.cbegin(), oldMarks.cend(), IsUserMark) != oldMarks.cend();
    auto predicates = numberMark.ToIdentityDataSharePredicates();
    if (!IsValidMark(numberMark)) {
        return RawDelete(NumberIdentityTables::NUMBER_MARK, predicates);
    }
    auto values = numberMark.ToDataShareValuesBucket();
    if (hasUserMark) {
        return RawUpdate(NumberIdentityTables::NUMBER_MARK, predicates, values);
    }
    return RawInsert(NumberIdentityTables::NUMBER_MARK, values);
}

int NumberMarkAbility::SetIntelligentDBUpdateTimestamp(const DataShareValuesBucket &values)
{
    double doubleValue = 0;
    int64_t timestamp;
    if (GetFromValueBucket(values, API_PARAM_UPDATE_TIMESTAMP, doubleValue)) {
        timestamp = static_cast<int64_t>(doubleValue);
    } else if (!GetFromValueBucket(values, API_PARAM_UPDATE_TIMESTAMP, timestamp)) {
        return NUMBER_IDENTITY_ERR_ARGUMENT_INVALID;
    }
    auto db = NumberIdentityDatabase::GetInstance();
    FAIL_IF_NULL(db, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    int result = db->PutProperty(PropertyKeys::INTELLIGENT_DB_UPDATE_TIMESTAMP, ToString(timestamp));
    if (result) {
        NUMBER_IDENTITY_LOGE("PutProperty error!");
        return result;
    }
    auto token = parentContext_ != nullptr ? parentContext_->GetToken() : nullptr;
    string timestampStr = ToString(timestamp);
    string timestampTemp;
    NUMBER_IDENTITY_LOGI("timestampStr: %{public}s.", timestampStr.c_str());
    if (GetSettingsData(UPDATE_LIBRARY_TIMESTAMP, timestampTemp, token)) {
        result = InsertSettingsData(UPDATE_LIBRARY_TIMESTAMP, timestampStr, token);
    } else {
        result = UpdateSettingsData(UPDATE_LIBRARY_TIMESTAMP, timestampStr, token);
    }
    NUMBER_IDENTITY_LOGI("result: %{public}d.", result);
    return result;
}

int NumberMarkAbility::RunInTransaction(const string &tag, function<int()> transaction)
{
    int errCode = NUMBER_IDENTITY_ERR_SUCCESS;
    vector<NumberMarkModel> marks;
    auto db = NumberIdentityDatabase::GetInstance();
    FAIL_IF_NULL(db, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    errCode = db->BeginTransaction();
    HANDLE_ERR("db->BeginTransaction()", errCode, return NUMBER_IDENTITY_ERR_WRITE_DATA_FAIL);
    errCode = transaction();
    if (errCode == NUMBER_IDENTITY_ERR_SUCCESS) {
        errCode = db->Commit();
        HANDLE_ERR("db->Commit()", errCode, return errCode);
    } else {
        errCode = db->RollBack();
        HANDLE_ERR("db->RollBack()", errCode, return errCode);
    }
    NUMBER_IDENTITY_LOGI("Transaction %{public}s done.", tag.c_str());
    return errCode;
}

int NumberMarkAbility::UpdateCallLog(const NumberMarkModel &numberMark)
{
    NUMBER_IDENTITY_LOGI("UpdateCallLog start.");
    int errCode = NUMBER_IDENTITY_ERR_SUCCESS;
    auto context = parentContext_;
    FAIL_IF_NULL(context, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    auto token = context->GetToken();
    FAIL_IF_NULL(token, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    auto helper = DataShareHelper::Creator(token, CALLLOG_URI);
    FAIL_IF_NULL(helper, return NUMBER_IDENTITY_ERR_LOCAL_PTR_NULL);
    Uri uri(CALL_SUBSECTION);
    DataSharePredicates predicates;
    DataShareValuesBucket values;
    predicates.EqualTo(CALL_PHONE_NUMBER, numberMark.number);
    predicates.NotEqualTo(CALL_ANSWER_STATE, static_cast<int64_t>(CallAnswerType::CALL_ANSWER_BLOCKED));
    values.Put(CALL_MARK_TYPE, static_cast<int64_t>(numberMark.MarkType()));
    values.Put(CALL_MARK_CONTENT, numberMark.name.value_or(""));
    values.Put(CALL_MARK_COUNT, numberMark.marked_count.value_or(0));
    values.Put(CALL_IS_CLOUD_MARK, numberMark.is_cloud);
    dealMarkSource(numberMark, values);
    auto updatedCount = helper->Update(uri, predicates, values);
    NUMBER_IDENTITY_LOGI("Updated %{public}d row(s) of call log.", updatedCount);
    return errCode;
}

void NumberMarkAbility::dealMarkSource(const NumberMarkModel &numberMark, DataShareValuesBucket &values)
{
    NUMBER_IDENTITY_LOGI("mark type: %{public}d, supplier: %{public}s.",
        numberMark.MarkType(), numberMark.supplier->c_str());
    if (numberMark.MarkType() == MarkType::MARK_TYPE_FRAUD && numberMark.supplier == CALL_MARK_SOURCE_FOR_AFS) {
        bool isAntiFraudCenterSwitchOn =
            isAntifraudSwitchOn(ANTIFRAUD_CENTER_BUNDLE_NAME, ANTIFRAUD_CENTER_SWITCH);
        bool isAntiFraudBestMindSwitchOn =
            isAntifraudSwitchOn(ANTIFRAUD_BESTMIND_BUNDLE_NAME, ANTIFRAUD_BESTMIND_SWITCH);
        if (isAntiFraudCenterSwitchOn || isAntiFraudBestMindSwitchOn) {
            NUMBER_IDENTITY_LOGI("CALL_MARK_SOURCE_FOR_AFS.");
            values.Put(CALL_MARK_SOURCE, CALL_MARK_SOURCE_FOR_AFS);
        } else {
            NUMBER_IDENTITY_LOGI("CALL_MARK_SOURCE_NOT_AFS.");
            values.Put(CALL_MARK_SOURCE, CALL_MARK_SOURCE_NOT_AFS);
        }
    } else if (numberMark.MarkType() == MarkType::MARK_TYPE_FRAUD) {
        NUMBER_IDENTITY_LOGI("set markSource empty for set mark to fraud type scene.");
        values.Put(CALL_MARK_SOURCE, "");
    }
    return;
}

bool NumberMarkAbility::isAntifraudSwitchOn(const string &bundleName, const string &appSwitchKey)
{
    string appName;
    int result = QueryAppName(bundleName, appName);
    auto token = parentContext_ != nullptr ? parentContext_->GetToken() : nullptr;
    string value;
    return !result && GetSettingsData(appSwitchKey, value, token) == NUMBER_IDENTITY_ERR_SUCCESS &&
        value == AFS_BUTTON_IS_ON;
}

} // namespace Telephony
} // namespace OHOS