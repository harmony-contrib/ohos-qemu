"""Synthetic ELF/transport fixtures cover identity rejection, not actual exits."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from build_library_exit_probes import CASES
from enclosing_acceptance_guest import validate_binding
import library_exit_binding as binding
from run_root_probe import digest


class LibraryExitBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = {'boot_id': '11111111-1111-1111-1111-111111111111',
            'guest_arch': 'arm64', 'device_type': 'phone', 'target': '127.0.0.1:12345',
            'external_keepalive': False, 'qemu_pid': 100, 'qmp_socket': '/tmp/synthetic-qmp',
            'qemu_command': 'qemu synthetic /tmp/synthetic-qmp', 'udid': 'a' * 64}
        self.identity = {'sha256': 'b' * 64}
        boot = self.root / 'bound-boot.json'; boot.write_text(json.dumps({
            'status': 'pass', 'scope': 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
            'purpose': 'acceptance', 'archive_sha256': self.identity['sha256'],
            'test_environment': self.environment}))
        validate_binding(json.loads(boot.read_text()), self.identity['sha256'])
        probes = self.root / 'probes'; (probes / 'arm64').mkdir(parents=True)
        elf = bytearray(64); elf[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<H', elf, 16, 3); struct.pack_into('<H', elf, 18, 183)
        artifacts = {}
        for case in CASES:
            path = probes / 'arm64' / case; path.write_bytes(elf)
            artifacts['arm64/' + case] = {'sha256': digest(path), 'link_order': list(CASES[case])}
        manifest = probes / 'manifest.json'; manifest.write_text(json.dumps({
            'source_sha256': digest(Path(binding.__file__).with_name('probes') / 'library_exit.c'), 'artifacts': artifacts}))
        p = {'scope': binding.SCOPE, 'schema_version': 2,
            'archive_binding': 'actual_enclosing_guest_before_each_exit_and_after',
            'status': 'pass', 'failures': [], 'archive_sha256': self.identity['sha256'],
            'boot_id': self.environment['boot_id'], 'arch': 'arm64', 'device': 'phone',
            'target': self.environment['target'], 'run_id': 'c' * 32, 'hdc': '/synthetic/hdc',
            'bound_boot': {'path': str(boot), 'sha256': digest(boot)},
            'probe_manifest': {'path': str(manifest), 'sha256': digest(manifest)},
            'repeats': 3, 'results': [], 'commands': [], 'cleanup_complete': True, 'cleanup_errors': []}
        remote = '/data/local/tmp/ohos-library-exit-' + p['run_id']
        for case in CASES:
            for repeat in range(3):
                nonce = format(len(p['results']) + 1, '032x')
                command = {'argv': [p['hdc'], '-t', p['target'], 'shell', binding.execution_script(remote, case, repeat, nonce, True)],
                    'transport_exit_code': 0, 'stderr': '', 'stdout': self.stdout(nonce)}
                row = {'case': case, 'repeat': repeat, 'nonce': nonce, 'guest_exit_code': 0,
                    'probe_sha256': artifacts['arm64/' + case]['sha256'], 'link_order': list(CASES[case]),
                    'command_index': len(p['commands'])}
                for suffix in ('out', 'err'):
                    path = self.root / (case + '-' + str(repeat) + '.' + suffix); path.write_bytes(b'')
                    row[suffix] = {'path': str(path), 'sha256': digest(path)}
                p['commands'].append(command); p['results'].append(row)
        p['cleanup_command_index'] = len(p['commands'])
        p['commands'].append({'argv': [p['hdc'], '-t', p['target'], 'shell', binding.cleanup_script(remote, p['run_id'])],
            'transport_exit_code': 0, 'stderr': '', 'stdout': '__OHOS_LIBRARY_CLEANED_' + p['run_id'] + '\n'})
        self.payload = p

    def stdout(self, nonce, boot=None):
        boot = boot or self.environment['boot_id']
        return '__OHOS_LIBRARY_BOOT_' + nonce + '_BEFORE=' + boot + '\n' + \
            '__OHOS_LIBRARY_BOOT_' + nonce + '_AFTER=' + boot + '\n' + '__OHOS_PROBE_EXIT_' + nonce + '=0\n'

    def test_synthetic_receipt_structure_can_be_rechecked(self):
        self.assertEqual(binding.verify_evidence(self.payload, self.identity, self.environment), self.payload)

    def test_outer_labels_cannot_replace_per_invocation_boot_observations(self):
        bad = deepcopy(self.payload)
        bad['commands'][0]['stdout'] = self.stdout(bad['results'][0]['nonce'], '22222222-2222-2222-2222-222222222222')
        with self.assertRaisesRegex(ValueError, 'exact guest boot'):
            binding.verify_evidence(bad, self.identity, self.environment)
        for key in ('boot_id', 'archive_sha256', 'archive_binding'):
            bad = deepcopy(self.payload); bad[key] = 'old'
            with self.assertRaises(ValueError): binding.verify_evidence(bad, self.identity, self.environment)

    def test_wrong_raw_command_nonce_exit_or_cleanup_is_refused(self):
        for mutate in (lambda p: p['commands'][0]['argv'].__setitem__(-1, 'true'),
                       lambda p: p['results'][1].update(nonce=p['results'][0]['nonce']),
                       lambda p: p['results'][0].update(guest_exit_code=False),
                       lambda p: p['commands'][0].update(transport_exit_code=False),
                       lambda p: p.update(cleanup_complete=False),
                       lambda p: p['commands'][-1].update(stdout='invented cleanup')):
            bad = deepcopy(self.payload); mutate(bad)
            with self.assertRaises(ValueError): binding.verify_evidence(bad, self.identity, self.environment)

    def test_changed_or_missing_probe_and_raw_output_are_refused(self):
        raw = Path(self.payload['results'][0]['err']['path']); raw.write_text('changed')
        with self.assertRaises(ValueError): binding.verify_evidence(self.payload, self.identity, self.environment)
        raw.write_bytes(b''); raw.unlink()
        with self.assertRaises(ValueError): binding.verify_evidence(self.payload, self.identity, self.environment)


if __name__ == '__main__': unittest.main()
