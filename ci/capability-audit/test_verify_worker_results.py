"""Synthetic strict-verifier fixtures only, never guest Worker acceptance."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from run_normal_hap_probe import PERSONAS, verifier_arguments
from run_root_probe import digest
from verify_gap_closure import behavior_results
from verify_worker_results import MODES, verify
from worker_contracts import generated, verify_inputs

RUN = 'c' * 32
IDENTITY = json.dumps({'applicationInfo': {'uid': 20010036, 'appPrivilegeLevel': 'normal', 'isSystemApp': False}})


def rows(mode):
    constructor, port, closed_code = MODES[mode]
    values = [dict(type='identity', run_id=RUN, worker_class=constructor, port_name=port,
                   main_parent_port_absent=True, main_worker_port_absent=True)]
    def step(generation, name, actual):
        values.append(dict(type='step', run_id=RUN, generation=generation, name=name, actual=actual))
    for generation in (1, 2):
        step(generation, 'created', 1)
        for sequence in (1, 2):
            values.append(dict(type='transfer', run_id=RUN, generation=generation, sequence=sequence,
                input_bytes=256, detached_bytes=-1, detached_length_error='TypeError: IsDetachedBuffer',
                detached_access_error='TypeError'))
            words = [((((int(RUN[:8], 16) + i * 257 + generation * 65537 + sequence * 17) & 0xffffffff) ^
                       0x5a5a5a5a) + generation + sequence) & 0xffffffff for i in range(64)]
            values.append(dict(type='data', run_id=RUN, generation=generation, sequence=sequence, nonce=RUN,
                words=words, bytes=256, input_bytes=256, port_name=port, port_usable=True, other_port_absent=True))
        step(generation, 'close_ack', 1)
        step(generation, 'exit', 0)
        step(generation, 'post_after_exit_error', closed_code)
        step(generation, 'post_after_exit_quiet', 1)
    values.append(dict(type='summary', run_id=RUN, cycles=2, passed=True,
                       scope='ordinary_worker_context_ports_and_transfer_lifecycle_only'))
    return values


def render(values):
    return '\n'.join(map(json.dumps, values))


class WorkerVerifierTests(unittest.TestCase):
    def test_two_versions_have_distinct_real_context_and_closed_message_contracts(self):
        for mode in MODES:
            actual = verify(render(rows(mode)), RUN, IDENTITY, mode)
            self.assertEqual(len(actual['rows']), 20)
            self.assertEqual(actual['actual_transformed_words'], 256)
            self.assertEqual(actual['cycles'], 2)
            with self.assertRaises(ValueError):
                verify(render(rows(mode)), RUN, IDENTITY, 'thread' if mode == 'legacy' else 'legacy')

    def test_reordered_missing_duplicate_stale_or_extra_rows_are_not_success(self):
        for mode in MODES:
            original = rows(mode)
            for changed in (original[:-1], original * 2, original[1:], list(reversed(original))):
                with self.assertRaises(ValueError):
                    verify(render(changed), RUN, IDENTITY, mode)
            for index in range(len(original)):
                changed = copy.deepcopy(original)
                changed[index]['run_id'] = 'd' * 32
                with self.assertRaises(ValueError):
                    verify(render(changed), RUN, IDENTITY, mode)

    def test_every_actual_transformed_word_and_detachment_boundary_matters(self):
        for mode in MODES:
            for index, row in enumerate(rows(mode)):
                if row['type'] == 'data':
                    for word in range(64):
                        changed = rows(mode)
                        changed[index]['words'][word] ^= 1
                        with self.assertRaises(ValueError):
                            verify(render(changed), RUN, IDENTITY, mode)
                changes = []
                if row['type'] == 'data':
                    changes += [('nonce', 'a' * 32), ('port_usable', 1), ('other_port_absent', False),
                                ('bytes', 0), ('input_bytes', True), ('port_name', 'fake')]
                elif row['type'] == 'transfer':
                    changes += [('detached_bytes', 256), ('detached_bytes', True), ('detached_bytes', 0),
                                ('detached_length_error', ''), ('detached_access_error', '')]
                elif row['type'] == 'step':
                    changes += [('actual', True), ('actual', row['actual'] + 1), ('generation', True)]
                elif row['type'] == 'identity':
                    changes += [('main_parent_port_absent', 1), ('main_worker_port_absent', False)]
                else:
                    changes += [('passed', 1), ('cycles', 1), ('scope', 'all workers')]
                for key, value in changes:
                    changed = rows(mode)
                    changed[index][key] = value
                    with self.subTest(mode=mode, index=index, key=key), self.assertRaises(ValueError):
                        verify(render(changed), RUN, IDENTITY, mode)

    def test_normal_account_context_is_mandatory(self):
        for key, value in (('uid', 0), ('uid', 10001), ('isSystemApp', True), ('appPrivilegeLevel', 'system_basic')):
            changed = json.loads(IDENTITY)
            changed['applicationInfo'][key] = value
            with self.assertRaises(ValueError):
                verify(render(rows('thread')), RUN, json.dumps(changed), 'thread')

    def test_orchestrator_separates_sticky_worker_versions_and_uses_nonce_and_real_identity(self):
        for mode in MODES:
            persona = 'worker-' + mode
            self.assertEqual(PERSONAS[persona][0], '--' + persona + '-only')
            self.assertEqual(PERSONAS[persona][2], '"summary"')
            arguments = verifier_arguments(persona, Path('/archive'), Path('/results'), Path('/identity'),
                                           RUN, 'arm64', Path('/verification'))
            self.assertIn('--application-identity', arguments)
            self.assertEqual(arguments[arguments.index('--mode') + 1], mode)
            self.assertEqual(arguments[arguments.index('--run-id') + 1], RUN)
        builder = Path(__file__).with_name('build_hap_probe.py').read_text()
        self.assertIn('args.worker_legacy_only, args.worker_thread_only, args.contact_sync_mode_only)) > 1:', builder)
        runner = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        self.assertIn("'uninstall', BUNDLE", runner)
        self.assertIn("compiled_contract_inputs_sha256=checksum(inputs)", runner)


class WorkerCompiledInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def inputs(self, mode):
        project = self.root / ('worker-' + mode) / 'project'
        sources, hashes = generated(mode, RUN)
        for relative, content in sources.items():
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        declaration = self.root / 'host-only-SDK-declaration-fixture.d.ts'
        declaration.write_text('host fixture NOT a real SDK')
        constructor, port, _ = MODES[mode]
        document = dict(schema_version=1, run_id=RUN, arch='arm64', role='ordinary_app', mode=mode,
            worker_class=constructor, port_name=port, scope='worker_context_ports_and_transfer_lifecycle_only',
            source_sha256=hashes, sdk_worker_declaration=str(declaration),
            sdk_worker_declaration_sha256=digest(declaration))
        path = project / ('worker-' + mode + '-probe-inputs.json')
        path.write_text(json.dumps(document))
        return path, document

    def test_exact_compiled_sources_sdk_declarations_and_challenge_are_bound(self):
        path, document = self.inputs('legacy')
        self.assertEqual(verify_inputs(document, path.parent, RUN, 'arm64', 'legacy'), generated('legacy', RUN)[1])
        for key, value in (('arch', 'x86_64'), ('run_id', 'a' * 32), ('role', 'root'), ('mode', 'thread'),
                           ('sdk_worker_declaration_sha256', 'a' * 64), ('source_sha256', {})):
            changed = dict(document, **{key: value})
            with self.assertRaises(ValueError):
                verify_inputs(changed, path.parent, RUN, 'arm64', 'legacy')
        source = path.parent / 'entry/src/main/ets/workers/ApiWorker.ets'
        content = source.read_text()
        source.write_text(content + '\n// modified fixture')
        with self.assertRaises(ValueError):
            verify_inputs(document, path.parent, RUN, 'arm64', 'legacy')
        source.unlink()
        owned = self.root / 'aliased-fixture.ets'
        owned.write_text(content)
        source.symlink_to(owned)
        with self.assertRaises(ValueError):
            verify_inputs(document, path.parent, RUN, 'arm64', 'legacy')

    def proof(self, mode):
        path, document = self.inputs(mode)
        work = path.parent.parent
        raw = work / 'results.log'
        raw.write_text(render(rows(mode)))
        identity = work / 'application-identity.json'
        identity.write_text(IDENTITY)
        verified = work / 'verified-result.json'
        verified.write_text(json.dumps(dict(status='pass', mode=mode, run_id=RUN, archive_sha256='a' * 64,
            compiled_inputs_sha256=digest(path), results_sha256=digest(raw),
            application_identity_sha256=digest(identity), result=verify(raw.read_text(), RUN, IDENTITY, mode))))
        evidence = dict(status='pass', persona='worker-' + mode, arch='arm64', boot_id='host-fixture',
            archive_sha256='a' * 64, run_id=RUN, raw_results_sha256=digest(raw),
            ordinary_identity_sha256=digest(identity), compiled_contract_inputs=str(path),
            compiled_contract_inputs_sha256=digest(path), result=str(verified), result_sha256=digest(verified))
        proof = work / 'evidence.json'
        proof.write_text(json.dumps(evidence))
        return work, proof, evidence

    def test_only_two_contextual_port_findings_close_not_other_workers_or_main_exports(self):
        self.proof('legacy')
        self.proof('thread')
        closed = behavior_results(self.root, 'host-fixture', 'a' * 64)
        self.assertEqual(set(closed), {'arkts_export:@ohos.worker:parentPort', 'arkts_export:@ohos.worker:workerPort'})
        self.assertEqual(behavior_results(self.root, 'wrong-boot', 'a' * 64), {})
        self.assertEqual(behavior_results(self.root, 'host-fixture', 'b' * 64), {})

    def test_raw_identity_inputs_or_verification_tamper_never_closes_even_with_refreshed_hash(self):
        work, proof, evidence = self.proof('thread')
        raw = work / 'results.log'
        raw.write_text(render(rows('thread')[:-1]))
        self.assertEqual(behavior_results(self.root, 'host-fixture', 'a' * 64), {})
        evidence['raw_results_sha256'] = digest(raw)
        proof.write_text(json.dumps(evidence))
        with self.assertRaises(ValueError):
            behavior_results(self.root, 'host-fixture', 'a' * 64)
        raw.write_text(render(rows('thread')))
        evidence['raw_results_sha256'] = digest(raw)
        proof.write_text(json.dumps(evidence))
        inputs = Path(evidence['compiled_contract_inputs'])
        document = json.loads(inputs.read_text())
        document['source_sha256'] = {}
        inputs.write_text(json.dumps(document))
        evidence['compiled_contract_inputs_sha256'] = digest(inputs)
        proof.write_text(json.dumps(evidence))
        with self.assertRaises(ValueError):
            behavior_results(self.root, 'host-fixture', 'a' * 64)

    def test_cli_failure_is_preserved_and_never_attests_the_package_gate(self):
        path, _ = self.inputs('legacy')
        archive = self.root / 'archive-fixture'
        archive.write_text('host only fixture')
        raw = self.root / 'results-fixture'
        raw.write_text(render(rows('legacy')[:-1]))
        identity = self.root / 'identity-fixture'
        identity.write_text(IDENTITY)
        output = self.root / 'result.json'
        completed = subprocess.run([sys.executable, str(Path(__file__).with_name('verify_worker_results.py')),
            '--archive', str(archive), '--results', str(raw), '--application-identity', str(identity),
            '--output', str(output), '--run-id', RUN, '--mode', 'legacy', '--arch', 'arm64', '--inputs', str(path)],
            capture_output=True)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(json.loads(output.read_text())['status'], 'fail')
        self.assertFalse(json.loads(output.read_text())['first_artifact_behavior_gate_passed'])


if __name__ == '__main__':
    unittest.main()
