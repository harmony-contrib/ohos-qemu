"""Pipeline/metadata regression checks, not a six-package build or guest pass."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_m144_swiftshader_artifacts as icd
import test_avc_backend_artifacts as elf_fixtures


class DependencyPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        component = ROOT / "patches/common/web/arkweb/m144_swiftshader"
        patches = {p.name: icd.checksum(p) for p in component.glob("*.patch")}
        self.manifest = {"schema_version": 1, "engine": "ArkWeb M144 SwiftShader Vulkan ICD",
            "chromium_milestone": 144, **icd.PINS, "source_patches": sorted(patches),
            "source_patch_sha256": patches, "artifacts": {}}
        for arch in icd.ARCHES:
            data = bytearray(elf_fixtures.fixture_elf(arch, symbols=icd.EXPORTS | {"vkCreateSurfaceOHOS"}))
            data[6] = 1
            is64 = data[4] == 2
            section_format = "<IIQQQQIIQQ" if is64 else "<IIIIIIIIII"
            section_size = struct.calcsize(section_format)
            dynamic = struct.unpack_from(section_format, data, 64 + 3 * section_size)
            struct.pack_into("<qQ" if is64 else "<iI", data, dynamic[4], 0x6ffffffb, 8)
            path = self.root / arch / "libvk_swiftshader.so"
            path.parent.mkdir()
            path.write_bytes(data)
            self.manifest["artifacts"][arch + "/libvk_swiftshader.so"] = {
                "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        self.save()

    def save(self, document=None):
        (self.root / "manifest.json").write_text(json.dumps(document or self.manifest))

    def test_three_synthetic_icd_abis_and_source_patch_content(self):
        self.assertEqual(set(icd.validate(self.root, list(icd.ARCHES))), set(icd.ARCHES))
        for change in (lambda d: d.update(chromium_revision="master"),
                       lambda d: d.update(source_patch_sha256={}),
                       lambda d: d["source_patch_sha256"].update({next(iter(d["source_patch_sha256"])): "0" * 64}),
                       lambda d: d["artifacts"]["arm64/libvk_swiftshader.so"].update(sha256="0" * 64)):
            data = deepcopy(self.manifest)
            change(data)
            self.save(data)
            with self.assertRaises(ValueError):
                icd.validate(self.root, ["arm64"])

    def test_no_nodelete_wrong_real_abi_or_aliased_icd_rejected(self):
        path = self.root / "arm64/libvk_swiftshader.so"
        data = bytearray(path.read_bytes())
        section_size = struct.calcsize("<IIQQQQIIQQ")
        dynamic = struct.unpack_from("<IIQQQQIIQQ", data, 64 + 3 * section_size)
        struct.pack_into("<qQ", data, dynamic[4], 0x6ffffffb, 0)
        with self.assertRaises(ValueError):
            icd.nodelete(data)
        struct.pack_into("<H", data, 18, 62)
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            icd.validate(self.root, ["arm64"])
        path.unlink()
        path.symlink_to(self.root / "x86_64/libvk_swiftshader.so")
        with self.assertRaises(ValueError):
            icd.validate(self.root, ["arm64"])

    def test_matrix_bootstraps_before_first_dependency_but_other_abis_wait_for_gate(self):
        matrix = (ROOT / "scripts/run_device_type_matrix_build_docker.sh").read_text()
        self.assertLess(matrix.index("SOURCE_PREPARE_ONLY=1"),
                        matrix.index('prepare_arch_dependencies "${MATRIX_FIRST_PRODUCT}"'))
        gate = matrix.index('python3 "${SCRIPT_DIR}/verify_first_artifact_gate.py"')
        others = matrix.index('for product in ${PRODUCTS}; do')
        self.assertLess(gate, others)
        self.assertGreater(matrix.index('prepare_arch_dependencies "${product}"'), gate)
        self.assertIn('main() {', matrix)
        pipeline = (ROOT / "scripts/prepare_qemu_release_dependencies.sh").read_text()
        self.assertLess(pipeline.index('"${frontend}" native'), pipeline.index('"${frontend}" hap'))
        self.assertLess(pipeline.index('m144_core_artifacts.py'), pipeline.index('"${frontend}" v8'))
        self.assertIn('verify_m144_swiftshader_artifacts.py', pipeline)
        self.assertIn('patches/lib/avc_artifacts.py', pipeline)

    def test_clean_host_preparation_no_hidden_prior_container_and_exact_v8_content(self):
        frontend = (ROOT / "scripts/run_m144_release_build_docker.sh").read_text()
        self.assertIn('base_image=ubuntu:22.04', frontend)
        self.assertIn('m144-build-env.Dockerfile', frontend)
        self.assertLess(frontend.index('bash /work/scripts/prepare_m144_build_host.sh'),
                        frontend.index('python3 /work/scripts/prepare_m144_release_sources.py'))
        self.assertIn('M144_GN_ONLY=1', frontend)
        validator = (ROOT / "patches/common/arkcompiler/jsvm/validate_artifacts.py").read_text()
        self.assertIn('source_patch_sha256', validator)
        self.assertIn('actual V8 public header content differs', validator)


if __name__ == "__main__":
    unittest.main()
