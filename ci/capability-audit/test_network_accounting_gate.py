"""Synthetic evidence replay boundaries, not guest acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from network_accounting_contract import SCOPE, PERMISSIONS, generate, inputs
from run_root_probe import digest
from test_network_accounting import RUN, UID, URL, IDENTITY, peer, observations, encoded
import verify_network_accounting_results as verifier
from verify_network_accounting_evidence import verify_evidence


class NetworkAccountingGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='network-gate-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        project = self.root / 'project'
        page = project / 'entry/src/main/ets/pages/Index.ets'
        page.parent.mkdir(parents=True)
        page.write_text(generate(RUN, URL))
        (project / 'entry/src/main/module.json5').write_text(json.dumps(
            {'module': {'requestPermissions': PERMISSIONS}}))
        api = self.root / 'sdk/ets/api'
        api.mkdir(parents=True)
        for name in ('net.http', 'process'):
            (api / ('@ohos.' + name + '.d.ts')).write_text('// Synthetic SDK fixture only\n')
        (api / '@ohos.net.statistics.d.ts').write_text('\n'.join(
            'function getUid' + direction + 'Bytes(uid: number' + suffix
            for direction in ('Rx', 'Tx')
            for suffix in ('): Promise<number>;', ', callback: AsyncCallback<number>): void;')))
        self.files = dict(result=self.root / 'verified-result.json', raw_results=self.root / 'results.log',
            ordinary_identity=self.root / 'application-identity.json', hap=self.root / 'ordinary-probe-signed.hap',
            compiled_contract_inputs=project / 'network-accounting-probe-inputs.json',
            http_peer=self.root / 'http-peer.json')
        self.files['compiled_contract_inputs'].write_text(json.dumps(inputs(project, self.root / 'sdk', 'arm64', RUN, URL)))
        self.files['raw_results'].write_text(encoded(observations()))
        self.files['ordinary_identity'].write_text(IDENTITY)
        self.files['hap'].write_text('synthetic fixture, not a signed application')
        self.files['http_peer'].write_text(json.dumps(peer()))
        self.value = dict(status='pass', scope=SCOPE, failures=[], archive_sha256='a' * 64,
            arch='arm64', run_id=RUN, first_artifact_behavior_gate_passed=False,
            verifier_sha256=digest(Path(verifier.__file__)),
            results_sha256=digest(self.files['raw_results']),
            application_identity_sha256=digest(self.files['ordinary_identity']),
            compiled_inputs_sha256=digest(self.files['compiled_contract_inputs']),
            http_peer_sha256=digest(self.files['http_peer']),
            result=verifier.verify(encoded(observations()), RUN, IDENTITY, peer(), URL))
        self.document = dict(status='pass', persona='network-accounting', failures=[], archive_sha256='a' * 64,
            boot_id='fixture-boot', arch='arm64', run_id=RUN, ordinary_uid=UID,
            first_artifact_behavior_gate_passed=False, result=str(self.files['result']))
        self.rehash()

    def rehash(self):
        self.files['result'].write_text(json.dumps(self.value))
        self.document.update({key + '_sha256': digest(path) for key, path in self.files.items()})

    def check(self, document=None):
        return verify_evidence(document or self.document, 'a' * 64, 'fixture-boot', 'arm64')

    def test_replays_contract_without_closing_complete_network(self):
        self.assertEqual(self.check()['closed'], [])

    def test_each_hash_required(self):
        for key in self.files:
            changed = dict(self.document, **{key + '_sha256': '0' * 64})
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(changed)

    def test_wrong_archive_boot_role_ABI_UID_or_nonce(self):
        for key, value in (('archive_sha256', 'b' * 64), ('boot_id', 'old'), ('arch', 'armv7a'),
                           ('persona', 'thermal'), ('ordinary_uid', 0), ('run_id', 'b' * 32),
                           ('first_artifact_behavior_gate_passed', True), ('status', 'fail')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(dict(self.document, **{key: value}))

    def test_rehashed_false_traffic_rejected(self):
        rows = observations()
        rows[4]['values'] = rows[2]['values']
        self.files['raw_results'].write_text(encoded(rows))
        self.value['results_sha256'] = digest(self.files['raw_results'])
        self.rehash()
        with self.assertRaises(ValueError): self.check()

    def test_rehashed_peer_missing_exchange_rejected(self):
        document = peer()
        document['requests'].pop()
        self.files['http_peer'].write_text(json.dumps(document))
        self.value['http_peer_sha256'] = digest(self.files['http_peer'])
        self.rehash()
        with self.assertRaises(ValueError): self.check()

    def test_stale_verifier_input_hash_and_forged_summary_rejected(self):
        original = copy.deepcopy(self.value)
        for key, value in (('verifier_sha256', '0' * 64), ('results_sha256', '0' * 64),
                           ('compiled_inputs_sha256', '0' * 64), ('http_peer_sha256', '0' * 64),
                           ('result', {'closed': ['all']})):
            self.value = dict(original, **{key: value})
            self.rehash()
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_extra_statistics_permission_rejected(self):
        module = self.root / 'project/entry/src/main/module.json5'
        module.write_text(json.dumps({'module': {'requestPermissions': PERMISSIONS +
            [{'name': 'ohos.permission.GET_NETWORK_STATS'}]}}))
        with self.assertRaises(ValueError): self.check()

    def test_both_profiles_require_actual_network_behavior(self):
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('network-accounting', REQUIRED_CHECKS)
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("personas += ('network-accounting',)", suite)
        self.assertIn("check('network-accounting', path, [record])", suite)


if __name__ == '__main__':
    unittest.main()
