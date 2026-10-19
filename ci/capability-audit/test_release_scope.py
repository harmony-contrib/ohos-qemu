"""Approved exclusions are not fixes and cannot expand to unrelated APIs."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from release_scope import SCOPE, IMAGE_GENERATION, exclusion_record, exclusion_labels, PROVIDER_IDS
from verify_gap_closure import LEDGER, requirements

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from verify_first_artifact_gate import verified_payload


class ReleaseScopeTests(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads(LEDGER.read_text())

    def test_original_ledger_remains_immutable(self):
        self.assertEqual(hashlib.sha256(LEDGER.read_bytes()).hexdigest(),
                         'ac9426982dff3d7cb80050a6815eae92afb8f77c027b2d4319bc8d9423d6e93c')

    def test_only_user_decided_features_and_no_broad_ArkUI_or_storage_exclusion(self):
        for device, count in (('phone', 19), ('2in1', 17)):
            expected = requirements(self.baseline['devices'][device])
            result = exclusion_record(device, expected)
            self.assertEqual(result['count'], count)
            self.assertEqual(set(result['features']), set(exclusion_labels(device)) - {'ArkTS Static'})
            unsupported = result['unsupported_public_providers']
            self.assertEqual(unsupported['status'], 'unsupported_not_fixed_not_runtime_validated')
            for row in unsupported['features'].values():
                self.assertIn(row['id'], PROVIDER_IDS.values())
                self.assertIs(row['repaired'], False); self.assertIs(row['runtime_pass'], False)
            self.assertEqual(set(result['features']['imageGeneration']), IMAGE_GENERATION)
            self.assertEqual(len(expected), len(set(expected) - set(result['ids'])) + count)
            self.assertNotIn('behavior:api26-runtime-export-mismatches-phone', result['ids'])
            self.assertEqual(result['status'], 'excluded_by_user_not_fixed_not_validated')

    def test_changed_audit_and_unknown_profile_fail_closed(self):
        with self.assertRaises(ValueError): exclusion_record('watch', [])
        with self.assertRaises(ValueError): exclusion_record('phone', [])

    def test_gate_recomputes_exact_scope_and_keeps_every_other_requirement(self):
        # Structural fixture only: not archive/guest acceptance.
        identity = {'sha256': 'a' * 64}
        environment = {'boot_id': 'fixture', 'device_type': 'phone'}
        expected = requirements(self.baseline['devices']['phone'])
        exclusions = exclusion_record('phone', expected)
        retained = set(expected) - set(exclusions['ids'])
        payload = {'schema_version': 2, 'scope': SCOPE, 'status': 'pass',
                   'boot_id': 'fixture', 'archive_sha256': identity['sha256'], 'unresolved': [],
                   'original_expected_count': len(expected), 'expected_count': len(retained),
                   'closed_count': len(retained), 'closed': {key: {} for key in retained},
                   'release_exclusions': exclusions, 'excluded': exclusion_labels('phone'),
                   'audit_baseline_sha256': hashlib.sha256(LEDGER.read_bytes()).hexdigest()}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'structural-fixture.json'
            identity['archive'] = str(Path(folder) / 'missing-fixture-archive.tar.gz')
            path.write_text(json.dumps(payload))
            # Isolate scope validation while requiring delegation to the raw
            # archive/boot verifier. These empty closure rows are not evidence.
            with mock.patch('verify_gap_closure.verify_evidence') as raw:
                verified_payload('cxx-arkts11-gaps', path, identity, environment)
                raw.assert_called_once_with(payload, Path(identity['archive']),
                                            path.parent / 'boot/boot.json', path.parent, 'phone')
                raw.reset_mock()
                for kind in ('missing-required', 'extra-exclusion', 'claim-excluded-fixed', 'old-scope', 'changed-policy'):
                    value = copy.deepcopy(payload)
                    if kind == 'missing-required': value['closed'].pop(next(iter(retained)))
                    elif kind == 'extra-exclusion': value['release_exclusions']['ids'].append('behavior:unrelated')
                    elif kind == 'claim-excluded-fixed': value['closed'][exclusions['ids'][0]] = {}
                    elif kind == 'old-scope': value['scope'] = 'complete_audited_Cxx_ArkTS11_gap_closure'
                    else: value['release_exclusions']['policy_sha256'] = '0' * 64
                    path.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        verified_payload('cxx-arkts11-gaps', path, identity, environment)
                    raw.assert_not_called()
            path.write_text(json.dumps(payload))
            with self.assertRaises((ValueError, OSError)):
                verified_payload('cxx-arkts11-gaps', path, identity, environment)


if __name__ == '__main__':
    unittest.main()
