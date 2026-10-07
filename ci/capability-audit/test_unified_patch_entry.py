"""Real shell entry forwarding and single-plan checks, not OHOS or guest tests."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class UnifiedPatchEntryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        (self.work / "patches/lib").mkdir(parents=True)
        (self.work / "scripts").mkdir()
        for relative in ("patches/lib/apply_device_type.sh", "patches/phone/apply.sh", "patches/2in1/apply.sh"):
            target = self.work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        (self.work / "scripts/build_standard_qemu_in_docker.sh").write_text(
            '#!/bin/bash\nexec "${FIXTURE_PYTHON}" -c \'import os,json,sys; '
            'print(json.dumps({"args":sys.argv[1:],"env":{k:os.environ.get(k) for k in '
            '("DEVICE_TYPE","OHOS_ROOT","JSVM_ENGINE_ARTIFACTS","QEMU_ARKWEB_CORE_ARTIFACTS",'
            '"QEMU_VULKAN_ARTIFACTS","QEMU_AVC_ARTIFACTS","OHOS_LFS_ASSET_ROOT",'
            '"PATCH_COMPONENTS_ONLY","QEMU_JSVM_COMPONENT","QEMU_VULKAN_COMPONENT")}})); '
            'sys.exit(int(os.environ.get("FIXTURE_STATUS","0")))\' "$@"\n')
        self.args = ["--source-root", "/source with space", "--v8-artifact-root", "/v8",
            "--core-artifact-root", "/core", "--vulkan-artifact-root", "/icd",
            "--avc-artifact-root", "/avc", "--lfs-asset-root", "/lfs",
            "--product", "arm64_virt", "--product", "armv7a_virt"]

    def run_entry(self, profile, args=None, status=0):
        import sys
        return subprocess.run(["bash", str(self.work / "patches" / profile / "apply.sh"),
            *(self.args if args is None else args)], text=True, capture_output=True,
            env={**os.environ, "FIXTURE_PYTHON": sys.executable, "FIXTURE_STATUS": str(status)})

    def test_phone_and_2in1_forward_all_roots_and_products_without_word_splitting(self):
        for profile in ("phone", "2in1"):
            result = self.run_entry(profile)
            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(result.stdout)
            self.assertEqual(document["args"], ["arm64_virt", "armv7a_virt"])
            self.assertEqual(document["env"], {"DEVICE_TYPE": profile, "OHOS_ROOT": "/source with space",
                "JSVM_ENGINE_ARTIFACTS": "/v8", "QEMU_ARKWEB_CORE_ARTIFACTS": "/core",
                "QEMU_VULKAN_ARTIFACTS": "/icd", "QEMU_AVC_ARTIFACTS": "/avc", "OHOS_LFS_ASSET_ROOT": "/lfs",
                "PATCH_COMPONENTS_ONLY": "1", "QEMU_JSVM_COMPONENT": "1", "QEMU_VULKAN_COMPONENT": "1"})

    def test_old_ambiguous_root_missing_values_missing_dependencies_and_unknown_product_rejected(self):
        for args in (["--artifact-root", "/old"], ["--source-root"], self.args[:-4],
                     [*self.args, "--product", "unknown"], [*self.args, "--core-artifact-root"]):
            result = self.run_entry("phone", args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")

    def test_builder_failure_is_not_hidden(self):
        self.assertEqual(self.run_entry("2in1", status=27).returncode, 27)

    def test_docker_and_patch_entry_call_exactly_one_ordered_plan(self):
        builder = (ROOT / "scripts/build_standard_qemu_in_docker.sh").read_text()
        self.assertEqual(builder.count("apply_qemu_capability_patch_plan() {"), 1)
        plan = builder.split("apply_qemu_capability_patch_plan() {", 1)[1].split("\n}\n", 1)[0]
        for component in ("core_hap_source", "RENDER_CONNECTION_REPLY_SCRIPT", "SHARED_FENCE_OWNER_SCRIPT",
                "LOCATION_NDK_COMPONENT_SCRIPT", "ETHERNET_API26_COMPONENT_SCRIPT", "PERMISSION_OPEN_SETTING_COMPONENT_SCRIPT",
                "AUDIO_SUITE_DSP_COMPONENT_SCRIPT", "CALENDAR_SOURCE_PROVIDER_COMPONENT_SCRIPT", "QEMU_CAMERA_JPEG_COMPONENT_SCRIPT",
                "ACCESS_TOKEN_ABI_COMPONENT_SCRIPT", "VULKAN_OHOS_SURFACE_COMPONENT_SCRIPT", "apply_qemu_serial_components"):
            self.assertIn(component, plan)
        self.assertLess(plan.index("core_hap_source"), plan.index("apply_armv7a_product_component"))
        self.assertLess(plan.index("apply_armv7a_product_component"), plan.index("configure_qemu_device_profile"))
        self.assertLess(plan.index("QEMU_BINDER_CONNECTOR_COMPONENT_SCRIPT"),
                        plan.index("QEMU_BINDER_OBJECT_SAFETY_COMPONENT_SCRIPT"))
        self.assertLess(plan.index("QEMU_BINDER_OBJECT_SAFETY_COMPONENT_SCRIPT"),
                        plan.index("RS_ASYNC_CALLER_IDENTITY_COMPONENT_SCRIPT"))
        entry = (ROOT / "patches/lib/apply_device_type.sh").read_text()
        self.assertNotIn("COMPONENTS=(", entry)
        self.assertIn("build_standard_qemu_in_docker.sh", entry)
        main = builder.split("\nmain() {", 1)[1]
        patch_only = main.split("  prepare_source_and_sdk", 1)[0]
        for required in ("verify_manifest_baseline", "m144_core_artifacts.py", "validate_artifacts.py",
                         "verify_m144_swiftshader_artifacts.py", "avc_artifacts.py", "apply_qemu_capability_patch_plan"):
            self.assertIn(required, patch_only)
        for forbidden in ("build_product ", "package_product ", "prepare_checkout", "install_deps"):
            self.assertNotIn(forbidden, patch_only)


if __name__ == "__main__":
    unittest.main()
