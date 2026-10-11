/*
 * Copyright (C) 2025-2025 Huawei Device Co., Ltd.
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

#include "result_set_napi.h"

#include "medialibrary_client_errno.h"
#include "medialibrary_napi_log.h"
#include "big_integer.h"
#include "asset_value.h"

using OHOS::HiviewDFX::HiLog;
using OHOS::HiviewDFX::HiLogLabel;

namespace OHOS {
namespace Media {
using namespace std;
using namespace OHOS::NativeRdb;
using Asset = AssetValue;
using BigInt = BigInteger;
using Assets = std::vector<Asset>;
using FloatVector = std::vector<float>;
thread_local napi_ref ResultSetNapi::sResultSetConstructor_ = nullptr;

template <>
napi_value Convert2JSValue(napi_env env, const int32_t &value)
{
    napi_value jsValue = nullptr;
    if (napi_create_int32(env, value, &jsValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_int32 failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const uint32_t &value)
{
    napi_value jsValue = nullptr;
    if (napi_create_uint32(env, value, &jsValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_uint32 failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const int64_t &value)
{
    napi_value jsValue = nullptr;
    if (napi_create_int64(env, value, &jsValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_int64 failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const std::string &value)
{
    napi_value jsValue = nullptr;
    if (napi_create_string_utf8(env, value.c_str(), value.size(), &jsValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_string failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const Asset &value)
{
    auto outputStatus = value.status & ~0xF0000000;
    std::vector<napi_property_descriptor> descriptors = {
        napi_property_descriptor(DECLARE_NAPI_DEFAULT_PROPERTY(("name"), Convert2JSValue((env), (value.name)))),
        napi_property_descriptor(DECLARE_NAPI_DEFAULT_PROPERTY(("uri"), Convert2JSValue((env), (value.uri)))),
        napi_property_descriptor(DECLARE_NAPI_DEFAULT_PROPERTY(("createTime"),
                                                               Convert2JSValue((env), (value.createTime)))),
        napi_property_descriptor(DECLARE_NAPI_DEFAULT_PROPERTY(("modifyTime"),
                                                               Convert2JSValue((env), (value.modifyTime)))),
        napi_property_descriptor(DECLARE_NAPI_DEFAULT_PROPERTY(("size"), Convert2JSValue((env), (value.size)))),
        napi_property_descriptor(DECLARE_NAPI_DEFAULT_PROPERTY(("path"), Convert2JSValue((env), (value.path)))),
        napi_property_descriptor(DECLARE_NAPI_DEFAULT_PROPERTY(("status"), Convert2JSValue((env), (outputStatus)))),
    };
    napi_value object = nullptr;
    if (napi_create_object_with_properties(env, &object, descriptors.size(), descriptors.data()) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_Asset failed");
        return object;
    }
    return object;
}

template <>
napi_value Convert2JSValue(napi_env env, const double &value)
{
    napi_value jsValue = nullptr;
    if (napi_create_double(env, value, &jsValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_double failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const bool &value)
{
    napi_value jsValue = nullptr;
    if (napi_get_boolean(env, value, &jsValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_boolean failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const float &value)
{
    napi_value jsValue = nullptr;
    if (napi_create_double(env, value, &jsValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_float failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const std::vector<uint8_t> &value)
{
    size_t size = value.size();
    void *data = nullptr;
    napi_value buffer = nullptr;
    if (napi_create_arraybuffer(env, size, &data, &buffer) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_buffer failed");
        return buffer;
    }
    if (size != 0 && data) {
        std::copy(value.begin(), value.end(), static_cast<uint8_t *>(data));
    } else {
        NAPI_ERR_LOG("Data is empty");
    }
    napi_value napiValue = nullptr;
    if (napi_create_typedarray(env, napi_uint8_array, size, buffer, 0, &napiValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_buffer failed");
        return buffer;
    }
    return napiValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const BigInt &value)
{
    napi_value jsValue = nullptr;
    if (napi_create_bigint_words(env, value.Sign(), value.Size(), value.TrueForm(), &jsValue) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_BigInt failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const std::vector<float> &value)
{
    napi_value jsValue = nullptr;
    float *native = nullptr;
    napi_value buffer = nullptr;
    napi_status status = napi_create_arraybuffer(env, value.size() * sizeof(float), (void **)&native, &buffer);
    if (status != napi_ok || native == nullptr) {
        NAPI_ERR_LOG("Napi_create_FLOAT_VECTOR failed");
        return jsValue;
    }

    for (size_t i = 0; i < value.size(); i++) {
        *(native + i) = value[i];
    }
    status = napi_create_typedarray(env, napi_float32_array, value.size(), buffer, 0, &jsValue);
    if (status != napi_ok) {
        NAPI_ERR_LOG("Napi_create_FLOAT_VECTOR failed");
        return jsValue;
    }
    return jsValue;
}

template <>
napi_value Convert2JSValue(napi_env env, const ValueObject &value)
{
    return Convert2JSValue(env, value.value);
}

template <>
napi_value Convert2JSValue(napi_env env, const RowEntity &rowEntity)
{
    napi_value ret = nullptr;
    if (napi_create_object(env, &ret) != napi_ok) {
        NAPI_ERR_LOG("Napi_create_object failed");
        return ret;
    }
    auto &values = rowEntity.Get();
    for (auto const &[key, object] : values) {
        napi_value value = Convert2JSValue(env, object.value);
        napi_set_named_property(env, ret, key.c_str(), value);
    }
    return ret;
}

static std::shared_ptr<ResultSet> GetInt32AndResultSet(napi_env env, napi_callback_info info, int32_t &ret)
{
    napi_status status;
    napi_value thisVar = nullptr;
    size_t argc = 1;
    napi_value args[1];
    CHECK_COND_WITH_ERR_MESSAGE(env, napi_get_cb_info(env, info, &argc, args, &thisVar, nullptr) == napi_ok,
                                JS_E_INNER_FAIL, "NAPI napi_get_cb_info failed");
    CHECK_COND_WITH_ERR_MESSAGE(env, napi_get_value_int32(env, args[0], &ret) == napi_ok, JS_E_PARAM_INVALID,
                                "NAPI napi_get_value_int32 failed");
    ResultSetNapi *obj = nullptr;
    status = napi_unwrap(env, thisVar, reinterpret_cast<void **>(&obj));
    CHECK_COND_WITH_ERR_MESSAGE(env, status == napi_ok && obj != nullptr, JS_E_INNER_FAIL, "NAPI env error");
    std::shared_ptr<ResultSet> rs = obj->resultSetPtr;
    CHECK_COND_WITH_ERR_MESSAGE(env, rs != nullptr, JS_E_INNER_FAIL, "ResultSet is null");
    return rs;
}

static ResultSetNapi *GetResultSetNapi(napi_env env, napi_callback_info info)
{
    napi_status status;
    napi_value thisVar = nullptr;
    GET_JS_OBJ_WITH_ZERO_ARGS(env, info, status, thisVar);
    CHECK_COND_WITH_ERR_MESSAGE(env, status == napi_ok, JS_E_INNER_FAIL, "GET_JS_OBJ_WITH_ZERO_ARGS failed");
    ResultSetNapi *obj = nullptr;
    status = napi_unwrap(env, thisVar, reinterpret_cast<void **>(&obj));
    CHECK_COND_WITH_ERR_MESSAGE(env, status == napi_ok && obj != nullptr, JS_E_INNER_FAIL, "NAPI_unwrap failed");
    return obj;
}

static std::shared_ptr<ResultSet> GetResultSet(napi_env env, napi_callback_info info)
{
    ResultSetNapi *obj = GetResultSetNapi(env, info);
    CHECK_COND_WITH_ERR_MESSAGE(env, obj != nullptr, JS_E_INNER_FAIL, "ResultSetNapi is nullptr");
    std::shared_ptr<ResultSet> rs = obj->resultSetPtr;
    CHECK_COND_WITH_ERR_MESSAGE(env, rs != nullptr, JS_E_INNER_FAIL, "ResultSet is nullptr");
    return rs;
}

ResultSetNapi::ResultSetNapi(std::shared_ptr<ResultSet> ptr) : resultSetPtr(std::move(ptr)), env_(nullptr) {}

ResultSetNapi::~ResultSetNapi() = default;

void ResultSetNapi::ResultSetNapiDestructor(napi_env env, void *nativeObject, void *finalize_hint)
{
    ResultSetNapi *resultSet = reinterpret_cast<ResultSetNapi *>(nativeObject);
    if (resultSet != nullptr) {
        delete resultSet;
    } else {
        NAPI_ERR_LOG("ResultSet is nullptr, invalid nativeObject in Finalizer");
    }
}

napi_value ResultSetNapi::Init(napi_env env, napi_value exports)
{
    NapiClassInfo info = {.name = RESULT_SET_NAPI_CLASS_NAME,
                          .ref = &sResultSetConstructor_,
                          .constructor = ResultSetNapiConstructor,
                          .props = {
                              // 属性
                              DECLARE_NAPI_GETTER("columnCount", JSGetColumnCount),
                              DECLARE_NAPI_GETTER("rowCount", JSGetRowCount),
                              DECLARE_NAPI_GETTER("rowIndex", JSGetRowIndex),
                              DECLARE_NAPI_GETTER("isAtLastRow", JSIsAtLastRow),
                              // 方法
                              DECLARE_NAPI_FUNCTION("goToRow", JSGoToRow),
                              DECLARE_NAPI_FUNCTION("goToFirstRow", JSGoToFirstRow),
                              DECLARE_NAPI_FUNCTION("goToNextRow", JSGoToNextRow),
                              DECLARE_NAPI_FUNCTION("getBlob", JSGetBlob),
                              DECLARE_NAPI_FUNCTION("getString", JSGetString),
                              DECLARE_NAPI_FUNCTION("getLong", JSGetLong),
                              DECLARE_NAPI_FUNCTION("getDouble", JSGetDouble),
                              DECLARE_NAPI_FUNCTION("getBool", JSGetBool),
                              DECLARE_NAPI_FUNCTION("getValue", JSGetValue),
                              DECLARE_NAPI_FUNCTION("getRow", JSGetRow),
                              DECLARE_NAPI_FUNCTION("close", JSClose),
                          }};
    MediaLibraryNapiUtils::NapiDefineClass(env, exports, info);
    return exports;
}

napi_value ResultSetNapi::ResultSetNapiConstructor(napi_env env, napi_callback_info info)
{
    napi_value thisArg;
    CHECK_COND_WITH_ERR_MESSAGE(env, napi_get_cb_info(env, info, nullptr, nullptr, &thisArg, nullptr) == napi_ok,
                                JS_E_INNER_FAIL, "Napi env error");
    return thisArg;
}

napi_value ResultSetNapi::CreateResultSetNapi(napi_env env, std::shared_ptr<ResultSet> &resultSet,
                                              JSAsyncContextOutput &asyncContext)
{
    if (resultSet == nullptr) {
        MediaLibraryNapiUtils::CreateNapiErrorObject(env, asyncContext.error, JS_E_INNER_FAIL, "ResultSet is null");
        return nullptr;
    }
    napi_value constructor;
    napi_status status = napi_get_reference_value(env, sResultSetConstructor_, &constructor);
    if (status != napi_ok) {
        MediaLibraryNapiUtils::CreateNapiErrorObject(env, asyncContext.error, JS_E_INNER_FAIL,
                                                     "Napi env error: Napi_get_reference_value");
        return nullptr;
    }
    napi_value instance;
    status = napi_new_instance(env, constructor, 0, nullptr, &instance);
    if (status != napi_ok) {
        MediaLibraryNapiUtils::CreateNapiErrorObject(env, asyncContext.error, JS_E_INNER_FAIL,
                                                     "Napi env error: Napi_new_instance");
        return nullptr;
    }
    ResultSetNapi *obj = new ResultSetNapi(resultSet);
    if (obj == nullptr) {
        MediaLibraryNapiUtils::CreateNapiErrorObject(env, asyncContext.error, JS_E_INNER_FAIL,
                                                     "ResultSetnapi create failed");
        return nullptr;
    }
    obj->env_ = env;
    status = napi_wrap(env, instance, obj, ResultSetNapi::ResultSetNapiDestructor, nullptr, nullptr);
    if (status != napi_ok) {
        delete obj;
        MediaLibraryNapiUtils::CreateNapiErrorObject(env, asyncContext.error, JS_E_INNER_FAIL, "Napi env error");
        return nullptr;
    }
    return instance;
}

napi_value ResultSetNapi::JSGetColumnCount(napi_env env, napi_callback_info info)
{
    std::shared_ptr<ResultSet> resultset = GetResultSet(env, info);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    int32_t count = 0;
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset->GetColumnCount(count) == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, count);
}

napi_value ResultSetNapi::JSGetRowCount(napi_env env, napi_callback_info info)
{
    std::shared_ptr<ResultSet> resultset = GetResultSet(env, info);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    int32_t count = 0;
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset->GetRowCount(count) == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, count);
}

napi_value ResultSetNapi::JSGetRowIndex(napi_env env, napi_callback_info info)
{
    std::shared_ptr<ResultSet> resultset = GetResultSet(env, info);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    int32_t index = 0;
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset->GetRowIndex(index) == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, index);
}

napi_value ResultSetNapi::JSIsAtLastRow(napi_env env, napi_callback_info info)
{
    std::shared_ptr<ResultSet> resultset = GetResultSet(env, info);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    bool isAtLast = false;
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset->IsAtLastRow(isAtLast) == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, isAtLast);
}

// 方法实现
napi_value ResultSetNapi::JSGoToRow(napi_env env, napi_callback_info info)
{
    int32_t position;
    int32_t rowCount;
    std::shared_ptr<ResultSet> resultset = GetInt32AndResultSet(env, info, position);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset->GetRowCount(rowCount) == E_OK, JS_E_INNER_FAIL, "Database error");
    int err = resultset->GoToRow(position);
    CHECK_COND_WITH_ERR_MESSAGE(env, err != E_ROW_OUT_RANGE, JS_E_PARAM_INVALID, "Index out of range");
    CHECK_COND_WITH_ERR_MESSAGE(env, err == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, true);
}

napi_value ResultSetNapi::JSGoToFirstRow(napi_env env, napi_callback_info info)
{
    std::shared_ptr<ResultSet> resultset = GetResultSet(env, info);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset->GoToFirstRow() == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, true);
}

napi_value ResultSetNapi::JSGoToNextRow(napi_env env, napi_callback_info info)
{
    std::shared_ptr<ResultSet> resultset = GetResultSet(env, info);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    int err = resultset->GoToNextRow();
    if (err == E_ROW_OUT_RANGE) {
        return Convert2JSValue(env, false);
    }
    CHECK_COND_WITH_ERR_MESSAGE(env, err == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, true);
}

napi_value ResultSetNapi::JSGetBlob(napi_env env, napi_callback_info info)
{
    int32_t columnIndex;
    std::shared_ptr<ResultSet> resultset = GetInt32AndResultSet(env, info, columnIndex);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    std::vector<uint8_t> result;
    int err = resultset->GetBlob(columnIndex, result);
    CHECK_COND_WITH_ERR_MESSAGE(env, err != E_COLUMN_OUT_RANGE, JS_E_PARAM_INVALID, "Column index of out range");
    CHECK_COND_WITH_ERR_MESSAGE(env, err == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, result);
}

napi_value ResultSetNapi::JSGetString(napi_env env, napi_callback_info info)
{
    int32_t columnIndex;
    std::shared_ptr<ResultSet> resultset = GetInt32AndResultSet(env, info, columnIndex);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    std::string result;
    int err = resultset->GetString(columnIndex, result);
    CHECK_COND_WITH_ERR_MESSAGE(env, err != E_COLUMN_OUT_RANGE, JS_E_PARAM_INVALID, "Column index of out range");
    CHECK_COND_WITH_ERR_MESSAGE(env, err == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, result);
}

napi_value ResultSetNapi::JSGetLong(napi_env env, napi_callback_info info)
{
    int32_t columnIndex;
    std::shared_ptr<ResultSet> resultset = GetInt32AndResultSet(env, info, columnIndex);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    int64_t result;
    int err = resultset->GetLong(columnIndex, result);
    CHECK_COND_WITH_ERR_MESSAGE(env, err != E_COLUMN_OUT_RANGE, JS_E_PARAM_INVALID, "Column index of out range");
    CHECK_COND_WITH_ERR_MESSAGE(env, err == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, result);
}

napi_value ResultSetNapi::JSGetDouble(napi_env env, napi_callback_info info)
{
    int32_t columnIndex;
    std::shared_ptr<ResultSet> resultset = GetInt32AndResultSet(env, info, columnIndex);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    double result;
    int err = resultset->GetDouble(columnIndex, result);
    CHECK_COND_WITH_ERR_MESSAGE(env, err != E_COLUMN_OUT_RANGE, JS_E_PARAM_INVALID, "Column index of out range");
    CHECK_COND_WITH_ERR_MESSAGE(env, err == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, result);
}

napi_value ResultSetNapi::JSGetBool(napi_env env, napi_callback_info info)
{
    int32_t columnIndex;
    std::shared_ptr<ResultSet> resultset = GetInt32AndResultSet(env, info, columnIndex);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    ValueObject result;
    int err = resultset->Get(columnIndex, result);
    CHECK_COND_WITH_ERR_MESSAGE(env, err != E_COLUMN_OUT_RANGE, JS_E_PARAM_INVALID, "Column index of out range");
    bool boolResult;
    err = result.GetBool(boolResult);
    CHECK_COND_WITH_ERR_MESSAGE(env, err == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, boolResult);
}

napi_value ResultSetNapi::JSGetValue(napi_env env, napi_callback_info info)
{
    int32_t columnIndex;
    std::shared_ptr<ResultSet> resultset = GetInt32AndResultSet(env, info, columnIndex);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    ValueObject result;
    int err = resultset->Get(columnIndex, result);
    CHECK_COND_WITH_ERR_MESSAGE(env, err != E_COLUMN_OUT_RANGE, JS_E_PARAM_INVALID, "Column index of out range");
    CHECK_COND_WITH_ERR_MESSAGE(env, err == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, result);
}

napi_value ResultSetNapi::JSGetRow(napi_env env, napi_callback_info info)
{
    std::shared_ptr<ResultSet> resultset = GetResultSet(env, info);
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset != nullptr, JS_E_INNER_FAIL, "Resultset is nullptr");
    RowEntity rowEntity;
    CHECK_COND_WITH_ERR_MESSAGE(env, resultset->GetRow(rowEntity) == E_OK, JS_E_INNER_FAIL, "Database error");
    return Convert2JSValue(env, rowEntity);
}

napi_value ResultSetNapi::JSClose(napi_env env, napi_callback_info info)
{
    ResultSetNapi *obj = GetResultSetNapi(env, info);
    if (obj->resultSetPtr != nullptr) {
        obj->resultSetPtr = nullptr;
    } else {
        NAPI_WARN_LOG("Resultset is already closed");
    }
    return nullptr;
}
}  // namespace Media
}  // namespace OHOS
