"""Synthetic contract boundaries, never a substitute for packaged guest tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from rpc_runtime_contract import SCOPE, source, inputs
from run_root_probe import digest
from test_rpc_runtime_results import RUN, IDENTITY, fixture, text
import verify_rpc_runtime_results as verifier


class RpcRuntimeGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='completion-gate-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        project = self.root / 'project'
        page = project / 'entry/src/main/ets/pages/Index.ets'
        page.parent.mkdir(parents=True)
        page.write_text(source(RUN))
        module = project / 'entry/src/main/module.json5'
        module.write_text(json.dumps({'module': {'requestPermissions': []}}))
        api = self.root / 'sdk/ets/api'
        api.mkdir(parents=True)
        (api / '@ohos.rpc.d.ts').write_text(
            '// Synthetic SDK fixture, not compiler evidence.\n'
            'abstract class IRemoteObject {\nclass RemoteObject extends IRemoteObject {\n'
            'class RemoteProxy extends IRemoteObject {\ncallback: AsyncCallback<RequestResult>\n')
        (api / '@ohos.base.d.ts').write_text('(err: BusinessError<E>, data: T): void;\n')
        self.files = {'result': self.root / 'verified-result.json',
            'raw_results': self.root / 'results.log',
            'ordinary_identity': self.root / 'application-identity.json',
            'hap': self.root / 'ordinary-probe-signed.hap',
            'compiled_contract_inputs': project / 'rpc-runtime-probe-inputs.json'}
        self.files['compiled_contract_inputs'].write_text(json.dumps(inputs(project, self.root / 'sdk', 'arm64', RUN)))
        self.files['raw_results'].write_text(text(fixture()))
        self.files['ordinary_identity'].write_text(IDENTITY)
        self.files['hap'].write_text('unit fixture, not an actual HAP')
        self.value = {'status': 'pass', 'scope': SCOPE, 'failures': [], 'archive_sha256': 'a' * 64,
            'arch': 'arm64', 'run_id': RUN, 'first_artifact_behavior_gate_passed': False,
            'verifier_sha256': digest(Path(verifier.__file__)),
            'results_sha256': digest(self.files['raw_results']),
            'application_identity_sha256': digest(self.files['ordinary_identity']),
            'compiled_inputs_sha256': digest(self.files['compiled_contract_inputs']),
            'result': verifier.verify(text(fixture()), RUN, IDENTITY)}
        self.document = {'status': 'pass', 'persona': 'rpc-runtime', 'failures': [],
            'archive_sha256': 'a' * 64, 'boot_id': 'fixture-boot', 'arch': 'arm64', 'run_id': RUN,
            'ordinary_uid': 20010000, 'first_artifact_behavior_gate_passed': False,
            'result': str(self.files['result'])}
        self.rehash()

    def rehash(self):
        self.files['result'].write_text(json.dumps(self.value))
        self.document.update({key + '_sha256': digest(path) for key, path in self.files.items()})

    def check(self, document=None):
        return verifier.verify_evidence(document or self.document, 'a' * 64, 'fixture-boot', 'arm64')

    def test_replays_narrow_native_contract_not_remote_death(self):
        self.assertEqual(self.check()['closed'], ['arkts_export:@ohos.rpc:IRemoteObject'])
        self.assertEqual(self.check()['observations'], 22)

    def test_wrong_guest_archive_role_or_nonce_rejected(self):
        for key, value in (('boot_id', 'old'), ('archive_sha256', 'b' * 64), ('arch', 'armv7a'),
                           ('persona', 'other'), ('run_id', 'b' * 32), ('ordinary_uid', 0),
                           ('first_artifact_behavior_gate_passed', True), ('status', 'fail')):
            document = deepcopy(self.document)
            document[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(document)

    def test_rehashed_false_raw_success_rejected(self):
        rows = fixture()
        rows[2]['values'] = rows[0]['values']
        self.files['raw_results'].write_text(text(rows))
        self.value['results_sha256'] = digest(self.files['raw_results'])
        self.rehash()
        with self.assertRaises(ValueError): self.check()

    def test_each_evidence_file_hash_required(self):
        for key in self.files:
            document = deepcopy(self.document)
            document[key + '_sha256'] = '0' * 64
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(document)

    def test_stale_verifier_and_forged_summary_rejected(self):
        original = deepcopy(self.value)
        for key, value in (('verifier_sha256', '0' * 64), ('results_sha256', '0' * 64),
                           ('compiled_inputs_sha256', '0' * 64), ('result', {'closed': ['all']})):
            self.value = dict(original, **{key: value})
            self.rehash()
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_permission_escalation_cannot_be_hidden_by_rehash(self):
        module = self.root / 'project/entry/src/main/module.json5'
        module.write_text(json.dumps({'module': {'requestPermissions': [{'name': 'ohos.permission.STORAGE_MANAGER'}]}}))
        with self.assertRaises(ValueError): self.check()

    def test_unified_suite_and_delivery_gate_require_rpc_on_both_profiles(self):
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('rpc-runtime', REQUIRED_CHECKS)
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("personas += ('rpc-runtime',)", suite)
        self.assertIn("check('rpc-runtime', path, [record])", suite)


if __name__ == '__main__':
    unittest.main()
