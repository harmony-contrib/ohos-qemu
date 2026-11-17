/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2023. All rights reserved.
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

#include "napi_number_identity.h"

#include <algorithm>
#include <initializer_list>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <utility>

#include "ability.h"
#include "base_context.h"
#include "context.h"
#include "datashare_errno.h"
#include "datashare_ext_ability.h"
#include "datashare_helper.h"
#include "datashare_predicates.h"
#include "js_error_code.h"
#include "js_native_api.h"
#include "js_native_api_types.h"
#include "napi/native_common.h"
#include "napi_base_context.h"
#include "napi_number_identity_types.h"
#include "napi_util.h"
#include "number_identity_errors.h"
#include "number_identity_log_wrapper.h"
#include "number_identity_models.h"
#include "number_identity_rdb_helper.h"
#include "number_identity_utils.h"
#include "telephony_errors.h"
#include "telephony_napi_common_error.h"
#include "telephony_permission.h"
#include "uri.h"

namespace OHOS {
using namespace std;
using namespace DataShare;
using namespace OHOS::AbilityRuntime;
using namespace OHOS::AppExecFwk;
namespace Telephony {
using namespace Permission;
using Fields = NumberMarkInfoFields;
static constexpr const char *GET_NUMBER_LOCATION = "getNumberLocation";
static constexpr const char *GET_NUMBER_LOCATIONS = "getNumberLocations";
static constexpr const char *GET_NUMBER_MARK_INFO = "getNumberMarkInfo";
static constexpr const char *SET_NUMBER_MARK_INFO = "setNumberMarkInfo";
const char *NUMBER_LCOATION_URI = "datashare:///com.ohos.numberlocationability";
const char *NUMBER_LCOATION = "number_location";
const char *NUMBER_MARK_URI = "datashare:///com.ohos.numbermarkability";
const char *NUMBER_MARK_INFO_URI = "datashare:///com.ohos.numbermarkability/number_mark_info";
static constexpr const char *JS_ERROR_TELEPHONY_SYSTEM_ERROR_STRING = "System internal error.";
static constexpr const char *JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING = "Invalid parameter value.";
constexpr size_t PARAMETER_COUNT_FOUR = 4;
constexpr size_t PARAMETER_COUNT_THREE = 3;
constexpr int32_t DEFAULT_REF_COUNT = 1;

// Each data share helper is created only once, and will not be released until the process is dead.

shared_ptr<DataShareHelper> GetNumberLocationHelper(shared_ptr<AbilityRuntime::Context> context)
{
    static shared_ptr<DataShareHelper> helper = nullptr;
    static std::mutex mutex;
    std::lock_guard lock(mutex);
    if (helper == nullptr) {
        helper = DataShareHelper::Creator(context->GetToken(), NUMBER_LCOATION_URI);
    }
    return helper;
}

shared_ptr<DataShareHelper> GetNumberMarkHelper(shared_ptr<AbilityRuntime::Context> context)
{
    static shared_ptr<DataShareHelper> helper = nullptr;
    static std::mutex mutex;
    std::lock_guard lock(mutex);
    if (helper == nullptr) {
        helper = DataShareHelper::Creator(context->GetToken(), NUMBER_MARK_URI);
    }
    return helper;
}

static inline bool CheckSystemAppCall(napi_env env, const char *funcName)
{
    if (!TelephonyPermission::CheckCallerIsSystemApp()) {
        NUMBER_IDENTITY_LOGE("Illegal use of System API: Invoke %{public}s in non-system applications.", funcName);
        auto err = NapiUtil::ConverErrorMessageForJs(TELEPHONY_ERR_ILLEGAL_USE_OF_SYSTEM_API);
        NapiUtil::ThrowError(env, err.errorCode, err.errorMessage);
        return false;
    }
    NUMBER_IDENTITY_LOGD("CheckNapiCall for %{public}s passed.", funcName);
    return true;
}

static inline JsError NapiError(int32_t errCode, const char *funcName, const char *permission)
{
    return NapiUtil::ConverErrorMessageWithPermissionForJs(errCode, funcName, permission);
}

static inline void Resolve(BaseContext *context)
{
    context->resolved = true;
    context->errorCode = NUMBER_IDENTITY_ERR_SUCCESS;
}

static inline void Reject(BaseContext *context, int errCode)
{
    context->resolved = false;
    context->errorCode = errCode;
}

static inline napi_value GetNextParam(napi_value *parameters, int &i)
{
    auto result = parameters[i];
    i++;
    return result;
}

napi_value NapiNumberIdentity::DeclareBasisInterface(napi_env env, napi_value exports)
{
    napi_property_descriptor desc[] = {
        DECLARE_NAPI_FUNCTION(GET_NUMBER_LOCATION, GetNumberLocation),
        DECLARE_NAPI_FUNCTION(GET_NUMBER_LOCATIONS, GetNumberLocations),
        DECLARE_NAPI_FUNCTION(GET_NUMBER_MARK_INFO, GetNumberMarkInfo),
        DECLARE_NAPI_FUNCTION(SET_NUMBER_MARK_INFO, SetNumberMarkInfo),
    };
    NAPI_CALL(env, napi_define_properties(env, exports, sizeof(desc) / sizeof(desc[0]), desc));
    return exports;
}

void NapiNumberIdentity::NativeGetNumberLocation(napi_env env, void *data)
{
    auto numberLocationContext = static_cast<NumberLocationAsyncContext *>(data);
    auto helper = GetNumberLocationHelper(numberLocationContext->context);
    if (helper == nullptr) {
        numberLocationContext->errorCode = TELEPHONY_ERR_PERMISSION_ERR;
        numberLocationContext->resolved = false;
        NUMBER_IDENTITY_LOGE("helper is nullptr, as no permission.");
        return;
    }
    DataShare::DataSharePredicates predicates;
    std::string isExactMatchStr = "false";
    if (numberLocationContext->isExactMatch) {
        isExactMatchStr = "true";
    }
    std::vector<std::string> columns;
    columns.push_back(isExactMatchStr);
    std::vector<std::string> phoneNumber;
    phoneNumber.push_back(numberLocationContext->number);
    predicates.SetWhereArgs(phoneNumber);
    std::vector<std::string> whereList = predicates.GetWhereArgs();
    OHOS::Uri uri(NUMBER_LCOATION_URI);
    auto resultSet = helper->Query(uri, predicates, columns);
    if (resultSet == nullptr) {
        NUMBER_IDENTITY_LOGE("resultSet is nullptr!");
        return;
    }
    resultSet->GoToFirstRow();
    int columnIndex = 0;
    resultSet->GetColumnIndex(NUMBER_LCOATION, columnIndex);
    std::string numberLocation = "";
    resultSet->GetString(columnIndex, numberLocation);
    resultSet->Close();
    numberLocationContext->resolved = true;
    numberLocationContext->numberLocation = numberLocation;
    NUMBER_IDENTITY_LOGD("NativeGetNumberLocation len = %{public}lu",
        static_cast<unsigned long>(numberLocationContext->numberLocation.length()));
}

void NapiNumberIdentity::GetNumberLocationCallback(napi_env env, napi_status status, void *data)
{
    auto asyncContext = static_cast<NumberLocationAsyncContext *>(data);
    NUMBER_IDENTITY_LOGD("GetNumberLocationCallback resolved = %{public}d", asyncContext->resolved);
    napi_value callbackValue = nullptr;
    if (asyncContext->resolved) {
        std::string numberLocation = asyncContext->numberLocation;
        napi_create_string_utf8(env, numberLocation.c_str(), numberLocation.length(), &callbackValue);
    } else {
        JsError error = NapiError(asyncContext->errorCode, GET_NUMBER_LOCATION, GET_TELEPHONY_STATE);
        callbackValue = NapiUtil::CreateErrorMessage(env, error.errorMessage, error.errorCode);
    }
    NUMBER_IDENTITY_LOGD("GetNumberLocationCallback end");
    NapiUtil::Handle2ValueCallback(env, asyncContext, callbackValue);
}

napi_value NapiNumberIdentity::GetNumberLocation(napi_env env, napi_callback_info info)
{
    if (!CheckSystemAppCall(env, GET_NUMBER_LOCATION)) {
        return nullptr;
    }
    size_t parameterCount = PARAMETER_COUNT_FOUR;
    napi_value parameters[PARAMETER_COUNT_FOUR] = { 0 };
    napi_value thisVar = nullptr;
    void *data = nullptr;
    NAPI_CALL(env, napi_get_cb_info(env, info, &parameterCount, parameters, &thisVar, &data));
    if (!MatchObjectAndStringParameter(env, parameters, parameterCount)) {
        NUMBER_IDENTITY_LOGE("parameter matching failed.");
        NapiUtil::ThrowParameterError(env);
        return nullptr;
    }
    auto asyncContext = std::make_unique<NumberLocationAsyncContext>();
    if (asyncContext == nullptr) {
        NUMBER_IDENTITY_LOGE("asyncContext is nullptr.");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_SYSTEM_ERROR, JS_ERROR_TELEPHONY_SYSTEM_ERROR_STRING);
        return nullptr;
    }
    size_t argc = ARGS_ONE;
    napi_value argv[ARGS_ONE] = { 0 };
    NAPI_CALL(env, napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr));
    auto context = OHOS::AbilityRuntime::GetStageModeContext(env, argv[0]);
    if (context == nullptr) {
        NUMBER_IDENTITY_LOGE("Failed to get native stage context instance");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_ARGUMENT_ERROR, JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING);
        return nullptr;
    }
    asyncContext->context = context;
    napi_get_value_string_utf8(env, parameters[ARRAY_INDEX_SECOND], asyncContext->number, PHONE_NUMBER_MAXIMUM_LIMIT,
        &(asyncContext->numberLen));
    if (parameterCount == PARAMETER_COUNT_THREE) {
        napi_valuetype valueType = napi_undefined;
        NAPI_CALL(env, napi_typeof(env, parameters[ARRAY_INDEX_THIRD], &valueType));
        if (valueType == napi_undefined) {
            NUMBER_IDENTITY_LOGD("undefined or null parameter detected, treating as no parameter input.");
            asyncContext->isExactMatch = true;
        } else if (valueType == napi_function) {
            auto p3 = parameters[ARRAY_INDEX_THIRD];
            NAPI_CALL(env, napi_create_reference(env, p3, DEFAULT_REF_COUNT, &asyncContext->callbackRef));
        } else if (valueType == napi_boolean) {
            NAPI_CALL(env, napi_get_value_bool(env, parameters[ARRAY_INDEX_THIRD], &asyncContext->isExactMatch));
        }
    } else if (parameterCount == PARAMETER_COUNT_FOUR) {
        NAPI_CALL(env, napi_get_value_bool(env, parameters[ARRAY_INDEX_THIRD], &asyncContext->isExactMatch));
        NAPI_CALL(env,
            napi_create_reference(env, parameters[ARRAY_INDEX_FOURTH], DEFAULT_REF_COUNT, &asyncContext->callbackRef));
    }
    return NapiUtil::HandleAsyncWork(
        env, asyncContext.release(), "GetNumberLocation", NativeGetNumberLocation, GetNumberLocationCallback);
}

