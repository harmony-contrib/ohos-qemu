"""Outer closure-binding fixtures; raw kernel/app parsers have independent tests."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))

from run_root_probe import digest
from test_run_root_probe import elf
from verify_gap_closure import behavior_results
from verify_storage_quota_closure import IDENTIFIER, verify


class StorageQuotaClosureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='storage-closure-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('boot', 'project-quota', 'project-quota-probes', 'storage-stats'):
            (self.root / name).mkdir()
        self.boot = {'status': 'pass', 'purpose': 'acceptance',
            'scope': 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate', 'archive_sha256': 'a' * 64,
            'test_environment': {'boot_id': 'fixture-boot', 'guest_arch': 'arm64',
                'device_type': 'phone', 'external_keepalive': False}}
        self.probe = self.root / 'project-quota-probes/project-quota-runtime'
        elf(self.probe)
        self.build = {'status': 'pass', 'arch': 'arm64', 'scope': 'SDK_compile_NOT_guest_or_Storage_API',
            'first_artifact_behavior_gate_passed': False, 'probe_sha256': digest(self.probe),
            'source_sha256': digest(Path(__file__).with_name('probes') / 'project_quota_runtime.c')}
        self.quota = {'status': 'pass', 'boot_id': 'fixture-boot', 'archive_sha256': 'a' * 64,
            'probe': str(self.probe), 'probe_sha256': digest(self.probe)}
        self.ordinary = {'status': 'pass', 'boot_id': 'fixture-boot', 'archive_sha256': 'a' * 64}
        self.save()

    def save(self):
        for path, value in (('boot/boot.json', self.boot), ('project-quota/result.json', self.quota),
                            ('storage-stats/evidence.json', self.ordinary),
                            ('project-quota-probes/build.json', self.build)):
            (self.root / path).write_text(json.dumps(value))

    def check(self):
        # Outer bindings only; never turn this fixture into runtime acceptance.
        with patch('verify_first_artifact_gate.verified_payload') as inner:
            result = verify(self.root, 'a' * 64, 'fixture-boot', 'phone')
            self.assertEqual([call.args[0] for call in inner.call_args_list], ['project-quota', 'storage-stats'])
            return result

    def test_closes_only_audited_quota_backend_not_all_storage(self):
        self.assertEqual(set(self.check()), {IDENTIFIER})
        self.assertIn('all_privileged_Storage_APIs', self.check()[IDENTIFIER]['not_claimed'])

    def test_old_or_diagnostic_boot_cannot_close(self):
        original = deepcopy(self.boot)
        for key, value in (('status', 'fail'), ('purpose', 'diagnostic'), ('archive_sha256', 'b' * 64),
                           ('candidate_kernel', '/candidate'), ('diagnostic_assistance', True)):
            self.boot = dict(original, **{key: value})
            self.save()
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()
        for key, value in (('boot_id', 'old'), ('device_type', '2in1'), ('external_keepalive', True)):
            self.boot = deepcopy(original)
            self.boot['test_environment'][key] = value
            self.save()
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_probe_substitution_stale_source_or_wrong_abi_rejected(self):
        original = deepcopy(self.build)
        for key, value in (('status', 'fail'), ('arch', 'x86_64'), ('scope', 'mock'),
                           ('probe_sha256', '0' * 64), ('source_sha256', '0' * 64)):
            self.build = dict(original, **{key: value})
            self.save()
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()
        self.build = original
        self.save()
        elf(self.probe, 'x86_64')
        self.build['probe_sha256'] = self.quota['probe_sha256'] = digest(self.probe)
        self.save()
        with self.assertRaises(ValueError): self.check()

    def test_either_missing_half_remains_unresolved(self):
        for name in ('project-quota/result.json', 'storage-stats/evidence.json'):
            self.save()
            (self.root / name).unlink()
            self.assertNotIn(IDENTIFIER, behavior_results(self.root, 'fixture-boot', 'a' * 64, 'phone'))
            with self.assertRaises(ValueError): self.check()

    def test_registry_requires_both_inner_verifiers(self):
        with patch('verify_first_artifact_gate.verified_payload', side_effect=ValueError('actual raw proof failed')):
            with self.assertRaisesRegex(ValueError, 'actual raw proof failed'):
                behavior_results(self.root, 'fixture-boot', 'a' * 64, 'phone')
        with patch('verify_first_artifact_gate.verified_payload') as inner:
            self.assertEqual(set(behavior_results(self.root, 'fixture-boot', 'a' * 64, 'phone')), {IDENTIFIER})
            self.assertEqual(inner.call_count, 2)


if __name__ == '__main__':
    unittest.main()
