#!/usr/bin/env python3
"""Compile and exercise the exact pixel-copy helper added by the ICD patch.

This is host-side layout/boundary coverage, not NativeWindow or QEMU E2E.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/common/web/arkweb/m144_swiftshader/0004-present-vulkan-to-ohos-native-window.patch"


def patched_file(name):
    section = PATCH.read_text().split(f"+++ b/{name}\n", 1)[1].split("diff --git ", 1)[0]
    return "\n".join(line[1:] for line in section.splitlines() if line.startswith("+")) + "\n"


PROGRAM = r'''
#include "OHOSPresentCopy.hpp"
#include <cassert>
#include <cstring>
#include <limits>
int main() {
    const uint8_t source[24] = {1,2,3,4,5,6,7,8,99,99,99,99,
                               11,12,13,14,15,16,17,18,99,99,99,99};
    uint8_t destination[32];
    memset(destination, 0xAC, sizeof(destination));
    assert(vk::CopyBGRA8ToRGBA8(source, 12, destination, 16, 2, 2));
    const uint8_t expected[8] = {3,2,1,4,7,6,5,8};
    const uint8_t second[8] = {13,12,11,14,17,16,15,18};
    assert(memcmp(destination, expected, 8) == 0);
    assert(memcmp(destination + 16, second, 8) == 0);
    for(int i = 8; i < 16; ++i) assert(destination[i] == 0xAC);
    for(int i = 24; i < 32; ++i) assert(destination[i] == 0xAC);
    uint8_t before[32]; memcpy(before, destination, sizeof(before));
    assert(!vk::CopyBGRA8ToRGBA8(nullptr, 12, destination, 16, 2, 2));
    assert(!vk::CopyBGRA8ToRGBA8(source, 12, nullptr, 16, 2, 2));
    assert(!vk::CopyBGRA8ToRGBA8(source, 7, destination, 16, 2, 2));
    assert(!vk::CopyBGRA8ToRGBA8(source, 12, destination, 7, 2, 2));
    assert(!vk::CopyBGRA8ToRGBA8(source, 12, destination, 16, 0, 2));
    assert(!vk::CopyBGRA8ToRGBA8(source, 12, destination, 16, 2, 0));
    assert(!vk::CopyBGRA8ToRGBA8(source, SIZE_MAX, destination, 16, 2, 2));
    assert(!vk::CopyBGRA8ToRGBA8(source, 12, destination, SIZE_MAX, 2, 2));
    assert(memcmp(before, destination, sizeof(before)) == 0);
}
'''


class PresentCopyTests(unittest.TestCase):
    def test_channel_order_padding_and_invalid_layouts(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        self.assertIsNotNone(compiler, "C++ compiler required for bridge boundary tests")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "OHOSPresentCopy.hpp").write_text(patched_file(
                "src/third_party/swiftshader/src/WSI/OHOSPresentCopy.hpp"))
            (root / "test.cpp").write_text(PROGRAM)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", str(root / "test.cpp"),
                            "-o", str(root / "test")], check=True)
            subprocess.run([str(root / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
