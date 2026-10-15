"""Nested parser fixtures only; these fixtures cannot attest a real VM boot."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_first_artifact_gate import verified_payload
from verify_native_graphics_results import verify


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FirstArtifactGLESTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.identity = {"sha256": "d" * 64}
        self.env = {"boot_id": "12345678-1234-1234-1234-123456789abc",
                    "guest_arch": "arm64", "device_type": "phone", "target": "fixture"}
        self.nonce = "a" * 32
        self.row = {"runId": self.nonce, "pid": 12, "uid": 0, "backend": "llvmpipe",
                    "glesVersions": [2, 3], "contextGenerations": 6, "shaderPrograms": 6,
                    "shaderPixels": 19507428, "pbufferPixels": 6, "swapCount": 6,
                    "teardownCount": 6, "patternHash": "123456789abcdef0",
                    "scope": "native_GLES_LLVM_shader_lifecycle", "compositorTested": False, "pass": True}
        (self.root / "stdout.jsonl").write_text(json.dumps(self.row) + "\n")
        (self.root / "stderr.txt").write_text("")
        self.child = {"status": "pass", "kind": "gles-llvm",
                      "scope": "isolated_root_probe_only_not_normal_app_or_full_capability_gate",
                      "archive_sha256": self.identity["sha256"], "boot_id": self.env["boot_id"],
                      "archive_binding": "actual_live_owned_boot_and_initial_full_archive_inventory",
                      "arch": "arm64", "device": "phone", "target": "fixture",
                      "kernel_boot_id_unchanged": True, "first_artifact_behavior_gate_passed": False,
                      "run_id": self.nonce, "probe_exit_code": 0,
                      "log_sha256": sha(self.root / "stdout.jsonl"),
                      "stderr_sha256": sha(self.root / "stderr.txt"),
                      "result": verify("gles-llvm", json.dumps(self.row), 0, self.nonce)}
        self.payload = {"status": "pass", "archive_sha256": self.identity["sha256"],
                        "boot_id": self.env["boot_id"], "results": {}}
        for kind in ("vulkan-device", "vulkan-headless", "vulkan-ohos-surface", "vulkan-window"):
            path = self.root / (kind + ".json")
            path.write_text(json.dumps({"status": "pass"}))
            self.payload["results"][kind] = {"evidence": str(path), "sha256": sha(path)}

    def evaluate(self):
        path = self.root / "gles-child.json"
        path.write_text(json.dumps(self.child))
        self.payload["results"]["gles-llvm"] = {"evidence": str(path), "sha256": sha(path)}
        parent = self.root / "graphics.json"
        parent.write_text(json.dumps(self.payload))
        return verified_payload("vulkan", parent, self.identity, self.env)

    def test_nested_raw_shader_contract_is_verified(self):
        self.evaluate()

    def test_stale_boot_nonce_wrong_recipe_scope_or_false_outer_pass_rejected(self):
        for key, value in (("boot_id", "old"), ("archive_sha256", "e" * 64),
                           ("run_id", "b" * 32), ("kernel_boot_id_unchanged", False),
                           ("scope", "static-only"), ("first_artifact_behavior_gate_passed", True)):
            original = self.child[key]
            self.child[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.evaluate()
            self.child[key] = original

    def test_changed_stderr_and_real_frame_registration_error_rejected(self):
        stderr = self.root / "stderr.txt"
        stderr.write_text("libunwind: bad fde: FDE is really a CIE\n")
        with self.assertRaises(ValueError):
            self.evaluate()
        self.child["stderr_sha256"] = sha(stderr)
        with self.assertRaisesRegex(ValueError, "registration"):
            self.evaluate()

    def test_changed_or_reduced_pixel_results_rejected_even_with_updated_hash(self):
        raw = self.root / "stdout.jsonl"
        raw.write_text(json.dumps({**self.row, "shaderPixels": 1}))
        self.child["log_sha256"] = sha(raw)
        with self.assertRaises(ValueError):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
