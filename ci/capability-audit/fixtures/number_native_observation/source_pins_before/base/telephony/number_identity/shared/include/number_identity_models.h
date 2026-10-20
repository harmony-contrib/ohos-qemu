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

#ifndef NUMBER_IDENTITY_MODELS_H
#define NUMBER_IDENTITY_MODELS_H

#include "datashare_predicates.h"
#include "datashare_values_bucket.h"
#include "result_set.h"
#include <cstdint>
#include <optional>
#include <stdint.h>
#include <string>

namespace OHOS {
namespace Telephony {
using DataShare::DataSharePredicates;
using DataShare::DataShareValuesBucket;
using NativeRdb::ResultSet;
using std::nullopt;
using std::optional;
using std::string;

/** Indicates the type of the number mark. */
enum class MarkType {
    /** Indicates the mark is none. */
    MARK_TYPE_NONE = 0,
    /** Indicates the mark is crank. */
    MARK_TYPE_CRANK = 1,
    /** Indicates the mark is fraud. */
    MARK_TYPE_FRAUD = 2,
    /** Indicates the mark is express. */
    MARK_TYPE_EXPRESS = 3,
    /** Indicates the mark is promote sales. */
    MARK_TYPE_PROMOTE_SALES = 4,
    /** Indicates the mark is house agent. */
    MARK_TYPE_HOUSE_AGENT = 5,
    /** Indicates the mark is insurance. */
    MARK_TYPE_INSURANCE = 6,
    /** Indicates the mark is taxi. */
    MARK_TYPE_TAXI = 7,
    /** Indicates the mark is custom. */
    MARK_TYPE_CUSTOM = 8,
    /** Indicates the mark is others. */
    MARK_TYPE_OTHERS = 9,
    /** Indicates the mark is yellow page. */
    MARK_TYPE_YELLOW_PAGE = 10,
    /** Indicates the mark is enterprise. */
    MARK_TYPE_ENTERPRISE = 11,
};

/**
 * @brief Indicates the cause when the call is answered.
 */
enum class CallAnswerType {
    /**
     * Indicates the call answer is call missed.
     */
    CALL_ANSWER_MISSED = 0,
    /**
     * Indicates the call answer is call active.
     */
    CALL_ANSWER_ACTIVED,
    /**
     * Indicates the call answer is call rejected.
     */
    CALL_ANSWER_REJECT,
    /**
     * Indicates the call answer is call blocked.
     */
    CALL_ANSWER_BLOCKED = 6,
};

template <typename T> inline bool GetMarkType(T v, MarkType &markType)
{
    if (static_cast<T>(MarkType::MARK_TYPE_NONE) <= v && v <= static_cast<T>(MarkType::MARK_TYPE_YELLOW_PAGE)) {
        markType = static_cast<MarkType>(v);
        return true;
    }
    markType = MarkType::MARK_TYPE_NONE;
    return false;
}

/**
 * Only used fields are defined.
 */
class YellowPageViewModel {
  public:
    int64_t id = 0;
    optional<string> photo = nullopt;
    optional<string> name = nullopt;
    optional<string> number = nullopt;
    int CreateFromResultSet(ResultSet &resultSet);
};

class NumberMarkModel {
  public:
    int64_t id = 0;
    string number = "";
    optional<string> name = nullopt;
    string classify = "";
    optional<int64_t> marked_count = nullopt;
    int64_t is_cloud = 0;
    optional<string> description = nullopt;
    string save_timestamp = "";
    optional<string> supplier = nullopt;
    optional<string> supplier_id = nullopt;
    int64_t is_intelligent_db = 0;
    int CreateFromResultSet(ResultSet &resultSet);
    MarkType MarkType() const;
    DataShareValuesBucket ToDataShareValuesBucket() const;
    DataSharePredicates ToIdentityDataSharePredicates() const;
};

MarkType GetMarkType(const string &text);

string GetClassify(MarkType markType);

class NumberMarkInfo {
  public:
    MarkType markType = MarkType::MARK_TYPE_NONE;
    optional<string> markContent = nullopt;
    optional<int64_t> markCount = nullopt;
    optional<string> markSource = nullopt;
    optional<bool> isCloud = nullopt;
    optional<string> markDetails = nullopt;
    void FromYellowPage(const YellowPageViewModel &yellowPage);
    void FromNumberMark(const NumberMarkModel &numberMark);
};

class NumberMarkInfoFields {
  public:
    static constexpr const char *markType = "markType";
    static constexpr const char *markContent = "markContent";
    static constexpr const char *markCount = "markCount";
    static constexpr const char *markSource = "markSource";
    static constexpr const char *isCloud = "isCloud";
    static constexpr const char *markDetails = "markDetails";
};

class SetNumberMarkParamsFields {
  public:
    static constexpr const char *markType = "markType";
    static constexpr const char *phoneNumber = "phoneNumber";
    static constexpr const char *customMarkContent = "customMarkContent";
};

} // namespace Telephony
} // namespace OHOS

#endif /* NUMBER_IDENTITY_MODELS_H */