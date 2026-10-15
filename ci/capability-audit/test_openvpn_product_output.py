"""Keep failed or foreign product output from replacing a successful build."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_openvpn_ohos import product_build_path, recipe_identity
from build_product_openvpn import publish


class OpenvpnProductOutputTests(unittest.TestCase):
    def fixture(self, path, binary):
        path.mkdir()
        (path / 'openvpn').write_bytes(binary)
        (path / 'compile.log').write_text('explicit unit fixture, not a real compilation\n')
        report = {'schema_version': 2, 'component': 'fixed source OpenVPN for QEMU OHOS',
            'product': 'arm64_virt', 'status': 'pass_source_build_ONLY_NOT_packaged_or_runtime',
            'recipe': recipe_identity(), 'runtime_gate_passed': False,
            'binary_sha256': hashlib.sha256(binary).hexdigest(),
            'commands': [{'log': 'compile.log', 'exit_code': 0,
                'sha256': hashlib.sha256((path / 'compile.log').read_bytes()).hexdigest()}]}
        (path / 'build-evidence.json').write_text(json.dumps(report))

    def test_scope_rejects_escapes_and_other_products(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            allowed = root / 'out/arm64_virt/gen/foundation/communication/netmanager_ext/qemu_openvpn'
            product_build_path(root, 'arm64_virt', allowed / 'source-build')
            for wrong in (allowed, root / 'caller', allowed / '../foreign',
                          root / 'out/x86_64_virt/gen/foundation/communication/netmanager_ext/qemu_openvpn/source-build'):
                with self.assertRaises(ValueError):
                    product_build_path(root, 'arm64_virt', wrong.resolve())

    def test_changed_logs_do_not_publish_or_move_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new = root / 'output', root / 'new'
            self.fixture(previous, b'old unit binary')
            self.fixture(new, b'new unit binary')
            (new / 'compile.log').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'evidence'):
                publish(new, previous)
            self.assertEqual((previous / 'openvpn').read_bytes(), b'old unit binary')
            self.assertTrue(new.is_dir())
            self.assertEqual(list(root.glob('output.previous-*')), [])

    def test_changed_caller_binary_and_alias_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new = root / 'output', root / 'new'
            self.fixture(previous, b'old unit binary')
            self.fixture(new, b'new unit binary')
            (previous / 'openvpn').write_bytes(b'caller modified binary')
            with self.assertRaisesRegex(ValueError, 'preserving caller'):
                publish(new, previous)
            self.assertEqual((previous / 'openvpn').read_bytes(), b'caller modified binary')
            alias = root / 'alias'
            alias.symlink_to(previous)
            with self.assertRaisesRegex(ValueError, 'alias'):
                publish(new, alias)
            self.assertTrue(alias.is_symlink())

    def test_success_preserves_previous_binary_logs_and_extra_caller_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new = root / 'output', root / 'new'
            self.fixture(previous, b'old unit binary')
            self.fixture(new, b'new unit binary')
            (previous / 'caller.txt').write_text('keep me')
            publish(new, previous)
            self.assertEqual((previous / 'openvpn').read_bytes(), b'new unit binary')
            backup, = root.glob('output.previous-*')
            self.assertEqual((backup / 'openvpn').read_bytes(), b'old unit binary')
            self.assertEqual((backup / 'caller.txt').read_text(), 'keep me')
            self.assertTrue((backup / 'compile.log').is_file())


if __name__ == '__main__':
    unittest.main()
