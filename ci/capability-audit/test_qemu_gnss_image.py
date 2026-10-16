"""Inventory trust mutations only; real ELF/image tests use external build outputs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_qemu_gnss_image as M


class GnssInventoryTests(unittest.TestCase):
    def fixture(self, directory):
        for name in M.LIBRARIES:
            (directory / name).write_bytes(b'explicit synthetic inventory fixture ONLY, never an accepted ELF')
        for name, original in [('init.json', 'qemu_gnss_input.cfg'), ('gnss.para', 'qemu_gnss.para')]:
            (directory / name).write_text(M.FILES[M.DIRECTORY + original])
        return {'schema_version': 1, 'product': 'arm64_virt', 'recipe': M.recipe(),
                'source_sha256': M.source_hashes(), 'GN_sha256': {n: 'a' * 64 for n in M.GRAPHS},
                'files_sha256': {p.name: M.sha(p) for p in directory.iterdir()},
                'first_artifact_behavior_gate_passed': False}

    def test_source_graph_recipe_and_schema_must_remain_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            value = self.fixture(directory)
            # Explicitly isolate inventory validation. Real ELF validation is
            # never bypassed by the production path or claimed by this test.
            with patch.object(M, 'elf'):
                M.check_inventory(value, 'arm64_virt', directory)
                for mode in ('source', 'graph', 'recipe', 'schema', 'runtime'):
                    broken = copy.deepcopy(value)
                    if mode == 'source': broken['source_sha256'] = {}
                    if mode == 'graph': broken['GN_sha256'] = {}
                    if mode == 'recipe': broken['recipe'] = {}
                    if mode == 'schema': broken['schema_version'] = True
                    if mode == 'runtime': broken['first_artifact_behavior_gate_passed'] = True
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        M.check_inventory(broken, 'arm64_virt', directory)

    def test_file_mutation_and_wrong_standalone_mode_fail_even_with_rehashed_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            value = self.fixture(directory)
            with patch.object(M, 'elf'):
                (directory / 'gnss.para').write_bytes(b'const.location.supl_mode=2\n')
                with self.assertRaises(ValueError): M.check_inventory(value, 'arm64_virt', directory)
                value['files_sha256']['gnss.para'] = M.sha(directory / 'gnss.para')
                with self.assertRaises(ValueError): M.check_inventory(value, 'arm64_virt', directory)
            with self.assertRaises(ValueError): M.elf(directory / 'provider.so', 'arm64_virt', True)


if __name__ == '__main__': unittest.main()
