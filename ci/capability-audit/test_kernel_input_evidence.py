#!/usr/bin/env python3
"""Kernel provenance and cache invalidation fixtures, not boot evidence."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import types
import unittest
import sys
from test_access_token_kernel import patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "patches/common/device/qemu/kernel_build_dependencies"
PATCH = COMPONENT / "0001-track-prepared-inputs-and-certify-rebuilt-kernel.patch"
SECTIONS = patch_sections(PATCH)
HELPER_NAME = "device/qemu/common/virt_full/kernel/kernel_input_evidence.py"
WRAPPER_NAME = "device/qemu/common/virt_full/kernel/build_kernel_with_evidence.sh"
HELPER_CODE = "\n".join(SECTIONS[HELPER_NAME][0][2])
HELPER = types.ModuleType("kernel_input_evidence_fixture")
exec(compile(HELPER_CODE, HELPER_NAME, "exec"), HELPER.__dict__)
sys.path.insert(0, str(ROOT / "patches/lib"))
import kernel_evidence


class KernelInputEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        for relative in HELPER.ROOTS:
            path = self.root / relative
            if path.suffix == ".sh":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("#!/bin/bash\ntrue\n")
            else:
                path.mkdir(parents=True, exist_ok=True)
                (path / "source.c").write_text("// source fixture\n")
        self.metadata = self.root / ".ohos-qemu-kernel-inputs.json"
        self.image = self.root / "out/arm64_virt/packages/phone/images/Image"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"NEW_KERNEL_FIXTURE")
        self.modules = self.root / "out/arm64_virt/kernel_modules"
        self.modules.mkdir(parents=True)
        for name in HELPER.MODULES:
            (self.modules / name).write_bytes(name.encode())
        self.certificate = self.image.parent / "kernel-inputs.json"
        HELPER.write(self.metadata, HELPER.collect(self.root))

    def record(self):
        document = HELPER.record(self.root, self.image, self.modules, "arm64", HELPER.sha(self.metadata))
        HELPER.write(self.certificate, document)
        return document

    def test_nested_patch_invalidates_even_when_top_directory_mtime_is_unchanged(self):
        directory = self.root / "kernel/linux/linux-6.6"
        before = directory.stat().st_mtime_ns
        (directory / "source.c").write_text("// real nested driver fix\n")
        self.assertEqual(before, directory.stat().st_mtime_ns)
        with self.assertRaisesRegex(ValueError, "changed after preparation"):
            HELPER.load_inputs(self.root)
        old = json.loads(self.metadata.read_text())["source_tree_sha256"]
        HELPER.write(self.metadata, HELPER.collect(self.root))
        self.assertNotEqual(old, json.loads(self.metadata.read_text())["source_tree_sha256"])

    def test_unchanged_inputs_preserve_metadata_mtime(self):
        before = self.metadata.stat().st_mtime_ns
        HELPER.write(self.metadata, HELPER.collect(self.root))
        self.assertEqual(before, self.metadata.stat().st_mtime_ns)
        directory = self.root / "vendor/ohemu/virt/hdf_config/khdf"
        (directory / "built-in.a").write_bytes(b"generated")
        (directory / ".hdf_hcs_hex.o.d").write_bytes(b"generated dependency file")
        HELPER.load_inputs(self.root)

    def test_certificate_rejects_stale_image_arch_modules_or_source(self):
        self.record()
        HELPER.verify(self.root, self.image, self.modules, "arm64", self.certificate)
        with self.assertRaises(ValueError):
            HELPER.verify(self.root, self.image, self.modules, "arm", self.certificate)
        self.image.write_bytes(b"OLD_KERNEL_FIXTURE")
        with self.assertRaises(ValueError):
            HELPER.verify(self.root, self.image, self.modules, "arm64", self.certificate)
        self.image.write_bytes(b"NEW_KERNEL_FIXTURE")
        (self.modules / HELPER.MODULES[0]).write_bytes(b"old module")
        with self.assertRaises(ValueError):
            HELPER.verify(self.root, self.image, self.modules, "arm64", self.certificate)
        (self.modules / HELPER.MODULES[0]).unlink()
        with self.assertRaises(ValueError):
            self.record()

    def test_missing_metadata_and_source_drift_never_certify_output(self):
        before = HELPER.sha(self.metadata)
        directory = self.root / "drivers/hdf_core"
        (directory / "new_input.h").write_text("// new dependency\n")
        with self.assertRaises(ValueError):
            HELPER.record(self.root, self.image, self.modules, "arm64", before)
        HELPER.write(self.metadata, HELPER.collect(self.root))
        with self.assertRaisesRegex(ValueError, "during compilation"):
            HELPER.record(self.root, self.image, self.modules, "arm64", before)
        self.metadata.unlink()
        with self.assertRaises(FileNotFoundError):
            self.record()

    def test_delivered_image_is_bound_to_input_inventory_and_architecture(self):
        document = self.record()
        package = self.root / "package"
        (package / "images").mkdir(parents=True)
        (package / "kernel-inputs.json").write_text(json.dumps(document))
        (package / "kernel-source-inputs.json").write_bytes(self.metadata.read_bytes())
        image = package / "images/Image"
        image.write_bytes(self.image.read_bytes())
        kernel_evidence.verify(package, "arm64")
        with self.assertRaises(ValueError):
            kernel_evidence.verify(package, "x86_64")
        image.write_bytes(b"stale image")
        with self.assertRaises(ValueError):
            kernel_evidence.verify(package, "arm64")
        image.write_bytes(self.image.read_bytes())
        (package / "kernel-source-inputs.json").write_text("{}")
        with self.assertRaises(ValueError):
            kernel_evidence.verify(package, "arm64")

    def test_component_apply_is_idempotent_and_wrapper_is_executable(self):
        for name, hunks in SECTIONS.items():
            if name in (HELPER_NAME, WRAPPER_NAME):
                continue
            path = self.root / name
            path.write_text("\n".join(hunks[0][1]) + "\n")
        command = ["bash", str(COMPONENT / "apply.sh"), "--source-root", str(self.root)]
        subprocess.run(command, capture_output=True, check=True)
        subprocess.run(command, capture_output=True, check=True)
        subprocess.run(["git", "-C", str(self.root), "apply", "--check", "--reverse", str(PATCH)], check=True)
        self.assertTrue(os.access(self.root / WRAPPER_NAME, os.X_OK))
        subprocess.run(["bash", "-n", str(self.root / WRAPPER_NAME)], check=True)

    def test_wrapper_forces_actual_build_and_normalizes_gn_relative_image_path(self):
        directory = self.root / "device/qemu/common/virt_full/kernel"
        (directory / "kernel_input_evidence.py").write_text(HELPER_CODE)
        wrapper = directory / "build_kernel_with_evidence.sh"
        wrapper.write_text("\n".join(SECTIONS[WRAPPER_NAME][0][2]) + "\n")
        stub = directory / "build_kernel.sh"
        stub.write_text('''#!/usr/bin/env bash
set -euo pipefail
[ "${OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE}" = 0 ]
image_dir="$(python3 -c 'from pathlib import Path; import sys; print((Path(sys.argv[1]) / sys.argv[2]).resolve())' "$1" "$3")"
mkdir -p "$image_dir" "$7"
printf 'REBUILT_KERNEL_FIXTURE' > "$image_dir/Image"
for name in ''' + " ".join(HELPER.MODULES) + '''; do printf '%s' "$name" > "$7/$name"; done
''')
        HELPER.write(self.metadata, HELPER.collect(self.root))
        out = self.root / "out/arm64_virt"
        script_relative = os.path.relpath(directory, out)
        source_relative = os.path.relpath(self.root, directory)
        image_relative = os.path.relpath(self.image.parent, directory)
        env = dict(os.environ, OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE="1")
        result = subprocess.run(["bash", str(wrapper), script_relative, source_relative, image_relative,
                                 "unused", script_relative, "arm64", "kernel_modules"],
                                cwd=out, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.image.read_bytes(), b"REBUILT_KERNEL_FIXTURE")
        HELPER.verify(self.root, self.image, self.modules, "arm64", self.certificate)


if __name__ == "__main__":
    unittest.main()
