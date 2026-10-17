"""Constrain the Contacts seed profile; these fixtures are not crypto evidence."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from sign_web_probe import CONTACTS_SEED_BUNDLE, CONTACTS_SEED_PERMISSIONS, contacts_seed_module


class ContactsSeedSignerProfileTest(unittest.TestCase):
    def hap(self, root, *, bundle=CONTACTS_SEED_BUNDLE, permissions=None, kind='entry'):
        value = dict(app=dict(bundleName=bundle), module=dict(type=kind,
            requestPermissions=[dict(name=name) for name in
                                (sorted(CONTACTS_SEED_PERMISSIONS) if permissions is None else permissions)]))
        raw = json.dumps(value).encode()
        path = root / 'seed.hap'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('module.json', raw)
        return path, raw

    def test_only_exact_seed_and_permission_pair_are_eligible(self):
        with tempfile.TemporaryDirectory() as directory:
            path, raw = self.hap(Path(directory))
            self.assertEqual(contacts_seed_module(path), raw)
        for options in (dict(bundle='com.ohos.qemu.contactpickercaller'),
                        dict(permissions=[]), dict(permissions=['ohos.permission.READ_CONTACTS']),
                        dict(permissions=[*CONTACTS_SEED_PERMISSIONS, 'ohos.permission.MANAGE_VPN']),
                        dict(permissions=['ohos.permission.READ_CONTACTS'] * 2), dict(kind='feature')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                path, _ = self.hap(Path(directory), **options)
                with self.assertRaises(ValueError):
                    contacts_seed_module(path)

    def test_fa_and_duplicate_stage_payloads_are_rejected(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as directory:
                path, raw = self.hap(Path(directory))
                with zipfile.ZipFile(path, 'a') as archive:
                    archive.writestr('module.json' if duplicate else 'config.json', raw)
                with self.assertRaises(ValueError):
                    contacts_seed_module(path)


if __name__ == '__main__':
    unittest.main()
