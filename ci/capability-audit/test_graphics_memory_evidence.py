"""Synthetic negative evidence fixtures; only real packaged guest runs close gaps."""
import copy
import json
from pathlib import Path
import unittest
import zipfile

import test_hitrace_evidence as payload_fixture
from test_graphics_memory_results import fixture as public_fixture, UID
from build_graphics_memory_app_probe import BUNDLE
from graphics_memory_kernel_contract import verify_samples
from run_root_probe import digest
from verify_graphics_memory_results import verify
from verify_graphics_memory_evidence import verify_evidence, GAP

ROOT = Path(__file__).resolve().parent


class GraphicsMemoryEvidenceTests(unittest.TestCase):
    def setUp(self):
        fixture = payload_fixture.HiTraceEvidenceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.runtime = fixture.runtime
        self.root = self.runtime / 'graphics-memory'
        fixture.root.rename(self.root)
        self.document = json.loads(json.dumps(fixture.document).replace(str(fixture.root), str(self.root)))
        self.document.update(runner_sha256=digest(ROOT / 'run_graphics_memory_diagnostic.py'),
            verifier_sha256=digest(ROOT / 'verify_graphics_memory_results.py'),
            kernel_verifier_sha256=digest(ROOT / 'graphics_memory_kernel_contract.py'), guest_commands=[])
        nonce = self.document['run_id']
        rows = public_fixture()
        for row in rows:
            row['runId'] = nonce
        self.put('actual-results.log', '\n'.join(json.dumps(row) for row in rows))
        self.document['actual_results_sha256'] = digest(self.root / 'actual-results.log')
        identity = self.put('ordinary-identity.json', json.dumps(dict(applicationInfo=dict(
            appPrivilegeLevel='normal', isSystemApp=False, uid=UID))))
        self.document['ordinary_identity_sha256'] = digest(identity)
        self.document['result'] = verify((self.root / 'actual-results.log').read_text(), nonce, UID)
        generated = self.put('project/entry/src/main/ets/pages/Index.ets',
            (ROOT / 'graphics_memory_app_probe.ets').read_text().replace('__RUN__', nonce))
        native = self.root / 'project/entry/libs/arm64-v8a/libgraphicsmemoryprobe.so'
        (native.parent / 'libhitraceprobe.so').rename(native)
        unsigned = self.root / 'project/entry/build/default/outputs/default/entry-default-unsigned.hap'
        signed = self.root / 'ordinary-signed.hap'
        for path in (unsigned, signed):
            with zipfile.ZipFile(path, 'w') as bundle:
                bundle.writestr('libs/arm64-v8a/libgraphicsmemoryprobe.so', native.read_bytes())
                bundle.writestr('ets/modules.abc', 'synthetic fixture only')
                if path == signed:
                    bundle.writestr('.pages.info', b'\0' * 8)
        inputs = json.loads((self.root / 'project/hitrace-probe-inputs.json').read_text())
        inputs.update(bundle=BUNDLE, source_sha256=digest(ROOT / 'graphics_memory_app_probe.cpp'),
            template_sha256=digest(ROOT / 'graphics_memory_app_probe.ets'),
            builder_sha256=digest(ROOT / 'build_graphics_memory_app_probe.py'),
            generated_source_sha256=digest(generated), native_library_sha256=digest(native), hap_sha256=digest(unsigned))
        path = self.put('project/graphicsmemory-probe-inputs.json', json.dumps(inputs))
        self.document.update(compiled_inputs_sha256=digest(path), signed_hap_sha256=digest(signed))
        header = 'Dma-buf objects usage of processes:\nProcess pid fd size_bytes ino exp_pid\n'
        baseline = 'audit 2134 4 4194304 10 0 audit NULL virtio_gpu\n'
        samples = [header + baseline + ''.join(f'audit 2134 {i + 5} 16777216 {ino} 0 audit NULL virtio_gpu\n'
                   for i, ino in enumerate(state)) for state in ([], [25], [25, 26], [26], [])]
        for index, sample in enumerate(samples):
            self.observe('kernel-before-allocations' if index == 0 else 'kernel-during-' + str(index - 1), sample)
        self.document['kernel_result'] = verify_samples(samples, 2134, [16384, 16384])
        self.observe('actual-process-identity', f'Pid:\t2134\nTgid:\t2134\nUid:\t{UID}\t{UID}\t{UID}\t{UID}\n')
        for label in ('boot-before', 'final-boot'):
            self.observe(label, self.document['boot_id'] + '\n')
        for label in ('power-before', 'power-after'):
            self.observe(label, 'ScreenOffTime: Timeout=9000000ms  OverrideTimeout=86400000ms\n')

    def put(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def observe(self, label, value):
        path = self.put('guest-commands/' + str(len(self.document['guest_commands'])).zfill(3) + '-' + label + '.log',
                        value + '\n__QEMU_CHILD_EXIT_' + 'f' * 32 + '__=0\n')
        self.document['guest_commands'].append(dict(log=str(path), sha256=digest(path), exit_code=0))

    def check(self, document=None):
        return verify_evidence(document or self.document, self.document['archive_sha256'],
                               self.document['boot_id'], 'arm64')

    def test_narrow_registered_backend_closure(self):
        self.assertEqual(self.check()['closed'], [GAP])
        self.put('diagnostic.json', json.dumps(self.document))
        from verify_gap_closure import behavior_results
        results = behavior_results(self.runtime, self.document['boot_id'], self.document['archive_sha256'], 'phone')
        self.assertEqual(set(results), {GAP})

    def test_foreign_boot_abi_policy_and_sources_fail(self):
        for key, value in (('boot_id', 'b' * 36), ('arch', 'x86_64'), ('archive_sha256', 'b' * 64),
                           ('power_after', {}), ('kernel_verifier_sha256', '0' * 64),
                           ('runner_sha256', '0' * 64), ('enclosing_guest_preserved', False)):
            document = copy.deepcopy(self.document)
            document[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(document)

    def test_rehashed_but_false_public_bigint_stays_failure(self):
        path = self.root / 'actual-results.log'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['publicTypes'][1] = 'bigint'
        path.write_text('\n'.join(json.dumps(row) for row in rows))
        self.document['actual_results_sha256'] = digest(path)
        with self.assertRaisesRegex(ValueError, 'must remain numbers'):
            self.check()

    def test_rehashed_kernel_wrong_inode_or_missing_release_fails(self):
        row = self.document['guest_commands'][3]
        path = Path(row['log'])
        path.write_text(path.read_text().replace(' 26 ', ' 25 '))
        row['sha256'] = digest(path)
        with self.assertRaises(ValueError):
            self.check()

    def test_rehashed_process_uid_is_not_an_app_identity(self):
        row = self.document['guest_commands'][5]
        path = Path(row['log'])
        path.write_text(path.read_text().replace(str(UID), '0'))
        row['sha256'] = digest(path)
        with self.assertRaises(ValueError):
            self.check()

    def test_matrix_gate_requires_actual_check(self):
        import verify_first_artifact_gate as gate
        self.assertIn('graphics-memory', gate.REQUIRED_CHECKS)
        suite = (ROOT / 'run_packaged_qemu_suite.py').read_text()
        self.assertIn("check('graphics-memory', work / 'graphics-memory/diagnostic.json'", suite)
