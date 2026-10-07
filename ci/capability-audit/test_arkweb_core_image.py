import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_arkweb_core_image import ARCHES, REQUIRED_LIBRARIES, REQUIRED_RESOURCES, verify_hap


class ArkWebCoreImageTests(unittest.TestCase):
    def hap(self, path, arch="arm64", omit=None, actual=None):
        abi, elf_class, machine = ARCHES[actual or arch]
        header = bytearray(64)
        header[:7] = b"\x7fELF" + bytes((elf_class, 1, 1))
        struct.pack_into("<HH", header, 16, 3, machine)
        intended_abi = ARCHES[arch][0]
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("module.json", json.dumps({"app": {"bundleName": "com.ohos.arkwebcore"}}))
            for name in REQUIRED_RESOURCES:
                archive.writestr(name, b"fixture only")
            for name in REQUIRED_LIBRARIES - {omit}:
                archive.writestr("libs/" + intended_abi + "/" + name, header)

    def test_each_architecture_checks_actual_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            for arch in ARCHES:
                path = Path(directory) / (arch + ".hap")
                self.hap(path, arch)
                self.assertEqual(verify_hap(path, arch)["abi"], ARCHES[arch][0])

    def test_arm64_only_hap_is_not_x64_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "core.hap"
            self.hap(path)
            with self.assertRaisesRegex(ValueError, "incomplete for x86_64"):
                verify_hap(path, "x86_64")

    def test_relabeling_library_directory_does_not_fix_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "core.hap"
            self.hap(path, "x86_64", actual="arm64")
            with self.assertRaisesRegex(ValueError, "wrong actual ELF ABI"):
                verify_hap(path, "x86_64")

    def test_partial_engine_is_not_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "core.hap"
            self.hap(path, omit="libffmpeg.so")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                verify_hap(path, "arm64")

    def test_packager_requires_full_hap_not_v8_alone(self):
        packager = (ROOT / "scripts/package_standard_qemu.sh").read_text()
        self.assertIn('python3 "${SCRIPT_DIR}/verify_arkweb_core_image.py"', packager)
        self.assertIn('--output "${PACKAGE_DIR}/arkweb-core-evidence.json"', packager)


if __name__ == "__main__":
    unittest.main()
