"""Signer adapter argv/scope fixtures, never HAP or guest validation evidence."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from sign_qemu_test_hap import BUNDLE, signing_command


class QemuTestHapSignerTests(unittest.TestCase):
    def test_only_exact_normal_bundle_concrete_udid_and_fixed_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unsigned = root / 'unsigned.hap'
            unsigned.write_bytes(b'fixture, not a real HAP')
            args = argparse.Namespace(unsigned=unsigned, output=root / 'signed.hap',
                bundle_name=BUNDLE, device_id='a' * 64, compatible_version='17', force=True)
            command = signing_command(args)
            self.assertEqual(command[-2:], ['--sign-code', '1'])
            self.assertIn('/work/ci/capability-audit/sign_web_probe.py', command)
            self.assertIn('type=volume,src=ohos-qemu-7_0-release-source,dst=/ohos,readonly', command)
            for key, value in (('bundle_name', 'system.bundle'), ('device_id', '*'),
                               ('compatible_version', '26'), ('force', False)):
                original = getattr(args, key)
                setattr(args, key, value)
                with self.assertRaises(ValueError):
                    signing_command(args)
                setattr(args, key, original)
            args.output = unsigned
            with self.assertRaises(ValueError):
                signing_command(args)


if __name__ == '__main__':
    unittest.main()
