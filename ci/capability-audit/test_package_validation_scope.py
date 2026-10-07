import copy
import json
from pathlib import Path
import re
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "patches/lib"))
from package_validation import PACKAGING_SCOPE, validate_packaging_scope


class PackageValidationScopeTests(unittest.TestCase):
    def test_archive_failure_preserves_completed_package_and_removes_temporary_file(self):
        script = (ROOT / "scripts/package_standard_qemu.sh").read_text()
        block = script[script.index('(\n  cd "${OUTPUT_DIR}"\n  # Avoid macOS AppleDouble'):]
        block = block[:block.index('\n\necho "${PACKAGE_DIR}"')]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            archive = output / "probe.tar.gz"
            archive.write_bytes(b"previous-completed-package")
            env = {"OUTPUT_DIR": directory, "PACKAGE_NAME": "probe", "PATH": "/usr/bin:/bin"}
            result = subprocess.run(["/bin/bash", "-euc", block], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(archive.read_bytes(), b"previous-completed-package")
            self.assertEqual(list(output.glob("*.tmp.*")), [])

    def test_archive_success_publishes_readable_package_without_temporary_file(self):
        script = (ROOT / "scripts/package_standard_qemu.sh").read_text()
        block = script[script.index('(\n  cd "${OUTPUT_DIR}"\n  # Avoid macOS AppleDouble'):]
        block = block[:block.index('\n\necho "${PACKAGE_DIR}"')]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "probe").mkdir()
            (output / "probe/payload").write_text("complete", encoding="utf-8")
            env = {"OUTPUT_DIR": directory, "PACKAGE_NAME": "probe", "PATH": "/usr/bin:/bin"}
            result = subprocess.run(["/bin/bash", "-euc", block], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            listed = subprocess.run(["tar", "-tzf", str(output / "probe.tar.gz")], capture_output=True, check=True)
            self.assertIn(b"probe/payload", listed.stdout)
            self.assertEqual(list(output.glob("*.tmp.*")), [])

    def test_actual_packager_emits_static_only_scope_and_verifier_requires_it(self):
        script = (ROOT / "scripts/package_standard_qemu.sh").read_text()
        match = re.search(r'  "validation": (\{.*?\n  \}),\n  "capabilities":', script, re.S)
        self.assertIsNotNone(match)
        scope = json.loads(match[1])
        self.assertEqual(scope, PACKAGING_SCOPE)
        validate_packaging_scope({"validation": scope})
        self.assertIn("Archive creation or the offline verifier cannot satisfy", script)
        verifier = (ROOT / "scripts/verify_device_type_package.sh").read_text()
        self.assertIn('patches/lib/package_validation.py', verifier)

    def test_missing_or_claimed_runtime_evidence_cannot_pass_static_gate(self):
        for key in PACKAGING_SCOPE:
            scope = copy.deepcopy(PACKAGING_SCOPE)
            del scope[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_packaging_scope({"validation": scope})
        for key in ("new_package_boot_tested", "runtime_behavior_tested", "first_artifact_behavior_gate_passed"):
            for value in (True, 0, "false", None):
                scope = {**PACKAGING_SCOPE, key: value}
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_packaging_scope({"validation": scope})
        for scope in (None, {}, [], {**PACKAGING_SCOPE, "all_apis_usable": True}):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                validate_packaging_scope({"validation": scope})


if __name__ == "__main__":
    unittest.main()
