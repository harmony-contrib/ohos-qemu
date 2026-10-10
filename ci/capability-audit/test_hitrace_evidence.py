"""Synthetic replay and tamper tests; no fixture represents a running device."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from test_enclosing_acceptance_guest import fixture as boot_fixture
from test_hitrace_kernel_contract import fixture as trace_fixture, RUN, PID, TID, UID
from hitrace_kernel_contract import trace_configuration, verify_restored_configuration, verify_trace
from run_root_probe import digest
from verify_hitrace_evidence import BUNDLE, GAP, ROOT, verify_evidence


class HiTraceEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hitrace-evidence-fixture-')
        self.addCleanup(temporary.cleanup)
        self.runtime = Path(temporary.name).resolve()
        self.root = self.runtime / 'hitrace'
        self.root.mkdir()
        boot = self.runtime / 'boot/boot.json'
        boot.parent.mkdir()
        self.binding = boot_fixture()
        boot.write_text(json.dumps(self.binding))
        env = self.binding['test_environment']
        self.document = dict(status='pass', failures=[], archive_sha256='a' * 64, boot_id=env['boot_id'],
            arch='arm64', device='phone', run_id=RUN, enclosing_guest_preserved=True,
            first_artifact_behavior_gate_passed=False, power_restoration='unchanged_enclosing_policy',
            power_before=dict(base_ms=9000000, override_ms=86400000),
            power_after=dict(base_ms=9000000, override_ms=86400000),
            runner_sha256=digest(ROOT / 'run_hitrace_diagnostic.py'),
            verifier_sha256=digest(ROOT / 'hitrace_kernel_contract.py'),
            enclosing_boot=str(boot), enclosing_boot_sha256=digest(boot), test_environment=env,
            guest_commands=[], commands=[])
        self.files = {}

        def put(relative, content):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
            return path
        self.put = put
        names = ['identity', 'native.0', 'arkts.0', 'native.1', 'arkts.1', 'summary']
        values = [[PID, UID, UID], [PID, UID, UID, 1, TID], [1], [PID, UID, UID, 1, TID], [1], [2]]
        rows = [dict(runId=RUN, name=name, values=value, error='') for name, value in zip(names, values)]
        self.files['actual_results'] = put('actual-results.log', '\n'.join(map(json.dumps, rows)))
        self.files['kernel_trace'] = put('actual-kernel-trace.log', trace_fixture())
        self.files['ordinary_identity'] = put('ordinary-identity.json', json.dumps(dict(applicationInfo=dict(
            appPrivilegeLevel='normal', isSystemApp=False, uid=UID))))
        module = put('project/entry/src/main/module.json5', json.dumps(dict(module=dict(requestPermissions=[]))))
        generated = put('project/entry/src/main/ets/pages/Index.ets',
                        (ROOT / 'hitrace_app_probe.ets').read_text().replace('__RUN__', RUN))
        elf = bytearray(64)
        elf[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<HH', elf, 16, 3, 183)
        library = put('project/entry/libs/arm64-v8a/libhitraceprobe.so', bytes(elf))
        unsigned = self.root / 'project/entry/build/default/outputs/default/entry-default-unsigned.hap'
        unsigned.parent.mkdir(parents=True)
        with zipfile.ZipFile(unsigned, 'w') as bundle:
            bundle.writestr('libs/arm64-v8a/libhitraceprobe.so', elf)
            bundle.writestr('ets/modules.abc', 'synthetic fixture only')
        signed = self.root / 'ordinary-signed.hap'
        with zipfile.ZipFile(signed, 'w') as bundle:
            bundle.writestr('libs/arm64-v8a/libhitraceprobe.so', elf)
            bundle.writestr('ets/modules.abc', 'synthetic fixture only')
            bundle.writestr('.pages.info', b'\0' * 8)
        self.files['signed_hap'] = signed
        inputs = dict(status='pass', arch='arm64', run_id=RUN, bundle=BUNDLE, request_permissions=[],
            first_artifact_behavior_gate_passed=False, source_sha256=digest(ROOT / 'hitrace_app_probe.cpp'),
            template_sha256=digest(ROOT / 'hitrace_app_probe.ets'), builder_sha256=digest(ROOT / 'build_hitrace_app_probe.py'),
            module_sha256=digest(module), generated_source_sha256=digest(generated),
            native_library_sha256=digest(library), hap_sha256=digest(unsigned))
        self.files['compiled_inputs'] = put('project/hitrace-probe-inputs.json', json.dumps(inputs))
        signed_log = put('sign-ordinary-no-permissions.log', '\n'.join(('verify codesign success',
            'Digest verify result: true', 'verify-app success', 'verify permission sign success')))
        self.document['commands'].append(dict(log=str(signed_log), exit_code=0, sha256=digest(signed_log)))
        before = '0\nnop\n1408\n[local] global\n0\n-1\n'
        enabled = '1\nnop\n4099\n[local] global\n' + str(1 << 62) + '\n-1\n'
        after = before.replace('1408', '1410')
        for field, value in (('trace_before', before), ('trace_enabled', enabled), ('trace_restored', after)):
            self.document[field] = trace_configuration(value)
        self.document['trace_restoration'] = verify_restored_configuration(
            self.document['trace_before'], self.document['trace_restored'], 4096, 'arm64')
        self.document['result'] = verify_trace(trace_fixture(), RUN, PID, TID)
        observations = {'actual-kernel-thread-identity': f'Pid:\t{TID}\nTgid:\t{PID}\nUid:\t{UID}\t{UID}\t{UID}\t{UID}\n',
            'actual-kernel-page-size': 'KernelPageSize: 4 kB\n',
            'trace-before': before, 'trace-enabled': enabled, 'trace-restored': after}
        for label in ('boot-before', 'final-same-boot', 'enclosing-final-boot'):
            observations[label] = env['boot_id'] + '\n'
        for label in ('power-before', 'enclosing-power-unchanged'):
            observations[label] = 'ScreenOffTime: Timeout=9000000ms  OverrideTimeout=86400000ms\n'
        for label, text in observations.items():
            path = put('guest-commands/000-' + label + '.log', text + '\n__QEMU_CHILD_EXIT_' + 'd' * 32 + '__=0\n')
            self.document['guest_commands'].append(dict(log=str(path), exit_code=0, sha256=digest(path)))
        self.rehash()

    def rehash(self):
        self.document.update({key + '_sha256': digest(path) for key, path in self.files.items()})

    def check(self, value=None):
        return verify_evidence(value or self.document, 'a' * 64, self.binding['test_environment']['boot_id'], 'arm64')

    def test_closes_only_original_kernel_backend_gap(self):
        self.assertEqual(self.check()['closed'], [GAP])
        self.assertEqual(self.check()['public_api_kernel_records'], 36)

    def test_wrong_package_boot_abi_or_lifecycle_fail(self):
        for key, value in (('archive_sha256', 'c' * 64), ('boot_id', 'old'), ('arch', 'armv7a'),
                           ('enclosing_guest_preserved', False), ('first_artifact_behavior_gate_passed', True),
                           ('power_after', {}), ('runner_sha256', '0' * 64)):
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(dict(self.document, **{key: value}))

    def test_raw_evidence_hashes_required(self):
        for key in self.files:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(dict(self.document, **{key + '_sha256': '0' * 64}))

    def test_rehashed_missing_kernel_event_rejected(self):
        lines = self.files['kernel_trace'].read_text().splitlines()
        self.files['kernel_trace'].write_text('\n'.join(lines[:-1]))
        self.rehash()
        with self.assertRaises(ValueError): self.check()

    def test_changed_or_missing_restoration_observation_rejected(self):
        value = copy.deepcopy(self.document)
        value['guest_commands'] = [row for row in value['guest_commands'] if 'trace-restored' not in row['log']]
        with self.assertRaises(ValueError): self.check(value)

    def test_rehashed_signed_payload_substitution_rejected(self):
        with zipfile.ZipFile(self.files['signed_hap'], 'a') as bundle:
            bundle.writestr('injected.txt', 'not built')
        self.rehash()
        with self.assertRaises(ValueError): self.check()

    def test_actual_kernel_uid_must_match(self):
        row = next(row for row in self.document['guest_commands'] if 'actual-kernel-thread-identity' in row['log'])
        path = Path(row['log'])
        path.write_text(path.read_text().replace(str(UID), '0'))
        row['sha256'] = digest(path)
        with self.assertRaises(ValueError): self.check()

    def test_registered_closure_is_same_runtime_and_narrow(self):
        from verify_gap_closure import behavior_results
        (self.root / 'diagnostic.json').write_text(json.dumps(self.document))
        closed = behavior_results(self.runtime, self.document['boot_id'], 'a' * 64, 'phone')
        self.assertEqual(set(closed), {GAP})

    def test_required_in_full_suite_and_delivery_gate(self):
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('hitrace', REQUIRED_CHECKS)
        suite = (ROOT / 'run_packaged_qemu_suite.py').read_text()
        self.assertIn("check('hitrace', work / 'hitrace/diagnostic.json'", suite)
        self.assertIn("'--boot', work / 'boot/boot.json', '--owned-child'", suite)