void NapiNumberIdentity::NativeGetNumberLocations(napi_env env, void *data)
{
    auto numberLocationsContext = static_cast<NumberLocationsAsyncContext *>(data);
    auto helper = GetNumberLocationHelper(numberLocationsContext->context);
    if (helper == nullptr) {
        numberLocationsContext->errorCode = TELEPHONY_ERR_PERMISSION_ERR;
        numberLocationsContext->resolved = false;
        NUMBER_IDENTITY_LOGE("helper is nullptr, as no permission.");
        return;
    }
    DataShare::DataSharePredicates predicates;
    std::string isExactMatchStr = "false";
    if (numberLocationsContext->isExactMatch) {
        isExactMatchStr = "true";
    }
    std::vector<std::string> columns;
    columns.push_back(isExactMatchStr);
    predicates.SetWhereArgs(numberLocationsContext->phoneNumbers);
    OHOS::Uri uri(NUMBER_LCOATION_URI);
    auto resultSet = helper->Query(uri, predicates, columns);
    if (resultSet == nullptr) {
        NUMBER_IDENTITY_LOGE("resultSet is nullptr!");
        return;
    }
    int rowCount;
    resultSet->GetRowCount(rowCount);
    for (int i = 0; i < rowCount; i++) {
        string numberLocation = "";
        resultSet->GoToRow(i);
        int columnIndex = 0;
        resultSet->GetColumnIndex(NUMBER_LCOATION, columnIndex);
        resultSet->GetString(columnIndex, numberLocation);
        numberLocationsContext->numberLocations.push_back(numberLocation);
    }
    resultSet->Close();
    numberLocationsContext->resolved = true;
    NUMBER_IDENTITY_LOGD("NativeGetNumberLocation len = %{public}lu",
        static_cast<unsigned long>(numberLocationsContext->numberLocations.size()));
}

