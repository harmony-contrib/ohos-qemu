"""Inventory rejection tests only; synthetic bytes never prove native behavior."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_qemu_msdp_image as M


class MsdpImageInventory(unittest.TestCase):
    def test_source_features_graph_units_and_payload_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for filename in M.LIBRARIES.values():(root / filename).write_bytes(b'synthetic metadata test, NOT ELF')
            value = {'schema_version': 1, 'product': 'arm64_virt', 'source_sha256': M.source_hashes(),
                     'recipe': M.recipe(), 'features': dict(M.EXPECTED), 'first_artifact_behavior_gate_passed': False,
                     'files_sha256': {p.name: M.file_sha256(p) for p in root.iterdir()},
                     'graphs': {name: {'sha256': 'a'*64, 'objects_sha256': {u: 'b'*64 for u in units},
                                      'compile_commands': {u: 'actual diagnostic fixture -c input -o output' for u in units},
                                      'cross_dso_cfi': True} for name, units in M.UNITS.items()}}
            with patch.object(M, 'elf'):
                M.check_inventory(value, 'arm64_virt', root)
                for case in ('source', 'recipe', 'sensor', 'mock', 'numeric', 'graph', 'object', 'command', 'cfi', 'extra'):
                    broken = copy.deepcopy(value)
                    if case in ('source', 'recipe'):broken['source_sha256' if case == 'source' else case] = {}
                    elif case == 'sensor':broken['features']['device_status_sensor_enable'] = False
                    elif case == 'mock':broken['features']['device_status_allow_mock_fallback'] = True
                    elif case == 'numeric':broken['features']['device_status_sensor_enable'] = 1
                    elif case == 'graph':broken['graphs']['algo']['sha256'] = ''
                    elif case == 'object':broken['graphs']['algo']['objects_sha256'].pop(next(iter(M.UNITS['algo'])))
                    elif case == 'command':broken['graphs']['service']['compile_commands'] = {}
                    elif case == 'cfi':broken['graphs']['service']['cross_dso_cfi'] = 1
                    else:broken['files_sha256']['unbound.so'] = 'c'*64
                    with self.subTest(case=case), self.assertRaises(ValueError):M.check_inventory(broken, 'arm64_virt', root)
                (root / M.LIBRARIES['algo']).write_bytes(b'tamper')
                with self.assertRaises(ValueError):M.check_inventory(value, 'arm64_virt', root)
            with self.assertRaises(ValueError):M.elf(root / M.LIBRARIES['service'], 'arm64_virt', True)


if __name__ == '__main__':unittest.main()
