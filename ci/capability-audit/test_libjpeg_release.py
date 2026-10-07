"""Exact dependency guards and installer failure propagation, not guest tests."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/third_party/libjpeg-turbo/release_3_1_0'
spec = importlib.util.spec_from_file_location('libjpeg_release_guard', COMPONENT / 'check.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def contents():
    originals, repaired = {}, {}
    for file in sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch')):
        for block in file.read_text().split('\ndiff --git a/third_party/libjpeg-turbo/'):
            if block.startswith('diff --git a/third_party/libjpeg-turbo/'):
                block = block.removeprefix('diff --git a/third_party/libjpeg-turbo/')
            elif block == file.read_text():
                continue
            lines = block.splitlines()
            name = lines[0].split()[0]
            body = lines[next(i for i, line in enumerate(lines) if line.startswith('@@ ')) + 1:]
            originals[name] = ''.join(line[1:] + '\n' for line in body if line.startswith('-'))
            repaired[name] = ''.join(line[1:] + '\n' for line in body if line.startswith('+'))
            if body[-1] == '\\ No newline at end of file':
                repaired[name] = repaired[name].removesuffix('\n')
            for position, line in enumerate(body):
                if line == '\\ No newline at end of file' and position and body[position - 1].startswith('-'):
                    originals[name] = originals[name].removesuffix('\n')
    return originals, repaired


class LibjpegReleaseTests(unittest.TestCase):
    def test_whole_numbered_patches_match_original_and_repaired_contracts(self):
        originals, repaired = contents()
        self.assertEqual(set(originals), set(guard.HASHES))
        for name, hashes in guard.HASHES.items():
            if hashes[0] is None:
                self.assertEqual(originals[name], '')
            else:
                self.assertEqual(hashlib.sha256(originals[name].encode()).hexdigest(), hashes[0], name)
            self.assertEqual(hashlib.sha256(repaired[name].encode()).hexdigest(), hashes[1], name)

    def installer(self):
        namespace = {'__name__': 'libjpeg_installer_fixture'}
        exec(compile(contents()[1]['install.py'], '<actual patched installer>', 'exec'), namespace)
        return namespace

    def test_patch_error_propagates_and_validates_before_apply(self):
        namespace = self.installer()
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            failure = subprocess.CalledProcessError(1, ['patch'])
            with patch.object(namespace['subprocess'], 'run', side_effect=failure) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    namespace['apply_patch']('candidate.patch', str(target))
                self.assertEqual(run.call_count, 1)
                self.assertIn('--dry-run', run.call_args.args[0])
                self.assertIn('--batch', run.call_args.args[0])
                self.assertIn('--forward', run.call_args.args[0])
            with patch.object(namespace['subprocess'], 'run') as run:
                namespace['apply_patch']('candidate.patch', str(target))
                self.assertEqual(run.call_count, 2)
                self.assertNotIn('--dry-run', run.call_args.args[0])

    def test_missing_and_symlink_patch_targets_rejected(self):
        namespace = self.installer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'link').symlink_to(root, target_is_directory=True)
            for target in (root / 'missing', root / 'link'):
                with self.assertRaises(ValueError):
                    namespace['apply_patch']('candidate.patch', str(target))

    def test_unknown_archive_fails_before_tar(self):
        namespace = self.installer()
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'archive'
            archive.write_bytes(b'not the pinned source')
            with patch.object(namespace['subprocess'], 'run') as run, self.assertRaises(ValueError):
                namespace['untar_file'](archive, temporary)
            run.assert_not_called()

    def test_exact_guard_rejects_drift_revision_partial_state_and_symlinks(self):
        originals, repaired = contents()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'third_party/libjpeg-turbo'
            source.mkdir(parents=True)
            (source / guard.ARCHIVE).write_bytes(b'archive fixture')
            def git(arguments, **kwargs):
                return guard.REVISION + '\n' if arguments[-1] == 'HEAD' else originals[arguments[-1][5:]].encode()
            with patch.object(guard.subprocess, 'check_output', side_effect=git), patch.object(
                    guard, 'ARCHIVE_SHA256', hashlib.sha256(b'archive fixture').hexdigest()):
                for name, data in originals.items():
                    if guard.HASHES[name][0] is not None:
                        (source / name).write_text(data)
                guard.validate(source)
                with self.assertRaises(ValueError):
                    guard.validate(source, True)
                for name, data in repaired.items():
                    (source / name).write_text(data)
                guard.validate(source, True)
                (source / 'install.py').write_text(repaired['install.py'] + '\n# unknown drift\n')
                with self.assertRaises(ValueError):
                    guard.validate(source)
                (source / 'install.py').unlink()
                (source / 'install.py').symlink_to(source / 'Add-loongarch64.patch')
                with self.assertRaises(ValueError):
                    guard.validate(source)
            with patch.object(guard.subprocess, 'check_output', return_value='wrong revision\n'), self.assertRaises(ValueError):
                guard.validate(source)

    def test_public_3_1_0_api_and_upstream_overflow_coverage_not_reverted(self):
        repaired = contents()[1]
        bugfix = repaired['libjpeg-turbo-2.1.x-bugfix.patch']
        self.assertEqual(bugfix.count('diff --git'), 2)
        self.assertNotIn('java/', bugfix)
        self.assertNotIn('tjunittest.c', bugfix)
        self.assertEqual(repaired['Add-loongarch64.patch'].count('+elseif('), 2)
        self.assertIn('+#ifndef LITEOS_M_TYPE_DEFINE', repaired['liteos_adapting.patch'])
        self.assertNotIn('-typedef long INT32;', repaired['liteos_adapting.patch'])
        self.assertIn('#define LIBJPEG_TURBO_VERSION  3.1.0', repaired['jconfig.h'])
        self.assertIn('#define LIBJPEG_TURBO_VERSION_NUMBER  3001000', repaired['jconfig.h'])
        self.assertIn('#define VERSION  "3.1.0"', repaired['jconfigint.h'])
        self.assertIn('#define THREAD_LOCAL __thread', repaired['jconfigint.h'])

    def test_component_runs_before_traversal_and_kernel_fingerprint(self):
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        call = builder.index('bash "${LIBJPEG_RELEASE_COMPONENT_SCRIPT}"')
        self.assertLess(call, builder.index('  write_source_preparation_metadata'))
        self.assertLess(call, builder.index('  for product in "${PRODUCTS[@]}"; do', call))

    def test_installer_uses_fresh_owned_stage_and_rolls_back_publication(self):
        namespace = self.installer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source, generated = root / 'source', root / 'generated'
            source.mkdir()
            generated.mkdir()
            tree = generated / 'libjpeg-turbo-3.1.0'
            tree.mkdir()
            (tree / 'old-generated').write_text('preserved fixture')
            stages = []
            def untar(archive, stage):
                stages.append(Path(stage))
                (Path(stage) / tree.name).mkdir()
            def move(src, target):
                headers = Path(target) / 'src'
                headers.mkdir()
                for name in ('jmorecfg.h', 'jerror.h', 'jpeglib.h', 'jconfig.h', 'jconfigint.h'):
                    (headers / name).write_text('valid fixture\n')
            with patch.dict(namespace, untar_file=untar, move_file=move, do_patch=lambda tree: None,
                            move_include=lambda src, dst: None):
                namespace['generate'](source, generated)
                namespace['generate'](source, generated)
            self.assertNotEqual(stages[0], stages[1])
            self.assertFalse((tree / 'old-generated').exists())
            self.assertFalse(list(generated.glob('.libjpeg-install-*')))
            for path in stages:
                self.assertEqual(path.parent, generated)
            with patch.dict(namespace, untar_file=untar, move_file=move,
                            do_patch=lambda tree: (_ for _ in ()).throw(ValueError('patch fixture failure'))), patch.dict(
                    namespace, move_include=lambda src, dst: self.fail('headers must not publish on patch failure')):
                with self.assertRaises(ValueError):
                    namespace['generate'](source, generated)
            self.assertEqual((tree / 'src/jconfig.h').read_text(), 'valid fixture\n')


if __name__ == '__main__':
    unittest.main()