void NapiNumberIdentity::GetNumberLocationsCallback(napi_env env, napi_status status, void *data)
{
    if (data == nullptr) {
        NapiUtil::ThrowParameterError(env);
        return;
    }
    auto numberLocationsAsyncContext = (NumberLocationsAsyncContext *)data;
    napi_value callbackValue = nullptr;
    if (numberLocationsAsyncContext->resolved == true) {
        napi_create_array(env, &callbackValue);
        for (uint32_t i = 0; i < numberLocationsAsyncContext->numberLocations.size(); i++) {
            napi_value info = nullptr;
            napi_create_object(env, &info);
            std::string numberLocation = numberLocationsAsyncContext->numberLocations[i];
            napi_create_string_utf8(env, numberLocation.c_str(), numberLocation.length(), &info);
            napi_set_element(env, callbackValue, i, info);
        }
    } else {
        JsError error = NapiError(numberLocationsAsyncContext->errorCode, GET_NUMBER_LOCATIONS, GET_TELEPHONY_STATE);
        callbackValue = NapiUtil::CreateErrorMessage(env, error.errorMessage, error.errorCode);
    }
    NapiUtil::Handle2ValueCallback(env, numberLocationsAsyncContext, callbackValue);
}

napi_value NapiNumberIdentity::GetNumberLocations(napi_env env, napi_callback_info info)
{
    if (!CheckSystemAppCall(env, GET_NUMBER_LOCATIONS)) {
        return nullptr;
    }
    size_t parameterCount = PARAMETER_COUNT_FOUR;
    napi_value parameters[PARAMETER_COUNT_FOUR] = { 0 };
    napi_value thisVar = nullptr;
    void *data = nullptr;
    NAPI_CALL(env, napi_get_cb_info(env, info, &parameterCount, parameters, &thisVar, &data));
    if (!MatchTwoObjectParameter(env, parameters, parameterCount)) {
        NUMBER_IDENTITY_LOGE("parameter matching failed.");
        NapiUtil::ThrowParameterError(env);
        return nullptr;
    }
    auto asyncContext = std::make_unique<NumberLocationsAsyncContext>();
    if (asyncContext == nullptr) {
        NUMBER_IDENTITY_LOGE("asyncContext is nullptr.");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_SYSTEM_ERROR, JS_ERROR_TELEPHONY_SYSTEM_ERROR_STRING);
        return nullptr;
    }
    size_t argc = ARGS_ONE;
    napi_value argv[ARGS_ONE] = { 0 };
    NAPI_CALL(env, napi_get_cb_info(env, info, &argc, argv, &thisVar, nullptr));
    auto context = OHOS::AbilityRuntime::GetStageModeContext(env, argv[0]);
    if (context == nullptr) {
        NUMBER_IDENTITY_LOGE("Failed to get native stage context instance");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_ARGUMENT_ERROR, JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING);
        return nullptr;
    }
    asyncContext->context = context;
    uint32_t arrayLength = 0;
    NAPI_CALL(env, napi_get_array_length(env, parameters[ARRAY_INDEX_SECOND], &arrayLength));
    napi_value napiFormId;
    std::string number = "";
    size_t len = 0;
    char phoneNumbers[PHONE_NUMBER_MAXIMUM_LIMIT + 1] = { 0 };
    napi_status getStringStatus = napi_invalid_arg;
    for (uint32_t i = 0; i < arrayLength; i++) {
        napi_get_element(env, parameters[ARRAY_INDEX_SECOND], i, &napiFormId);
        getStringStatus = napi_get_value_string_utf8(env, napiFormId, phoneNumbers, PHONE_NUMBER_MAXIMUM_LIMIT, &len);
        if (getStringStatus == napi_ok && len > 0) {
            number = std::string(phoneNumbers, len);
            (asyncContext->phoneNumbers).push_back(number);
        }
    }
    if (parameterCount == PARAMETER_COUNT_THREE) {
        napi_valuetype valueType = napi_undefined;
        NAPI_CALL(env, napi_typeof(env, parameters[ARRAY_INDEX_THIRD], &valueType));
        if (valueType == napi_undefined) {
            NUMBER_IDENTITY_LOGD("undefined or null parameter detected, treating as no parameter input.");
            asyncContext->isExactMatch = true;
        } else if (valueType == napi_function) {
            auto p3 = parameters[ARRAY_INDEX_THIRD];
            NAPI_CALL(env, napi_create_reference(env, p3, DEFAULT_REF_COUNT, &asyncContext->callbackRef));
        } else if (valueType == napi_boolean) {
            NAPI_CALL(env, napi_get_value_bool(env, parameters[ARRAY_INDEX_THIRD], &asyncContext->isExactMatch));
        }
    } else if (parameterCount == PARAMETER_COUNT_FOUR) {
        NAPI_CALL(env, napi_get_value_bool(env, parameters[ARRAY_INDEX_THIRD], &asyncContext->isExactMatch));
        NAPI_CALL(env,
            napi_create_reference(env, parameters[ARRAY_INDEX_FOURTH], DEFAULT_REF_COUNT, &asyncContext->callbackRef));
    }
    return NapiUtil::HandleAsyncWork(
        env, asyncContext.release(), "GetNumberLocations", NativeGetNumberLocations, GetNumberLocationsCallback);
}

