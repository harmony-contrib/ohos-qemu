"""V8 feature/provenance fixtures, not a compiled V8 or a JSVM guest pass."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("jsvm_artifact_contract",
    ROOT / "patches/common/arkcompiler/jsvm/validate_artifacts.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


class JsvmIntlArtifactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        headers = self.root / "v8-include/v8-include"
        headers.mkdir(parents=True)
        header = b"// synthetic public header fixture\n"
        (headers / "v8.h").write_bytes(header)
        patch_root = ROOT / "patches/common/web/arkweb/m144_v8_shared"
        patches = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in patch_root.glob("*.patch")}
        self.configuration = {"v8_enable_i18n_support": True, "icu_use_data_file": False,
                              "v8_use_external_startup_data": False}
        self.manifest = {"schema_version": 1, "engine": "ArkWeb M144 V8", "chromium_milestone": 144,
            "libcxx_abi_namespace": "__h", "libcxx_abi_version": 1, **contract.PINNED_REVISIONS,
            "runtime_configuration": self.configuration, "source_patches": sorted(patches),
            "source_patch_sha256": patches, "headers_sha256": hashlib.sha256(b"v8.h\0" + header).hexdigest(),
            "build_args_sha256": {}, "artifacts": {}}
        for arch, machine in contract.ELF_MACHINES.items():
            directory = self.root / "v8" / arch
            directory.mkdir(parents=True)
            arguments = directory / "args.gn"
            arguments.write_text("\n".join(name + "=" + str(value).lower()
                for name, value in self.configuration.items()) + "\n")
            self.manifest["build_args_sha256"][arguments.relative_to(self.root).as_posix()] = hashlib.sha256(arguments.read_bytes()).hexdigest()
            data = bytearray(64)
            data[:7] = b"\x7fELF" + bytes((1 if arch == "arm" else 2, 1, 1))
            struct.pack_into("<HH", data, 16, 3, machine)
            data.extend(b"synthetic NSt3__h ABI fixture, not actual V8")
            for relative in ("libv8_shared.so", "lib.unstripped_v8/lib.unstripped/libv8_shared.so"):
                library = directory / relative
                library.parent.mkdir(parents=True, exist_ok=True)
                library.write_bytes(data)
                self.manifest["artifacts"][library.relative_to(self.root).as_posix()] = {
                    "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        self.save(self.manifest)

    def save(self, document):
        (self.root / "manifest.json").write_text(json.dumps(document))

    def test_all_three_fixture_abis_with_embedded_icu(self):
        contract.validate(self.root, list(contract.ELF_MACHINES))

    def test_disabled_intl_external_icu_or_numeric_booleans_rejected(self):
        for name, value in (("v8_enable_i18n_support", False), ("icu_use_data_file", True),
                            ("v8_use_external_startup_data", True), ("v8_enable_i18n_support", 1)):
            document = deepcopy(self.manifest)
            document["runtime_configuration"][name] = value
            self.save(document)
            with self.assertRaises(SystemExit):
                contract.validate(self.root, ["arm64"])

    def test_actual_args_guard_rejects_disabled_or_duplicate_assignment_even_if_rehashed(self):
        path = self.root / "v8/arm64/args.gn"
        for content in ("v8_enable_i18n_support=false\nicu_use_data_file=false\nv8_use_external_startup_data=false\n",
                        path.read_text() + "v8_enable_i18n_support=true\n"):
            path.write_text(content)
            document = deepcopy(self.manifest)
            document["build_args_sha256"]["v8/arm64/args.gn"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.save(document)
            with self.assertRaises(SystemExit):
                contract.validate(self.root, ["arm64"])

    def test_headers_and_elf_class_cannot_be_faked_by_manifest_machine_only(self):
        (self.root / "v8-include/v8-include/v8.h").write_text("changed")
        with self.assertRaises(SystemExit):
            contract.validate(self.root, ["arm64"])
        path = self.root / "v8/arm/libv8_shared.so"
        data = bytearray(path.read_bytes())
        data[4] = 2
        path.write_bytes(data)
        with self.assertRaises(SystemExit):
            contract.elf_machine(path)

    def test_builder_and_e2e_retain_intl_and_boundary_regressions(self):
        builder = (ROOT / "scripts/build_m144_v8_in_docker.sh").read_text()
        self.assertIn("v8_enable_i18n_support=true", builder)
        self.assertIn("icu_use_data_file=false", builder)
        self.assertIn("v8_use_external_startup_data=false", builder)


if __name__ == "__main__":
    unittest.main()
