"""Negative provenance tests; these fixtures do not model a running guest."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("mesa_image", ROOT / "scripts/verify_mesa_llvm_image.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class MesaImageTests(unittest.TestCase):
    def records(self):
        product = "arm64_virt"
        manifest = {"schema_version": 1, "component": "QEMU Mesa private LLVM 10.0.0",
                    "product": product, "arch": "arm64", **M.expected_identity(),
                    "archive": {"machines": [183], "objects": 1}, "runtime_gate_passed": False,
                    "files": {"lib/libllvm.a": {"sha256": "a" * 64}}}
        build = {"schema_version": 1, "product": product,
                 "dependency": manifest["recipe_sha256"], "runtime_gate_passed": False,
                 "llvm_archive_sha256": "a" * 64, "driver_sha256": "b" * 64,
                 "actual_options": {"llvm": "enabled", "draw-use-llvm": True,
                                    "shared-llvm": "disabled", "cpp_std": "c++17"},
                 "build_inputs": {
                     "product": product, "llvm_manifest": "c" * 64,
                     "base_builder": M.BASE_BUILDERS[product],
                     "build_id_backport": {name: M.digest(ROOT / 'patches/common/third_party/mesa3d/build_id_boundaries' / name)
                         for name in ('apply_mesa_build_id.py',
                             '0001-bound-ELF-note-payloads-before-reading-or-advancing.patch')},
                     "builder": M.digest(ROOT / "patches/common/third_party/mesa3d/llvm_backend/files/build_qemu_mesa_llvm.py"),
                     "mapping": M.digest(ROOT / "patches/common/third_party/mesa3d/kms_mapping_synchronization/files/apply_mesa_kms_mapping.py")}}
        inventory = {name: {"sha256": "b" * 64, "size": 4096, "elf_machine": 183}
                     for name in M.LIBRARIES}
        return build, manifest, inventory

    def test_reject_old_recipe_wrong_product_and_false_runtime_claims(self):
        build, manifest, _ = self.records()
        M.check_build(build, manifest, "c" * 64, "arm64_virt")
        for changes in ({"recipe_sha256": "0" * 64}, {"product": "x86_64_virt"},
                        {"runtime_gate_passed": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                M.check_build(build, {**manifest, **changes}, "c" * 64, "arm64_virt")

    def test_reject_different_actual_consumer_and_llvm_configuration(self):
        build, manifest, _ = self.records()
        for field in ("builder", "base_builder", "mapping", "llvm_manifest", "build_id_backport"):
            changed = copy.deepcopy(build)
            changed["build_inputs"][field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                M.check_build(changed, manifest, "c" * 64, "arm64_virt")
        changed = copy.deepcopy(build)
        changed["actual_options"]["llvm"] = "disabled"
        with self.assertRaises(ValueError):
            M.check_build(changed, manifest, "c" * 64, "arm64_virt")

    def test_all_six_outputs_and_actual_driver_are_required(self):
        build, _, inventory = self.records()
        M.check_inventory(inventory, build, "arm64_virt")
        missing = dict(inventory)
        del missing["libGLESv2.so.2.0.0"]
        with self.assertRaisesRegex(ValueError, "six"):
            M.check_inventory(missing, build, "arm64_virt")
        inventory["kms_swrast_dri.so"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "actual build"):
            M.check_inventory(inventory, build, "arm64_virt")

    def test_packaged_evidence_checksums_and_symlinks(self):
        build, manifest, inventory = self.records()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, contents in zip(M.REPORTS, (build, manifest, inventory)):
                (directory / name).write_text(json.dumps(contents))
            build["build_inputs"]["llvm_manifest"] = M.digest(directory / "llvm-manifest.json")
            (directory / "build.json").write_text(json.dumps(build))
            record = {"schema_version": 1, "product": "arm64_virt", "runtime_gate_passed": False,
                      "files": {name: M.digest(directory / name) for name in M.REPORTS}}
            (directory / "provenance.json").write_text(json.dumps(record))
            self.assertEqual(M.load_packaged_provenance(directory, "arm64_virt"), inventory)
            (directory / "libraries.json").write_text('{}')
            with self.assertRaisesRegex(ValueError, "changed packaged"):
                M.load_packaged_provenance(directory, "arm64_virt")
            (directory / "libraries.json").unlink()
            outside = directory / "outside.json"
            outside.write_text(json.dumps(inventory))
            (directory / "libraries.json").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "regular"):
                M.load_packaged_provenance(directory, "arm64_virt")


if __name__ == "__main__":
    unittest.main()
