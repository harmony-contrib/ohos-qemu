#ifndef CAMERA_FIXTURE_STREAM_H
#define CAMERA_FIXTURE_STREAM_H
#include "camera.h"
namespace OHOS::Camera {
enum CameraBufferStatus { CAMERA_BUFFER_STATUS_OK, CAMERA_BUFFER_STATUS_DROP, CAMERA_BUFFER_STATUS_INVALID };
class IBuffer {
public:
    CameraBufferStatus status = CAMERA_BUFFER_STATUS_OK;
    int captureId = -1;
    int streamId = 11;
    CameraBufferStatus GetBufferStatus() { return status; }
    void SetBufferStatus(CameraBufferStatus value) { status = value; }
    int GetIndex() { return 0; }
    int GetStreamId() { return streamId; }
    void SetStreamId(int value) { streamId = value; }
    int GetCaptureId() { return captureId; }
    void SetCaptureId(int value) { captureId = value; }
    void SetEncodeType(int) {}
    int GetSize() { return 320 * 180; }
};
}
#endif
