#pragma once
#include "host_prelude.h"
namespace OHOS { namespace Media {
enum MediaServiceErrCode { MSERR_OK=0, MSERR_INVALID_VAL=-10, MSERR_INVALID_OPERATION=-11,
 MSERR_UNSUPPORT_FILE=-12, MSERR_OPEN_FILE_FAILED=-13, MSERR_START_FAILED=-14 };
constexpr int INVALID_FD=-1;
} }
