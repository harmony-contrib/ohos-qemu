"""Composition and source-preservation regressions; no guest acceptance claims."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "mesa_llvm_backend",
    REPO / "patches/common/third_party/mesa3d/llvm_backend/apply_backend.py",
)
BACKEND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKEND)
SOURCES = json.loads(gzip.decompress(base64.b64decode(
    Path(__file__).with_name("fixtures").joinpath("mesa_llvm_mapping_inputs.json.gz.b64").read_text())))
RECIPE = "1" * 64


class MesaLLVMCompositionTests(unittest.TestCase):
    def test_action_script_exec_mode_new_and_replayed_without_overwriting_unknown_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / 'build_qemu_mesa_llvm.py'
            payload = b'#!/usr/bin/env python3\nprint("actual exec permission probe")\n'
            for previous_mode in (None, 0o644, 0o755):
                if previous_mode is not None:
                    script.write_bytes(payload)
                    script.chmod(previous_mode)
                else:
                    script.unlink(missing_ok=True)
                before = script.read_bytes() if script.exists() else None
                BACKEND.atomic_write(script, payload, before, mode=0o755)
                self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o755)
                result = subprocess.run(['/usr/bin/env', str(script)], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), 'actual exec permission probe')
            original = script.read_bytes() + b'# unrecognized concurrent edit\n'
            script.write_bytes(original)
            script.chmod(0o640)
            with self.assertRaisesRegex(ValueError, 'source changed'):
                BACKEND.atomic_write(script, payload, payload, mode=0o755)
            self.assertEqual(script.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o640)
            data = root / 'metadata.json'
            BACKEND.atomic_write(data, b'{}\n', None)
            self.assertEqual(stat.S_IMODE(data.stat().st_mode), 0o644)

    def test_empty_cross_abi_and_aliased_cached_objects_are_rejected(self):
        spec = importlib.util.spec_from_file_location('mesa_native_consumer',
            REPO / 'patches/common/third_party/mesa3d/llvm_backend/files/build_qemu_mesa_llvm.py')
        consumer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(consumer)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'src').mkdir()
            obj = root / 'src/cached.o'
            arm64 = b'\x7fELF\x02\x01\x01' + bytes(9) + b'\x01\x00\xb7\x00'
            obj.write_bytes(arm64)
            self.assertEqual(consumer.check_cached_objects(root, 183), 1)
            for corrupt in (b'', b'not an ELF object', arm64[:18] + b'\x28\x00'):
                obj.write_bytes(corrupt)
                with self.assertRaisesRegex(ValueError, 'invalid cached Mesa object'):
                    consumer.check_cached_objects(root, 183)
            outside = root / 'caller.o'
            outside.write_bytes(arm64)
            obj.unlink()
            obj.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'invalid cached Mesa object'):
                consumer.check_cached_objects(root, 183)
            self.assertEqual(outside.read_bytes(), arm64)

    def test_common_both_cpu_actions_track_actual_dependency(self):
        name = "device/qemu/common/virt_full/hardware/gpu/BUILD.gn"
        result = BACKEND.transform(name, SOURCES[name].encode(), RECIPE).decode()
        self.assertIn('qemu_llvm_product = "arm64_virt"', result)
        self.assertIn('if (target_cpu == "x86_64")', result)
        self.assertIn('qemu_llvm_product = "x86_64_virt"', result)
        self.assertIn("/$qemu_llvm_product/manifest.json", result)
        self.assertIn("/$qemu_llvm_product/lib/libllvm.a", result)
        self.assertIn("mesa-llvm-build-provenance.json", result)
        for line in SOURCES[name].splitlines():
            if "mesa_kms_mapping/" in line:
                self.assertIn(line, result)

    def test_arm_hook_keeps_non_qemu_builder_and_mapping_dependencies(self):
        name = "third_party/mesa3d/ohos/BUILD.gn"
        result = BACKEND.transform(name, SOURCES[name].encode(), RECIPE).decode()
        self.assertIn('script = "build_mesa3d.py"', result)
        self.assertIn('if (product_name == "armv7a_virt")', result)
        self.assertIn("/armv7a_virt/lib/libllvm.a", result)
        self.assertIn('script = "//third_party/mesa3d/build_qemu_mesa_llvm.py"', result)
        for line in SOURCES[name].splitlines():
            if "mesa_kms_mapping/" in line:
                self.assertIn(line, result)

    def test_unknown_base_bytes_and_invalid_recipe_are_rejected(self):
        name = next(iter(BACKEND.GN_FILES))
        original = SOURCES[name].encode()
        with self.assertRaisesRegex(ValueError, "unexpected base"):
            BACKEND.transform(name, original + b"# user edit\n", RECIPE)
        with self.assertRaisesRegex(ValueError, "recipe"):
            BACKEND.transform(name, original, "../not-a-recipe")

    def prepare(self, root, build_id_backport=True):
        hooks = {}
        for name in BACKEND.GN_FILES:
            original = SOURCES[name].encode()
            self.assertEqual(hashlib.sha256(original).hexdigest(), BACKEND.GN_FILES[name])
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(BACKEND.transform(name, original, RECIPE, build_id_backport))
            hooks[name] = {"base": base64.b64encode(original).decode()}
        record = root / BACKEND.HOOK_RECORD
        record.write_text(json.dumps({"identity": {"recipe_sha256": RECIPE}, "hooks": hooks,
                                     "build_id_backport": build_id_backport}))

    def test_previous_hooks_restore_before_build_id_dependency_upgrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root, False)
            record = root / BACKEND.HOOK_RECORD
            old = json.loads(record.read_text())
            del old['build_id_backport']
            record.write_text(json.dumps(old))
            _, changes = BACKEND.restore_plan(root)
            self.assertEqual(len(changes), 2)
            for path, original in changes:
                name = path.relative_to(root).as_posix()
                self.assertEqual(original.decode(), SOURCES[name])
                upgraded = BACKEND.transform(name, original, RECIPE).decode()
                for asset in BACKEND.BUILD_ID_FILES:
                    self.assertIn('//third_party/mesa3d/qemu_build_id/' + asset, upgraded)

    def test_restore_then_reapply_is_exact_and_preserves_base_builders(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root)
            for name, content in SOURCES.items():
                if name.endswith(".py"):
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
            _, changes = BACKEND.restore_plan(root)
            self.assertEqual(len(changes), 2)
            for path, original in changes:
                BACKEND.atomic_write(path, original)
                name = path.relative_to(root).as_posix()
                self.assertEqual(path.read_text(), SOURCES[name])
                path.write_bytes(BACKEND.transform(name, original, RECIPE))
            self.assertEqual(len(BACKEND.restore_plan(root)[1]), 2)
            for name, content in SOURCES.items():
                if name.endswith(".py"):
                    self.assertEqual((root / name).read_text(), content)

    def test_modified_hook_fails_before_any_source_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root)
            edited = root / next(iter(BACKEND.GN_FILES))
            edited.write_bytes(edited.read_bytes() + b"# caller edit\n")
            before = {name: (root / name).read_bytes() for name in BACKEND.GN_FILES}
            with self.assertRaisesRegex(ValueError, "preserving"):
                BACKEND.restore_plan(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in BACKEND.GN_FILES})

    def test_symlinked_managed_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            (root / "third_party").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                BACKEND.restore_plan(root)

    def test_publish_rechecks_bytes_after_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "BUILD.gn"
            path.write_bytes(b"caller changed the file")
            with self.assertRaisesRegex(ValueError, "preserving"):
                BACKEND.atomic_write(path, b"new hook", b"original")
            self.assertEqual(path.read_bytes(), b"caller changed the file")


if __name__ == "__main__":
    unittest.main()
