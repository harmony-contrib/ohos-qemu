/*
 * Copyright (C) 2026 OpenHarmony Contributors.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#include "knowledge_content_napi.h"
#include "knowledge_content_query.h"
#include "accesstoken_kit.h"
#include "ipc_skeleton.h"
#include "medialibrary_napi_utils.h"
#include "media_asset_rdbstore.h"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <limits>
#include <memory>
#include <sys/random.h>
namespace OHOS::Media {
namespace {
constexpr int32_t PERMISSION = 201;
constexpr int32_t SYSTEM_APP = 202;
constexpr int32_t PARAMETER = 13900020;
constexpr int32_t SCENARIO = 23800151;
constexpr int32_t INTERNAL = 23800301;
constexpr size_t SUGGESTION_TYPE_COUNT = 7;
const std::vector<int32_t> DEFAULT_FIELDS = {1,2,3,4,5,6,8};
struct Suggestion {
    int32_t type = 0;
    std::string value;
    int32_t count = 0;
};
struct Work {
    napi_async_work work = nullptr;
    napi_deferred deferred = nullptr;
    Knowledge::Query query;
    bool related = false;
    size_t count = 10;
    int32_t error = 0;
    std::string message;
    std::vector<Knowledge::Entity> entities;
    std::vector<Suggestion> suggestions;
};
int32_t AccessError()
{
    // Both checks execute natively against the actual process token/security
    // service, including when the request starts and when it completes.
    if (!MediaLibraryNapiUtils::IsSystemApp()) {
        return SYSTEM_APP;
    }
    using namespace OHOS::Security::AccessToken;
    if (AccessTokenKit::VerifyAccessToken(static_cast<AccessTokenID>(IPCSkeleton::GetSelfTokenID()),
        "ohos.permission.READ_IMAGEVIDEO") != PermissionState::PERMISSION_GRANTED) {
        return PERMISSION;
    }
    return 0;
}
napi_value Error(napi_env env, int32_t code, const std::string &message)
{
    napi_value text = nullptr;
    napi_value error = nullptr;
    napi_value number = nullptr;
    if (napi_create_string_utf8(env, message.c_str(), message.size(), &text) != napi_ok ||
        napi_create_error(env, nullptr, text, &error) != napi_ok ||
        napi_create_int32(env, code, &number) != napi_ok ||
        napi_set_named_property(env, error, "code", number) != napi_ok) {
        return nullptr;
    }
    return error;
}
napi_value Throw(napi_env env, int32_t code, const std::string &message)
{
    napi_value error = Error(env, code, message);
    if (error != nullptr) {
        napi_throw(env, error);
    }
    return nullptr;
}
bool Number(napi_env env, napi_value value, int32_t &result)
{
    napi_valuetype type;
    double number = 0;
    if (napi_typeof(env, value, &type) != napi_ok || type != napi_number ||
        napi_get_value_double(env, value, &number) != napi_ok || !std::isfinite(number) ||
        std::trunc(number) != number || number < std::numeric_limits<int32_t>::min() ||
        number > std::numeric_limits<int32_t>::max()) {
        return false;
    }
    result = static_cast<int32_t>(number);
    return true;
}
bool String(napi_env env, napi_value value, std::string &result)
{
    napi_valuetype type;
    size_t size = 0;
    if (napi_typeof(env, value, &type) != napi_ok || type != napi_string ||
        napi_get_value_string_utf8(env, value, nullptr, 0, &size) != napi_ok) {
        return false;
    }
    std::vector<char> bytes(size + 1);
    size_t read = 0;
    if (napi_get_value_string_utf8(env, value, bytes.data(), bytes.size(), &read) != napi_ok || read != size) {
        return false;
    }
    result.assign(bytes.data(), size);
    return true;
}
bool IntegerArray(napi_env env, napi_value value, std::vector<int32_t> &result, bool suggestions)
{
    bool array = false;
    uint32_t length = 0;
    if (napi_is_array(env, value, &array) != napi_ok || !array ||
        napi_get_array_length(env, value, &length) != napi_ok || length == 0 ||
        (suggestions && length > SUGGESTION_TYPE_COUNT)) {
        return false;
    }
    for (uint32_t i = 0; i < length; ++i) {
        napi_value element = nullptr;
        int32_t field = 0;
        if (napi_get_element(env, value, i, &element) != napi_ok || !Number(env, element, field) ||
            (suggestions ? (field < 0 || field > 6) : !Knowledge::IsField(field))) {
            return false;
        }
        if (std::find(result.begin(), result.end(), field) == result.end()) {
            result.push_back(field);
        }
    }
    return true;
}
bool Object(napi_env env, napi_value value)
{
    napi_valuetype type;
    bool array = false;
    napi_value nullValue = nullptr;
    bool isNull = false;
    return napi_typeof(env, value, &type) == napi_ok && type == napi_object &&
        napi_is_array(env, value, &array) == napi_ok && !array &&
        napi_get_null(env, &nullValue) == napi_ok &&
        napi_strict_equals(env, value, nullValue, &isNull) == napi_ok && !isNull;
}
bool FieldProperty(napi_env env, napi_value object, const char *key, std::vector<int32_t> &fields)
{
    napi_value value = nullptr;
    return napi_get_named_property(env, object, key, &value) == napi_ok && IntegerArray(env, value, fields, false);
}
bool SetString(napi_env env, napi_value object, const char *name, const std::string &value)
{
    napi_value result = nullptr;
    return napi_create_string_utf8(env, value.c_str(), value.size(), &result) == napi_ok &&
        napi_set_named_property(env, object, name, result) == napi_ok;
}
bool SetNumber(napi_env env, napi_value object, const char *name, int32_t value)
{
    napi_value result = nullptr;
    return napi_create_int32(env, value, &result) == napi_ok &&
        napi_set_named_property(env, object, name, result) == napi_ok;
}
void ReadEntities(const std::shared_ptr<NativeRdb::ResultSet> &result, int rows, Work &work)
{
    for (int i = 0; i < rows; ++i) {
        Knowledge::Entity entity;
        std::string alias;
        if (result->GoToNextRow() != NativeRdb::E_OK || result->GetInt(0, entity.field) != NativeRdb::E_OK ||
            result->GetString(1, entity.id) != NativeRdb::E_OK || result->GetString(2, entity.name) != NativeRdb::E_OK ||
            result->GetString(3, alias) != NativeRdb::E_OK || result->GetLong(4, entity.votes) != NativeRdb::E_OK ||
            entity.id.empty() || entity.name.empty() || entity.votes <= 0 || !Knowledge::HasProducer(entity.field)) {
            work.error = INTERNAL;
            return;
        }
        if (work.entities.empty() || work.entities.back().field != entity.field ||
            work.entities.back().id != entity.id || work.entities.back().name != entity.name) {
            work.entities.push_back(std::move(entity));
        }
        auto &existing = work.entities.back();
        if (!alias.empty() && std::find(existing.aliases.begin(), existing.aliases.end(), alias) == existing.aliases.end()) {
            existing.aliases.push_back(alias);
        }
    }
}
void ReadSuggestions(const std::shared_ptr<NativeRdb::ResultSet> &result, int rows, Work &work)
{
    for (int i = 0; i < rows; ++i) {
        Suggestion suggestion;
        int64_t count = 0;
        if (result->GoToNextRow() != NativeRdb::E_OK || result->GetInt(0, suggestion.type) != NativeRdb::E_OK ||
            result->GetString(1, suggestion.value) != NativeRdb::E_OK || result->GetLong(2, count) != NativeRdb::E_OK ||
            suggestion.type < 0 || suggestion.type > 6 || suggestion.value.empty() || count <= 0 ||
            count > std::numeric_limits<int32_t>::max()) {
            work.error = INTERNAL;
            return;
        }
        suggestion.count = static_cast<int32_t>(count);
        work.suggestions.push_back(std::move(suggestion));
    }
}
void Execute(napi_env, void *data)
{
    auto &work = *static_cast<Work *>(data);
    work.error = AccessError();
    if (work.error != 0) {
        return;
    }
    std::vector<NativeRdb::ValueObject> args;
    for (const auto &argument : work.query.args) {
        if (std::holds_alternative<int64_t>(argument)) {
            args.emplace_back(std::get<int64_t>(argument));
        } else {
            args.emplace_back(std::get<std::string>(argument));
        }
    }
    auto result = MediaAssetRdbStore::GetInstance()->QueryByStep(work.query.sql, args);
    int rows = 0;
    if (result == nullptr || result->GetRowCount(rows) != NativeRdb::E_OK || rows < 0) {
        if (result != nullptr) {
            result->Close();
        }
        work.error = INTERNAL;
        work.message = "Knowledge database query unavailable";
        return;
    }
    if (work.related) {
        ReadEntities(result, rows, work);
    } else {
        ReadSuggestions(result, rows, work);
    }
    result->Close();
    if (work.error == 0 && work.related) {
        if (work.entities.empty() || work.count == 0) {
            work.entities.clear();
            return;
        }
        uint64_t seed = 0;
        size_t received = 0;
        while (received < sizeof(seed)) {
            const ssize_t bytes = getrandom(reinterpret_cast<char *>(&seed) + received, sizeof(seed) - received, 0);
            if (bytes < 0 && errno == EINTR) {
                continue;
            }
            if (bytes <= 0) {
                work.error = INTERNAL;
                return;
            }
            received += static_cast<size_t>(bytes);
        }
        std::mt19937_64 random(seed);
        work.entities = Knowledge::RandomVote(std::move(work.entities), work.count, random);
    }
}
napi_value BuildResult(napi_env env, const Work &work)
{
    napi_value output = nullptr;
    const size_t size = work.related ? work.entities.size() : work.suggestions.size();
    if (napi_create_array_with_length(env, size, &output) != napi_ok) {
        return nullptr;
    }
    for (size_t i = 0; i < size; ++i) {
        napi_value object = nullptr;
        if (napi_create_object(env, &object) != napi_ok) {
            return nullptr;
        }
        if (work.related) {
            const auto &entity = work.entities[i];
            napi_value aliases = nullptr;
            if (!SetString(env, object, "id", entity.id) || !SetString(env, object, "name", entity.name) ||
                !SetNumber(env, object, "field", entity.field) ||
                napi_create_array_with_length(env, entity.aliases.size(), &aliases) != napi_ok) {
                return nullptr;
            }
            for (size_t j = 0; j < entity.aliases.size(); ++j) {
                napi_value alias = nullptr;
                if (napi_create_string_utf8(env, entity.aliases[j].c_str(), entity.aliases[j].size(), &alias) != napi_ok ||
                    napi_set_element(env, aliases, j, alias) != napi_ok) {
                    return nullptr;
                }
            }
            if (napi_set_named_property(env, object, "alias", aliases) != napi_ok) {
                return nullptr;
            }
        } else {
            const auto &suggestion = work.suggestions[i];
            if (!SetNumber(env, object, "type", suggestion.type) || !SetString(env, object, "value", suggestion.value) ||
                !SetNumber(env, object, "count", suggestion.count)) {
                return nullptr;
            }
        }
        if (napi_set_element(env, output, i, object) != napi_ok) {
            return nullptr;
        }
    }
    return output;
}
void Complete(napi_env env, napi_status status, void *data)
{
    std::unique_ptr<Work> work(static_cast<Work *>(data));
    const int32_t access = AccessError();
    if (access != 0) {
        work->error = access;
    } else if (status != napi_ok) {
        work->error = INTERNAL;
    }
    napi_value result = work->error == 0 ? BuildResult(env, *work) : nullptr;
    if (result != nullptr) {
        napi_resolve_deferred(env, work->deferred, result);
    } else {
        bool pending = false;
        napi_value error = nullptr;
        if (napi_is_exception_pending(env, &pending) == napi_ok && pending) {
            napi_get_and_clear_last_exception(env, &error);
        } else {
            error = Error(env, work->error == 0 ? INTERNAL : work->error,
                work->message.empty() ? "Knowledge content request failed" : work->message);
        }
        if (error != nullptr) {
            napi_reject_deferred(env, work->deferred, error);
        }
    }
    napi_delete_async_work(env, work->work);
}
napi_value Schedule(napi_env env, std::unique_ptr<Work> work)
{
    napi_value promise = nullptr;
    napi_value name = nullptr;
    if (napi_create_promise(env, &work->deferred, &promise) != napi_ok ||
        napi_create_string_utf8(env, "KnowledgeContent", NAPI_AUTO_LENGTH, &name) != napi_ok ||
        napi_create_async_work(env, nullptr, name, Execute, Complete, work.get(), &work->work) != napi_ok) {
        return Throw(env, INTERNAL, "Cannot create knowledge request");
    }
    if (napi_queue_async_work(env, work->work) != napi_ok) {
        napi_delete_async_work(env, work->work);
        return Throw(env, INTERNAL, "Cannot queue knowledge request");
    }
    work.release();
    return promise;
}
} // namespace
napi_value KnowledgeContentNapi::Constructor(napi_env env, napi_callback_info info)
{
    napi_value self = nullptr;
    size_t argc = 0;
    if (napi_get_cb_info(env, info, &argc, nullptr, &self, nullptr) != napi_ok) {
        return nullptr;
    }
    return self;
}
napi_value KnowledgeContentNapi::GetRelatedEntity(napi_env env, napi_callback_info info)
{
    const int32_t access = AccessError();
    if (access != 0) {
        return Throw(env, access, "System application and READ_IMAGEVIDEO required");
    }
    napi_value argv[4] = {};
    size_t argc = 4;
    std::string topic;
    std::vector<int32_t> topicFields;
    std::vector<int32_t> suggestionFields = DEFAULT_FIELDS;
    auto work = std::make_unique<Work>();
    work->related = true;
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc < 2 || argc > 3 ||
        !String(env, argv[0], topic) || topic.empty() || !Object(env, argv[1]) ||
        !FieldProperty(env, argv[1], "topicField", topicFields)) {
        return Throw(env, PARAMETER, "Invalid related entity parameters");
    }
    if (argc == 3) {
        napi_valuetype type;
        if (napi_typeof(env, argv[2], &type) != napi_ok) {
            return nullptr;
        }
        if (type != napi_undefined) {
            if (!Object(env, argv[2])) {
                return Throw(env, PARAMETER, "Invalid related entity options");
            }
            bool has = false;
            napi_value value = nullptr;
            int32_t number = 0;
            for (const char *key : {"rankingMethod", "recommendationCount", "suggestionFields"}) {
                if (napi_has_named_property(env, argv[2], key, &has) != napi_ok) {
                    return nullptr;
                }
                if (!has) {
                    continue;
                }
                if (napi_get_named_property(env, argv[2], key, &value) != napi_ok) {
                    return nullptr;
                }
                napi_valuetype valueType;
                if (napi_typeof(env, value, &valueType) != napi_ok) {
                    return nullptr;
                }
                if (valueType == napi_undefined) {
                    continue;
                }
                if (std::string(key) == "suggestionFields") {
                    suggestionFields.clear();
                    if (!IntegerArray(env, value, suggestionFields, false)) {
                        return Throw(env, PARAMETER, "Invalid suggestion fields");
                    }
                } else if (!Number(env, value, number) ||
                    (std::string(key) == "rankingMethod" ? number != 0 : number < 0)) {
                    return Throw(env, PARAMETER, "Invalid ranking or recommendation count");
                } else if (std::string(key) == "recommendationCount") {
                    work->count = static_cast<size_t>(number);
                }
            }
        }
    }
    if (std::any_of(topicFields.begin(), topicFields.end(), [](int32_t field) {return !Knowledge::HasProducer(field);}) ||
        std::any_of(suggestionFields.begin(), suggestionFields.end(), [](int32_t field) {return !Knowledge::HasProducer(field);})) {
        return Throw(env, INTERNAL, "Requested knowledge field has no indexed producer");
    }
    work->query = Knowledge::Related(topic, topicFields, suggestionFields);
    return Schedule(env, std::move(work));
}
napi_value KnowledgeContentNapi::GetSearchSuggestion(napi_env env, napi_callback_info info)
{
    const int32_t access = AccessError();
    if (access != 0) {
        return Throw(env, access, "System application and READ_IMAGEVIDEO required");
    }
    napi_value argv[2] = {};
    size_t argc = 2;
    std::vector<int32_t> types;
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 1 ||
        !IntegerArray(env, argv[0], types, true)) {
        return Throw(env, SCENARIO, "Search suggestion types must contain 1 to 7 valid entries");
    }
    auto work = std::make_unique<Work>();
    work->query = Knowledge::Suggestions(types);
    return Schedule(env, std::move(work));
}
napi_value KnowledgeContentNapi::Init(napi_env env, napi_value exports)
{
    const napi_property_descriptor methods[] = {
        {"getRelatedEntity", nullptr, GetRelatedEntity, nullptr, nullptr, nullptr, napi_static, nullptr},
        {"getSearchSuggestion", nullptr, GetSearchSuggestion, nullptr, nullptr, nullptr, napi_static, nullptr},
    };
    napi_value constructor = nullptr;
    if (napi_define_class(env, "KnowledgeContent", NAPI_AUTO_LENGTH, Constructor, nullptr,
        sizeof(methods) / sizeof(methods[0]), methods, &constructor) != napi_ok ||
        napi_set_named_property(env, exports, "KnowledgeContent", constructor) != napi_ok) {
        return nullptr;
    }
    return exports;
}
} // namespace OHOS::Media