void NapiNumberIdentity::NativeGetNumberMarkInfo(napi_env env, void *data)
{
    NUMBER_IDENTITY_LOGI("NativeGetNumberMarkInfo begin");
    auto getNumberMarkContext = static_cast<GetNumberMarkInfoAsyncContext *>(data);
    auto helper = GetNumberMarkHelper(getNumberMarkContext->context);
    FAIL_IF_NULL(helper, {
        Reject(getNumberMarkContext, TELEPHONY_ERR_PERMISSION_ERR);
        return;
    });
    DataSharePredicates predicates;
    auto &markInfo = getNumberMarkContext->markInfo;
    predicates.SetWhereArgs({ getNumberMarkContext->phoneNumber });
    Uri uri(NUMBER_MARK_INFO_URI);
    vector<string> columns;
    auto resultSet = helper->Query(uri, predicates, columns);
    FAIL_IF_NULL(resultSet, {
        Reject(getNumberMarkContext, NUMBER_IDENTITY_ERR_DATABASE_READ_FAIL);
        return;
    });
    bool isNull;
    int count;
    int columnIndex;
    int errCode;
    int64_t longValue;
    string stringValue;
    errCode = resultSet->GetRowCount(count);
    HANDLE_ERR("resultSet->GetRowCount", errCode, goto error);
    if (count == 0) {
        NUMBER_IDENTITY_LOGI("Number mark not found.");
    } else {
        errCode = resultSet->GoToFirstRow();
        HANDLE_ERR("resultSet->GoToFirstRow()", errCode, goto error);
        FETCH_FIELD(Fields::markContent, String, stringValue, isNull, *resultSet, columnIndex, errCode, goto error);
        ASSIGN_IF_NOT_NULL(markInfo.markContent, stringValue, isNull);
        FETCH_FIELD(Fields::markCount, Long, longValue, isNull, *resultSet, columnIndex, errCode, goto error);
        ASSIGN_IF_NOT_NULL(markInfo.markCount, longValue, isNull);
        FETCH_FIELD(Fields::markType, Long, longValue, isNull, *resultSet, columnIndex, errCode, goto error);
        ASSIGN_IF_NOT_NULL(markInfo.markType, static_cast<MarkType>(longValue), isNull);
        FETCH_FIELD(Fields::markSource, String, stringValue, isNull, *resultSet, columnIndex, errCode, goto error);
        ASSIGN_IF_NOT_NULL(markInfo.markSource, stringValue, isNull);
        FETCH_FIELD(Fields::isCloud, Long, longValue, isNull, *resultSet, columnIndex, errCode, goto error);
        ASSIGN_IF_NOT_NULL(markInfo.isCloud, longValue == 1L, isNull);
        FETCH_FIELD(Fields::markDetails, String, stringValue, isNull, *resultSet, columnIndex, errCode, goto error);
        ASSIGN_IF_NOT_NULL(markInfo.markDetails, stringValue, isNull);
    }
    Resolve(getNumberMarkContext);
    resultSet->Close();
    return;
error:
    Reject(getNumberMarkContext, NUMBER_IDENTITY_ERR_READ_DATA_FAIL);
    resultSet->Close();
}

