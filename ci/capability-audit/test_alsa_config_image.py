"""ALSA package verifier fixtures are not audio behavior evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
from verify_alsa_config_image import INVENTORY, check_file, validate_inventory, verify_image


class AlsaConfigImageTests(unittest.TestCase):
    def test_full_package_verifier_requires_alsa_closure_without_runtime_claim(self):
        script = (REPO / 'scripts/verify_device_type_package.sh').read_text()
        start = script.index('VENDOR_IMG="${PACKAGE}/images/vendor.img"')
        end = script.index('VIBRATOR_FOUND=', start)
        block = script[start:end]
        self.assertIn('if [ -n "${REQUIRE_FULL_DEVICE}" ]; then', block)
        self.assertIn('"${SCRIPT_DIR}/verify_alsa_config_image.py"', block)
        self.assertIn('--vendor-image "${VENDOR_IMG}" --machine "${ELF_MACHINE}"', block)
        self.assertIn('FAIL=1', block)
        self.assertIn('offline only, not audio behavior', block)

    def test_pinned_complete_inventory_and_unsafe_entries(self):
        complete = json.loads(INVENTORY.read_text())
        self.assertEqual(len(validate_inventory(complete)), 79)
        for key, value in (('source_revision', 'master'), ('manifest_revision', 'master'),
                           ('runtime_directory', '/data/local/tmp')):
            broken = copy.deepcopy(complete)
            broken[key] = value
            with self.assertRaises(ValueError): validate_inventory(broken)
        for name in ('../../alsa.conf', '/alsa.conf', 'x/../alsa.conf', 'evil.conf;id'):
            broken = copy.deepcopy(complete)
            broken['files'][name] = broken['files'].pop('cards/ENS1371.conf')
            with self.assertRaises(ValueError): validate_inventory(broken)
        broken = copy.deepcopy(complete)
        del broken['files']['cards/ENS1370.conf']
        with self.assertRaises(ValueError): validate_inventory(broken)

    def test_missing_empty_or_mismatched_config_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'alsa.conf'
            expected = hashlib.sha256(b'fixture only').hexdigest()
            with self.assertRaises(ValueError): check_file(target, expected)
            target.write_bytes(b'')
            with self.assertRaises(ValueError): check_file(target, expected)
            target.write_bytes(b'fixture only')
            self.assertEqual(check_file(target, expected), expected)
            target.write_bytes(b'changed')
            with self.assertRaises(ValueError): check_file(target, expected)

    def test_debugfs_zero_exit_with_no_dump_is_not_success(self):
        with patch('verify_alsa_config_image.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'no ALSA config'):
                verify_image(Path('/fixture/vendor.img'), 183, json.loads(INVENTORY.read_text()), 'debugfs-fixture')
            self.assertEqual(run.call_count, 2)
            self.assertTrue(all(call.kwargs['check'] for call in run.call_args_list))


if __name__ == '__main__':
    unittest.main()
