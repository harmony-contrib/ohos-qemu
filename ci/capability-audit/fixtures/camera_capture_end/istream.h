#ifndef CAMERA_FIXTURE_ISTREAM_H
#define CAMERA_FIXTURE_ISTREAM_H
#include "camera.h"
namespace OHOS::Camera {
class CaptureRequest;
class IStream {
public:
    virtual ~IStream() = default;
    virtual int32_t GetStreamId() const = 0;
    virtual RetCode Capture(const std::shared_ptr<CaptureRequest>&) = 0;
    virtual RetCode OnFrame(const std::shared_ptr<CaptureRequest>&) = 0;
    virtual RetCode CancelRequest(const std::shared_ptr<CaptureRequest>&) = 0;
};
}
#endif
