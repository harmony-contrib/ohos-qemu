#pragma once
#include <cstdint>
// Controlled dependency only. Three positive values are actual clang17-03
// diagnostics (launcher.log:3117-3125); -11 is a synthetic invalid-operation
// symbol for the generic fallback, not a claim about the product enum value.
namespace OHOS { namespace Media {
enum MediaServiceErrCode { MSERR_OK=0, MSERR_INVALID_OPERATION=-11,
    MSERR_OPEN_FILE_FAILED=331350559, MSERR_SERVICE_DIED=331350529,
    MSERR_UNSUPPORT_FILE=331350549 };
} }
