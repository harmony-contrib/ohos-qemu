#ifndef CAMERA_FIXTURE_PLATFORM_H
#define CAMERA_FIXTURE_PLATFORM_H
#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
namespace OHOS::Camera {
enum RetCode { RC_OK = 0, RC_ERROR = -1 };
}
#define CAMERA_LOGE(...) ((void)0)
#define CAMERA_LOGV(...) ((void)0)
#define CHECK_IF_PTR_NULL_RETURN_VALUE(p, value) if ((p) == nullptr) { return value; }
#define PR_SET_NAME 15
inline int prctl(int, const char*) { return 0; }
#endif
