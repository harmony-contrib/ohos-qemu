"""Source graph composition and existing signer policy; not guest acceptance."""
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'patches/lib'))
import mms_provider as M


class MmsSourceProvider(unittest.TestCase):
    def test_real_pinned_profile_changes_only_public_OS_leaf_and_expiry(self):
        fixtures = ROOT / 'ci/capability-audit/fixtures/mms_source_provider'
        row = json.loads((fixtures / 'provenance.json').read_text())['files']['signature/mms.p7b']
        data = gzip.decompress(base64.b64decode((fixtures / row['file']).read_bytes()))
        self.assertEqual(hashlib.sha256(data).hexdigest(), M.PROFILE_SHA)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.p7b';path.write_bytes(data)
            original = M.cms(path)
        leaf = (fixtures / 'os-application-leaf.pem').read_bytes()
        result = M.desired_profile(original, leaf)
        self.assertEqual(result['bundle-info']['apl'], 'normal')
        result['bundle-info']['distribution-certificate'] = original['bundle-info']['distribution-certificate']
        result['validity']['not-after'] = original['validity']['not-after']
        self.assertEqual(result, original)
        for field, value in (('apl', 'system_core'), ('bundle-name', 'other.bundle')):
            broken = copy.deepcopy(original);broken['bundle-info'][field] = value
            with self.assertRaises(ValueError): M.desired_profile(broken, leaf)

    def test_full_HAP_stack_replays_and_unknown_successor_fails_without_mutation(self):
        fixture = ROOT / 'ci/capability-audit/fixtures/batch_apps/admin_provider/hap-pristine.json'
        pristine = json.loads(fixture.read_text())
        data = gzip.decompress(base64.b64decode(pristine['gzip_base64']))
        self.assertEqual(hashlib.sha256(data).hexdigest(), pristine['sha256'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'applications/standard/hap/BUILD.gn';path.parent.mkdir(parents=True);path.write_bytes(data)
            components = ['calendar_provider', 'photos_provider', 'settings_provider', 'admin_provider', 'mms_provider']
            for cycle in range(3):
                for name in components:
                    result = subprocess.run(['bash', str(ROOT / 'patches/common/applications/standard/hap' / name / 'apply.sh'),
                                             '--source-root', str(root)], capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            changed = path.read_bytes() + b'\n# unknown edit\n';path.write_bytes(changed)
            for name in ('admin_provider', 'mms_provider'):
                result = subprocess.run(['bash', str(ROOT / 'patches/common/applications/standard/hap' / name / 'apply.sh'),
                                         '--source-root', str(root)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(path.read_bytes(), changed)

    def test_source_unsigned_build_preserves_original_profile_and_rejects_partial_state(self):
        fixtures = ROOT / 'ci/capability-audit/fixtures/mms_source_provider'
        provenance = json.loads((fixtures / 'provenance.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for name, row in provenance['files'].items():
                data = gzip.decompress(base64.b64decode((fixtures / row['file']).read_bytes()))
                self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
                target = root / M.PROJECT / name;target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(data)
            profile = root / M.PROJECT / 'signature/mms.p7b';before = profile.read_bytes()
            argv = ['bash', str(ROOT / 'patches/common/applications/standard/mms/source_provider/apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                result = subprocess.run(argv, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(profile.read_bytes(), before)
            (root / M.PROJECT / 'BUILD.gn').unlink()
            build_profile = root / M.PROJECT / 'build-profile.json5';changed = build_profile.read_bytes()
            self.assertNotEqual(subprocess.run(argv, capture_output=True).returncode, 0)
            self.assertEqual(build_profile.read_bytes(), changed)
            self.assertFalse((root / M.PROJECT / 'BUILD.gn').exists())

    def test_signer_rebinding_preserves_grants_and_rejects_unknown_privilege_or_signer(self):
        for expected in (M.CAPABILITY, M.GRANTS):
            original = [dict(bundleName='other', app_signature=['other']), copy.deepcopy(expected)]
            result = json.loads(M.policy(json.dumps(original).encode(), expected))
            self.assertEqual(result[0], original[0])
            self.assertEqual(result[1], dict(expected, app_signature=[M.SIGNATURE]))
            self.assertEqual(json.loads(M.policy(json.dumps(result).encode(), expected)), result)
            for row in (dict(expected, app_signature=['*']), dict(expected, app_signature=[M.OLD_SIGNER, M.SIGNATURE]),
                        dict(expected, arbitraryPrivilege=True)):
                with self.assertRaises(ValueError): M.policy(json.dumps([row]).encode(), expected)
            with self.assertRaises(ValueError): M.policy(json.dumps([expected, expected]).encode(), expected)

    def test_BMS_boolean_policy_fields_reject_numeric_lookalikes(self):
        for field, numeric in (('singleton', 1), ('keepAlive', 0)):
            row = copy.deepcopy(M.CAPABILITY);row[field] = numeric
            with self.subTest(field=field), self.assertRaises(ValueError):
                M.policy(json.dumps([row]), M.CAPABILITY)
        for index in range(len(M.GRANTS['permissions'])):
            row = copy.deepcopy(M.GRANTS)
            row['permissions'][index]['userCancellable'] = int(row['permissions'][index]['userCancellable'])
            with self.subTest(index=index), self.assertRaises(ValueError):
                M.policy(json.dumps([row]), M.GRANTS)

    def test_actual_BMS_install_selection_requires_the_unique_original_directory(self):
        entry = {'app_dir': '/system/app/com.ohos.mms', 'removable': False}
        self.assertEqual(M.install_entry(json.dumps({'install_list': [entry]})), entry)
        for rows in ([], [dict(entry, removable=True)], [dict(entry, removable=0)], [entry, entry],
                     [dict(entry, app_dir='/system/app/Mms')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                M.install_entry(json.dumps({'install_list': rows}))


if __name__ == '__main__': unittest.main()
