"""Deny old/partial attestation and role forgery; fixtures are never guest gates."""
import copy
import json
from pathlib import Path
import unittest
import tempfile
from insight_contract_common import EVIDENCE_SCOPE, identity
from build_insight_navigation_probe import BUNDLE
from verify_insight_contract_evidence import verify_evidence

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/insight_navigation_bms_identity.json').read_text())


class InsightContractEvidenceTests(unittest.TestCase):
    def test_captured_three_role_bms_identity_requires_actual_bundle_apl_and_account(self):
        for role, value in FIXTURE['roles'].items():
            text = BUNDLE + ':\n' + json.dumps(value)
            self.assertEqual(identity(text, BUNDLE, role), value['applicationInfo']['uid'])
            for field, replacement in (('uid', 0), ('uid', True), ('bundleName', 'other.bundle'),
                    ('isSystemApp', role == 'normal'), ('appPrivilegeLevel', 'system_basic')):
                changed = copy.deepcopy(value); changed['applicationInfo'][field] = replacement
                with self.subTest(role=role, field=field), self.assertRaises(ValueError):
                    identity(json.dumps(changed), BUNDLE, role)

    def test_diagnostic_partial_or_foreign_scope_never_registers_seven_contracts(self):
        for status, scope in (('collected_diagnostic_only', 'old_R44_diagnostic_NOT_gate'),
                ('pass', 'old_R44_diagnostic_NOT_gate'), ('fail', EVIDENCE_SCOPE), ('pass', 'metadata_only')):
            with self.subTest(status=status, scope=scope), self.assertRaises(ValueError):
                verify_evidence(dict(status=status, scope=scope), 'a' * 64,
                    '11111111-1111-1111-1111-111111111111', 'arm64', 'phone', '127.0.0.1:12345')

    def test_self_reported_complete_data_without_actual_commands_is_rejected(self):
        from run_insight_contract_probe import OWNED_BUNDLES
        document=dict(status='pass',scope=EVIDENCE_SCOPE,archive_sha256='a'*64,
            boot_id='11111111-1111-1111-1111-111111111111',arch='arm64',device='phone',
            target='127.0.0.1:12345',udid='b'*64,failures=[],caller_cleanup_verified=True,
            cleanup={bundle:dict(process_absent=True) for bundle in OWNED_BUNDLES},commands=[])
        with self.assertRaisesRegex(ValueError,'actual intent command journal required'):
            verify_evidence(document,document['archive_sha256'],document['boot_id'],
                document['arch'],document['device'],document['target'])

    def test_ledger_rejects_diagnostic_assisted_and_foreign_boot_even_for_passing_child(self):
        from verify_gap_closure import behavior_results
        archive = 'a' * 64; boot_id = '11111111-1111-1111-1111-111111111111'
        for change in ('diagnostic', 'assisted', 'foreign'):
            with tempfile.TemporaryDirectory() as directory:
                runtime = Path(directory)
                (runtime / 'insight-contract').mkdir(); (runtime / 'boot').mkdir()
                child = dict(status='pass', archive_sha256=archive, boot_id=boot_id)
                (runtime / 'insight-contract/evidence.json').write_text(json.dumps(child))
                boot = dict(status='pass', purpose='acceptance', scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                    archive_sha256=archive, test_environment=dict(boot_id=boot_id, external_keepalive=False,
                        device_type='phone', guest_arch='arm64', target='fixture'))
                if change == 'diagnostic': boot['purpose'] = 'diagnostic'
                elif change == 'assisted': boot['diagnostic_assistance'] = True
                else: boot['archive_sha256'] = 'b' * 64
                (runtime / 'boot/boot.json').write_text(json.dumps(boot))
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'unchanged fresh acceptance package'):
                    behavior_results(runtime, boot_id, archive, 'phone')


if __name__ == '__main__':
    unittest.main()
