#!/usr/bin/env python3
"""SceneBoard generated init config and source-built evidence regressions."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "patches/lib"))
sys.path.insert(0, str(REPO / "scripts"))
from sceneboard_profile import boot_unlock_configuration, configure_boot_unlock_publisher
from record_sceneboard_boot_unlock import validate


def cem(machine=183):
    data = bytearray(24)
    data[:4] = b"\x7fELF"
    data[18:20] = machine.to_bytes(2, "little")
    return bytes(data) + b"userId"


class SceneBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.etc = self.root / "vendor/ohemu/virt/etc"
        self.etc.mkdir(parents=True)
        (self.etc / "BUILD.gn").write_text('group("product_etc_conf") {\n  deps = [\n  ]\n}\n')

    def test_generated_config_and_evidence_all_three_abis(self):
        configure_boot_unlock_publisher(self.root, True)
        before = (self.etc / "BUILD.gn").read_text()
        config = json.loads((self.etc / "qemu_sceneboard_unlock.cfg").read_text())
        for machine in (183, 40, 62):
            validate(cem(machine), config, machine)
        configure_boot_unlock_publisher(self.root, True)
        self.assertEqual(before, (self.etc / "BUILD.gn").read_text())
        self.assertEqual(before.count('":qemu_sceneboard_unlock_cfg"'), 1)
        configure_boot_unlock_publisher(self.root, False)
        self.assertFalse((self.etc / "qemu_sceneboard_unlock.cfg").exists())
        self.assertNotIn("qemu_sceneboard_unlock", (self.etc / "BUILD.gn").read_text())

    def test_wrong_architecture_or_unpatched_publisher_fails(self):
        for data in (cem(40), cem().replace(b"userId", b"noUser"), b""):
            with self.assertRaises(ValueError):
                validate(data, boot_unlock_configuration(), 183)

    def test_service_routing_and_permissions_fail_closed(self):
        config = boot_unlock_configuration()
        for service in range(2):
            for field in config["services"][service]:
                bad = copy.deepcopy(config)
                del bad["services"][service][field]
                with self.subTest(service=service, field=field), self.assertRaises(ValueError):
                    validate(cem(), bad, 183)
        for bad in ([], [config["services"][0]] * 2):
            with self.assertRaises(ValueError):
                validate(cem(), {**config, "services": bad}, 183)

    def test_migrate_only_known_generated_legacy_config(self):
        legacy = json.dumps(boot_unlock_configuration()).replace("qemu_sceneboard", "qemu_2in1")
        path = self.etc / "qemu_2in1_unlock.cfg"
        path.write_text(legacy)
        configure_boot_unlock_publisher(self.root, True)
        self.assertFalse(path.exists())
        modified = json.loads(legacy)
        modified["services"][0]["uid"] = "root"
        path.write_text(json.dumps(modified))
        with self.assertRaises(SystemExit):
            configure_boot_unlock_publisher(self.root, True)
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
