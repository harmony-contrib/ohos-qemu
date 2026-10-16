"""Pinned real profiles and original typed Contacts/Wallpaper install policy."""
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'patches/lib'))
import contacts_theme_providers as P


class ContactsThemeProfiles(unittest.TestCase):
    def test_real_profiles_preserve_every_field_except_existing_OS_leaf_and_expiry(self):
        fixtures = ROOT / 'ci/capability-audit/fixtures/contacts_theme_profiles'
        rows = json.loads((fixtures / 'provenance.json').read_text())
        leaf = (ROOT / 'ci/capability-audit/fixtures/mms_source_provider/os-application-leaf.pem').read_bytes()
        for name, config in P.PROFILES.items():
            raw = gzip.decompress(base64.b64decode((fixtures / rows[name]['fixture']).read_bytes()))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), config['sha256'])
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'original.p7b';path.write_bytes(raw)
                original = P.cms(path)
            desired = P.desired_profile(original, leaf, config)
            self.assertEqual(desired['bundle-info']['apl'], config['apl'])
            desired['bundle-info']['distribution-certificate'] = original['bundle-info']['distribution-certificate']
            desired['validity']['not-after'] = original['validity']['not-after']
            self.assertEqual(desired, original)
            for field, value in (('apl', 'system_core'), ('bundle-name', 'wrong.bundle'),
                                 ('app-feature', 'normal')):
                broken = copy.deepcopy(original);broken['bundle-info'][field] = value
                with self.subTest(name=name, field=field), self.assertRaises(ValueError):
                    P.desired_profile(broken, leaf, config)

    def test_contacts_grants_preserve_all_existing_policy_and_reject_type_or_privilege_changes(self):
        for expected in P.POLICIES.values():
            original = [{'bundleName': 'unrelated', 'unchanged': True}, copy.deepcopy(expected)]
            actual = json.loads(P.policy(json.dumps(original), expected))
            self.assertEqual(actual[0], original[0])
            self.assertEqual(actual[1], dict(expected, app_signature=[P.SIGNATURE]))
            self.assertEqual(json.loads(P.policy(json.dumps(actual), expected, True)), actual)
            for row in (dict(expected, app_signature=['*']), dict(expected, extraPrivilege=True)):
                with self.assertRaises(ValueError):P.policy(json.dumps([row]), expected)
            with self.assertRaises(ValueError):P.policy(json.dumps([expected, expected]), expected)
            if 'permissions' in expected:
                for index in range(len(expected['permissions'])):
                    row = copy.deepcopy(expected);row['permissions'][index]['userCancellable'] = 0
                    with self.assertRaises(ValueError):P.policy(json.dumps([row]), expected)
            else:
                for key in ('singleton', 'keepAlive'):
                    row = copy.deepcopy(expected);row[key] = int(row[key])
                    with self.assertRaises(ValueError):P.policy(json.dumps([row]), expected)

    def test_wallpaper_original_removability_is_true_and_numeric_lookalikes_fail(self):
        for name, config in P.PROFILES.items():
            good = {'app_dir': '/system/app/' + config['bundle'], 'removable': config['removable']}
            self.assertEqual(P.entry(json.dumps({'install_list': [good]}), config['bundle'], config['removable']), good)
            for value in (int(config['removable']), not config['removable']):
                broken = dict(good, removable=value)
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    P.entry(json.dumps({'install_list': [broken]}), config['bundle'], config['removable'])
            with self.assertRaises(ValueError):P.entry(json.dumps({'install_list': [good]}), config['bundle'], 1)


if __name__ == '__main__':unittest.main()
