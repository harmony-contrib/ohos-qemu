"""Inventory mutation tests only; ELF/image integration uses actual external evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_qemu_runtime_assets_image as M


class RuntimeAssetInventoryTests(unittest.TestCase):
    def test_inventory_rejects_stale_recipe_source_feature_and_unbound_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'sensor.so').write_bytes(b'explicit synthetic inventory fixture, not an ELF')
            name = 'vendor/ohemu/virt/etc/qemu_sensor_input.cfg'
            (root / 'sensor-init.json').write_text(M.SENSOR_FILES[name])
            (root / 'resource.json').write_bytes(M.contract(None))
            value = {'schema_version': 1, 'product': 'arm64_virt', 'recipe': M.recipe(),
                'source_sha256': M.source_hashes(), 'features': dict(M.EXPECTED), 'sensor_GN_sha256': '1' * 64,
                'calendar': {'asset_sha256': None, 'source': None}, 'first_artifact_behavior_gate_passed': False,
                'files_sha256': {p.name: M.file_sha256(p) for p in root.iterdir()}}
            # This test concerns inventory trust only. It never accepts the
            # synthetic file as a real Sensor DSO or a package capability.
            with patch.object(M, 'elf'):
                M.check_inventory(value, 'arm64_virt', root)
                for mode in ('recipe', 'source', 'feature-value', 'boolean-type', 'extra-asset', 'graph'):
                    broken = copy.deepcopy(value)
                    if mode == 'recipe': broken['recipe'] = {}
                    elif mode == 'source': broken['source_sha256'] = {}
                    elif mode == 'feature-value': broken['features']['device_status_allow_mock_fallback'] = True
                    elif mode == 'boolean-type': broken['features']['drivers_peripheral_sensor_feature_community'] = 1
                    elif mode == 'extra-asset': broken['files_sha256']['holidays.ics'] = 'a' * 64
                    else: broken['sensor_GN_sha256'] = ''
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        M.check_inventory(broken, 'arm64_virt', root)
                (root / 'sensor-init.json').write_text('modified init')
                with self.assertRaises(ValueError):
                    M.check_inventory(value, 'arm64_virt', root)

    def test_a_regular_calendar_requires_matching_contract_and_source_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            name = 'vendor/ohemu/virt/etc/qemu_sensor_input.cfg'
            data = b'BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n'
            payloads = {'sensor.so': b'synthetic inventory only', 'sensor-init.json': M.SENSOR_FILES[name].encode(),
                        'resource.json': M.contract(data), 'holidays.ics': data}
            for name, content in payloads.items():
                (root / name).write_bytes(content)
            value = {'schema_version': 1, 'product': 'arm64_virt', 'recipe': M.recipe(),
                'source_sha256': M.source_hashes(), 'features': dict(M.EXPECTED), 'sensor_GN_sha256': 'a' * 64,
                'calendar': {'asset_sha256': hashlib.sha256(data).hexdigest(), 'source': 'labeled synthetic test input'},
                'first_artifact_behavior_gate_passed': False,
                'files_sha256': {p.name: M.file_sha256(p) for p in root.iterdir()}}
            with patch.object(M, 'elf'):
                M.check_inventory(value, 'arm64_virt', root)
                (root / 'holidays.ics').write_bytes(data + b'tampered')
                with self.assertRaises(ValueError):
                    M.check_inventory(value, 'arm64_virt', root)
                value['files_sha256']['holidays.ics'] = M.file_sha256(root / 'holidays.ics')
                with self.assertRaises(ValueError):
                    M.check_inventory(value, 'arm64_virt', root)


if __name__ == '__main__':
    unittest.main()
