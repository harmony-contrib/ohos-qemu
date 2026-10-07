// Real Linux V4L2 ABI selector boundaries; not a captured-frame or Camera test.
#include <cstdio>
#include <cstring>
#include <string>
#include "../../../patches/common/drivers/peripheral/camera/vivid_capture/files/qemu_v4l2_capture.h"

namespace {
int checks = 0;
int failures = 0;
std::string challenge;
void Check(const char *name, bool pass)
{
    ++checks;
    failures += !pass;
    std::printf("{\"run_id\":\"%s\",\"case\":\"%s\",\"pass\":%s}\n",
        challenge.c_str(), name, pass ? "true" : "false");
}
template<size_t N> void Set(__u8 (&field)[N], const char *value)
{
    std::memset(field, 0, N);
    const auto length = std::strlen(value);
    if (length >= N) std::abort();
    std::memcpy(field, value, length);
}
v4l2_capability Device()
{
    v4l2_capability cap {};
    Set(cap.driver, "vivid");
    Set(cap.card, "vivid");
    Set(cap.bus_info, "platform:vivid-000");
    cap.capabilities = V4L2_CAP_DEVICE_CAPS | V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_VIDEO_OUTPUT | V4L2_CAP_STREAMING;
    cap.device_caps = V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_STREAMING;
    return cap;
}
}

int main(int argc, char **argv)
{
    if (argc != 2 || std::strlen(argv[1]) != 32 || std::strspn(argv[1], "0123456789abcdef") != 32) return 2;
    challenge = argv[1];
    using namespace OHOS::Camera;
#ifdef QEMU_VIVID_CAPTURE_ENABLED
    constexpr bool enabled = true;
#else
    constexpr bool enabled = false;
#endif
    auto original = Device();
    auto cap = original;
    Check("actual_single_planar_capture_node", QemuStreamingCapture(cap));
    Check("explicit_opt_in_only", QemuCaptureDriverMatches(cap, "uvcvideo") == enabled);
    Check("selector_does_not_mutate_kernel_identity", std::memcmp(&cap, &original, sizeof(cap)) == 0);
    for (const auto *unexpected : {"", "vivid", "other", "uvcvideo-extra"}) {
        Check("only_fixed_USB_adapter_request", !QemuCaptureDriverMatches(cap, unexpected));
    }
    for (const auto *driver : {"v4l2loopback", "vivid-extra", "", "other"}) {
        cap = original;
        Set(cap.driver, driver);
        Check("other_driver_rejected", !QemuCaptureDriverMatches(cap, "uvcvideo"));
    }
    for (const auto *card : {"vivid-extra", "", "uvcvideo"}) {
        cap = original;
        Set(cap.card, card);
        Check("other_card_rejected", !QemuCaptureDriverMatches(cap, "uvcvideo"));
    }
    for (const auto *bus : {"platform:vivid-001", "platform:vivid-00", "platform:vivid-000-extra", "usb-000", ""}) {
        cap = original;
        Set(cap.bus_info, bus);
        Check("other_instance_or_bus_rejected", !QemuCaptureDriverMatches(cap, "uvcvideo"));
    }
    cap = original;
    Set(cap.driver, "uvcvideo");
    Set(cap.card, "actual USB webcam");
    Set(cap.bus_info, "usb-0000:00:01.0-1");
    Check("real_USB_camera_preserved", QemuCaptureDriverMatches(cap, "uvcvideo"));
    for (const auto *unexpected : {"vivid", "other", ""}) {
        Check("USB_does_not_bypass_wrong_adapter_request", !QemuCaptureDriverMatches(cap, unexpected));
    }
    for (__u32 bits : {__u32(0), __u32(V4L2_CAP_STREAMING), __u32(V4L2_CAP_VIDEO_CAPTURE),
            __u32(V4L2_CAP_VIDEO_OUTPUT | V4L2_CAP_STREAMING),
            __u32(V4L2_CAP_META_CAPTURE | V4L2_CAP_STREAMING),
            __u32(V4L2_CAP_VIDEO_CAPTURE_MPLANE | V4L2_CAP_STREAMING)}) {
        cap = original;
        cap.device_caps = bits;
        Check("aggregate_caps_cannot_promote_output_meta_or_wrong_buffer_type", !QemuStreamingCapture(cap));
        cap.capabilities = bits;
        cap.device_caps = original.device_caps;
        Check("legacy_caps_still_require_real_capture_and_streaming", !QemuStreamingCapture(cap));
    }
    cap = original;
    cap.capabilities = V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_STREAMING;
    cap.device_caps = 0;
    Check("legacy_real_capture_supported", QemuStreamingCapture(cap));
    for (int field = 0; field != 3; ++field) {
        cap = original;
        if (field == 0) std::memset(cap.driver, 'v', sizeof(cap.driver));
        if (field == 1) std::memset(cap.card, 'v', sizeof(cap.card));
        if (field == 2) std::memset(cap.bus_info, 'v', sizeof(cap.bus_info));
        Check("unterminated_kernel_string_rejected_without_overread", !QemuCaptureDriverMatches(cap, "uvcvideo"));
    }
    std::printf("{\"run_id\":\"%s\",\"case\":\"summary\",\"pass\":%s,\"checks\":%d,"
                "\"failures\":%d,\"vivid_opt_in\":%s,\"scope\":\"real_Linux_ABI_selector_not_frames\"}\n",
        challenge.c_str(), failures ? "false" : "true", checks, failures, enabled ? "true" : "false");
    return failures ? 1 : 0;
}
