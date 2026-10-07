"""Platform patch regression, not proof of ARM32 JIT/WSI runtime behavior."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/common/web/arkweb/m144_swiftshader/0005-configure-subzero-posix-headers-on-ohos.patch"
FIXTURE = '''if (supports_subzero) {
    if (is_win) {
      include_dirs +=
          [ "../../third_party/llvm-subzero/build/Windows/include/" ]
    } else if (is_linux || is_chromeos) {
      include_dirs += [ "../../third_party/llvm-subzero/build/Linux/include/" ]
    } else if (is_fuchsia) {
      include_dirs +=
          [ "../../third_party/llvm-subzero/build/Fuchsia/include/" ]
    }

    if (is_win) {
      if (is_clang) {
        if (is_debug) {
          cflags += [ "-Wno-sign-compare" ]
        }
      }
    } else if (is_linux || is_chromeos || is_mac || is_fuchsia) {
      cflags += [ "-Wno-macro-redefined" ]
    }

}
'''


class SubzeroPlatformTests(unittest.TestCase):
    def test_actual_patch_supplies_posix_config_without_disabling_arm32_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "src/third_party/swiftshader/src/Reactor/BUILD.gn"
            path.parent.mkdir(parents=True)
            path.write_text(FIXTURE)
            subprocess.run(["git", "apply", str(PATCH)], cwd=root, check=True, capture_output=True)
            text = path.read_text()
            self.assertIn("is_linux || is_chromeos || is_ohos", text)
            self.assertIn("is_linux || is_chromeos || is_mac || is_fuchsia || is_ohos", text)
            self.assertIn("llvm-subzero/build/Linux/include/", text)
            self.assertIn("if (supports_subzero)", text)
            self.assertNotIn("supports_subzero = false", text)
            subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)], cwd=root,
                           check=True, capture_output=True)
            subprocess.run(["git", "apply", "--reverse", str(PATCH)], cwd=root, check=True, capture_output=True)
            self.assertEqual(path.read_text(), FIXTURE)


if __name__ == "__main__":
    unittest.main()
