"""Synthetic evidence exercises rejection paths, not guest success."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from run_root_probe import digest
import test_fa_particle_results as fixtures
from verify_fa_particle_results import BUNDLE, verify, verify_evidence


class FaEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fa-evidence-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        project = self.root / 'project'
        project.mkdir()
        base = fixtures.FaParticleResultTests()
        base.setUp()
        raw = '\n'.join('QEMU_FA_PARTICLE:' + json.dumps(row) for row in base.rows)
        raw += '\nQEMU_FA_PAGE:' + json.dumps({'nonce': fixtures.NONCE, 'status': 'pass'})
        self.doc = dict(status='pass', persona='fa-particle', archive_sha256='a' * 64,
                        boot_id='test-boot', arch='arm64', failures=[], closed=[],
                        first_artifact_behavior_gate_passed=False,
                        cleanup='force stop process successfully.', nonce=fixtures.NONCE,
                        processes=[{'pid': 101, 'uid': 20010043,
                                    'status': 'Uid:\t20010043\t20010043\t20010043\t20010043\n'}],
                        result=verify(raw, fixtures.NONCE, base.identity))
        inputs = dict(nonce=fixtures.NONCE, bundle=BUNDLE, build_status='pass', model='FA',
                      ability_kind='service', request_permissions=[],
                      builder_sha256=digest(Path(__file__).with_name('build_fa_particle_probe.py')))
        for path, key in ((project / 'entry/src/main/js/ParticleService/service.js', 'source_sha256'),
                          (project / 'entry/src/main/js/MainAbility/pages/index/index.js', 'page_source_sha256')):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic source fixture')
            inputs[key] = digest(path)
        unsigned = project / 'unsigned.hap'
        with zipfile.ZipFile(unsigned, 'w') as hap:
            hap.writestr('config.json', json.dumps({'app': {'bundleName': BUNDLE}, 'module': {}}))
            for member in ('assets/js/ParticleService/service.abc', 'assets/js/MainAbility/pages/index/index.abc'):
                hap.writestr(member, b'synthetic ABC fixture')
        inputs.update(unsigned_hap=str(unsigned), unsigned_hap_sha256=digest(unsigned))
        for key, path, data in (('identity', self.root / 'identity.json', base.identity),
                                ('results', self.root / 'results.log', raw),
                                ('caller_inputs', project / 'caller-inputs.json', json.dumps(inputs))):
            path.write_text(data)
            self.doc.update({key: str(path), key + '_sha256': digest(path)})
        signed = self.root / 'ordinary-fa.hap'
        signed.write_bytes(b'synthetic signed HAP fixture')
        self.doc['signed_hap_sha256'] = digest(signed)
        log = self.root / 'command.log'
        log.write_text('synthetic command fixture')
        self.doc['commands'] = [dict(argv=['synthetic-test'], exit_code=0,
                                     log=str(log), sha256=digest(log))]

    def check(self, document=None):
        return verify_evidence(self.doc if document is None else document, 'a' * 64, 'test-boot', 'arm64')

    def test_recomputes_narrow_result_without_claiming_stage(self):
        self.assertEqual(self.check(), self.doc['result'])
        self.assertIn('same-archive Stage regression', self.check()['requires'])

    def test_packaged_suite_requires_fa_alongside_stage(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('fa-particle', REQUIRED_CHECKS)
        source = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("check('fa-particle', work / 'fa-particle/evidence.json', [fa_record])", source)
        self.assertIn("Path(__file__).with_name('run_normal_hap_probe.py')", source)

    def test_package_boot_arch_and_false_closure_rejected(self):
        for key, value in (('archive_sha256', 'b' * 64), ('boot_id', 'other'), ('arch', 'x86_64'),
                           ('cleanup', ''), ('closed', ['all']), ('first_artifact_behavior_gate_passed', True),
                           ('status', 'fail'), ('failures', ['failure'])):
            changed = copy.deepcopy(self.doc)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(changed)

    def test_raw_hashes_and_signed_package_cannot_be_replaced(self):
        for key in ('identity_sha256', 'results_sha256', 'caller_inputs_sha256', 'signed_hap_sha256'):
            changed = copy.deepcopy(self.doc)
            changed[key] = 'b' * 64
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(changed)

    def test_process_privilege_and_duplicate_pid_rejected(self):
        for processes in ([], self.doc['processes'] * 2,
                          [dict(pid=True, uid=20010043, status=self.doc['processes'][0]['status'])],
                          [dict(pid=101, uid=20010043, status='Uid:\t0\t0\t0\t0\n')]):
            changed = copy.deepcopy(self.doc)
            changed['processes'] = processes
            with self.assertRaises(ValueError):
                self.check(changed)

    def test_failed_or_modified_command_and_summary_rejected(self):
        for key, value in (('exit_code', 1), ('timed_out', True), ('sha256', 'b' * 64), ('argv', [])):
            changed = copy.deepcopy(self.doc)
            changed['commands'][0][key] = value
            with self.assertRaises(ValueError):
                self.check(changed)
        changed = copy.deepcopy(self.doc)
        changed['result']['observations'] = 100
        with self.assertRaises(ValueError):
            self.check(changed)


if __name__ == '__main__':
    unittest.main()
