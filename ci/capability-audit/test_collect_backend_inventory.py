"""Collector contract fixtures, not new-package runtime evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from collect_backend_inventory import QUERIES, collect
from verify_gap_closure import behavior_results


BOOT = '12345678-1234-1234-1234-123456789abc'


class Guest:
    def __init__(self, changed=False):
        self.calls = []
        self.changed = changed

    def healthy(self):
        pass

    def shell(self, script, label):
        self.calls.append((script, label))
        if script == 'cat /proc/sys/kernel/random/boot_id':
            return (BOOT if not self.changed or label.endswith('before') else
                    '87654321-1234-1234-1234-123456789abc') + '\n'
        return 'ABSENT\n'


class BackendInventoryTests(unittest.TestCase):
    def test_missing_hardware_is_diagnostic_and_never_closes_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guest = Guest()
            actual = collect(guest, root / 'backend-inventory', '0' * 64, BOOT)
            self.assertEqual(actual['status'], 'diagnostic_NOT_behavior_pass')
            self.assertFalse(actual['first_artifact_behavior_gate_passed'])
            self.assertTrue(actual['kernel_boot_id_unchanged'])
            self.assertEqual(len(actual['observations']), 4)
            self.assertEqual(len(guest.calls), 6)
            self.assertEqual(behavior_results(root, BOOT, '0' * 64), {})
            for row in actual['observations']:
                raw = Path(row['raw'])
                self.assertEqual(raw.read_text(), 'ABSENT\n')
                self.assertEqual(row['sha256'], hashlib.sha256(raw.read_bytes()).hexdigest())
            self.assertEqual(json.loads((root / 'backend-inventory/inventory.json').read_text()), actual)

    def test_boot_change_and_existing_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'inventory'
            with self.assertRaisesRegex(ValueError, 'exact owned new boot'):
                collect(Guest(changed=True), output, '0' * 64, BOOT)
            document = json.loads((output / 'inventory.json').read_text())
            self.assertNotIn('kernel_boot_id_unchanged', document)
            with self.assertRaises(FileExistsError):
                collect(Guest(), output, '0' * 64, BOOT)

    def test_only_fixed_read_only_queries_and_identity_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            for archive, boot in (('', BOOT), ('0' * 64, 'old-boot')):
                with self.assertRaises(ValueError):
                    collect(Guest(), Path(temporary) / 'inventory', archive, boot)
            text = '\n'.join(script for _, script in QUERIES)
            for forbidden in ('chmod', 'chown', 'echo ', 'power-shell', 'param set',
                              'setenforce', 'hidumper', '>>', 'rm ', 'kill ', 'mkdir '):
                self.assertNotIn(forbidden, text)
            for path in ('/sys/class/thermal/', '/sys/class/net/', '/sys/class/bluetooth',
                         '/vendor/etc/thermal_config/', '/system/etc/thermal_config/'):
                self.assertIn(path, text)
            suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
            self.assertIn("collect_backend_inventory(guest, work / 'backend-inventory'", suite)
            self.assertLess(suite.index('collect_backend_inventory(guest,'),
                            suite.index("'build-actual-whole-Native-ABI-caller'"))


if __name__ == '__main__':
    unittest.main()
