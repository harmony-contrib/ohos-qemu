#!/usr/bin/env python3
import unittest
from PIL import Image
from verify_vulkan_window import verify_lifecycle, verify_pixels


def line(event, generation, destroyed):
    return f"vulkan_window.{event}|frames=5 width=16 height=14 cleaned=1 destroyed={destroyed} generation={generation}"


GOOD = "\n".join((line("present", 1, 0), line("destroyed", 1, 1), line("present", 2, 0)))


class VulkanWindowTests(unittest.TestCase):
    def test_exact_lifecycle(self):
        self.assertEqual(len(verify_lifecycle(GOOD)), 3)

    def test_timeout_stale_missing_cleanup_or_destroy_fails(self):
        for text in ("", GOOD + "\n" + GOOD, GOOD + "\nvulkan_window.timeout|timeout", GOOD.replace("cleaned=1", "cleaned=0"),
                     "\n".join((line("present", 1, 0), line("present", 2, 0))), GOOD.replace("generation=2", "generation=1")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                verify_lifecycle(text)

    def test_full_interior_pixels(self):
        image = Image.new("RGBA", (30, 30), (51, 102, 153, 255))
        self.assertEqual(verify_pixels(image, (2, 3, 16, 14), {"width": 16, "height": 14}), 24)
        image.putpixel((8, 9), (0, 0, 0, 255))
        with self.assertRaises(ValueError):
            verify_pixels(image, (2, 3, 16, 14), {"width": 16, "height": 14})

    def test_wrong_rect_empty_or_offscreen_fails(self):
        image = Image.new("RGB", (30, 30), (51, 102, 153))
        for rectangle in ((-1, 0, 16, 14), (0, 0, 15, 14), (20, 20, 16, 14), (0, 0, 0, 0)):
            with self.subTest(rectangle=rectangle), self.assertRaises(ValueError):
                verify_pixels(image, rectangle, {"width": 16, "height": 14})


if __name__ == "__main__":
    unittest.main()
