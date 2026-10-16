/* SPDX-License-Identifier: Apache-2.0 */
#ifndef OHOS_MEDIA_KNOWLEDGE_HOLIDAY_INDEX_H
#define OHOS_MEDIA_KNOWLEDGE_HOLIDAY_INDEX_H
#include <cstdint>
#include <memory>
#include "rdb_store.h"
namespace OHOS::Media {
// Service-only fixed system resource. Not exposed as a path/SQL/write API to HAPs.
class KnowledgeHolidayIndex final {
public:
    static int32_t Refresh(NativeRdb::RdbStore &store);
    static int32_t StopObserver();
    static int32_t Observe(const std::shared_ptr<NativeRdb::RdbStore> &store);
};
}
#endif
