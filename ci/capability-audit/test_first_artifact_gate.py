"""Evidence-contract unit fixtures; no fixture is real guest acceptance."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from snapshot_build_inputs import digest_files
from verify_first_artifact_gate import REQUIRED_CHECKS, checksum, verify


class FirstArtifactGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.repo = self.work / 'repo'
        (self.repo / 'scripts').mkdir(parents=True)
        (self.repo / 'patches').mkdir()
        (self.repo / 'scripts/build.sh').write_text('unit fixture, not a real build')
        files = digest_files(self.repo)
        tree = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        inputs = json.dumps({'files_sha256': files, 'tree_sha256': tree}).encode()
        self.archive = self.work / 'openharmony-qemu-arm64-arm64_virt-phone.tar.gz'
        with tarfile.open(self.archive, 'w:gz') as package:
            member = tarfile.TarInfo(self.archive.name.removesuffix('.tar.gz') + '/build-inputs.json')
            member.size = len(inputs)
            package.addfile(member, io.BytesIO(inputs))
        records = {}
        for name in REQUIRED_CHECKS:
            path = self.work / (name + '.unit-evidence')
            path.write_text('structure-only unit fixture, not actual guest results')
            records[name] = {'status': 'pass', 'evidence': path.name, 'sha256': checksum(path),
                             'commands': [{'argv': ['unit-fixture'], 'exit_code': 0}]}
        self.document = {'schema_version': 2, 'scope': 'new_packaged_qemu_behavior',
                         'first_artifact_behavior_gate_passed': True,
                         'package': {'archive': str(self.archive), 'sha256': checksum(self.archive),
                                     'build_inputs_tree_sha256': tree},
                         'test_environment': {'product': 'arm64_virt', 'device_type': 'phone',
                                              'external_keepalive': False,
                                              'boot_id': '12345678-1234-1234-1234-123456789abc',
                                              'target': 'fixture', 'guest_arch': 'arm64',
                                              'qemu_command': ['unit-fixture'], 'guest_identity': {'fixture': True}},
                         'application_test_setup': {
                             'method': 'existing_power-shell_development_override',
                             'after_unassisted_default_policy_boot_validation': True,
                             'not_default_power_policy_acceptance': True, 'restored': True,
                             'policy_states': {'before': {'base_ms': 10000, 'override_ms': None},
                                 'setup': {'base_ms': 10000, 'override_ms': 86400000},
                                 'restored': {'base_ms': 10000, 'override_ms': None}}},
                         'checks': records}
        self.evidence = self.work / 'gate.json'

    def run_verify(self, document):
        self.evidence.write_text(json.dumps(document))
        # These preexisting tests cover only the outer archive/evidence
        # contract. Actual inner result semantics have separate tests below;
        # text fixtures can never satisfy the real validator.
        with patch('verify_first_artifact_gate.verified_payload'):
            return verify(self.archive, self.evidence, self.repo, 'arm64_virt', 'phone')

    def test_contract_structure_can_validate_without_claiming_to_run_guest(self):
        self.assertEqual(self.run_verify(self.document), self.document)

    def test_static_old_failed_wrong_archive_and_wrong_checksum_rejected(self):
        for change in (lambda d: d.update(scope='static_packaging_contract_only'),
                       lambda d: d.update(first_artifact_behavior_gate_passed=False),
                       lambda d: d['package'].update(archive='/old-image.tar.gz'),
                       lambda d: d['package'].update(sha256='0' * 64),
                       lambda d: d['package'].update(build_inputs_tree_sha256='0' * 64)):
            data = deepcopy(self.document)
            change(data)
            with self.assertRaises(ValueError):
                self.run_verify(data)

    def test_unattended_matrix_cannot_accept_incomplete_or_assisted_boot(self):
        for change in (lambda d: d['test_environment'].update(external_keepalive=True),
                       lambda d: d['test_environment'].update(device_type='2in1'),
                       lambda d: d['test_environment'].update(guest_identity={}),
                       lambda d: d['checks'].pop('arkweb'),
                       lambda d: d['checks']['vulkan'].update(status='fail'),
                       lambda d: d['checks']['issue20-library-exit'].update(commands=[]),
                       lambda d: d['checks']['native-bindings-e2e']['commands'][0].update(exit_code=1)):
            data = deepcopy(self.document)
            change(data)
            with self.assertRaises(ValueError):
                self.run_verify(data)

    def test_changed_runtime_evidence_and_changed_current_sources_rejected(self):
        (self.work / 'arkweb.unit-evidence').write_text('changed')
        with self.assertRaises(ValueError):
            self.run_verify(self.document)

        (self.repo / 'scripts/build.sh').write_text('changed input')
        with self.assertRaisesRegex(ValueError, 'current frozen'):
            self.run_verify(self.document)

    def test_failed_or_false_policy_cleanup_cannot_release_matrix(self):
        for change in (lambda d: d.pop('application_test_setup'),
                       lambda d: d['application_test_setup'].update(restored=False),
                       lambda d: d['application_test_setup']['policy_states']['before'].update(override_ms=99),
                       lambda d: d['application_test_setup']['policy_states']['setup'].update(override_ms=1),
                       lambda d: d['application_test_setup']['policy_states']['restored'].update(base_ms=9000000)):
            data = deepcopy(self.document)
            change(data)
            with self.assertRaises(ValueError):
                self.run_verify(data)

    def test_matrix_places_real_gate_before_architecture_traversal_and_rejects_old_reuse(self):
        text = (ROOT / 'scripts/run_device_type_matrix_build_docker.sh').read_text()
        self.assertLess(text.index('python3 "${SCRIPT_DIR}/verify_first_artifact_gate.py"'),
                        text.index('for product in ${PRODUCTS}; do'))
        self.assertIn('verify_current_inputs "${package_tar}"', text)
        self.assertIn('--package-archive "${first_tar}"', text)
        self.assertEqual(text.count('verify_package_runtime "${device_type}" "${product}" "${package_dir}" "${package_tar}"'), 2)
        self.assertIn('MATRIX_PACKAGE_VALIDATOR', text)
        self.assertIn('all_required_packaging_capabilities', text)
        self.assertNotIn('archive.read_bytes()', text)

    def test_two_in_one_also_requires_serial_and_boolean_exit_is_not_success(self):
        data = deepcopy(self.document)
        data['test_environment']['device_type'] = '2in1'
        self.evidence.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            verify(self.archive, self.evidence, self.repo, 'arm64_virt', '2in1')
        serial = self.work / 'serial.unit-evidence'
        serial.write_text('unit structure fixture, not a Serial guest result')
        data['checks']['serial'] = {'status': 'pass', 'evidence': serial.name,
            'sha256': checksum(serial), 'commands': [{'argv': ['fixture-serial'], 'exit_code': 0}]}
        self.evidence.write_text(json.dumps(data))
        with patch('verify_first_artifact_gate.verified_payload'):
            self.assertEqual(verify(self.archive, self.evidence, self.repo, 'arm64_virt', '2in1'), data)
        data['checks']['serial']['commands'][0]['exit_code'] = False
        self.evidence.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            verify(self.archive, self.evidence, self.repo, 'arm64_virt', '2in1')


if __name__ == '__main__':
    unittest.main()