void NapiNumberIdentity::GetNumberMarkInfoCallback(napi_env env, napi_status status, void *data)
{
    auto asyncContext = static_cast<GetNumberMarkInfoAsyncContext *>(data);
    NUMBER_IDENTITY_LOGD("GetNumberMarkInfoCallback resolved = %{public}d", asyncContext->resolved);
    if (!asyncContext->resolved) {
        auto error = NapiError(asyncContext->errorCode, GET_NUMBER_MARK_INFO, GET_TELEPHONY_STATE);
        auto callbackValue = NapiUtil::CreateErrorMessage(env, error.errorMessage, error.errorCode);
        NapiUtil::Handle2ValueCallback(env, asyncContext, callbackValue);
        return;
    }
    const auto &markInfo = asyncContext->markInfo;
    napi_value returnObject = nullptr;
    NAPI_CALL_RETURN_VOID(env, napi_create_object(env, &returnObject));
    if (markInfo.markContent.has_value()) {
        NapiUtil::SetPropertyStringUtf8(env, returnObject, Fields::markContent, *markInfo.markContent);
    }
    if (markInfo.markCount.has_value()) {
        NapiUtil::SetPropertyInt32(env, returnObject, Fields::markCount, *markInfo.markCount);
    }
    if (markInfo.markSource.has_value()) {
        NapiUtil::SetPropertyStringUtf8(env, returnObject, Fields::markSource, *markInfo.markSource);
    }
    auto markType = static_cast<int32_t>(markInfo.markType);
    NapiUtil::SetPropertyInt32(env, returnObject, Fields::markType, markType);
    if (markInfo.isCloud.has_value()) {
        NapiUtil::SetPropertyBoolean(env, returnObject, Fields::isCloud, *markInfo.isCloud);
    }
    if (markInfo.markDetails.has_value()) {
        NapiUtil::SetPropertyStringUtf8(env, returnObject, Fields::markDetails, *markInfo.markDetails);
    }
    NapiUtil::Handle2ValueCallback(env, asyncContext, returnObject);
}

