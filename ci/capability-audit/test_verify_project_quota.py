"""Synthetic parser boundaries, not guest evidence."""
import json
import argparse
from pathlib import Path
import tempfile
import unittest

from verify_project_quota import verify
from run_project_quota_diagnostic import data_device
from run_root_probe import digest, probe_command, run_probe, verify_result


class ProjectQuotaEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.nonce = 'abc01234' * 4
        self.row = dict(nonce=self.nonce, scope='disposable_guest_kernel_NOT_app_api',
                        project=0x60001234, limitedBytes=2 * 1024 * 1024,
                        recoveredBytes=4 * 1024 * 1024, unprivilegedEdquot=True, cleanup=True)

    def text(self, row=None):
        return 'QEMU_PROJECT_QUOTA:' + json.dumps(self.row if row is None else row)

    def test_complete_observation_does_not_close_storage_api(self):
        self.assertEqual(verify(self.text(), self.nonce)['closed'], [])

    def test_stale_duplicate_missing_and_incomplete_evidence_rejected(self):
        for text in ('', self.text() + '\n' + self.text(), 'QEMU_PROJECT_QUOTA:[]'):
            with self.assertRaises(ValueError):
                verify(text, self.nonce)
        with self.assertRaises(ValueError):
            verify(self.text(), '0' * 32)
        for key in self.row:
            row = self.row.copy()
            del row[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(self.text(row), self.nonce)

    def test_bypass_failure_cleanup_and_invalid_boundaries_rejected(self):
        for key, value in (('unprivilegedEdquot', False), ('unprivilegedEdquot', 1),
                           ('cleanup', False), ('cleanup', 1), ('limitedBytes', 0),
                           ('limitedBytes', 2097153), ('limitedBytes', True),
                           ('recoveredBytes', 4194303), ('recoveredBytes', 5242881),
                           ('project', 0), ('project', 0x70000000),
                           ('scope', 'ordinary_app_api')):
            row = dict(self.row, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify(self.text(row), self.nonce)

    def test_actual_mount_requires_each_quota_and_existing_security_flag(self):
        flags = ['rw', 'nosuid', 'nodev', 'usrquota', 'grpquota', 'prjquota']
        def mount(options):
            return '/dev/block/vda /data f2fs ' + ','.join(options) + ' 0 0\n'
        self.assertEqual(data_device(mount(flags)), '/dev/block/vda')
        for flag in flags:
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                data_device(mount([item for item in flags if item != flag]))
        for bad in (mount(flags) * 2, mount(flags).replace('f2fs', 'ext4'),
                    mount(flags).replace('/dev/block/vda', '/dev/sda')):
            with self.assertRaises(ValueError):
                data_device(bad)

    def test_root_runner_requires_actual_device_and_process_success(self):
        command = probe_command('project-quota', '/data/local/tmp/owned', self.nonce, '/dev/block/vda')
        self.assertIn('--disposable-guest /dev/block/vda ' + self.nonce, command)
        self.assertTrue(command.startswith('unset LD_LIBRARY_PATH LD_PRELOAD; '))
        self.assertIn('probe_status=$?', command)
        for device in (None, '/dev/sda', '/dev/block/vda; reboot', '/data', ''):
            with self.assertRaises(ValueError):
                probe_command('project-quota', '/data/local/tmp/owned', self.nonce, device)
        self.assertEqual(verify_result('project-quota', self.text(), 'arm64', self.nonce, 0)['closed'], [])
        for code in (False, None, 1, 127):
            with self.assertRaises(ValueError):
                verify_result('project-quota', self.text(), 'arm64', self.nonce, code)

    def test_unowned_target_is_rejected_before_any_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(kind='project-quota', target='not-owned', arch='arm64', device='phone',
                output=Path(temporary) / 'result')
            def forbidden(*args, **kwargs):
                self.fail('must not contact an unowned guest')
            result = run_probe(args, runner=forbidden)
            self.assertEqual(result['status'], 'fail')
            self.assertIn('live owned disposable', result['failures'][0])
            self.assertEqual(result['commands'], [])

    def test_delivery_gate_replays_raw_quota_and_mount_observations(self):
        from verify_first_artifact_gate import REQUIRED_CHECKS, verified_payload
        self.assertIn('project-quota', REQUIRED_CHECKS)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / 'stdout.jsonl'
            raw.write_text(self.text())
            mounts = root / 'actual-mounts.log'
            mounts.write_text('/dev/block/vda /data f2fs rw,nosuid,nodev,usrquota,grpquota,prjquota 0 0\n')
            path = root / 'result.json'
            payload = {'status': 'pass', 'kind': 'project-quota', 'boot_id': 'fixture-boot',
                'archive_sha256': 'a' * 64, 'arch': 'arm64', 'device': 'phone', 'target': 'owned',
                'scope': 'isolated_root_probe_only_not_normal_app_or_full_capability_gate',
                'archive_binding': 'actual_live_owned_boot_and_initial_full_archive_inventory',
                'kernel_boot_id_unchanged': True, 'first_artifact_behavior_gate_passed': False,
                'run_id': self.nonce, 'probe_exit_code': 0, 'log_sha256': digest(raw),
                'result': verify(self.text(), self.nonce), 'quota_device': '/dev/block/vda',
                'actual_mounts_sha256': digest(mounts)}
            environment = {'boot_id': 'fixture-boot', 'guest_arch': 'arm64', 'device_type': 'phone', 'target': 'owned'}
            def check():
                path.write_text(json.dumps(payload))
                verified_payload('project-quota', path, {'sha256': 'a' * 64}, environment)
            check()
            mounts.write_text(mounts.read_text().replace(',prjquota', ''))
            payload['actual_mounts_sha256'] = digest(mounts)
            with self.assertRaises(ValueError): check()

    def test_unified_runner_builds_each_actual_arch_and_same_boot(self):
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("'--sdk', sdk / 'native', '--arch', arch, '--output', quota_probes", suite)
        self.assertIn("check('project-quota', work / 'project-quota/result.json', [quota_build, quota_runtime])", suite)


if __name__ == '__main__':
    unittest.main()
