"""Reject broader ACLs, unknown signers, duplicate rows and policy redirects."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'patches/lib'))
import admin_provider as M


class AdminPolicyTests(unittest.TestCase):
    def test_prepare_preserves_other_apps_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name in M.POLICIES:
                path = Path(temporary) / name
                other = {'bundleName': 'unrelated', 'app_signature': ['existing']}
                document = {'install_list': [other]} if name.startswith('install_list_capability') else [other]
                path.write_text(json.dumps(document))
                updated = M.policy_bytes(path, name, True)
                path.write_bytes(updated)
                self.assertEqual(updated, M.policy_bytes(path, name))
                entries = json.loads(updated)
                rows = entries['install_list'] if isinstance(entries, dict) else entries
                self.assertEqual(rows, [other, M.POLICIES[name]])

    def test_unknown_signer_extra_permission_and_duplicate_app_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name, expected in M.POLICIES.items():
                path = Path(temporary) / name
                bad_signer = {**expected, 'app_signature': ['*']}
                broader = {**expected, 'allowUnexpectedPrivilege': True}
                for rows in ([bad_signer], [broader], [expected, expected]):
                    document = {'install_list': rows} if name.startswith('install_list_capability') else rows
                    path.write_text(json.dumps(document))
                    with self.subTest(name=name, rows=rows), self.assertRaises(ValueError):
                        M.policy_bytes(path, name, True)

    def test_missing_and_redirected_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'policy.json'
            path.write_text('[]')
            with self.assertRaisesRegex(ValueError, 'missing'):
                M.policy_bytes(path, 'install_list_permissions.json')
            alias = path.with_name('alias.json')
            alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError, 'regular'):
                M.policy_bytes(alias, 'install_list_permissions.json', True)


if __name__ == '__main__':
    unittest.main()
