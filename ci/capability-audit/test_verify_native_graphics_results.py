import json
import unittest
from verify_native_graphics_results import verify


class NativeGraphicsResultsTests(unittest.TestCase):
    def test_real_queue_readback_and_narrow_headless_scope(self):
        log = ("loader_api=1.3.0\ninstance=ok\nphysical_devices=1 name=SwiftShader Device api=1.3.0\n"
               "logical_device=ok compute_queue_family=0\nmapped_buffer=ok byte=5a size=4096\n"
               "device_fill=ok words=1024 pattern=12345678\n")
        self.assertEqual(verify("vulkan-device", log, 0)["verified_words"], 1024)
        self.assertFalse(verify("vulkan-headless", "headless_surface=ok queue_family=0 swapchain_images=1\n", 0)["compositor_tested"])
        for changed in (log.replace("device_fill=ok", "device_fill=fail"), log.rsplit("device_fill", 1)[0],
                        log + log, log.replace("physical_devices=1", "physical_devices=0")):
            with self.assertRaises(ValueError):
                verify("vulkan-device", changed, 0)
        with self.assertRaises(ValueError):
            verify("vulkan-device", log, 1)

    def test_native_window_exact_typed_frame_pixel_and_resize_contract(self):
        row = {"scope": "OHOS NativeWindow buffer-queue WSI (not compositor)", "presented_frames": 10,
               "verified_rgba_pixels": 1500, "resize_out_of_date": True, "pass": True}
        self.assertFalse(verify("vulkan-ohos-surface", json.dumps(row), 0)["compositor_tested"])
        for key, value in (("presented_frames", 1), ("verified_rgba_pixels", 0),
                           ("resize_out_of_date", False), ("pass", 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify("vulkan-ohos-surface", json.dumps({**row, key: value}), 0)

    def test_native_gles_requires_both_contexts_and_pixels_not_webgl_claim(self):
        log = "".join(f"gles{version}.egl_get_display=1 initialize=1 error=0x3000 version=1.5\n"
                      f"gles{version}.choose=1 count=1 error=0x3000\n"
                      f"gles{version}.surface=1 context=1 current=1 error=0x3000 vendor=Mesa renderer=llvmpipe gl_version=ES 3.0\n"
                      f"gles{version}.readback=51,102,153,255 gl_error=0x0 pass=1\n" for version in (2, 3))
        self.assertFalse(verify("gles", log, 0)["webgl_tested"])
        for changed in (log.replace("gles3.readback=51", "gles3.readback=0"),
                        log.replace("context=1", "context=0"), log + "extra\n"):
            with self.assertRaises(ValueError):
                verify("gles", changed, 0)


if __name__ == "__main__":
    unittest.main()
