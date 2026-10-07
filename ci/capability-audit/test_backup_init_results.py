#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest

from run_backup_init_probe import run
from run_root_probe import digest
from verify_backup_init_results import verify
from verify_gap_closure import behavior_results


GOOD = '''[pid=1][Init][INFO]ServiceStart started info backup_sa(pid 1480 uid 1089)
[pid=1480][Init][INFO][init_service.c:291]ServiceExec backup_sa
SAMGR: Start dynamic proc:backup_sa,5203,0_8ms
'''


class BackupInitResultsTests(unittest.TestCase):
    def test_new_package_start_exec_and_snapshot_close_only_init_finding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'package.tar.gz'
            archive.write_bytes(b'actual-archive-bytes')
            boot = root / 'boot'
            boot.mkdir()
            (boot / 'qemu.log').write_text(GOOD)
            (boot / 'boot.json').write_text(json.dumps({
                'status': 'pass', 'purpose': 'acceptance', 'archive_sha256': digest(archive),
                'test_environment': {'boot_id': 'fresh', 'external_keepalive': False},
            }))
            evidence = run(archive, boot / 'boot.json', root / 'backup-init')
            self.assertEqual(evidence['result']['pid'], 1480)
            closed = behavior_results(root, 'fresh', digest(archive), 'phone')
            self.assertIn('behavior:backup-init-invalid-linux-capability', closed)
            self.assertEqual(len(closed), 1)
            (root / 'backup-init/serial.log').write_text(GOOD.replace('1480', '1481'))
            self.assertNotIn('behavior:backup-init-invalid-linux-capability',
                             behavior_results(root, 'fresh', digest(archive), 'phone'))

    def test_rejects_missing_exec_wrong_identity_and_duplicate_start(self):
        for serial in (GOOD.replace('ServiceExec backup_sa', 'ServiceExec other'),
                       GOOD.replace('uid 1089', 'uid 0'),
                       GOOD.replace('pid 1480 uid 1089', 'pid 1481 uid 1089'),
                       GOOD + GOOD.splitlines()[0] + '\n'):
            with self.subTest(serial=serial):
                with self.assertRaises(ValueError):
                    verify(serial)

    def test_rejects_older_or_assisted_boot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'package.tar.gz'
            archive.write_bytes(b'archive')
            (root / 'qemu.log').write_text(GOOD)
            base = {'status': 'pass', 'purpose': 'acceptance', 'archive_sha256': digest(archive),
                    'test_environment': {'boot_id': 'fresh', 'external_keepalive': False}}
            for change in ({'archive_sha256': 'other'}, {'purpose': 'diagnostic'},
                           {'test_environment': {'boot_id': 'fresh', 'external_keepalive': True}}):
                boot = root / 'boot.json'
                boot.write_text(json.dumps(base | change))
                with self.assertRaises(ValueError):
                    run(archive, boot, root / 'evidence')
