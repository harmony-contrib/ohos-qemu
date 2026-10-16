"""Exercise source installation transactions; not backend runtime acceptance."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_qemu_openvpn_backend as installer


class OpenvpnSourceInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'source'
        self.root.mkdir()
        self.original = (ROOT / 'ci/capability-audit/fixtures/openvpn_source_install/BUILD.gn').read_bytes()
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), installer.BUILD_SHA256)
        self.build = self.root / installer.BUILD
        self.build.parent.mkdir(parents=True)
        self.build.write_bytes(self.original)
        self.native_cfg = self.root / installer.NATIVE_CFG
        self.native_cfg.parent.mkdir(parents=True)
        self.native_original = (ROOT / 'ci/capability-audit/fixtures/openvpn_source_install/netsysnative.cfg').read_bytes()
        self.assertEqual(hashlib.sha256(self.native_original).hexdigest(), installer.NATIVE_CFG_SHA256)
        self.native_cfg.write_bytes(self.native_original)
        self.archive = Path(self.temporary.name) / 'source.tar.gz'
        self.archive.write_bytes(b'isolated archive contract fixture')

    def valid_fixture_archive(self, path, lock):
        # The real fixed-archive validator has its own digest/length/symlink
        # regressions. Substitute only that input here; all source/GN/init/
        # recipe/policy bytes and installation operations remain real.
        if path.is_symlink() or path.read_bytes() != b'isolated archive contract fixture':
            raise ValueError('invalid isolated archive')

    def install(self):
        with mock.patch.object(installer, 'validate_archive', self.valid_fixture_archive):
            return installer.install(self.root, self.archive)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_complete_install_and_reapply_preserve_product_gates_and_inventory(self):
        report = self.install()
        first = self.snapshot()
        self.assertGreater(len(report['files_sha256']), 20)
        self.assertFalse(report['first_artifact_behavior_gate_passed'])
        for name, checksum in report['files_sha256'].items():
            self.assertEqual(hashlib.sha256(first[name]).hexdigest(), checksum)
        build = self.build.read_text()
        self.assertIn('netmanager_ext_feature_sysvpn && !netmanager_ext_fpga_mode_enable', build)
        self.assertEqual(build.count('qemu_openvpn_backend'), 1)
        for product in ('armv7a_virt', 'arm64_virt', 'x86_64_virt'):
            self.assertIn('product_name == "' + product + '"', build)
        cfg = json.loads(first[installer.PROJECT + '/qemu_openvpn/qemu_openvpn.cfg'])
        service = cfg['services'][0]
        self.assertEqual(service['uid'], 'netsysnative')
        self.assertEqual(service['disabled'], 1)
        self.assertEqual(service['secon'], 'u:r:netsysnative:s0')
        self.assertEqual(service['socket'][0]['name'], 'qemu_openvpn')
        native = json.loads(first[installer.NATIVE_CFG])
        original_native = json.loads(self.native_original)
        native_service = next(s for s in native['services'] if s['name'] == 'netsysnative')
        self.assertEqual(native_service['socket'].pop(0)['name'], 'qemu_openvpn_tunfd')
        self.assertEqual(native, original_native)
        self.install()
        self.assertEqual(first, self.snapshot())

    def test_foreign_file_anywhere_rejects_before_changing_gn_or_other_payloads(self):
        path = self.root / (installer.POLICY_BASE + 'system/parameter_contexts')
        path.parent.mkdir(parents=True)
        path.write_bytes(b'caller policy\n')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'preserving edits'):
            self.install()
        self.assertEqual(before, self.snapshot())

    def test_missing_or_modified_native_cfg_rejects_before_publication(self):
        for content in (None, self.native_original + b'\ncaller change\n'):
            with self.subTest(content=content is None):
                self.native_cfg.unlink(missing_ok=True)
                if content is not None:
                    self.native_cfg.write_bytes(content)
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, 'netsysnative|preserving edits'):
                    self.install()
                self.assertEqual(before, self.snapshot())

    def test_changed_owned_input_and_gn_are_not_overwritten(self):
        self.install()
        for name in [installer.BUILD, installer.PROJECT + '/qemu_openvpn/supervisor.cpp']:
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b'\ncaller modification\n')
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.install()
                self.assertEqual(before, self.snapshot())
                path.write_bytes(original)

    def test_invalid_actual_archive_rejects_before_source_writes(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'fixed source lock'):
            installer.install(self.root, self.archive)
        self.assertEqual(before, self.snapshot())

    def test_alias_and_path_escape_do_not_write_outside_source(self):
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        (self.root / installer.POLICY).parent.mkdir(parents=True)
        (self.root / installer.POLICY).symlink_to(outside, target_is_directory=True)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'linked source'):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(before, self.snapshot())
        for name in ('../outside/file', '/absolute/file'):
            with self.assertRaises(ValueError):
                installer.checked(self.root, name)

    def test_mid_publish_failure_rolls_back_all_prior_files(self):
        before = self.snapshot()
        replace = installer.replace_bytes
        counter = 0

        def fail_once(path, data):
            nonlocal counter
            counter += 1
            if counter == 8:
                raise OSError('injected publication failure')
            replace(path, data)

        with mock.patch.object(installer, 'replace_bytes', fail_once):
            with self.assertRaisesRegex(OSError, 'publication failure'):
                self.install()
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
