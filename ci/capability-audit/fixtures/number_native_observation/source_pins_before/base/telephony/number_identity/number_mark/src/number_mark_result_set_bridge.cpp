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

#include "number_mark_result_set_bridge.h"
#include "number_identity_datashare_transform.h"
#include "number_identity_models.h"
#include "number_identity_result_set_bridge_template.h"
#include "number_identity_utils.h"

#include "rdb_errno.h"

#include <algorithm>
#include <cstdint>
#include <string>
#include <variant>
#include <vector>

namespace OHOS {
namespace Telephony {
using namespace std;

vector<NumberMarkResultSetBridge::ColumnDefinition> g_markInfoColumns = {
    { .name = NumberMarkInfoFields::markType,
        .write =
            [](Writer &writer, const NumberMarkInfo &markInfo, uint32_t columnIndex) {
                return WriteInt64(writer, columnIndex, static_cast<int64_t>(markInfo.markType));
            } },
    { .name = NumberMarkInfoFields::markContent,
        .write = [](Writer &writer, const NumberMarkInfo &markInfo,
                     uint32_t columnIndex) { return WriteOptionalString(writer, columnIndex, markInfo.markContent); } },
    { .name = NumberMarkInfoFields::markCount,
        .write = [](Writer &writer, const NumberMarkInfo &markInfo,
                     uint32_t columnIndex) { return WriteOptionalInt64(writer, columnIndex, markInfo.markCount); } },
    { .name = NumberMarkInfoFields::markSource,
        .write = [](Writer &writer, const NumberMarkInfo &markInfo,
                     uint32_t columnIndex) { return WriteOptionalString(writer, columnIndex, markInfo.markSource); } },
    { .name = NumberMarkInfoFields::isCloud,
        .write = [](Writer &writer, const NumberMarkInfo &markInfo,
                     uint32_t columnIndex) { return WriteOptionalInt64(writer, columnIndex, markInfo.isCloud); } },
    { .name = NumberMarkInfoFields::markDetails,
        .write = [](Writer &writer, const NumberMarkInfo &markInfo,
                     uint32_t columnIndex) { return WriteOptionalString(writer, columnIndex, markInfo.markDetails); } },
};

NumberMarkResultSetBridge::NumberMarkResultSetBridge(const vector<NumberMarkInfo> &data)
    : NumberIdentityResultSetBridge<NumberMarkInfo>(data)
{
    NUMBER_IDENTITY_LOGI("creat NumberMarkResultSetBridge");
    this->columns = g_markInfoColumns;
}

NativeDataResultSetBridge::NativeDataResultSetBridge(const NativeDataSet &dataSet)
    : NumberIdentityResultSetBridge<NativeRecord>(dataSet.records)
{
    DefineColumns(dataSet.columnNames);
    NUMBER_IDENTITY_LOGI("NativeDataResultSetBridge done");
}

NumberIdentityResultSetBridge<vector<NativeData>>::WriteFunc g_writeNativeData =
    [](Writer &writer, const vector<NativeData> &record, uint32_t columnIndex) -> int {
    if (columnIndex >= record.size()) {
        NUMBER_IDENTITY_LOGE("%{public}u >= %{public}lu skipped", columnIndex, record.size());
        return NativeRdb::E_OK;
    }
    const NativeData *cell = &record[columnIndex];
    if (auto ptr = std::get_if<int64_t>(cell); ptr != nullptr) {
        return WriteInt64(writer, columnIndex, *ptr);
    }
    if (auto ptr = std::get_if<double_t>(cell); ptr != nullptr) {
        return WriteDouble64(writer, columnIndex, *ptr);
    }
    if (auto ptr = std::get_if<string>(cell); ptr != nullptr) {
        return WriteString(writer, columnIndex, *ptr);
    }
    if (auto ptr = std::get_if<vector<uint8_t>>(cell); ptr != nullptr) {
        return WriteBlob(writer, columnIndex, *ptr);
    }
    return NativeRdb::E_OK;
};
void NativeDataResultSetBridge::DefineColumns(const vector<string> &dynamicColumns)
{
    MapVector<string, ColumnDefinition>(dynamicColumns, this->columns,
        [](const string &name) -> ColumnDefinition { return { .name = name, .write = g_writeNativeData }; });
}

} // namespace Telephony
} // namespace OHOS