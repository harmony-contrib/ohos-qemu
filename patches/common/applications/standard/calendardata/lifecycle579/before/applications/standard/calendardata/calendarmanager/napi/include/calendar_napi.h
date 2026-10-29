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

#ifndef CALENDAR_NAPI_H
#define CALENDAR_NAPI_H

#include "napi/native_api.h"
#include "napi/native_common.h"
#include "napi/native_node_api.h"
#include "native_calendar.h"
namespace OHOS::CalendarApi {
class CalendarNapi {
public:
    CalendarNapi() = default;
    ~CalendarNapi() = default;
    static napi_value Init(napi_env env, napi_value exports);
    static napi_value Constructor(napi_env env);

    static napi_value New(napi_env env, napi_callback_info info);
    static napi_status ToJson(napi_env env, napi_value inner, CalendarNapi*& out);

    void SetNative(std::shared_ptr<Native::Calendar>& calendar); // todo fix
    std::shared_ptr<Native::Calendar>& GetNative();

    static napi_value AddEvent(napi_env env, napi_callback_info info);
    static napi_value AddEvents(napi_env env, napi_callback_info info);
    static napi_value DeleteEvent(napi_env env, napi_callback_info info);
    static napi_value DeleteEvents(napi_env env, napi_callback_info info);
    static napi_value UpdateEvent(napi_env env, napi_callback_info info);
    static napi_value UpdateEvents(napi_env env, napi_callback_info info);
    static napi_value GetEvents(napi_env env, napi_callback_info info);
    static napi_value GetConfig(napi_env env, napi_callback_info info);
    static napi_value SetConfig(napi_env env, napi_callback_info info);
    static napi_value GetAccount(napi_env env, napi_callback_info info);
    static napi_value QueryEventInstances(napi_env env, napi_callback_info info);
private:
    std::shared_ptr<Native::Calendar> calendar_ = nullptr;
};


}  // namespace OHOS::CalendarApi
#endif  //  CALENDAR_NAPI_H
