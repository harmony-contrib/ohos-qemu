"""Runner/gate contract regressions; constructed data never proves a guest."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import parallel_runtime_suite as suite


class ParallelRuntimeSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.archive = self.root / 'unit-only.tar.gz'; self.archive.write_bytes(b'not a package')
        self.boot_dir = self.root / 'boot'; self.boot_dir.mkdir()
        qmp = str(self.root / 'qmp.sock')
        self.env = dict(product='arm64_virt', device_type='phone', guest_arch='arm64',
            boot_id='12345678-1234-1234-1234-123456789abc', target='127.0.0.1:1234',
            external_keepalive=False, qemu_pid=999, qmp_socket=qmp,
            qemu_command='unit-test-only-qemu -qmp ' + qmp, udid='a' * 64)
        self.boot = self.boot_dir / 'boot.json'
        self.boot.write_text(json.dumps(dict(status='pass', purpose='acceptance',
            scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
            archive_sha256=suite.digest(self.archive), test_environment=self.env)))
        self.plan = dict(schema_version=1, product='arm64_virt', device_type='phone', families={})
        for name, (_, required, _) in suite.FAMILIES.items():
            self.plan['families'][name] = {}
            for key in required:
                path = self.root / (name + '-' + key)
                if key == 'signer-dist': path.mkdir()
                else: path.write_text('unit data only')
                self.plan['families'][name][key] = str(path)

    def plan_path(self, value):
        path = self.root / 'inputs.json'; path.write_text(json.dumps(value)); return path

    def result(self, name):
        directory = self.root / name; directory.mkdir(exist_ok=True)
        path = directory / 'evidence.json'
        path.write_text(json.dumps(dict(status='pass', archive_sha256=suite.digest(self.archive),
            boot_id=self.env['boot_id'], cleanup_complete=True, cleanup_errors=[])))
        suite.boot_copy(self.boot, self.boot_dir / (name + '-boot.json'))
        return path

    def test_input_plan_cannot_supply_executables_arguments_or_omit_a_family(self):
        suite.load_plan(self.plan_path(self.plan), self.env)
        for mutation in (lambda d: d.update(executable='arbitrary'),
                         lambda d: d['families'].pop('wallpaper'),
                         lambda d: d['families']['wallpaper'].update(argv=['arbitrary']),
                         lambda d: d['families']['contacts-picker'].pop('observer-receipt'),
                         lambda d: d['families']['external-inputs'].update(artifacts='relative.json')):
            value = copy.deepcopy(self.plan); mutation(value)
            with self.assertRaises(ValueError): suite.load_plan(self.plan_path(value), self.env)
        with self.assertRaises(ValueError): suite.load_plan(None, self.env)
        self.plan_path(self.plan).write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): suite.load_plan(self.root / 'inputs.json', self.env)

    def test_runner_and_owned_power_receipt_are_fixed_by_family(self):
        command = suite.argv('wallpaper', self.plan, self.boot, self.archive, '/hdc', self.root / 'output', self.root / 'suite.json')
        self.assertTrue(command[1].endswith('/batch_media_wallpaper_suite.py'))
        self.assertEqual(command[-2:], ['--suite-evidence', str(self.root / 'suite.json')])
        with self.assertRaises(KeyError): suite.argv('unregistered', self.plan, self.boot, self.archive, '/hdc', self.root, self.root)

    def test_later_parent_wake_cannot_change_stable_child_boot(self):
        (self.boot_dir / 'qemu.log').write_text('unit-only serial')
        snapshot = suite.boot_copy(self.boot, self.boot_dir / 'wallpaper-boot.json')
        original = snapshot.read_bytes(); self.boot.write_text('{"later_parent_wake":true}')
        self.assertEqual(snapshot.read_bytes(), original)
        self.assertEqual((snapshot.parent / 'qemu.log').read_text(), 'unit-only serial')
        with self.assertRaises(FileExistsError): suite.boot_copy(self.boot, snapshot)
        with self.assertRaises(ValueError): suite.boot_copy(self.boot, self.root / 'foreign-boot.json')

    def test_outer_pass_cannot_bypass_real_family_raw_verifier(self):
        path = self.result('contacts-picker')
        verifier = Mock(side_effect=ValueError('actual raw session rejected'))
        with patch.object(suite.importlib, 'import_module', return_value=types.SimpleNamespace(verify_evidence=verifier)):
            with self.assertRaisesRegex(ValueError, 'raw session'): suite.verify_family('contacts-picker', path, self.archive, self.env)
        verifier.assert_called_once_with(path, self.archive, self.boot_dir / 'contacts-picker-boot.json')

    def test_partial_contacts_results_cannot_satisfy_complete_boundary_gate(self):
        path = self.result('contacts-picker')
        for partial in ({}, {'full_boundaries_verified': False}, None):
            with patch.object(suite.importlib, 'import_module', return_value=types.SimpleNamespace(
                    verify_evidence=Mock(return_value=partial))):
                with self.assertRaisesRegex(ValueError, 'deadline/navigation'):
                    suite.verify_family('contacts-picker', path, self.archive, self.env)

    def test_matching_boot_id_cannot_hide_replaced_VM_or_failed_cleanup(self):
        path = self.result('external-inputs')
        for changed in (dict(self.env, qemu_pid=1000), dict(self.env, target='127.0.0.1:5678')):
            with self.assertRaisesRegex(ValueError, 'actual VM'): suite.verify_family('external-inputs', path, self.archive, changed)
        value = json.loads(path.read_text()); value['cleanup_complete'] = False; path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'incomplete'): suite.verify_family('external-inputs', path, self.archive, self.env)

    def test_public_still_subset_cannot_close_original_broad_MSDP_finding(self):
        path = self.result('external-inputs')
        with patch.object(suite, 'verify_family') as verify:
            self.assertEqual(suite.verified_closures('external-inputs', path, self.archive, self.env), {})
        verify.assert_called_once()
        with patch.object(suite, 'verify_family', side_effect=ValueError('raw failure')):
            with self.assertRaisesRegex(ValueError, 'raw failure'):
                suite.verified_closures('external-inputs', path, self.archive, self.env)


if __name__ == '__main__': unittest.main()
