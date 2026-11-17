import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]

EXACT_COMPONENTS = (
    "patches/common/device/qemu/gbm_height_align4",
    "patches/common/foundation/window/window_manager/pad_decor_compat",
    "patches/common/third_party/f2fs-tools/va_copy_log_buffer",
    "patches/common/third_party/libpng/arm_neon_guard",
    "patches/common/foundation/communication/netmanager_ext/netfirewall_32bit_log",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LatestPatchesInTreeTest(unittest.TestCase):
    def test_exact_components_exist_and_syntax_clean(self) -> None:
        for rel in EXACT_COMPONENTS:
            comp = REPO_ROOT / rel
            self.assertTrue((comp / "apply.sh").is_file(), f"missing apply.sh in {rel}")
            self.assertTrue((comp / "verify_source.py").is_file(), f"missing verify_source.py in {rel}")
            self.assertTrue((comp / "README.md").is_file(), f"missing README.md in {rel}")
            patches = sorted(comp.glob("[0-9][0-9][0-9][0-9]-*.patch"))
            self.assertGreaterEqual(len(patches), 1, f"missing .patch in {rel}")
            subprocess.run(["bash", "-n", str(comp / "apply.sh")], check=True)
            vs = load_module(comp / "verify_source.py", f"vs_{comp.name}")
            self.assertGreaterEqual(len(vs.FILES), 1)
            for _, orig_sha, rep_sha in vs.FILES:
                self.assertEqual(len(orig_sha), 64)
                self.assertEqual(len(rep_sha), 64)
                self.assertNotEqual(orig_sha, rep_sha)

        for sh in (
            REPO_ROOT / "scripts/build_standard_qemu_in_docker.sh",
            REPO_ROOT / "scripts/package_standard_qemu.sh",
        ):
            subprocess.run(["bash", "-n", str(sh)], check=True)

        bsd = (REPO_ROOT / "scripts/build_standard_qemu_in_docker.sh").read_text(encoding="utf-8")
        for needle in (
            "common/foundation/window/window_manager/pad_decor_compat/apply.sh",
            "common/device/qemu/gbm_height_align4/apply.sh",
            "common/third_party/f2fs-tools/va_copy_log_buffer/apply.sh",
            "common/third_party/libpng/arm_neon_guard/apply.sh",
            "common/foundation/communication/netmanager_ext/netfirewall_32bit_log/apply.sh",
        ):
            self.assertIn(needle, bsd)

    def test_mesa_bounds_and_guard_patch_hashes_and_llvm_backend_compat(self) -> None:
        bg_dir = REPO_ROOT / "patches/common/third_party/mesa3d/bounds_and_guard"
        mod = load_module(bg_dir / "apply_mesa_bounds_and_guard.py", "mesa_bg")
        for name, expected_sha in mod.PATCHES:
            p = bg_dir / name
            self.assertTrue(p.is_file(), f"missing {p}")
            self.assertEqual(sha256_bytes(p.read_bytes()), expected_sha)

        bqm = (REPO_ROOT / "patches/common/third_party/mesa3d/llvm_backend/files/build_qemu_mesa_llvm.py").read_text(encoding="utf-8")
        self.assertIn("apply_mesa_bounds_and_guard.py", bqm)
        self.assertIn("bounds_and_guard_backport", bqm)

        artifacts_mod = load_module(REPO_ROOT / "scripts/qemu_mesa_llvm_artifacts.py", "llvm_artifacts")
        recipe_sha = artifacts_mod.expected_identity(REPO_ROOT / "scripts")["recipe_sha256"]

        ab_mod = load_module(REPO_ROOT / "patches/common/third_party/mesa3d/llvm_backend/apply_backend.py", "apply_backend_mod")
        amb_mod = load_module(REPO_ROOT / "scripts/apply_qemu_mesa_bounds_fix.py", "amb_mod")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hook_test_root = root / "hook_test"
            (hook_test_root / "third_party/mesa3d").mkdir(parents=True)
            (hook_test_root / "third_party/mesa3d/build_qemu_mesa_llvm.py").write_text(bqm, encoding="utf-8")
            self.assertEqual(amb_mod.install_mesa_builder_hook(hook_test_root, verify=True), [])
            self.assertEqual(amb_mod.install_mesa_builder_hook(hook_test_root, verify=False), [])

            sample_gn = "\n".join([
                'qemu_mesa_dir = "//third_party/mesa3d"',
                '  outputs = []',
                '  action("x") {',
                '    script = "//device/qemu/arm_virt/linux_full_armv7a/build_armv7a_mesa.py"',
                '    inputs = [',
                '    ]',
                '  }',
                '',
            ]).encode("utf-8")
            old_gn_hashes = dict(ab_mod.GN_FILES)
            try:
                ab_mod.GN_FILES["third_party/mesa3d/ohos/BUILD.gn"] = sha256_bytes(sample_gn)
                with_bg = ab_mod.transform("third_party/mesa3d/ohos/BUILD.gn", sample_gn, recipe_sha, True, True).decode("utf-8")
                without_bg = ab_mod.transform("third_party/mesa3d/ohos/BUILD.gn", sample_gn, recipe_sha, True, False).decode("utf-8")
                self.assertIn("apply_mesa_bounds_and_guard.py", with_bg)
                self.assertNotIn("apply_mesa_bounds_and_guard.py", without_bg)

                (root / "third_party/mesa3d/ohos").mkdir(parents=True)
                gn_file = root / "third_party/mesa3d/ohos/BUILD.gn"
                gn_file.write_text(without_bg, encoding="utf-8")
                (root / ab_mod.HOOK_RECORD).write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "identity": {"recipe_sha256": recipe_sha},
                            "build_id_backport": True,
                            "hooks": {
                                "third_party/mesa3d/ohos/BUILD.gn": {
                                    "base": base64.b64encode(sample_gn).decode("ascii"),
                                }
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                _, changes = ab_mod.restore_plan(root)
                self.assertEqual(len(changes), 1)
                self.assertEqual(changes[0][1], sample_gn)
            finally:
                ab_mod.GN_FILES.clear()
                ab_mod.GN_FILES.update(old_gn_hashes)


if __name__ == "__main__":
    unittest.main()
