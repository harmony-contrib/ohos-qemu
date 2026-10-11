"""Synthetic tamper tests; these files never constitute a device run."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import verify_image_metadata_results as verifier
from run_root_probe import digest


class ImageMetadataEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='image-metadata-evidence-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.nonce, self.archive, self.boot = '12' * 16, 'a' * 64, 'unit-boot-id'
        self.identity = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal',
            'isSystemApp': False, 'uid': 20010001}})
        self.rows = [dict(runId=self.nonce, name=name, values=values, text=text, error='')
                     for name, (values, text) in verifier.EXPECTED.items()]
        project = self.root / 'project'
        template = Path(verifier.__file__).with_name('image_metadata_probe.ets')
        page = project / 'entry/src/main/ets/pages/Index.ets'
        page.parent.mkdir(parents=True)
        page.write_text(template.read_text().replace('__IMAGE_METADATA_RUN__', self.nonce))
        module = project / 'entry/src/main/module.json5'
        module.write_text(json.dumps({'module': {'requestPermissions': []}}))
        fixture = project / 'entry/src/main/resources/rawfile/unit.bin'
        fixture.parent.mkdir(parents=True)
        fixture.write_bytes(b'synthetic parser fixture identity test only')
        fixtures = {'unit.bin': digest(fixture)}
        for name in ('verify_image_metadata_results.FIXTURES', 'image_metadata_fixtures.FIXTURES'):
            mocked = patch(name, fixtures)
            mocked.start()
            self.addCleanup(mocked.stop)
        inputs = project / 'image-metadata-probe-inputs.json'
        inputs.write_text(json.dumps(dict(schema_version=1, run_id=self.nonce, arch='arm64',
            scope=verifier.SCOPE, fixtures=fixtures, template_sha256=digest(template),
            generated_source_sha256=digest(page), module_sha256=digest(module),
            request_permissions=[], sdk_declaration_sha256='b' * 64)))
        self.files = {'raw_results': self.root / 'results.log',
            'ordinary_identity': self.root / 'application-identity.json',
            'hap': self.root / 'ordinary-probe-signed.hap', 'compiled_contract_inputs': inputs,
            'result': self.root / 'verified-result.json'}
        self.files['raw_results'].write_text('\n'.join(map(json.dumps, self.rows)))
        self.files['ordinary_identity'].write_text(self.identity)
        self.files['hap'].write_bytes(b'unit payload identity only, not signed runtime evidence')
        self.inner = dict(status='pass', scope=verifier.SCOPE, failures=[], archive_sha256=self.archive,
            arch='arm64', run_id=self.nonce, first_artifact_behavior_gate_passed=False,
            verifier_sha256=digest(Path(verifier.__file__)),
            results_sha256=digest(self.files['raw_results']),
            application_identity_sha256=digest(self.files['ordinary_identity']),
            inputs_sha256=digest(inputs), result=verifier.verify(self.files['raw_results'].read_text(), self.nonce, self.identity))
        self.files['result'].write_text(json.dumps(self.inner))
        self.document = dict(status='pass', persona='image-metadata', archive_sha256=self.archive,
            boot_id=self.boot, arch='arm64', failures=[], first_artifact_behavior_gate_passed=False,
            run_id=self.nonce, result=str(self.files['result']), ordinary_uid=20010001,
            **{key + '_sha256': digest(path) for key, path in self.files.items()})

    def check(self, document=None):
        return verifier.verify_evidence(self.document if document is None else document,
                                        self.archive, self.boot, 'arm64')

    def test_bound_raw_contract_remains_narrow(self):
        self.assertEqual(self.check()['closed'], ['arkts_export:@ohos.multimedia.image:AvisMetadata'])
        self.assertEqual(self.check()['observations'], 22)

    def test_ledger_replays_actual_evidence_and_rejects_diagnostic_boot(self):
        from verify_gap_closure import behavior_results
        runtime = self.root / 'ledger'
        (runtime / 'image-metadata').mkdir(parents=True)
        (runtime / 'boot').mkdir()
        (runtime / 'image-metadata/evidence.json').write_text(json.dumps(self.document))
        boot = dict(status='pass', purpose='acceptance',
            scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate', archive_sha256=self.archive,
            test_environment=dict(boot_id=self.boot, guest_arch='arm64', device_type='phone',
                                  external_keepalive=False))
        boot_path = runtime / 'boot/boot.json'
        boot_path.write_text(json.dumps(boot))
        check = lambda: behavior_results(runtime, self.boot, self.archive, 'phone')
        self.assertEqual(set(check()), {verifier.AVIS_CONTRACT})
        boot_path.write_text(json.dumps(dict(boot, purpose='diagnostic')))
        with self.assertRaises(ValueError):
            check()
        boot_path.write_text(json.dumps(boot))
        self.files['raw_results'].write_text('{}')
        with self.assertRaises(ValueError):
            check()

    def test_every_recorded_file_rejects_unrecorded_changes(self):
        for key, path in self.files.items():
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
            path.write_bytes(original)

    def test_foreign_archive_boot_arch_persona_or_uid_rejected(self):
        for key, value in (('archive_sha256', 'c' * 64), ('boot_id', 'other'), ('arch', 'x86_64'),
                           ('persona', 'camera'), ('ordinary_uid', 0), ('run_id', '34' * 16)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(dict(self.document, **{key: value}))

    def test_rehashed_string_code_still_fails(self):
        rows = copy.deepcopy(self.rows)
        rows[2]['values'][1] = '7700204'
        self.files['raw_results'].write_text('\n'.join(map(json.dumps, rows)))
        self.inner['results_sha256'] = digest(self.files['raw_results'])
        self.files['result'].write_text(json.dumps(self.inner))
        self.document.update(raw_results_sha256=digest(self.files['raw_results']),
                             result_sha256=digest(self.files['result']))
        with self.assertRaises(ValueError):
            self.check()

    def test_compiled_source_change_rejected(self):
        page = self.root / 'project/entry/src/main/ets/pages/Index.ets'
        page.write_text(page.read_text() + '\n// changed\n')
        with self.assertRaises(ValueError):
            self.check()

    def test_full_gate_and_suite_require_actual_metadata_diagnostic(self):
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / 'scripts'))
        from verify_first_artifact_gate import REQUIRED_CHECKS, verified_payload
        self.assertIn('image-metadata', REQUIRED_CHECKS)
        suite = (root / 'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        self.assertIn("personas += ('image-metadata',)", suite)
        path = self.root / 'outer.json'
        path.write_text(json.dumps(self.document))
        verified_payload('image-metadata', path, {'sha256': self.archive},
                         {'boot_id': self.boot, 'guest_arch': 'arm64'})
        path.write_text(json.dumps(dict(self.document, ordinary_uid=0)))
        with self.assertRaises(ValueError):
            verified_payload('image-metadata', path, {'sha256': self.archive},
                             {'boot_id': self.boot, 'guest_arch': 'arm64'})
