"""Replay the real two-component MSDP stack; reject incomplete successors."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import batch_system_public_still as batch


def guard(name):
    spec = importlib.util.spec_from_file_location('msdp_' + name, batch.COMPONENT.parent / name / 'apply.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class MsdpSourceComposition(unittest.TestCase):
    def test_complete_stack_replays_and_rejects_changed_companion(self):
        old, new = guard('sensor_input'), guard('public_still')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve();batch.materialize(root)
            new.apply(root)
            for _ in range(3):
                self.assertEqual(old.apply(root)['status'], 'already_applied')
                self.assertEqual(new.apply(root)['status'], 'already_applied')
            path = root / 'base/msdp/device_status/libs/include/algorithm/algo_base.h'
            changed = path.read_bytes() + b'\n// unknown companion\n';path.write_bytes(changed)
            for module in (old, new):
                with self.assertRaises(ValueError):module.apply(root)
                self.assertEqual(path.read_bytes(), changed)


if __name__ == '__main__':unittest.main()
