#ifndef CAMERA_FIXTURE_STREAM_H
#define CAMERA_FIXTURE_STREAM_H
#include "camera.h"
namespace OHOS::Camera {
enum CameraBufferStatus { CAMERA_BUFFER_STATUS_OK, CAMERA_BUFFER_STATUS_DROP, CAMERA_BUFFER_STATUS_INVALID };
class IBuffer {
public:
    CameraBufferStatus status = CAMERA_BUFFER_STATUS_OK;
    CameraBufferStatus GetBufferStatus() { return status; }
    void SetBufferStatus(CameraBufferStatus value) { status = value; }
    int GetIndex() { return 0; }
    int GetStreamId() { return 11; }
};
}
#endif
