import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apply_qemu_mesa_bounds_fix",
    REPO_ROOT / "scripts/apply_qemu_mesa_bounds_fix.py",
)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)


class QemuMesaBoundsFixTest(unittest.TestCase):
    def _populate_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        base_mesa = root / "third_party/mesa3d"
        extracted_mesa = base_mesa / "qemu_llvm_build/arm64_virt/f3f7ede4ac7402a0be383515/source"
        gralloc = root / "device/qemu/common/virt_full/hardware/display/src/display_gralloc"
        wm_dir = root / "foundation/window/window_manager/wm"

        for m in (base_mesa, extracted_mesa):
            (m / "src/gallium/drivers/llvmpipe").mkdir(parents=True)
            (m / "src/gallium/winsys/sw/kms-dri").mkdir(parents=True)
            (m / "src/gallium/drivers/llvmpipe/lp_rast_priv.h").write_text(
                MOD.LP_RAST_PRIV_OLD + "\n{\n" + MOD.LP_RAST_PRIV_CALL_OLD + "\n}\n",
                encoding="utf-8",
            )
            (m / "src/gallium/drivers/llvmpipe/lp_rast.c").write_text(
                "void tile(void) {\n"
                + MOD.LP_RAST_TILE_OLD
                + "\n}\nvoid mask(void) {\n"
                + MOD.LP_RAST_MASK_OLD
                + "\n}\nvoid create(void) {\n"
                + MOD.LP_RAST_CREATE_OLD
                + "\n}\n",
                encoding="utf-8",
            )
            (m / "src/gallium/drivers/llvmpipe/lp_rast_linear_fallback.c").write_text(
                "void f1(void) {\n"
                + MOD.LP_LINEAR_FB_WHOLE_OLD
                + "\n}\nvoid f2(void) {\n"
                + MOD.LP_LINEAR_FB_MASK_OLD
                + "\n}\n",
                encoding="utf-8",
            )
            (m / "src/gallium/winsys/sw/kms-dri/kms_dri_sw_winsys.c").write_text(
                "struct kms_sw_displaytarget {\n"
                + MOD.KMS_DT_STRUCT_OLD
                + "\n};\nvoid d(void) {\n"
                + MOD.KMS_DESTROY_OLD
                + "\n}\n"
                + MOD.KMS_MAP_OLD
                + "\n   return 0;\n}\nvoid u(void) {\n"
                + MOD.KMS_UNMAP_OLD
                + "\n}\n",
                encoding="utf-8",
            )

        gralloc.mkdir(parents=True)
        (gralloc / "hi_gbm_internal.h").write_text(MOD.HI_GBM_OLD + "\n", encoding="utf-8")
        (gralloc / "hi_gbm.cpp").write_text("// untouched hi_gbm.cpp\n", encoding="utf-8")

        (wm_dir / "src").mkdir(parents=True)
        (wm_dir / "src/window_session_impl.cpp").write_text(
            MOD.WM_TITLE_MOVE_OLD
            + "\n        return WMError::WM_ERROR_DEVICE_NOT_SUPPORT;\n    }\n}\n\n"
            + "WMError WindowSessionImpl::SetTitleButtonVisible() {\n"
            + MOD.WM_TITLE_BTN_OLD
            + "\n}\n",
            encoding="utf-8",
        )
        # Include a CRLF line elsewhere in window_scene_session_impl.cpp to verify newline preservation.
        with (wm_dir / "src/window_scene_session_impl.cpp").open("w", encoding="utf-8", newline="") as fh:
            fh.write(
                "// mixed crlf line\r\n"
                + "WMError WindowSceneSessionImpl::SetWindowTitle(const std::string& title) {\n"
                + MOD.WM_SET_TITLE_OLD
                + "\n        return WMError::WM_OK;\n    }\n}\n\n"
                + "WMError WindowSceneSessionImpl::Recover() {\n"
                + MOD.WM_RECOVER_OLD
                + "\n    return checkRet;\n}\n"
            )

        orig_builder = (
            "def build(out_dir):\n"
            "    cache_identity = {\n"
            + MOD.MESA_BUILDER_CACHE_OLD
            + "\n"
            + MOD.MESA_BUILDER_CALL_OLD
            + "\n"
        )
        builder_path = base_mesa / "build_qemu_mesa_llvm.py"
        builder_path.write_text(orig_builder, encoding="utf-8")
        orig_sha = hashlib.sha256(builder_path.read_bytes()).hexdigest()
        (base_mesa / "qemu_llvm_recipe_hooks.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "payloads": {MOD.MESA_BUILDER_REL: orig_sha},
                    "hooks": {},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return base_mesa, extracted_mesa, gralloc, wm_dir

    def test_patch_verify_hook_and_rewind_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base_mesa, extracted_mesa, gralloc, wm_dir = self._populate_fixture(root)

            orig_base_priv = (base_mesa / "src/gallium/drivers/llvmpipe/lp_rast_priv.h").read_bytes()
            orig_hi_gbm_cpp = (gralloc / "hi_gbm.cpp").read_bytes()
            orig_hdr = (gralloc / "hi_gbm_internal.h").read_bytes()
            orig_wm_session = (wm_dir / "src/window_session_impl.cpp").read_bytes()
            orig_wm_scene = (wm_dir / "src/window_scene_session_impl.cpp").read_bytes()
            orig_builder = (base_mesa / "build_qemu_mesa_llvm.py").read_bytes()

            with self.assertRaises(RuntimeError):
                MOD.main(["--source-root", str(root), "--verify"])

            rc = MOD.main(["--source-root", str(root), "--install-mesa-builder-hook", str(root)])
            self.assertEqual(rc, 0)

            # Base third_party/mesa3d git checkout files and hi_gbm.cpp must remain 100% untouched.
            self.assertEqual(
                (base_mesa / "src/gallium/drivers/llvmpipe/lp_rast_priv.h").read_bytes(),
                orig_base_priv,
            )
            self.assertEqual((gralloc / "hi_gbm.cpp").read_bytes(), orig_hi_gbm_cpp)

            # Extracted Mesa tree, hi_gbm_internal.h, WM decor files, and Mesa builder hook must pass verify.
            self.assertEqual(
                MOD.main(
                    [
                        "--source-root",
                        str(root),
                        "--install-mesa-builder-hook",
                        str(root),
                        "--verify",
                    ]
                ),
                0,
            )
            self.assertIn(b"\r\n", (wm_dir / "src/window_scene_session_impl.cpp").read_bytes())

            # Second apply must be a clean no-op.
            self.assertEqual(MOD.patch_mesa_tree(extracted_mesa), [])
            self.assertEqual(MOD.patch_display_gralloc(gralloc), [])
            self.assertEqual(MOD.patch_window_manager_decor(wm_dir), [])
            self.assertEqual(MOD.install_mesa_builder_hook(root), [])

            # Rewind + restore hook must restore exact upstream bytes.
            self.assertEqual(
                MOD.main(
                    [
                        "--source-root",
                        str(root),
                        "--rewind",
                        "--restore-mesa-builder-hook",
                        str(root),
                    ]
                ),
                0,
            )
            self.assertEqual((gralloc / "hi_gbm_internal.h").read_bytes(), orig_hdr)
            self.assertEqual((wm_dir / "src/window_session_impl.cpp").read_bytes(), orig_wm_session)
            self.assertEqual((wm_dir / "src/window_scene_session_impl.cpp").read_bytes(), orig_wm_scene)
            self.assertEqual((base_mesa / "build_qemu_mesa_llvm.py").read_bytes(), orig_builder)
            self.assertFalse((base_mesa / "qemu_bounds_fix").exists())


if __name__ == "__main__":
    unittest.main()
