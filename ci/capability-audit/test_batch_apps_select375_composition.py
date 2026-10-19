"""Host source/transaction checks only; never a native/SDK/guest pass."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from batch_apps_select375_fixture import COMPONENT, installer, materialize


class Composition(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='select375-owned-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        materialize(self.root)
        self.app = installer()
        self.value = self.app.manifest()

    def apply(self):
        with mock.patch.object(self.app, 'revisions'):
            return self.app.apply(self.root)

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mode & 0o777)
                for p in self.root.rglob('*') if p.is_file() and '.ohos-qemu-patches' not in p.parts}

    def test_current_complete_vector_normal_and_two_replays(self):
        self.assertEqual(self.app.state(self.root, self.value, False), 'before')
        self.assertEqual(self.apply()['status'], 'applied')
        self.assertEqual(self.app.state(self.root, self.value, False), 'after')
        after = self.snapshot()
        for _ in range(2):
            self.assertEqual(self.apply()['status'], 'already_applied')
            self.assertEqual(self.snapshot(), after)

    def test_current_modal_and_wallpaper_are_exact_immutable_dependencies(self):
        keep = {name: (self.root / name).read_bytes() for name in self.value['dependencies']}
        self.apply()
        self.assertEqual(keep, {name: (self.root / name).read_bytes() for name in keep})
        self.assertEqual(len(self.value['files']), 9)
        self.assertEqual(len(self.value['patches']), 3)

    def test_publication_returns_exact_owned_identity(self):
        path = self.root / 'owned-publication'
        path.write_bytes(b'old')
        published = self.app.atomic_write(path, b'new', 0o640)
        self.assertEqual(published, self.app.identity(path.lstat()))
        self.assertEqual(path.read_bytes(), b'new')
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(path.parent.glob('.owned-publication.qemu-choose-*')), [])

    def test_parent_alias_root_rejects_before_any_write(self):
        with tempfile.TemporaryDirectory(prefix='select375-root-alias-') as temporary:
            parent = Path(temporary).resolve()
            alias = parent / 'alias'
            alias.symlink_to(self.root.parent, target_is_directory=True)
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, 'canonical'):
                self.app.apply(alias / self.root.name)
            self.assertEqual(self.snapshot(), before)

    def test_root_shared_guards_require_every_target_and_dependency(self):
        self.apply()
        run = subprocess.check_output
        # These fixture copies have no project repositories. Only the project
        # revision/toplevel observations are host doubles; all guard source and
        # source hashes, patch inventories and full-vector checks execute.
        for project in self.value['projects']:
            (self.root / project / '.git').mkdir()
        def project_observation(argv, *args, **kwargs):
            if len(argv) >= 5 and argv[:2] == ['git', '-C'] and argv[3] == 'rev-parse':
                relative = Path(argv[2]).relative_to(self.root).as_posix()
                if argv[4:] in (['--verify', 'HEAD^{commit}'], ['HEAD']):
                    return self.value['projects'][relative] + '\n'
                if argv[4:] == ['--show-toplevel']:
                    return argv[2] + '\n'
            return run(argv, *args, **kwargs)
        with mock.patch.object(subprocess, 'check_output', side_effect=project_observation):
            for name in ['share_picker', 'wallpaper_settings']:
                spec = importlib.util.spec_from_file_location('select375_guard_' + name,
                    COMPONENT.parent / name / 'verify_source.py')
                guard = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(guard)
                self.assertTrue(guard.validate(self.root, require_patched=True))
                for relative in [*self.value['files'], *self.value['dependencies']]:
                    with self.subTest(guard=name, relative=relative):
                        path = self.root / relative
                        original = path.read_bytes()
                        path.write_bytes(original + b'unknown')
                        try:
                            with self.assertRaises(ValueError):
                                guard.validate(self.root, require_patched=True)
                        finally:
                            path.write_bytes(original)

    def test_old_modal_dependencies_are_not_current_predecessor(self):
        old = json.loads((COMPONENT / 'historical-v1.json').read_bytes())
        self.assertNotEqual(old['dependencies'], self.value['dependencies'])
        with tempfile.TemporaryDirectory(prefix='select375-historical-') as temporary:
            root = Path(temporary).resolve()
            materialize(root, historical=True)
            with self.assertRaisesRegex(ValueError, 'predecessor dependency'):
                self.app.state(root, self.value, False)

    def test_each_partial_native_settings_or_new_file_rejects(self):
        original = {name: (self.root / name).read_bytes() if (self.root / name).exists() else None
                    for name in self.value['files']}
        self.apply()
        for name in self.value['files']:
            with self.subTest(name=name):
                path = self.root / name
                final = path.read_bytes()
                if original[name] is None:
                    path.unlink()
                else:
                    path.write_bytes(original[name])
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, 'mixed'):
                    self.apply()
                self.assertEqual(self.snapshot(), before)
                path.write_bytes(final)

    def test_all_dependencies_unknown_edits_reject_without_any_writes(self):
        for name in self.value['dependencies']:
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b'unknown')
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, 'predecessor dependency'):
                    self.apply()
                self.assertEqual(self.snapshot(), before)
                path.write_bytes(original)

    def test_hardlink_and_symlink_are_rejected_before_and_after_apply(self):
        for applied in [False, True]:
            if applied:
                self.apply()
            for name in [next(iter(self.value['files'])), next(iter(self.value['dependencies']))]:
                with self.subTest(applied=applied, name=name):
                    path = self.root / name
                    data = path.read_bytes()
                    alias = self.root / 'alias'
                    os.link(path, alias)
                    with self.assertRaisesRegex(ValueError, 'alias'):
                        self.apply()
                    alias.unlink()
                    path.unlink()
                    alias.write_bytes(data)
                    path.symlink_to(alias)
                    with self.assertRaisesRegex(ValueError, 'symlink'):
                        self.apply()
                    path.unlink()
                    path.write_bytes(data)
                    alias.unlink()

    def mutate_during_prepare(self, mutate):
        run = self.app.subprocess.run
        changed = False
        def wrapper(*args, **kwargs):
            nonlocal changed
            result = run(*args, **kwargs)
            command = args[0] if args else kwargs.get('args', [])
            if not changed and '-C' in command and 'apply' in command:
                changed = True
                mutate()
            return result
        with mock.patch.object(self.app.subprocess, 'run', side_effect=wrapper):
            with self.assertRaises(ValueError):
                self.apply()

    def test_prewrite_chmod_is_not_hidden_by_same_state_enum(self):
        name = next(iter(self.value['files']))
        path = self.root / name
        data = path.read_bytes()
        self.mutate_during_prepare(lambda: path.chmod(0o600))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.read_bytes(), data)
        self.assertFalse(any((self.root / n).exists() for n, r in self.value['files'].items() if r['before'] is None))

    def test_prewrite_same_bytes_new_inode_hardlink_and_symlink_reject(self):
        name = next(iter(self.value['files']))
        path = self.root / name
        original = path.read_bytes()
        for kind in ['replace', 'hardlink', 'symlink']:
            with self.subTest(kind=kind):
                external = self.root / 'external'
                external.write_bytes(original)
                def change():
                    path.unlink()
                    if kind == 'replace':
                        replacement = self.root / 'replacement'
                        replacement.write_bytes(original)
                        os.replace(replacement, path)
                    elif kind == 'hardlink':
                        os.link(external, path)
                    else:
                        path.symlink_to(external)
                self.mutate_during_prepare(change)
                self.assertEqual(external.read_bytes(), original)
                self.assertEqual(path.is_symlink(), kind == 'symlink')
                path.unlink()
                path.write_bytes(original)
                external.unlink()

    def test_prewrite_dependency_mode_change_is_preserved(self):
        path = self.root / next(iter(self.value['dependencies']))
        self.mutate_during_prepare(lambda: path.chmod(0o600))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_unwritten_external_edit_after_first_publish_is_not_rolled_back(self):
        names = list(self.value['files'])
        first = self.root / names[0]
        next_path = self.root / names[1]
        data = first.read_bytes()
        mode = first.stat().st_mode & 0o777
        write = self.app.atomic_write
        fired = False
        def change(target, contents, permissions):
            nonlocal fired
            result = write(target, contents, permissions)
            if not fired:
                fired = True
                next_path.write_bytes(b'external-edit')
            return result
        with mock.patch.object(self.app, 'atomic_write', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'changed during transaction'):
                self.apply()
        self.assertEqual(next_path.read_bytes(), b'external-edit')
        self.assertEqual(first.read_bytes(), data)
        self.assertEqual(first.stat().st_mode & 0o777, mode)

    def test_external_edit_of_published_file_is_preserved_and_recovery_kept(self):
        first = self.root / next(iter(self.value['files']))
        write = self.app.atomic_write
        fired = False
        def change(target, contents, permissions):
            nonlocal fired
            result = write(target, contents, permissions)
            if not fired:
                fired = True
                target.write_bytes(b'external-published-edit')
            return result
        with mock.patch.object(self.app, 'atomic_write', side_effect=change):
            with self.assertRaisesRegex(RuntimeError, 'rollback incomplete') as raised:
                self.apply()
        self.assertEqual(first.read_bytes(), b'external-published-edit')
        recovery = Path(str(raised.exception).split('retained at ', 1)[1].split(';', 1)[0])
        self.addCleanup(shutil.rmtree, recovery)
        self.assertTrue((recovery / 'original.json').is_file())

    def test_failed_write_restores_all_actual_writes_and_modes(self):
        for index, name in enumerate(self.value['files']):
            path = self.root / name
            if path.exists():
                path.chmod(0o600 if index % 2 else 0o640)
        before = self.snapshot()
        write = self.app.atomic_write
        calls = 0
        def fail(target, data, mode):
            nonlocal calls
            calls += 1
            if calls == 5:
                raise OSError('before-publication-fault')
            return write(target, data, mode)
        with mock.patch.object(self.app, 'atomic_write', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'before-publication-fault'):
                self.apply()
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
