"""Synthetic parser boundaries, not guest evidence."""
import json
import unittest

from verify_project_quota import verify
from run_project_quota_diagnostic import data_device


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


if __name__ == '__main__':
    unittest.main()
