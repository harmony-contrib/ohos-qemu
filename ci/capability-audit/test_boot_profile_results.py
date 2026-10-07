#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_boot_profile_probe import run
from run_root_probe import digest
from verify_boot_profile_results import verify
from verify_gap_closure import behavior_results


MODULE = 'Inode: 204   Type: regular    Mode:  0755\nSize: 127584\n'
MISSING = 'File not found by ext2_lookup\n'
SERIAL = '''[pid=1][Init][INFO]check_module_update start.
[pid=95][Init][INFO]HandleModuleUpdate, exec chekc_module_update.
SAFWK: Start OnStart-SA:1907 finished, spend:1 ms
[pid=1][Init][INFO]boot completed, uninstall module_update_init.
SAFWK: Publish SA:1907 result:0,spend:1ms
'''


class BootProfileResultsTests(unittest.TestCase):
    def test_actual_image_and_boot_snapshot_close_two_narrow_findings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'package.tar.gz'
            archive.write_bytes(b'archive')
            boot_dir = root / 'boot'
            directory = boot_dir / 'extract/package'
            image = directory / 'images/system.img'
            image.parent.mkdir(parents=True)
            image.write_bytes(b'ext-image-fixture')
            (boot_dir / 'qemu.log').write_text(SERIAL)
            boot = boot_dir / 'boot.json'
            boot.write_text(json.dumps({'status': 'pass', 'purpose': 'acceptance',
                'archive_sha256': digest(archive),
                'initial_package_file_sha256': {'images/system.img': digest(image)},
                'test_environment': {'boot_id': 'fresh', 'external_keepalive': False,
                                     'freshly_extracted_directory': str(directory)}}))
            with patch('run_boot_profile_probe.image_stat', side_effect=[MODULE, MISSING, MISSING]):
                evidence = run(archive, boot, root / 'boot-profile', 'local-docker-image')
            self.assertTrue(evidence['result']['invalid_usage_init_absent'])
            closed = behavior_results(root, 'fresh', digest(archive), 'phone')
            self.assertIn('behavior:module-update-initializer-missing', closed)
            self.assertIn('behavior:usage-statistics-stale-init-profile', closed)
            (root / 'boot-profile/usage-root-stat.txt').write_text(MODULE)
            self.assertNotIn('behavior:usage-statistics-stale-init-profile',
                             behavior_results(root, 'fresh', digest(archive), 'phone'))

    def test_rejects_partial_or_false_image_and_serial_proof(self):
        for module, usages, serial in (
                ('File not found by ext2_lookup', [MISSING, MISSING], SERIAL),
                (MODULE, [MODULE, MISSING], SERIAL),
                (MODULE, [MISSING], SERIAL),
                (MODULE, [MISSING, MISSING], SERIAL.replace('Publish SA:1907 result:0',
                                                             'Publish SA:1907 result:-1')),
                (MODULE, [MISSING, MISSING], SERIAL + 'module_update_init exec error\n')):
            with self.subTest(module=module, usages=usages, serial=serial):
                with self.assertRaises(ValueError):
                    verify(module, usages, serial)
