"""Keep failed or foreign product output from replacing a successful build."""
import hashlib
import json
import errno
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_openvpn_ohos import product_build_path, recipe_identity
from build_product_openvpn import publish


class OpenvpnProductOutputTests(unittest.TestCase):
    def snapshot(self, root):
        return {str(path.relative_to(root)):
            ('alias', os.readlink(path)) if path.is_symlink() else
            ('directory',) if path.is_dir() else ('file', path.read_bytes())
            for path in root.rglob('*')}

    def assert_preserved_rejection(self, root, new, previous):
        before = self.snapshot(root)
        with self.assertRaises(ValueError):
            publish(new, previous)
        self.assertEqual(self.snapshot(root), before)

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

    def test_empty_gn_directory_is_replaced_without_touching_parent_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new = root / 'source-build', root / 'new'
            previous.mkdir(mode=0o755)
            for name in ('qemu_openvpn.stamp', 'NOTICE.txt'):
                (root / name).write_bytes(b'GN parent artifact\n')
            self.fixture(new, b'new unit binary')
            source_inode = new.stat().st_ino
            publish(new, previous)
            self.assertEqual(previous.stat().st_ino, source_inode)
            self.assertFalse(new.exists())
            self.assertEqual((previous / 'openvpn').read_bytes(), b'new unit binary')
            for name in ('qemu_openvpn.stamp', 'NOTICE.txt'):
                self.assertEqual((root / name).read_bytes(), b'GN parent artifact\n')
            self.assertEqual(list(root.glob('source-build.previous-*')), [])

    def test_nonempty_unknown_directory_including_stamp_is_preserved(self):
        for name in ('caller.txt', 'NOTICE.txt', 'qemu_openvpn.stamp'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                previous, new = root / 'output', root / 'new'
                previous.mkdir()
                (previous / name).write_bytes(b'unknown caller content\n')
                self.fixture(new, b'new unit binary')
                self.assert_preserved_rejection(root, new, previous)

    def test_unknown_file_arriving_before_empty_rename_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new = root / 'output', root / 'new'
            previous.mkdir()
            self.fixture(new, b'new unit binary')
            replace = os.replace

            def race(source, destination):
                self.assertEqual((source, destination), (new, previous))
                (previous / 'caller.txt').write_bytes(b'arrived after empty check')
                replace(source, destination)  # real kernel must reject nonempty directory

            with patch('build_product_openvpn.os.replace', side_effect=race) as renamed:
                with self.assertRaises(OSError) as failure:
                    publish(new, previous)
            self.assertIn(failure.exception.errno, (errno.ENOTEMPTY, errno.EEXIST))
            self.assertEqual(renamed.call_count, 1)
            self.assertEqual((previous / 'caller.txt').read_bytes(), b'arrived after empty check')
            self.assertEqual((new / 'openvpn').read_bytes(), b'new unit binary')
            self.assertEqual(list(root.glob('output.previous-*')), [])

    def test_alias_arriving_before_empty_rename_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new, foreign = root / 'output', root / 'new', root / 'foreign'
            previous.mkdir()
            foreign.mkdir()
            self.fixture(new, b'new unit binary')
            replace = os.replace

            def race(source, destination):
                replace(previous, root / 'original-empty')
                previous.symlink_to(foreign, target_is_directory=True)
                replace(source, destination)  # directory rename cannot replace an alias

            with patch('build_product_openvpn.os.replace', side_effect=race):
                with self.assertRaises(OSError):
                    publish(new, previous)
            self.assertTrue(previous.is_symlink())
            self.assertEqual(list(foreign.iterdir()), [])
            self.assertTrue((root / 'original-empty').is_dir())
            self.assertEqual((new / 'openvpn').read_bytes(), b'new unit binary')

    def test_empty_directory_rename_failure_preserves_both_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new = root / 'output', root / 'new'
            previous.mkdir()
            self.fixture(new, b'new unit binary')
            before = self.snapshot(root)
            with patch('build_product_openvpn.os.replace', side_effect=PermissionError(errno.EACCES, 'unit injected rename failure')):
                with self.assertRaises(PermissionError):
                    publish(new, previous)
            self.assertEqual(self.snapshot(root), before)

    def test_aliases_to_empty_or_missing_directories_are_preserved(self):
        for alias_side in ('source', 'destination'):
            for target_exists in (False, True):
                with self.subTest(alias_side=alias_side, target_exists=target_exists), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    previous, new, target = root / 'output', root / 'new', root / 'foreign'
                    if target_exists:
                        target.mkdir()
                    self.fixture(new, b'new unit binary')
                    if alias_side == 'destination':
                        previous.symlink_to(target, target_is_directory=True)
                    else:
                        previous.mkdir()
                        os.replace(new, root / 'original-source')
                        new.symlink_to(target, target_is_directory=True)
                    self.assert_preserved_rejection(root, new, previous)

    def test_old_command_evidence_must_be_complete_safe_and_unchanged(self):
        cases = ('changed-log', 'empty', 'missing', 'not-list', 'not-command', 'missing-log',
                 'unsafe-log', 'alias-log', 'missing-file', 'directory-log', 'bad-hash', 'nonzero', 'boolean-exit')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                previous, new = root / 'output', root / 'new'
                self.fixture(previous, b'old unit binary')
                self.fixture(new, b'new unit binary')
                receipt = previous / 'build-evidence.json'
                report = json.loads(receipt.read_text())
                if case == 'changed-log':
                    (previous / 'compile.log').write_text('caller changed the old log')
                elif case == 'empty':
                    report['commands'] = []
                elif case == 'missing':
                    del report['commands']
                elif case == 'not-list':
                    report['commands'] = {}
                elif case == 'not-command':
                    report['commands'] = [None]
                elif case == 'missing-log':
                    del report['commands'][0]['log']
                elif case == 'unsafe-log':
                    (root / 'outside.log').write_bytes((previous / 'compile.log').read_bytes())
                    report['commands'][0]['log'] = '../outside.log'
                elif case == 'alias-log':
                    (root / 'outside.log').write_bytes((previous / 'compile.log').read_bytes())
                    (previous / 'compile.log').unlink()
                    (previous / 'compile.log').symlink_to(root / 'outside.log')
                elif case == 'missing-file':
                    (previous / 'compile.log').unlink()
                elif case == 'directory-log':
                    (previous / 'compile.log').unlink()
                    (previous / 'compile.log').mkdir()
                elif case == 'bad-hash':
                    report['commands'][0]['sha256'] = 'not-a-sha256'
                elif case == 'nonzero':
                    report['commands'][0]['exit_code'] = 1
                elif case == 'boolean-exit':
                    report['commands'][0]['exit_code'] = False
                receipt.write_text(json.dumps(report))
                self.assert_preserved_rejection(root, new, previous)

    def test_old_recipe_must_be_structured_and_internally_consistent(self):
        for case in ('missing', 'not-object', 'empty-files', 'bad-file-hash', 'bad-recipe-hash', 'unsafe-path'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                previous, new = root / 'output', root / 'new'
                self.fixture(previous, b'old unit binary')
                self.fixture(new, b'new unit binary')
                receipt = previous / 'build-evidence.json'
                report = json.loads(receipt.read_text())
                if case == 'missing':
                    del report['recipe']
                elif case == 'not-object':
                    report['recipe'] = []
                elif case == 'empty-files':
                    report['recipe']['files_sha256'] = {}
                elif case == 'bad-file-hash':
                    name = next(iter(report['recipe']['files_sha256']))
                    report['recipe']['files_sha256'][name] = 'invalid'
                elif case == 'bad-recipe-hash':
                    report['recipe']['recipe_sha256'] = '0' * 64
                elif case == 'unsafe-path':
                    report['recipe']['files_sha256'] = {'../caller': 'a' * 64}
                if case in ('empty-files', 'bad-file-hash', 'unsafe-path'):
                    report['recipe']['recipe_sha256'] = hashlib.sha256(
                        json.dumps(report['recipe']['files_sha256'], sort_keys=True).encode()).hexdigest()
                receipt.write_text(json.dumps(report))
                self.assert_preserved_rejection(root, new, previous)

    def test_valid_historical_recipe_may_differ_from_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new = root / 'output', root / 'new'
            self.fixture(previous, b'old unit binary')
            self.fixture(new, b'new unit binary')
            receipt = previous / 'build-evidence.json'
            report = json.loads(receipt.read_text())
            name = next(iter(report['recipe']['files_sha256']))
            report['recipe']['files_sha256'][name] = '1' * 64
            report['recipe']['recipe_sha256'] = hashlib.sha256(
                json.dumps(report['recipe']['files_sha256'], sort_keys=True).encode()).hexdigest()
            receipt.write_text(json.dumps(report))
            historical = receipt.read_bytes()
            publish(new, previous)
            backup, = root.glob('output.previous-*')
            self.assertEqual((backup / 'build-evidence.json').read_bytes(), historical)
            self.assertEqual((previous / 'openvpn').read_bytes(), b'new unit binary')

    def test_malformed_or_alias_receipt_is_preserved_on_both_sides(self):
        for side in ('old', 'new'):
            for case in ('invalid-json', 'list', 'alias'):
                with self.subTest(side=side, case=case), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    previous, new = root / 'output', root / 'new'
                    self.fixture(previous, b'old unit binary')
                    self.fixture(new, b'new unit binary')
                    receipt = (previous if side == 'old' else new) / 'build-evidence.json'
                    if case == 'invalid-json':
                        receipt.write_text('{invalid')
                    elif case == 'list':
                        receipt.write_text('[]')
                    else:
                        target = root / 'foreign-receipt.json'
                        target.write_bytes(receipt.read_bytes())
                        receipt.unlink()
                        receipt.symlink_to(target)
                    self.assert_preserved_rejection(root, new, previous)

    def test_new_commands_cannot_be_empty_or_malformed(self):
        for commands in ([], {}, [None], [{'log': 3, 'exit_code': 0, 'sha256': 'a' * 64}]):
            with self.subTest(commands=commands), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                previous, new = root / 'output', root / 'new'
                self.fixture(previous, b'old unit binary')
                self.fixture(new, b'new unit binary')
                receipt = new / 'build-evidence.json'
                report = json.loads(receipt.read_text())
                report['commands'] = commands
                receipt.write_text(json.dumps(report))
                self.assert_preserved_rejection(root, new, previous)

    def test_controlled_old_output_and_new_attempt_survive_second_rename_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, new = root / 'output', root / 'new'
            self.fixture(previous, b'old unit binary')
            self.fixture(new, b'new unit binary')
            (previous / 'caller.txt').write_bytes(b'preserve alongside controlled output')
            old_snapshot, new_snapshot = self.snapshot(previous), self.snapshot(new)
            replace = os.replace

            def fail_publication(source, destination):
                if source == new:
                    raise PermissionError(errno.EACCES, 'unit injected publication failure')
                replace(source, destination)

            with patch('build_product_openvpn.os.replace', side_effect=fail_publication):
                with self.assertRaises(PermissionError):
                    publish(new, previous)
            backup, = root.glob('output.previous-*')
            self.assertEqual(self.snapshot(backup), old_snapshot)
            self.assertEqual(self.snapshot(new), new_snapshot)


if __name__ == '__main__':
    unittest.main()
