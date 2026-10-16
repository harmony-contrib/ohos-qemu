"""Exact predecessor migration and failed-write recovery; no GN/build execution."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import test_batch_system_gnss_installers as fixture


class GnssMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='apps-gnss-migration-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        _, self.root, self.component, self.guard, self.manifest = fixture.candidate(self.base)
        self.before = {name: (self.root / name).read_bytes() for name in self.manifest['originals']}

    def snapshot(self):
        return {name: (self.root / name).read_bytes() if (self.root / name).exists() else None
                for name in [*self.manifest['originals'], *self.manifest['files'], *self.manifest['dependencies']]}

    def predecessor(self):
        self.guard.apply(self.root)
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
        self.assertEqual(shipped['files'][self.guard.BUILD]['sha256'],
                         'a33e9ad3ab6652be5e57eb1b310f31652f1b1491b1221dad79d6684a68ad4f16')

    def test_complete_predecessor_changes_only_build_without_reapplying_patch(self):
        self.predecessor()
        build = self.root / self.guard.BUILD
        build.chmod(0o640)
        unchanged = {name: ((self.root / name).read_bytes(), (self.root / name).stat())
                     for name in self.snapshot() if name != self.guard.BUILD}
        with mock.patch.object(self.guard.subprocess, 'run', wraps=subprocess.run) as run:
            result = self.guard.apply(self.root)
        self.assertEqual(result['status'], 'migrated')
        self.assertEqual(result['files'], [self.guard.BUILD])
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
        self.assertEqual(saved, {self.guard.BUILD: {'existed': True, 'mode': 0o640,
                                                  'sha256': self.guard.PREDECESSOR[self.guard.BUILD]}})


if __name__ == '__main__':
    unittest.main()
