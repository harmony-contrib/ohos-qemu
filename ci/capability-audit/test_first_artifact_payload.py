"""Reject fabricated outer pass claims; synthetic fixtures are not real boots."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from verify_first_artifact_gate import verified_payload


class FirstArtifactPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'payload.json'
        self.identity = {'sha256': 'a' * 64, 'build_inputs_tree_sha256': 'b' * 64}
        self.environment = {'boot_id': '12345678-1234-1234-1234-123456789abc',
                            'target': 'fixture', 'guest_arch': 'arm64', 'device_type': 'phone'}

    def reject(self, name, payload):
        self.path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            verified_payload(name, self.path, self.identity, self.environment)

    def test_generic_text_or_pass_document_cannot_satisfy_any_required_behavior(self):
        for name in ('boot', 'arkweb', 'vulkan', 'native-bindings-e2e', 'cxx-arkts11-gaps',
                     'issue20-library-exit', 'power-suspend', 'serial', 'certificate-manager', 'rs-objects', 'application-home', 'photos-asset', 'settings-navigation'):
            self.reject(name, {'status': 'pass'})
        self.path.write_text('a command printed success; no actual behavior proof')
        with self.assertRaises(ValueError):
            verified_payload('boot', self.path, self.identity, self.environment)

    def test_old_assisted_or_short_boot_rejected(self):
        payload = {'status': 'pass', 'scope': 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
            'purpose': 'acceptance', 'test_environment': {**self.environment, 'external_keepalive': False},
            'archive_sha256': self.identity['sha256'],
            'build_inputs_tree_sha256': self.identity['build_inputs_tree_sha256'],
            'kernel_boot_id_unchanged': True,
            'stable_seconds_without_external_keepalive': 60}
        # This old clockless synthetic fixture no longer satisfies real boot
        # acceptance. Clock/raw-helper semantics have their own complete tests.
        self.reject('boot', payload)
        with patch('watchdog_boot_clocks.verify'):
            self.path.write_text(json.dumps(payload))
            verified_payload('boot', self.path, self.identity, self.environment)
            for key, value in (('purpose', 'diagnostic'), ('archive_sha256', 'c' * 64),
                               ('stable_seconds_without_external_keepalive', 30)):
                self.reject('boot', {**payload, key: value})
            self.reject('boot', {**payload, 'test_environment': {**self.environment, 'external_keepalive': True}})

    def test_full_original_ledger_summary_without_any_raw_child_is_refused(self):
        from verify_gap_closure import LEDGER, requirements
        from release_scope import SCOPE, exclusion_record
        from run_root_probe import digest
        baseline = requirements(json.loads(LEDGER.read_text())['devices']['phone'])
        exclusions = exclusion_record('phone', baseline)
        expected = set(baseline) - set(exclusions['ids'])
        archive = self.path.parent / 'synthetic.tar.gz'; archive.write_bytes(b'unit archive')
        self.identity.update(archive=str(archive), sha256=digest(archive))
        boot = self.path.parent / 'boot/boot.json'; boot.parent.mkdir()
        boot.write_text(json.dumps({'status': 'pass', 'purpose': 'acceptance',
            'archive_sha256': self.identity['sha256'],
            'test_environment': {**self.environment, 'external_keepalive': False}}))
        self.reject('cxx-arkts11-gaps', dict(schema_version=2, status='pass', scope=SCOPE,
            archive_sha256=self.identity['sha256'], boot_id=self.environment['boot_id'],
            original_expected_count=len(baseline), release_exclusions=exclusions,
            excluded=['ArkTS Static', 'CloudSync', 'imageGeneration'], unresolved=[],
            expected_count=len(expected), closed_count=len(expected), audit_baseline_sha256=digest(LEDGER),
            closed={key: {'evidence': '/missing/old-guest.json', 'sha256': '0' * 64} for key in expected}))

    def test_fake_small_ledger_and_omitted_vulkan_WSI_are_not_full_closure(self):
        base = {'status': 'pass', 'boot_id': self.environment['boot_id'],
                'archive_sha256': self.identity['sha256']}
        self.reject('cxx-arkts11-gaps', {**base, 'scope': 'complete_audited_Cxx_ArkTS11_gap_closure',
            'unresolved': [], 'expected_count': 1, 'closed_count': 1, 'closed': {'behavior:one-sample': {}}})
        self.reject('vulkan', {**base, 'results': {'vulkan-device': {'status': 'pass'}}})


if __name__ == '__main__':
    unittest.main()