napi_value NapiNumberIdentity::GetNumberMarkInfo(napi_env env, napi_callback_info info)
{
    if (!CheckSystemAppCall(env, GET_NUMBER_MARK_INFO)) {
        return nullptr;
    }
    napi_value parameters[] = { nullptr, nullptr };
    size_t parameterCount = sizeof(parameters) / sizeof(parameters[0]);
    NAPI_CALL(env, napi_get_cb_info(env, info, &parameterCount, parameters, nullptr, nullptr));
    if (!NapiUtil::MatchParameters(env, parameters, { napi_object, napi_string })) {
        NUMBER_IDENTITY_LOGE("Parameter matching failed, expected (object, string).");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_ARGUMENT_ERROR, JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING);
        return nullptr;
    }
    auto context = AbilityRuntime::GetStageModeContext(env, parameters[0]);
    if (context == nullptr) {
        NUMBER_IDENTITY_LOGE("Failed to get native stage context instance.");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_ARGUMENT_ERROR, JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING);
        return nullptr;
    }
    auto phoneNumber = NapiUtil::GetStringFromValue(env, parameters[1]);
    if (phoneNumber.empty()) {
        NUMBER_IDENTITY_LOGE("Invalid empty phone number.");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_ARGUMENT_ERROR, JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING);
        return nullptr;
    }
    auto asyncContext = std::make_unique<GetNumberMarkInfoAsyncContext>();
    asyncContext->context = context;
    asyncContext->phoneNumber = phoneNumber;
    return NapiUtil::HandleAsyncWork(
        env, asyncContext.release(), "GetNumberMarkInfo", NativeGetNumberMarkInfo, GetNumberMarkInfoCallback);
}

