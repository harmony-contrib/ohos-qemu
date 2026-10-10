"""Synthetic strict evidence tests; fixtures do not demonstrate guest success."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from thermal_contract import SCOPE, TEMPLATE, inputs
from run_root_probe import digest
from test_thermal_backend import HDI, POLICY, KERNEL, SERVICE
from test_thermal_results import RUN, IDENTITY, fixture, text
import verify_thermal_backend as backend
import verify_thermal_results as verifier


class ThermalGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='thermal-gate-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        project = self.root / 'project'
        page = project / 'entry/src/main/ets/pages/Index.ets'
        page.parent.mkdir(parents=True)
        page.write_text(TEMPLATE.read_text().replace('__THERMAL_RUN_ID__', RUN))
        (project / 'entry/src/main/module.json5').write_text(json.dumps({'module': {'requestPermissions': []}}))
        api = self.root / 'sdk/ets/api'
        api.mkdir(parents=True)
        (api / '@ohos.thermal.d.ts').write_text('// Synthetic SDK fixture, not compilation evidence\n' +
            '\n'.join('function ' + name + '();' for name in ('getLevel', 'getThermalLevel',
                'registerThermalLevelCallback', 'unregisterThermalLevelCallback',
                'subscribeThermalLevel', 'unsubscribeThermalLevel')))
        self.files = {'result': self.root / 'verified-result.json', 'raw_results': self.root / 'results.log',
            'ordinary_identity': self.root / 'application-identity.json',
            'hap': self.root / 'ordinary-probe-signed.hap',
            'compiled_contract_inputs': project / 'thermal-probe-inputs.json',
            'thermal_backend': self.root / 'thermal-backend.json'}
        self.files['compiled_contract_inputs'].write_text(json.dumps(inputs(project, self.root / 'sdk', 'arm64', RUN)))
        self.files['raw_results'].write_text(text(fixture()))
        self.files['ordinary_identity'].write_text(IDENTITY)
        self.files['hap'].write_text('unit fixture, not an actual HAP')
        self.backend = {'archive_sha256': 'a' * 64, 'boot_id': 'fixture-boot', 'run_id': RUN,
                        'verifier_sha256': digest(Path(backend.__file__))}
        for phase in ('before', 'after'):
            self.backend[phase] = {}
            for name, content in zip(backend.COMMANDS, (HDI, POLICY, KERNEL, SERVICE)):
                path = self.root / ('thermal-' + phase + '-' + name + '.log')
                path.write_text(content)
                self.backend[phase][name] = {'path': str(path), 'sha256': digest(path)}
        self.value = {'status': 'pass', 'scope': SCOPE, 'failures': [], 'archive_sha256': 'a' * 64,
            'boot_id': 'fixture-boot', 'arch': 'arm64', 'run_id': RUN, 'first_artifact_behavior_gate_passed': False,
            'verifier_sha256': digest(Path(verifier.__file__)),
            'results_sha256': digest(self.files['raw_results']),
            'application_identity_sha256': digest(self.files['ordinary_identity']),
            'compiled_inputs_sha256': digest(self.files['compiled_contract_inputs']),
            'result': verifier.verify(text(fixture()), RUN, IDENTITY),
            'backend': backend.verify_capture(self.backend, 'a' * 64, 'fixture-boot', RUN)}
        self.document = {'status': 'pass', 'persona': 'thermal', 'failures': [],
            'archive_sha256': 'a' * 64, 'boot_id': 'fixture-boot', 'arch': 'arm64', 'run_id': RUN,
            'ordinary_uid': 20010000, 'first_artifact_behavior_gate_passed': False,
            'result': str(self.files['result'])}
        self.rehash()

    def rehash(self):
        self.files['thermal_backend'].write_text(json.dumps(self.backend))
        self.value['backend_sha256'] = digest(self.files['thermal_backend'])
        self.files['result'].write_text(json.dumps(self.value))
        self.document.update({key + '_sha256': digest(path) for key, path in self.files.items()})

    def check(self, document=None):
        return verifier.verify_evidence(document or self.document, 'a' * 64, 'fixture-boot', 'arm64')

    def test_both_real_paths_required_and_narrow_scope(self):
        result = self.check()
        self.assertEqual(result['closed'], [])
        self.assertEqual(result['callbacks']['generations'], 4)
        self.assertFalse(result['backend']['after']['hot_transitions_proven'])

    def test_wrong_identity_archive_boot_role_and_nonce_rejected(self):
        for key, value in (('boot_id', 'old'), ('archive_sha256', 'b' * 64), ('arch', 'armv7a'),
                           ('persona', 'other'), ('run_id', 'b' * 32), ('ordinary_uid', 0),
                           ('first_artifact_behavior_gate_passed', True), ('status', 'fail')):
            document = dict(self.document, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(document)

    def test_each_raw_file_and_backend_phase_is_replayed(self):
        for key in self.files:
            document = dict(self.document, **{key + '_sha256': '0' * 64})
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(document)
        for phase in ('before', 'after'):
            path = Path(self.backend[phase]['service']['path'])
            path.write_text(SERVICE.replace('2600', '0'))
            self.backend[phase]['service']['sha256'] = digest(path)
            self.rehash()
            with self.assertRaises(ValueError): self.check()
            path.write_text(SERVICE)
            self.backend[phase]['service']['sha256'] = digest(path)
            self.rehash()

    def test_rehashed_false_ordinary_result_is_rejected(self):
        rows = fixture()
        rows[1]['values'][2] = 0
        self.files['raw_results'].write_text(text(rows))
        self.value['results_sha256'] = digest(self.files['raw_results'])
        self.rehash()
        with self.assertRaises(ValueError): self.check()

    def test_backend_identity_and_verifier_cannot_be_changed(self):
        original = deepcopy(self.backend)
        for key, value in (('boot_id', 'old'), ('run_id', 'f' * 32), ('archive_sha256', 'b' * 64),
                           ('verifier_sha256', '0' * 64)):
            self.backend = dict(original, **{key: value})
            self.rehash()
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_permissions_and_source_cannot_be_hidden_by_summary(self):
        page = self.root / 'project/entry/src/main/ets/pages/Index.ets'
        page.write_text(page.read_text() + '\n// different caller\n')
        with self.assertRaises(ValueError): self.check()

    def test_unified_gate_requires_thermal_for_both_profiles(self):
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('thermal', REQUIRED_CHECKS)
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("personas += ('thermal',)", suite)
        self.assertIn("check('thermal', path, [record])", suite)


if __name__ == '__main__':
    unittest.main()
