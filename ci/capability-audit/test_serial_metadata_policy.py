"""Exact fixed policy transformation units, not enforcing/device acceptance."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / 'patches/2in1/base/security/selinux_adapter/serial_metadata/check.py'
SPEC = importlib.util.spec_from_file_location('serial_metadata_guard', GUARD)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ORIGINAL = (Path(__file__).parent / 'fixtures/serial_service.fixed-cfc1d5b3.te').read_bytes()


class SerialMetadataPolicyTest(unittest.TestCase):
    def test_exact_fixed_input_hash(self):
        self.assertEqual(hashlib.sha256(ORIGINAL).hexdigest(), MODULE.ORIGINAL_SHA256)
        self.assertEqual(len(MODULE.REVISION), 40)

    def test_only_serial_tty_metadata_permission_changes(self):
        patched = MODULE.repaired(ORIGINAL)
        self.assertEqual(patched.replace(MODULE.NEW, MODULE.OLD), ORIGINAL)
        self.assertEqual(patched.count(MODULE.NEW), 1)
        self.assertEqual(len(patched) - len(ORIGINAL), len(b'getattr '))
        for subject in (b'hap_domain', b'root', b'domain'):
            self.assertEqual(patched.count(b'allow ' + subject + b' '), ORIGINAL.count(b'allow ' + subject + b' '))

    def test_refuses_foreign_edits_or_already_patched_as_original(self):
        for value in (ORIGINAL + b'\n# user changes\n', ORIGINAL.replace(b'lock ioctl', b'lock ioctl execute'),
                      MODULE.repaired(ORIGINAL), b''):
            with self.assertRaises(ValueError):
                MODULE.repaired(value)

    def test_fixed_numbered_patch_contains_no_extra_grants(self):
        patch = (GUARD.parent / '0001-allow-serial-domain-attachment-metadata.patch').read_text()
        additions = [line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(additions, [MODULE.NEW.decode()])


if __name__ == '__main__':
    unittest.main()
