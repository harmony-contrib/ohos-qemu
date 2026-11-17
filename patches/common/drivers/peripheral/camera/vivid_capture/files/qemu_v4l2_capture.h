// SPDX-License-Identifier: Apache-2.0
// A real kernel V4L2 capture stream, never synthetic public-API success.
#ifndef QEMU_V4L2_CAPTURE_H
#define QEMU_V4L2_CAPTURE_H
#include <cstring>
#include <linux/videodev2.h>
#include <string>

namespace OHOS::Camera {
template<size_t N>
inline bool QemuBoundedV4l2String(const __u8 (&value)[N], const std::string& expected)
{
    const size_t size = strnlen(reinterpret_cast<const char*>(value), N);
    return size < N && size == expected.size() &&
        memcmp(value, expected.data(), size) == 0;
}

inline bool QemuStreamingCapture(const v4l2_capability& cap)
{
    // A device's aggregate caps may include other output/meta nodes. Use this
    // node's device_caps when provided; the current adapter is single-planar.
    const __u32 caps = (cap.capabilities & V4L2_CAP_DEVICE_CAPS) ? cap.device_caps : cap.capabilities;
    constexpr __u32 required = V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_STREAMING;
    return (caps & required) == required;
}

inline bool QemuCaptureDriverMatches(const v4l2_capability& cap, const std::string& expected)
{
    if (expected != "uvcvideo") {
        return false;
    }
    if (QemuBoundedV4l2String(cap.driver, expected)) {
        return true;
    }
#ifdef QEMU_VIVID_CAPTURE_ENABLED
    // Exactly one QEMU platform instance. Preserve its actual driver/name;
    // never impersonate USB or accept other virtual/output/meta drivers.
    return expected == "uvcvideo" && QemuBoundedV4l2String(cap.driver, "vivid") &&
        QemuBoundedV4l2String(cap.card, "vivid") &&
        QemuBoundedV4l2String(cap.bus_info, "platform:vivid-000");
#else
    return false;
#endif
}
} // namespace OHOS::Camera
#endif