void NapiNumberIdentity::NativeSetNumberMarkInfo(napi_env env, void *data)
{
    NUMBER_IDENTITY_LOGI("NativeSetNumberMarkInfo begin");
    auto setNumberMarkContext = static_cast<SetNumberMarkInfoAsyncContext *>(data);
    auto helper = GetNumberMarkHelper(setNumberMarkContext->context);
    FAIL_IF_NULL(helper, {
        Reject(setNumberMarkContext, TELEPHONY_ERR_PERMISSION_ERR);
        return;
    });
    auto &markInfo = setNumberMarkContext->markInfo;
    Uri uri(NUMBER_MARK_INFO_URI);
    DataSharePredicates predicates;
    DataShareValuesBucket values;
    values.Put(SetNumberMarkParamsFields::phoneNumber, setNumberMarkContext->phoneNumber);
    values.Put(SetNumberMarkParamsFields::markType, static_cast<int64_t>(markInfo.markType));
    if (markInfo.markContent.has_value()) {
        values.Put(SetNumberMarkParamsFields::customMarkContent, *markInfo.markContent);
    }
    auto errCode = helper->Update(uri, predicates, values);
    if (errCode == NUMBER_IDENTITY_ERR_SUCCESS) {
        // According to DataShare API, `DataShareHelper::Update` should return the number of data records updated.
        // But here DataShare is ONLY used for parameter passing.
        // The business logic overall is implemented in the DataShare ability, including creating number mark,
        // updating number mark, deleting number mark, reporting it to cloud and other stuff.
        // So the return value is the ERROR CODE, NOT the number of data records updated.
        Resolve(setNumberMarkContext);
    } else {
        Reject(setNumberMarkContext, errCode);
    }
}

void NapiNumberIdentity::SetNumberMarkInfoCallback(napi_env env, napi_status status, void *data)
{
    auto asyncContext = static_cast<SetNumberMarkInfoAsyncContext *>(data);
    NUMBER_IDENTITY_LOGD("SetNumberMarkInfoCallback resolved = %{public}d", asyncContext->resolved);
    if (!asyncContext->resolved) {
        auto error = NapiError(asyncContext->errorCode, SET_NUMBER_MARK_INFO, SET_TELEPHONY_STATE);
        auto callbackValue = NapiUtil::CreateErrorMessage(env, error.errorMessage, error.errorCode);
        NapiUtil::Handle2ValueCallback(env, asyncContext, callbackValue);
        return;
    }
    auto returnObject = NapiUtil::CreateUndefined(env);
    NapiUtil::Handle2ValueCallback(env, asyncContext, returnObject);
}

napi_value NapiNumberIdentity::SetNumberMarkInfo(napi_env env, napi_callback_info info)
{
    if (!CheckSystemAppCall(env, SET_NUMBER_MARK_INFO)) {
        return nullptr;
    }
    napi_value parameters[] = { nullptr, nullptr, nullptr, nullptr };
    auto maxParameterCount = sizeof(parameters) / sizeof(parameters[0]);
    size_t parameterCount = maxParameterCount;
    NAPI_CALL(env, napi_get_cb_info(env, info, &parameterCount, parameters, nullptr, nullptr));
    if (!NapiUtil::MatchParameters(env, parameters, { napi_object, napi_string, napi_number }) &&
        !NapiUtil::MatchParameters(env, parameters, { napi_object, napi_string, napi_number, napi_string })) {
        NUMBER_IDENTITY_LOGE("Parameter matching failed, expected (object, string, MarkType, string?).");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_ARGUMENT_ERROR, JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING);
        return nullptr;
    }
    double numberValue;
    napi_valuetype type;
    int i = 0;
    auto context = AbilityRuntime::GetStageModeContext(env, GetNextParam(parameters, i));
    if (context == nullptr) {
        NUMBER_IDENTITY_LOGE("Failed to get native stage context instance.");
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_ARGUMENT_ERROR, JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING);
        return nullptr;
    }
    auto phoneNumber = NapiUtil::GetStringFromValue(env, GetNextParam(parameters, i));
    MarkType markType;
    NAPI_CALL(env, napi_get_value_double(env, GetNextParam(parameters, i), &numberValue));
    if (!GetMarkType(numberValue, markType)) {
        NUMBER_IDENTITY_LOGE("Invalid mark type %{public}d.", static_cast<int>(numberValue));
        NapiUtil::ThrowError(env, JS_ERROR_TELEPHONY_ARGUMENT_ERROR, JS_ERROR_TELEPHONY_ARGUMENT_ERROR_STRING);
        return nullptr;
    }
    optional<string> customMarkContent;
    auto markContent = GetNextParam(parameters, i);
    NAPI_CALL(env, napi_typeof(env, markContent, &type));
    if (type == napi_string) {
        customMarkContent = NapiUtil::GetStringFromValue(env, markContent);
    }
    auto asyncContext = std::make_unique<SetNumberMarkInfoAsyncContext>();
    asyncContext->context = context;
    asyncContext->phoneNumber = phoneNumber;
    asyncContext->markInfo.markContent = customMarkContent;
    asyncContext->markInfo.markType = markType;
    NUMBER_IDENTITY_LOGI("AsyncWork SetNumberMarkInfo Start");
    return NapiUtil::HandleAsyncWork(
        env, asyncContext.release(), "SetNumberMarkInfo", NativeSetNumberMarkInfo, SetNumberMarkInfoCallback);
}

