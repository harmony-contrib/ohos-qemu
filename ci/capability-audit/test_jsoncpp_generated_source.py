"""Build generator boundaries; these tests are not guest API acceptance."""
import hashlib
import functools
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/third_party/jsoncpp/generated_source'
spec = importlib.util.spec_from_file_location('jsoncpp_generated_guard', COMPONENT / 'check.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@functools.lru_cache(maxsize=1)
def contents():
    lines = (COMPONENT / '0001-fail-closed-generation-without-source-writes.patch').read_text().splitlines()
    body = lines[next(i for i, line in enumerate(lines) if line.startswith('@@')) + 1:]
    original, first = tuple(''.join(line[1:] + '\n' for line in body if line.startswith(prefix))
                            for prefix in ('-', '+'))
    if hashlib.sha256(first.encode()).hexdigest() != guard.FIRST_PATCH_SHA256:
        raise AssertionError('first fixed installer patch changed')
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / 'third_party/jsoncpp/install.py'
        target.parent.mkdir(parents=True)
        target.write_text(first)
        subprocess.run(['git', '-C', temporary, 'apply', '--check', str(
            COMPONENT / '0002-accept-only-empty-gn-output-skeleton.patch')], check=True, capture_output=True)
        subprocess.run(['git', '-C', temporary, 'apply', str(
            COMPONENT / '0002-accept-only-empty-gn-output-skeleton.patch')], check=True, capture_output=True)
        return original, target.read_text()


def installer():
    namespace = {'__name__': 'jsoncpp_install_fixture'}
    exec(compile(contents()[1], '<actual patched jsoncpp installer>', 'exec'), namespace)
    return namespace


def valid_tree(root):
    root.mkdir()
    for relative in installer()['OUTPUTS']:
        output = root / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text('generated fixture\n')


class JsoncppGeneratedSourceTests(unittest.TestCase):
    def test_exact_numbered_patch_bytes(self):
        original, repaired = contents()
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), guard.ORIGINAL_SHA256)
        self.assertEqual(hashlib.sha256(repaired.encode()).hexdigest(), guard.REPAIRED_SHA256)

    def test_guard_preserves_unknown_revision_archive_edits_and_symlinks(self):
        original, repaired = contents()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'third_party/jsoncpp'
            source.mkdir(parents=True)
            (source / guard.ARCHIVE).write_bytes(b'archive fixture')
            (source / 'install.py').write_text(original)
            def git(argv, **kwargs):
                return guard.REVISION + '\n' if argv[-1] == 'HEAD' else original.encode()
            with patch.object(guard.subprocess, 'check_output', side_effect=git), patch.object(
                    guard, 'ARCHIVE_SHA256', hashlib.sha256(b'archive fixture').hexdigest()):
                guard.validate(source)
                with self.assertRaises(ValueError):
                    guard.validate(source, True)
                (source / 'install.py').write_text(repaired)
                guard.validate(source, True)
                (source / 'install.py').write_text(repaired + '# unknown\n')
                with self.assertRaises(ValueError):
                    guard.validate(source)
                (source / 'install.py').unlink()
                (source / 'install.py').symlink_to(source / guard.ARCHIVE)
                with self.assertRaises(ValueError):
                    guard.validate(source)
            with patch.object(guard.subprocess, 'check_output', return_value='unknown\n'), self.assertRaises(ValueError):
                guard.validate(source)

    def test_archive_drift_and_symlink_fail_before_tar_or_output(self):
        ns = installer()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'
            source.mkdir()
            archive = source / ns['ARCHIVE']
            archive.write_bytes(b'unknown')
            generated = Path(temporary) / 'generated'
            with patch.object(ns['subprocess'], 'run') as run, self.assertRaises(ValueError):
                ns['install'](source, generated)
            run.assert_not_called()
            self.assertFalse(generated.exists())
            archive.unlink()
            archive.symlink_to(source / 'not-present')
            with self.assertRaises(ValueError):
                ns['install'](source, generated)

    def test_generation_rejects_root_source_and_symlink_ancestors(self):
        ns = installer()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'
            source.mkdir()
            link = Path(temporary) / 'linked'
            link.symlink_to(source, target_is_directory=True)
            with patch.dict(ns, validate_archive=lambda source: source / 'archive'):
                for generated in (Path('/'), source, source / 'nested', link / 'nested'):
                    with self.subTest(generated=generated), self.assertRaises(ValueError):
                        ns['install'](source, generated)

    def test_tar_failure_propagates_and_existing_output_survives(self):
        ns = installer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            gen = root / 'gen'
            gen.mkdir()
            tree = gen / ns['TREE']
            valid_tree(tree)
            before = {file: (tree / file).read_bytes() for file in ns['OUTPUTS']}
            with patch.dict(ns, validate_archive=lambda source: source / 'archive'), patch.object(
                    ns['subprocess'], 'run', side_effect=subprocess.CalledProcessError(2, ['tar'])):
                with self.assertRaises(subprocess.CalledProcessError):
                    ns['install'](source, gen)
            self.assertEqual(before, {file: (tree / file).read_bytes() for file in ns['OUTPUTS']})
            self.assertFalse(list(gen.glob('.jsoncpp-install-*')))

    def test_missing_partial_or_symlink_outputs_rejected(self):
        ns = installer()
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary) / 'tree'
            valid_tree(tree)
            ns['verify_tree'](tree)
            (tree / ns['OUTPUTS'][0]).unlink()
            with self.assertRaises(ValueError):
                ns['verify_tree'](tree)
            (tree / ns['OUTPUTS'][0]).symlink_to(tree / ns['OUTPUTS'][1])
            with self.assertRaises(ValueError):
                ns['verify_tree'](tree)

    def test_publish_failure_rolls_back_previous_generated_tree(self):
        ns = installer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            gen = root / 'gen'
            gen.mkdir()
            old = gen / ns['TREE']
            valid_tree(old)
            def extract(argv, **kwargs):
                valid_tree(Path(argv[4]) / ns['TREE'])
            rename = Path.rename
            def fail_publish(path, target):
                if path.name == ns['TREE'] and path.parent.name.startswith('.jsoncpp-install-'):
                    raise OSError('publication fixture failure')
                return rename(path, target)
            with patch.dict(ns, validate_archive=lambda source: source / 'archive'), patch.object(
                    ns['subprocess'], 'run', side_effect=extract), patch.object(Path, 'rename', fail_publish):
                with self.assertRaises(OSError):
                    ns['install'](source, gen)
            ns['verify_tree'](old)

    def test_generation_component_precedes_traversal(self):
        build = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertLess(build.index('bash "${JSONCPP_GENERATED_SOURCE_COMPONENT_SCRIPT}"'),
                        build.index('  write_source_preparation_metadata'))
        self.assertNotIn('rm', contents()[1].split('import argparse', 1)[1])

    def test_only_known_directory_only_GN_skeleton_is_accepted(self):
        ns = installer()
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary) / ns['TREE']
            (tree / 'src/lib_json').mkdir(parents=True)
            (tree / 'include/json').mkdir(parents=True)
            self.assertTrue(ns['empty_gn_skeleton'](tree))
            (tree / 'unknown').mkdir()
            self.assertFalse(ns['empty_gn_skeleton'](tree))
            (tree / 'unknown').rmdir()
            partial = tree / ns['OUTPUTS'][0]
            partial.write_text('partial generated file')
            self.assertFalse(ns['empty_gn_skeleton'](tree))
            partial.unlink()
            partial.symlink_to(tree / 'include')
            self.assertFalse(ns['empty_gn_skeleton'](tree))

    def test_real_skeleton_survives_failed_generation_and_then_publishes(self):
        ns = installer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            generated = root / 'gen'
            skeleton = generated / ns['TREE']
            (skeleton / 'src/lib_json').mkdir(parents=True)
            with patch.dict(ns, validate_archive=lambda source: source / 'archive'), patch.object(
                    ns['subprocess'], 'run', side_effect=subprocess.CalledProcessError(2, ['tar'])):
                with self.assertRaises(subprocess.CalledProcessError):
                    ns['install'](source, generated)
            self.assertTrue(ns['empty_gn_skeleton'](skeleton))
            def extract(argv, **kwargs):
                valid_tree(Path(argv[4]) / ns['TREE'])
            with patch.dict(ns, validate_archive=lambda source: source / 'archive'), patch.object(
                    ns['subprocess'], 'run', side_effect=extract):
                ns['install'](source, generated)
            ns['verify_tree'](skeleton)


if __name__ == '__main__':
    unittest.main()
