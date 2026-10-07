"""Synthetic ELF plumbing/unit checks, not linked-component/guest evidence."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_runtime_elf_contract import ElfInfo
from verify_shared_fence_owner import ARCHES, GLOBAL, NATIVE_APIS, needed_libraries, verify_pair, verify_pixelmap
from test_access_token_kernel import write_preimages
import subprocess


def dynamic_fixture(path, arch, needed):
    elf_class, machine = ARCHES[arch]
    data = bytearray(64)
    data[:7] = b"\x7fELF" + bytes((elf_class, 1, 1))
    struct.pack_into("<HH", data, 16, 3, machine)
    strings = bytearray(b"\0")
    offsets = []
    for name in needed:
        offsets.append(len(strings))
        strings.extend(name.encode() + b"\0")
    dynamic_format = "<qQ" if elf_class == 2 else "<iI"
    section_format = "<IIQQQQIIQQ" if elf_class == 2 else "<IIIIIIIIII"
    strings_offset = len(data)
    data.extend(strings)
    dynamic_offset = len(data)
    dynamic = b"".join(struct.pack(dynamic_format, 1, offset) for offset in offsets)
    dynamic += struct.pack(dynamic_format, 0, 0)
    data.extend(dynamic)
    section_offset = len(data)
    sections = ((0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                (0, 3, 0, 0, strings_offset, len(strings), 0, 0, 1, 0),
                (0, 6, 0, 0, dynamic_offset, len(dynamic), 1, 0, 8, struct.calcsize(dynamic_format)))
    for section in sections:
        data.extend(struct.pack(section_format, *section))
    struct.pack_into("<Q" if elf_class == 2 else "<I", data, 40 if elf_class == 2 else 32, section_offset)
    struct.pack_into("<HH", data, 58 if elf_class == 2 else 46, struct.calcsize(section_format), 3)
    path.write_bytes(data)


class SharedFenceOwnerTests(unittest.TestCase):
    def test_actual_dependency_parser_each_abi_and_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.so"
            for arch in ARCHES:
                dynamic_fixture(path, arch, ["libsync_fence.z.so", "libc.so"])
                self.assertEqual(needed_libraries(path), {"libsync_fence.z.so", "libc.so"})
                path.write_bytes(path.read_bytes()[:-1])
                with self.assertRaisesRegex(ValueError, "truncated"):
                    needed_libraries(path)

    def check_pair(self, defined_surface=(), defined_fence=None, needed_surface=("libsync_fence.z.so",),
                   undefined_surface=None):
        with tempfile.TemporaryDirectory() as directory:
            surface, fence = Path(directory) / "surface.so", Path(directory) / "fence.so"
            dynamic_fixture(surface, "arm64", needed_surface)
            dynamic_fixture(fence, "arm64", ["libc.so"])
            info = [ElfInfo(183, frozenset(defined_surface), frozenset({GLOBAL} if undefined_surface is None else undefined_surface)),
                    ElfInfo(183, frozenset(({GLOBAL} | NATIVE_APIS) if defined_fence is None else defined_fence), frozenset())]
            with patch("verify_shared_fence_owner.read_elf", side_effect=info):
                return verify_pair(surface, fence, "arm64")

    def test_single_shared_provider_contract(self):
        self.assertIn("libsync_fence.z.so", self.check_pair()["surface"]["DT_NEEDED"])

    def test_duplicate_global_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate SyncFence"):
            self.check_pair(defined_surface={GLOBAL})

    def test_provider_missing_or_native_api_removed_rejected(self):
        with self.assertRaisesRegex(ValueError, "consume the shared"):
            self.check_pair(needed_surface=["libc.so"])
        with self.assertRaisesRegex(ValueError, "Native Fence API"):
            self.check_pair(defined_fence={GLOBAL})

    def test_existing_surface_internal_fence_imports_must_resolve(self):
        method = "_ZN4OHOS9SyncFence12InvalidFenceEv"
        with self.assertRaisesRegex(ValueError, "imported surface ABI"):
            self.check_pair(undefined_surface={GLOBAL, method})
        result = self.check_pair(undefined_surface={GLOBAL, method, "unrelated_dependency"},
                                 defined_fence={GLOBAL, method} | NATIVE_APIS)
        self.assertEqual(set(result["surface"]["shared_fence_imports"]), {GLOBAL, method})

    def test_pixelmap_relink_dependency_and_imported_provider_are_required(self):
        method, api = "_ZN4OHOS9SyncFence12InvalidFenceEv", "OH_PixelmapNative_CreatePixelmap"
        with tempfile.TemporaryDirectory() as directory:
            pixelmap, fence = Path(directory) / "pixelmap.so", Path(directory) / "fence.so"
            consumer = ElfInfo(183, frozenset({api}), frozenset({method}))
            provider = ElfInfo(183, frozenset({method}), frozenset())
            for needed in (("libsurface.z.so",), ("libsurface.z.so", "libsync_fence.z.so")):
                dynamic_fixture(pixelmap, "arm64", needed)
                with patch("verify_shared_fence_owner.read_elf", side_effect=(consumer, provider)):
                    if "libsync_fence.z.so" in needed:
                        self.assertEqual(verify_pixelmap(pixelmap, fence, "arm64")["shared_fence_imports"], [method])
                    else:
                        with self.assertRaisesRegex(ValueError, "directly consume"):
                            verify_pixelmap(pixelmap, fence, "arm64")
            for invalid in (ElfInfo(183, frozenset(), consumer.undefined),
                            ElfInfo(62, consumer.defined, consumer.undefined),
                            ElfInfo(183, consumer.defined, frozenset())):
                with patch("verify_shared_fence_owner.read_elf", side_effect=(invalid, provider)):
                    with self.assertRaises(ValueError):
                        verify_pixelmap(pixelmap, fence, "arm64")
            with patch("verify_shared_fence_owner.read_elf", side_effect=(consumer, ElfInfo(183, frozenset(), frozenset()))):
                with self.assertRaisesRegex(ValueError, "directly consume"):
                    verify_pixelmap(pixelmap, fence, "arm64")

    def test_component_pristine_repeat_and_marker_drift(self):
        component = ROOT / "patches/common/foundation/graphic/graphic_surface/shared_fence_owner"
        patch_file = component / "0001-use-single-shared-sync-fence-owner.patch"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            write_preimages(source, patch_file)
            command = ["bash", str(component / "apply.sh"), "--source-root", str(source)]
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
            subprocess.run(["git", "-C", str(source), "apply", "--reverse", str(patch_file)], check=True)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_full_profile_package_mandatory_ownership_check(self):
        packager = (ROOT / "scripts/package_standard_qemu.sh").read_text()
        self.assertIn('python3 "${SCRIPT_DIR}/verify_shared_fence_owner.py"', packager)
        self.assertIn('--output "${PACKAGE_DIR}/shared-fence-owner-evidence.json"', packager)


if __name__ == "__main__":
    unittest.main()