bool NapiNumberIdentity::MatchObjectAndStringParameter(
    napi_env env, const napi_value parameters[], const size_t parameterCount)
{
    NUMBER_IDENTITY_LOGD("MatchObjectAndStringParameter %{public}zu", parameterCount);
    switch (parameterCount) {
        case TWO_VALUE_LIMIT:
            return NapiUtil::MatchParameters(env, parameters, { napi_object, napi_string });
        case THREE_VALUE_MAXIMUM_LIMIT:
            return NapiUtil::MatchParameters(env, parameters, { napi_object, napi_string, napi_boolean }) ||
                   NapiUtil::MatchParameters(env, parameters, { napi_object, napi_string, napi_function }) ||
                   NapiUtil::MatchParameters(env, parameters, { napi_object, napi_string, napi_undefined });
        case FOUR_VALUE_MAXIMUM_LIMIT:
            return NapiUtil::MatchParameters(
                env, parameters, { napi_object, napi_string, napi_boolean, napi_function });
        default:
            return false;
    }
}

bool NapiNumberIdentity::MatchTwoObjectParameter(
    napi_env env, const napi_value parameters[], const size_t parameterCount)
{
    NUMBER_IDENTITY_LOGD("MatchTwoObjectParameter %{public}zu", parameterCount);
    switch (parameterCount) {
        case TWO_VALUE_LIMIT:
            return NapiUtil::MatchParameters(env, parameters, { napi_object, napi_object });
        case THREE_VALUE_MAXIMUM_LIMIT:
            return NapiUtil::MatchParameters(env, parameters, { napi_object, napi_object, napi_function }) ||
                   NapiUtil::MatchParameters(env, parameters, { napi_object, napi_object, napi_boolean }) ||
                   NapiUtil::MatchParameters(env, parameters, { napi_object, napi_object, napi_undefined });
        case FOUR_VALUE_MAXIMUM_LIMIT:
            return NapiUtil::MatchParameters(
                env, parameters, { napi_object, napi_object, napi_boolean, napi_function });
        default:
            return false;
    }
}

napi_value NapiNumberIdentity::RegisterNumberIdentityFunc(napi_env env, napi_value exports)
{
    DeclareBasisInterface(env, exports);
    return exports;
}

static napi_module g_nativeNumberIdentityModule = {
    .nm_version = NATIVE_VERSION,
    .nm_flags = NATIVE_FLAGS,
    .nm_filename = nullptr,
    .nm_register_func = NapiNumberIdentity::RegisterNumberIdentityFunc,
    .nm_modname = "telephony.numberidentity",
    .nm_priv = nullptr,
    .reserved = { nullptr },
};

static napi_module g_nativeNumberLookupModule = {
    .nm_version = NATIVE_VERSION,
    .nm_flags = NATIVE_FLAGS,
    .nm_filename = nullptr,
    .nm_register_func = NapiNumberIdentity::RegisterNumberIdentityFunc,
    .nm_modname = "contact.numberlookup",
    .nm_priv = nullptr,
    .reserved = { nullptr },
};

extern "C" __attribute__((constructor)) void RegisterNumberIdentityModule(void)
{
    napi_module_register(&g_nativeNumberIdentityModule);
    napi_module_register(&g_nativeNumberLookupModule);
}
} // namespace Telephony
} // namespace OHOS
