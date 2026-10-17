"""Exact complete QGN1 migrations and failed-write recovery; no GN/build execution."""
import base64
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

import test_batch_system_gnss_installers as fixture


class GnssMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='apps-gnss-migration-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        _, self.root, self.component, self.guard, self.manifest = fixture.candidate(self.base)
        self.before = {name: (self.root / name).read_bytes() for name in self.manifest['originals']}
        history = json.loads((Path(__file__).parent / 'fixtures/batch_apps/gnss_qgn1_overlay.json').read_text())
        self.qgn1_bytes = {name: gzip.decompress(base64.b64decode(row['gzip_base64']))
                           for name, row in history['files'].items()}
        self.assertEqual({name: hashlib.sha256(data).hexdigest() for name, data in self.qgn1_bytes.items()},
                         self.guard.QGN1_FILES)
        self.qgn1_updates = [name for name, row in self.manifest['files'].items()
                            if row['sha256'] != self.guard.QGN1_FILES[name]]
        self.legacy_updates = [name for name in self.manifest['files']
                               if name == self.guard.BUILD or name in self.qgn1_updates]

    def snapshot(self):
        return {name: ((self.root / name).read_bytes(), stat.S_IMODE((self.root / name).stat().st_mode))
                if (self.root / name).exists() else None
                for name in [*self.manifest['originals'], *self.manifest['files'], *self.manifest['dependencies']]}

    def qgn1(self):
        self.guard.apply(self.root)
        for name, data in self.qgn1_bytes.items():
            (self.root / name).write_bytes(data)
        self.assertEqual(self.guard.source_state(self.root, self.manifest), 'qgn1')

    def predecessor(self):
        self.qgn1()
        target = self.root / self.guard.BUILD
        current = target.read_bytes()
        previous = current.replace(b'  output_prefix_override = true\n',
                                   b'  output_prefix = ""\n  output_prefix_override = true\n')
        self.assertEqual(hashlib.sha256(previous).hexdigest(), self.guard.PREDECESSOR[self.guard.BUILD])
        target.write_bytes(previous)
        self.assertEqual(self.guard.source_state(self.root, self.manifest), 'predecessor')

    def assert_refused_unchanged(self, error=(ValueError, OSError)):
        before = self.snapshot()
        with self.assertRaises(error):
            self.guard.apply(self.root)
        self.assertEqual(self.snapshot(), before)

    def external_change(self, path, kind):
        alias = None
        if kind == 'mode':
            path.chmod(0o601)
        elif kind == 'bytes':
            path.write_bytes(path.read_bytes() + b'\n// concurrent external edit\n')
        else:
            alias = self.base / 'external-identical-bytes'
            alias.write_bytes(path.read_bytes())
            alias.chmod(stat.S_IMODE(path.stat().st_mode))
            path.unlink()
            if kind == 'hardlink':
                os.link(alias, path)
            else:
                path.symlink_to(alias)
        return alias

    def restore_changed_path(self, path, data, mode, alias):
        path.unlink()
        path.write_bytes(data)
        path.chmod(mode)
        if alias is not None:
            alias.unlink()

    def test_shipped_contract_keeps_all_other_fixed_bytes(self):
        shipped = json.loads((fixture.previous.ROOT / 'patches/common/device/qemu/external_gnss/manifest.json').read_text())
        self.assertEqual(shipped['projects'], {
            'drivers/peripheral': '69094b77aa2200160207b1b06b3c0b586ae2157c',
            'device/qemu': 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b'})
        self.assertEqual(len(shipped['originals']), 3)
        self.assertEqual(len(shipped['files']), 5)
        self.assertEqual(shipped['patch_sha256'], '931097628212553a66c95f5ce63901cce15f7035638f4d0ed242d081a618fcf4')
        self.assertEqual(shipped['abi_header_sha256'], 'f0df806ff59b5cad6a793a25191b36f546e77c72afb638681fbe1261e39035b5')
        self.assertEqual(shipped['installed_predecessor'], self.guard.PREDECESSOR)
        self.assertEqual(shipped['installed_qgn1'], self.guard.QGN1_FILES)
        self.assertEqual(shipped['files'][self.guard.BUILD]['sha256'],
                         'a33e9ad3ab6652be5e57eb1b310f31652f1b1491b1221dad79d6684a68ad4f16')

    def test_complete_predecessor_changes_four_files_without_reapplying_hdi_patch(self):
        self.predecessor()
        build = self.root / self.guard.BUILD
        build.chmod(0o640)
        unchanged = {name: ((self.root / name).read_bytes(), (self.root / name).stat())
                     for name in self.snapshot() if name not in self.legacy_updates}
        with mock.patch.object(self.guard.subprocess, 'run', wraps=subprocess.run) as run:
            result = self.guard.apply(self.root)
        self.assertEqual(result['status'], 'migrated')
        self.assertEqual(result['files'], self.legacy_updates)
        self.assertEqual(len(result['files']), 4)
        self.assertFalse(any('apply' in call.args[0] for call in run.call_args_list))
        self.assertEqual(build.stat().st_mode & 0o777, 0o640)
        for name, (data, stat) in unchanged.items():
            with self.subTest(path=name):
                path = self.root / name
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual((path.stat().st_ino, path.stat().st_mtime_ns, path.stat().st_mode),
                                 (stat.st_ino, stat.st_mtime_ns, stat.st_mode))
        self.assertTrue(self.guard.validate(self.root, self.manifest, require_patched=True))
        for _ in range(2):
            self.assertEqual(self.guard.apply(self.root)['status'], 'already_applied')

    def test_require_patched_does_not_accept_predecessor(self):
        self.predecessor()
        self.assertFalse(self.guard.validate(self.root, self.manifest))
        with self.assertRaisesRegex(ValueError, 'complete patch'):
            self.guard.validate(self.root, self.manifest, require_patched=True)

    def test_every_original_must_be_exact_complete_patched_version(self):
        self.predecessor()
        for name in self.manifest['originals']:
            path = self.root / name
            patched = path.read_bytes()
            for invalid in [self.before[name], patched + b'// foreign\n']:
                with self.subTest(path=name, pristine=invalid == self.before[name]):
                    path.write_bytes(invalid)
                    self.assert_refused_unchanged()
            path.write_bytes(patched)

    def test_every_unchanged_overlay_must_remain_exact_and_present(self):
        self.predecessor()
        for name in self.manifest['files']:
            if name == self.guard.BUILD:
                continue
            path = self.root / name
            data = path.read_bytes()
            with self.subTest(path=name, absent=False):
                path.write_bytes(data + b'// foreign\n')
                self.assert_refused_unchanged()
            with self.subTest(path=name, absent=True):
                path.unlink()
                self.assert_refused_unchanged()
            path.write_bytes(data)

    def test_unknown_build_preserved(self):
        self.predecessor()
        path = self.root / self.guard.BUILD
        path.write_bytes(path.read_bytes() + b'# foreign\n')
        self.assert_refused_unchanged()

    def test_partial_install_never_admitted_as_predecessor(self):
        path = self.root / self.guard.BUILD
        current = (self.component / self.manifest['files'][self.guard.BUILD]['component_file']).read_bytes()
        path.write_bytes(current.replace(b'  output_prefix_override = true\n',
                                        b'  output_prefix = ""\n  output_prefix_override = true\n'))
        self.assert_refused_unchanged()

    def test_abi_missing_or_changed_preserved(self):
        self.predecessor()
        path = self.root / self.guard.ABI_HEADER
        path.write_bytes(path.read_bytes() + b'// ABI changed\n')
        self.assert_refused_unchanged()
        path.unlink()
        self.assert_refused_unchanged()

    def test_both_projects_git_metadata_mandatory(self):
        self.predecessor()
        for name in self.manifest['projects']:
            with self.subTest(project=name):
                metadata = self.root / name / '.git'
                saved = self.base / 'saved-git'
                metadata.rename(saved)
                self.assert_refused_unchanged()
                saved.rename(metadata)

    def test_wrong_head_of_either_project_rejects_predecessor(self):
        self.predecessor()
        for name in self.manifest['projects']:
            project = self.root / name
            old = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
            subprocess.run(['git', '-C', str(project), '-c', 'user.name=Fixture',
                            '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                            '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'other revision', '--allow-empty'], check=True)
            with self.subTest(project=name):
                self.assert_refused_unchanged()
            subprocess.run(['git', '-C', str(project), 'reset', '--soft', old], check=True)

    def test_invalid_git_object_rejects_even_matching_manifest_head_text(self):
        self.predecessor()
        project = self.root / 'device/qemu'
        (project / '.git/HEAD').write_text(self.manifest['projects']['device/qemu'] + '\n')
        shutil.rmtree(project / '.git/objects')
        (project / '.git/objects').mkdir()
        self.assert_refused_unchanged()

    def test_real_repo_metadata_symlinks_allowed(self):
        self.predecessor()
        for index, name in enumerate(self.manifest['projects']):
            metadata = self.root / name / '.git'
            saved = self.base / ('repo-metadata-' + str(index))
            metadata.rename(saved)
            metadata.symlink_to(saved, target_is_directory=True)
        self.assertEqual(self.guard.apply(self.root)['status'], 'migrated')

    def test_source_build_and_overlay_parent_symlinks_rejected(self):
        self.predecessor()
        for name in [next(iter(self.manifest['originals'])), self.guard.BUILD]:
            path = self.root / name
            saved = self.base / 'external-file'
            path.rename(saved)
            path.symlink_to(saved)
            with self.subTest(path=name):
                self.assert_refused_unchanged()
                self.assertTrue(path.is_symlink())
            path.unlink()
            saved.rename(path)
        parent = (self.root / self.guard.BUILD).parent
        saved = self.base / 'external-directory'
        parent.rename(saved)
        parent.symlink_to(saved, target_is_directory=True)
        self.assert_refused_unchanged()
        self.assertTrue(parent.is_symlink())

    def test_manifest_cannot_admit_a_different_predecessor(self):
        self.predecessor()
        manifest = self.component / 'manifest.json'
        value = json.loads(manifest.read_text())
        value['installed_predecessor'][self.guard.BUILD] = '0' * 64
        manifest.write_text(json.dumps(value))
        self.assert_refused_unchanged()

    def test_failures_before_and_after_build_rename_restore_original_mode_bytes(self):
        self.predecessor()
        path = self.root / self.guard.BUILD
        path.chmod(0o640)
        real_write = self.guard.atomic_write
        for after in [False, True]:
            calls = 0
            def fail_once(target, data, mode):
                nonlocal calls
                calls += 1
                if calls == 1:
                    if after:
                        real_write(target, data, mode)
                    raise OSError('injected write failure')
                real_write(target, data, mode)
            before = self.snapshot()
            with self.subTest(after_rename=after), mock.patch.object(self.guard, 'atomic_write', fail_once):
                with self.assertRaisesRegex(OSError, 'injected write'):
                    self.guard.apply(self.root)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(self.guard.source_state(self.root, self.manifest), 'predecessor')

    def test_failed_final_validation_rolls_back(self):
        self.predecessor()
        original_validate = self.guard.validate
        def fail_final(root, *args, **kwargs):
            if Path(root).resolve() == self.root.resolve():
                raise ValueError('injected final validation')
            return original_validate(root, *args, **kwargs)
        before = self.snapshot()
        with mock.patch.object(self.guard, 'validate', fail_final):
            with self.assertRaisesRegex(ValueError, 'injected final'):
                self.guard.apply(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_failed_rollback_retains_recoverable_old_bytes_and_mode(self):
        self.predecessor()
        path = self.root / self.guard.BUILD
        path.chmod(0o640)
        previous = path.read_bytes()
        real_write = self.guard.atomic_write
        calls = 0
        def fail_both(target, data, mode):
            nonlocal calls
            calls += 1
            if calls == 1:
                real_write(target, data, mode)
            raise OSError('injected write and rollback failure')
        with mock.patch.object(self.guard, 'atomic_write', fail_both):
            with self.assertRaisesRegex(RuntimeError, 'rollback incomplete') as failure:
                self.guard.apply(self.root)
        recovery = Path(str(failure.exception).split('original bytes retained at ', 1)[1].split(';', 1)[0])
        self.addCleanup(shutil.rmtree, recovery)
        self.assertEqual((recovery / self.guard.BUILD).read_bytes(), previous)
        saved = json.loads((recovery / 'original.json').read_text())
        self.assertEqual(saved, {name: {'existed': True, 'mode': 0o640 if name == self.guard.BUILD else 0o644,
                                      'sha256': self.guard.PREDECESSOR.get(name, self.guard.QGN1_FILES[name])}
                                 for name in self.legacy_updates})

    def test_complete_b4_qgn1_changes_only_three_different_overlay_files(self):
        self.qgn1()
        for index, name in enumerate(self.qgn1_updates):
            (self.root / name).chmod((0o640, 0o751, 0o4750)[index])
        before = self.snapshot()
        untouched = {name: (self.root / name).stat() for name in before if name not in self.qgn1_updates}
        with mock.patch.object(self.guard.subprocess, 'run', wraps=subprocess.run) as run:
            result = self.guard.apply(self.root)
        self.assertEqual(result['status'], 'migrated')
        self.assertEqual(result['files'], self.qgn1_updates)
        self.assertEqual(len(result['files']), 3)
        self.assertFalse(any('apply' in call.args[0] for call in run.call_args_list))
        after = self.snapshot()
        for name in before:
            self.assertEqual(after[name][1], before[name][1])
            if name in untouched:
                self.assertEqual(after[name], before[name])
                observed = (self.root / name).stat()
                self.assertEqual((observed.st_ino, observed.st_mtime_ns, observed.st_mode),
                                 (untouched[name].st_ino, untouched[name].st_mtime_ns, untouched[name].st_mode))
        for _ in range(2):
            before = self.snapshot()
            with mock.patch.object(self.guard, 'atomic_write', side_effect=AssertionError('idempotent write')):
                self.assertEqual(self.guard.apply(self.root)['status'], 'already_applied')
            self.assertEqual(self.snapshot(), before)

    def test_all_new_old_overlay_combinations_admit_only_complete_real_states(self):
        self.qgn1()
        build = self.root / self.guard.BUILD
        current_build = build.read_bytes()
        old_build = current_build.replace(b'  output_prefix_override = true\n',
                                          b'  output_prefix = ""\n  output_prefix_override = true\n')
        for old in (False, True):
            build.write_bytes(old_build if old else current_build)
            for bits in itertools.product((False, True), repeat=len(self.qgn1_updates)):
                for name, new in zip(self.qgn1_updates, bits):
                    data = (self.component / self.manifest['files'][name]['component_file']).read_bytes()
                    (self.root / name).write_bytes(data if new else self.qgn1_bytes[name])
                with self.subTest(old_build=old, new_bits=bits):
                    if not any(bits):
                        self.assertEqual(self.guard.source_state(self.root, self.manifest),
                                         'predecessor' if old else 'qgn1')
                    elif all(bits) and not old:
                        self.assertEqual(self.guard.source_state(self.root, self.manifest), 'patched')
                    else:
                        self.assert_refused_unchanged()

    def test_each_missing_or_foreign_overlay_rejected_from_both_historical_states(self):
        self.qgn1()
        for legacy in (False, True):
            if legacy:
                path = self.root / self.guard.BUILD
                path.write_bytes(path.read_bytes().replace(b'  output_prefix_override = true\n',
                    b'  output_prefix = ""\n  output_prefix_override = true\n'))
            for name in self.manifest['files']:
                path = self.root / name
                data = path.read_bytes()
                path.unlink()
                with self.subTest(legacy=legacy, name=name, mutation='missing'):
                    self.assert_refused_unchanged()
                path.write_bytes(data + b'\n// external change\n')
                with self.subTest(legacy=legacy, name=name, mutation='foreign'):
                    self.assert_refused_unchanged()
                path.write_bytes(data)

    def test_qgn1_manifest_hashes_cannot_be_extended_removed_or_changed(self):
        self.qgn1()
        path = self.component / 'manifest.json'
        original = path.read_bytes()
        for mutation in ('change', 'remove', 'extend'):
            value = json.loads(original)
            if mutation == 'change':
                value['installed_qgn1'][self.qgn1_updates[0]] = '0' * 64
            elif mutation == 'remove':
                del value['installed_qgn1'][self.qgn1_updates[0]]
            else:
                value['installed_qgn1']['device/qemu/foreign.cpp'] = '0' * 64
            path.write_text(json.dumps(value))
            with self.subTest(mutation=mutation):
                self.assert_refused_unchanged()
            path.write_bytes(original)

    def test_hardlink_aliases_rejected_for_sources_overlays_abi_and_component_files(self):
        self.qgn1()
        names = [next(iter(self.manifest['originals'])), *self.manifest['files'], self.guard.ABI_HEADER]
        component_paths = [self.component / 'manifest.json', next(self.component.glob('*.patch')),
                           *[self.component / row['component_file'] for row in self.manifest['files'].values()]]
        for path in [*[self.root / name for name in names], *component_paths]:
            alias = self.base / 'hardlink-alias'
            os.link(path, alias)
            try:
                with self.subTest(path=str(path)):
                    self.assert_refused_unchanged()
                    self.assertEqual(alias.read_bytes(), path.read_bytes())
            finally:
                alias.unlink()

    def test_noncanonical_manifest_paths_rejected(self):
        self.qgn1()
        for relative in ('./device/qemu', 'device//qemu', 'device/qemu/', '.', ''):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.guard.safe_path(self.root, relative)

    def test_every_upgrade_write_failure_before_and_after_replace_restores_all_bytes_and_modes(self):
        self.qgn1()
        for legacy in (False, True):
            if legacy:
                path = self.root / self.guard.BUILD
                path.write_bytes(path.read_bytes().replace(b'  output_prefix_override = true\n',
                    b'  output_prefix = ""\n  output_prefix_override = true\n'))
            updates = self.legacy_updates if legacy else self.qgn1_updates
            for index, name in enumerate(updates):
                (self.root / name).chmod((0o640, 0o751, 0o4750, 0o604)[index])
            before = self.snapshot()
            for fail_at in range(1, len(updates) + 1):
                for after in (False, True):
                    real_write = self.guard.atomic_write
                    calls = 0
                    def fail_once(target, data, mode):
                        nonlocal calls
                        calls += 1
                        if calls == fail_at:
                            if after:
                                real_write(target, data, mode)
                            raise OSError('injected transaction failure')
                        real_write(target, data, mode)
                    with self.subTest(legacy=legacy, fail_at=fail_at, after=after), \
                            mock.patch.object(self.guard, 'atomic_write', fail_once):
                        with self.assertRaisesRegex(OSError, 'injected transaction'):
                            self.guard.apply(self.root)
                    self.assertEqual(self.snapshot(), before)
                    self.assertEqual(self.guard.source_state(self.root, self.manifest),
                                     'predecessor' if legacy else 'qgn1')

    def test_qgn1_failed_final_validation_restores_all_changed_files(self):
        self.qgn1()
        before = self.snapshot()
        original_validate = self.guard.validate
        def fail_final(root, *args, **kwargs):
            if Path(root).resolve() == self.root.resolve():
                raise ValueError('injected final validation')
            return original_validate(root, *args, **kwargs)
        with mock.patch.object(self.guard, 'validate', fail_final):
            with self.assertRaisesRegex(ValueError, 'injected final'):
                self.guard.apply(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_mode_change_during_preparation_is_preserved_and_refused(self):
        self.qgn1()
        target = self.root / self.qgn1_updates[0]
        original_validate = self.guard.validate
        def change_mode(root, *args, **kwargs):
            result = original_validate(root, *args, **kwargs)
            if Path(root).resolve() != self.root.resolve():
                target.chmod(0o601)
            return result
        before = self.snapshot()
        with mock.patch.object(self.guard, 'validate', change_mode):
            with self.assertRaisesRegex(ValueError, 'source state changed'):
                self.guard.apply(self.root)
        before[self.qgn1_updates[0]] = (before[self.qgn1_updates[0]][0], 0o601)
        self.assertEqual(self.snapshot(), before)

    def test_every_guarded_file_external_changes_after_preflight_are_preserved(self):
        self.qgn1()
        original_validate = self.guard.validate
        for name in self.snapshot():
            path = self.root / name
            data, mode = self.snapshot()[name]
            for kind in ('mode', 'bytes', 'hardlink', 'symlink'):
                alias = None
                expected = None
                def change_after_candidate(root, *args, **kwargs):
                    nonlocal alias, expected
                    result = original_validate(root, *args, **kwargs)
                    if Path(root).resolve() != self.root.resolve():
                        alias = self.external_change(path, kind)
                        expected = self.snapshot()
                    return result
                try:
                    with self.subTest(name=name, mutation=kind), \
                            mock.patch.object(self.guard, 'validate', change_after_candidate), \
                            mock.patch.object(self.guard, 'atomic_write', side_effect=AssertionError('no write allowed')):
                        with self.assertRaises((ValueError, OSError)):
                            self.guard.apply(self.root)
                    self.assertEqual(self.snapshot(), expected)
                    if kind == 'symlink':
                        self.assertTrue(path.is_symlink())
                    if kind == 'hardlink':
                        self.assertEqual(path.stat().st_nlink, 2)
                finally:
                    self.restore_changed_path(path, data, mode, alias)

    def test_unwritten_overlay_source_and_dependency_changes_after_first_replace_preserved(self):
        self.qgn1()
        victims = [self.qgn1_updates[-1], next(iter(self.manifest['originals'])), self.guard.ABI_HEADER]
        for name in victims:
            path = self.root / name
            data, mode = self.snapshot()[name]
            for kind in ('mode', 'bytes', 'hardlink', 'symlink'):
                before = self.snapshot()
                alias = None
                expected = None
                calls = []
                real_write = self.guard.atomic_write
                def change_after_first(target, content, permissions):
                    nonlocal alias, expected
                    calls.append(Path(target).relative_to(self.root).as_posix())
                    real_write(target, content, permissions)
                    if len(calls) == 1:
                        alias = self.external_change(path, kind)
                        expected = {**before, name: self.snapshot()[name]}
                try:
                    with self.subTest(name=name, mutation=kind), \
                            mock.patch.object(self.guard, 'atomic_write', change_after_first):
                        with self.assertRaises((ValueError, OSError)):
                            self.guard.apply(self.root)
                    self.assertEqual(self.snapshot(), expected)
                    self.assertNotIn(name, calls, 'never-written foreign changes must not be rolled back')
                    self.assertEqual(calls, [self.qgn1_updates[0], self.qgn1_updates[0]])
                    if kind == 'symlink':
                        self.assertTrue(path.is_symlink())
                    if kind == 'hardlink':
                        self.assertEqual(path.stat().st_nlink, 2)
                finally:
                    self.restore_changed_path(path, data, mode, alias)

    def test_failed_attempt_before_rename_never_overwrites_foreign_target(self):
        self.qgn1()
        name = self.qgn1_updates[0]
        path = self.root / name
        data, mode = self.snapshot()[name]
        for kind in ('mode', 'bytes', 'hardlink', 'symlink'):
            alias = None
            expected = None
            calls = 0
            def fail_before_rename(target, content, permissions):
                nonlocal alias, expected, calls
                calls += 1
                self.assertEqual(calls, 1, 'a never-written external target must not be restored')
                alias = self.external_change(Path(target), kind)
                expected = self.snapshot()
                raise OSError('external change before rename')
            try:
                with self.subTest(mutation=kind), mock.patch.object(self.guard, 'atomic_write', fail_before_rename):
                    with self.assertRaisesRegex(RuntimeError, 'rollback incomplete') as failure:
                        self.guard.apply(self.root)
                self.assertEqual(calls, 1)
                self.assertEqual(self.snapshot(), expected)
                recovery = Path(str(failure.exception).split('original bytes retained at ', 1)[1].split(';', 1)[0])
                self.addCleanup(shutil.rmtree, recovery)
                self.assertEqual((recovery / name).read_bytes(), data)
                self.assertEqual(json.loads((recovery / 'original.json').read_text())[name]['mode'], mode)
                if kind == 'symlink':
                    self.assertTrue(path.is_symlink())
                if kind == 'hardlink':
                    self.assertEqual(path.stat().st_nlink, 2)
            finally:
                self.restore_changed_path(path, data, mode, alias)

    def test_pristine_still_installs_and_new_state_is_idempotent(self):
        self.assertEqual(self.guard.source_state(self.root, self.manifest), 'pristine')
        result = self.guard.apply(self.root)
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(len(result['files']), len(self.manifest['originals']) + len(self.manifest['files']))
        self.assertTrue(self.guard.validate(self.root, self.manifest, require_patched=True))
        before = self.snapshot()
        with mock.patch.object(self.guard, 'atomic_write', side_effect=AssertionError('idempotent write')):
            self.assertEqual(self.guard.apply(self.root)['status'], 'already_applied')
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
