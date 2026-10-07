"""Cache bootstrap fixtures are not an actual OHPM/HAP or guest acceptance."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('m144_host_cache_fixture',
    ROOT / 'scripts/prepare_m144_host_cache.py')
CACHE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHE)


class M144HostCacheTests(unittest.TestCase):
    def test_new_and_existing_cache_preserve_home_contents_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            marker = home / 'unrelated'
            marker.write_bytes(b'owned existing home content')
            first = CACHE.prepare_cache(home)
            self.assertFalse(first['target_preexisted'])
            cache_marker = home / '.ohpm/existing-cache'
            cache_marker.write_bytes(b'preserve package cache')
            second = CACHE.prepare_cache(home)
            self.assertTrue(second['target_preexisted'])
            self.assertTrue(second['cache_writable'])
            self.assertEqual(marker.read_bytes(), b'owned existing home content')
            self.assertEqual(cache_marker.read_bytes(), b'preserve package cache')
            self.assertEqual(sorted(p.name for p in (home / '.ohpm').iterdir()), ['existing-cache'])

    def test_dangling_absolute_and_relative_alias_targets_created_without_replacement(self):
        for relative in (False, True):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                home = root / 'home'
                home.mkdir()
                target = root / 'private/cache/.ohpm'
                alias = Path('../private/cache/.ohpm') if relative else target
                cache = home / '.ohpm'
                cache.symlink_to(alias)
                result = CACHE.prepare_cache(home)
                self.assertEqual(cache.readlink(), alias)
                self.assertEqual(result['target'], str(target.resolve()))
                self.assertEqual(result['preserved_alias'], str(alias))
                self.assertTrue(target.is_dir())
                self.assertEqual(list(target.iterdir()), [])
                self.assertTrue(CACHE.prepare_cache(home)['target_preexisted'])

    def test_unknown_file_and_broad_alias_rejected_without_mutation(self):
        for kind in ('file', 'target_file', 'home_alias', 'root_alias', 'noncache_alias', 'cycle'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                home = root / 'home'
                home.mkdir()
                cache = home / '.ohpm'
                if kind == 'file': cache.write_bytes(b'keep file')
                elif kind == 'target_file':
                    target = root / '.ohpm'
                    target.write_bytes(b'keep target')
                    cache.symlink_to(target)
                elif kind == 'home_alias': cache.symlink_to(home)
                elif kind == 'root_alias': cache.symlink_to('/')
                elif kind == 'noncache_alias': cache.symlink_to(root / 'unknown/cache')
                else: cache.symlink_to('.ohpm')
                before = cache.readlink() if cache.is_symlink() else cache.read_bytes()
                with self.assertRaises((ValueError, RuntimeError)):
                    CACHE.prepare_cache(home)
                self.assertEqual(cache.readlink() if cache.is_symlink() else cache.read_bytes(), before)
                self.assertFalse((root / 'unknown').exists())
                if kind == 'target_file': self.assertEqual(target.read_bytes(), b'keep target')

    def test_invalid_home_and_build_entry_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            for home in (Path('relative-home'), Path(directory) / 'missing'):
                with self.assertRaises(ValueError): CACHE.prepare_cache(home)
        script = (ROOT / 'scripts/prepare_m144_build_host.sh').read_text()
        self.assertIn('python3 "${script_dir}/prepare_m144_host_cache.py"', script)
        dockerfile = (ROOT / 'scripts/docker/m144-build-env.Dockerfile').read_text()
        self.assertIn('COPY scripts/prepare_m144_host_cache.py', dockerfile)
        self.assertNotIn('export HOME=', script)


if __name__ == '__main__':
    unittest.main()
