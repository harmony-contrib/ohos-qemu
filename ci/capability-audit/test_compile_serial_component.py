"""Serial scratch input staging fixtures; never product/runtime acceptance."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compile_serial_component import (materialize_idl_inputs, copy_jsoncpp_installer_workspace,
                                      build_environment, NODE_RELATIVE_PATH, quarantine_moved_cmake_caches,
                                      configure_serial_profile, PRODUCT_PATHS, jsoncpp_repair_evidence)


class SerialCompileIsolationFixtureTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='serial-idl-fixture-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve() / 'production'
        self.staged = Path(self.directory.name).resolve() / 'scratch'
        self.source = self.root / 'base/hiviewdfx/hiview/service.idl'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'interface Source {}\n')
        self.other = self.source.with_suffix('.cpp')
        self.other.write_bytes(b'// unchanged source\n')
        self.staged.mkdir()
        (self.staged / 'base').symlink_to(self.root / 'base', target_is_directory=True)

    def test_materializes_original_bytes_only_and_is_repeatable(self):
        records = materialize_idl_inputs(self.root, self.staged)
        target = self.staged / self.source.relative_to(self.root)
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_bytes(), b'interface Source {}\n')
        self.assertTrue((self.staged / self.other.relative_to(self.root)).is_symlink())
        self.assertEqual(records, [{'source': str(self.source.relative_to(self.root)),
                                    'sha256': hashlib.sha256(self.source.read_bytes()).hexdigest()}])
        self.assertEqual(materialize_idl_inputs(self.root, self.staged), records)
        self.assertEqual(self.source.read_bytes(), b'interface Source {}\n')

    def test_refuses_changed_local_idl_and_preserves_original(self):
        materialize_idl_inputs(self.root, self.staged)
        (self.staged / self.source.relative_to(self.root)).write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError, 'differs'):
            materialize_idl_inputs(self.root, self.staged)
        self.assertEqual(self.source.read_bytes(), b'interface Source {}\n')

    def test_refuses_unexpected_directory_and_file_links(self):
        (self.staged / 'base').unlink()
        (self.staged / 'base').symlink_to(self.source.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'directory symlink'):
            materialize_idl_inputs(self.root, self.staged)
        (self.staged / 'base').unlink()
        (self.staged / 'base/hiviewdfx/hiview').mkdir(parents=True)
        (self.staged / self.source.relative_to(self.root)).symlink_to(self.other)
        with self.assertRaisesRegex(ValueError, 'input symlink'):
            materialize_idl_inputs(self.root, self.staged)

    def test_refuses_source_idl_escape(self):
        outside = Path(self.directory.name) / 'outside.idl'
        outside.write_bytes(b'outside\n')
        self.source.unlink()
        self.source.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'outside'):
            materialize_idl_inputs(self.root, self.staged)


class SerialJsoncppIsolationFixtureTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='serial-jsoncpp-fixture-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve() / 'production'
        self.staged = Path(self.directory.name).resolve() / 'scratch'
        self.original = self.root / 'third_party/jsoncpp'
        self.original.mkdir(parents=True)
        self.archive = self.original / 'jsoncpp-1.9.6.tar.gz'
        self.archive.write_bytes(b'unit fixture archive, not upstream compile evidence')
        (self.original / 'install.py').write_bytes(b'# original installer bytes\n')
        (self.staged / 'third_party').mkdir(parents=True)
        (self.staged / 'third_party/jsoncpp').symlink_to(self.original, target_is_directory=True)
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def test_preserves_exact_bytes_in_owned_work_directory(self):
        records = copy_jsoncpp_installer_workspace(self.root, self.staged, self.sha)
        self.assertEqual(len(records), 2)
        self.assertFalse((self.staged / 'third_party/jsoncpp').is_symlink())
        self.assertEqual((self.staged / 'third_party/jsoncpp/install.py').read_bytes(), b'# original installer bytes\n')
        self.assertEqual(self.archive.read_bytes(), b'unit fixture archive, not upstream compile evidence')

    def test_rejects_changed_archive_and_unowned_target(self):
        with self.assertRaisesRegex(ValueError, 'fixed release'):
            copy_jsoncpp_installer_workspace(self.root, self.staged, 'incorrect')
        link = self.staged / 'third_party/jsoncpp'
        link.unlink()
        link.mkdir()
        (link / 'user.txt').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'scratch target'):
            copy_jsoncpp_installer_workspace(self.root, self.staged, self.sha)
        self.assertEqual((link / 'user.txt').read_text(), 'preserve')

    def test_rejects_production_or_input_symlink(self):
        with self.assertRaisesRegex(ValueError, 'independently owned'):
            copy_jsoncpp_installer_workspace(self.root, self.root, self.sha)
        (self.original / 'external.py').symlink_to(self.archive)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            copy_jsoncpp_installer_workspace(self.root, self.staged, self.sha)


class SerialJsoncppEvidenceFixtureTest(unittest.TestCase):
    def test_records_complete_stack_not_just_first_overlapping_patch(self):
        with tempfile.TemporaryDirectory(prefix='serial-jsoncpp-evidence-fixture-') as temporary:
            repo, staged = Path(temporary) / 'repo', Path(temporary) / 'scratch'
            component = repo / 'patches/common/third_party/jsoncpp/generated_source'
            component.mkdir(parents=True)
            patches = [('0001-first.patch', b'first patch fixture'), ('0002-second.patch', b'second patch fixture')]
            for name, payload in reversed(patches):
                (component / name).write_bytes(payload)
            (component / 'apply.py').write_bytes(b'exact stack applicator fixture')
            installer = staged / 'third_party/jsoncpp/install.py'
            installer.parent.mkdir(parents=True)
            installer.write_bytes(b'actual installed bytes fixture')
            result = jsoncpp_repair_evidence(repo, staged)
            self.assertEqual(result['patches'], [{'path': name, 'sha256': hashlib.sha256(payload).hexdigest()}
                                                 for name, payload in patches])
            self.assertEqual(result['installer_sha256'], hashlib.sha256(installer.read_bytes()).hexdigest())
            self.assertEqual(result['applicator_sha256'],
                             hashlib.sha256((component / 'apply.py').read_bytes()).hexdigest())


class SerialNodeEnvironmentFixtureTest(unittest.TestCase):
    def test_fixed_tools_precede_system_path_and_cache_is_scratch_only(self):
        with tempfile.TemporaryDirectory(prefix='serial-node-environment-fixture-') as temporary:
            root, staged = Path(temporary).resolve() / 'production', Path(temporary).resolve() / 'scratch'
            node_bin = root / NODE_RELATIVE_PATH / 'bin'
            node_bin.mkdir(parents=True)
            for name in ('node', 'npm'):
                (node_bin / name).write_bytes(b'host environment fixture, not actual tool evidence')
            environment = build_environment(root, staged)
            self.assertEqual(environment['PATH'].split(':')[0], str(node_bin))
            self.assertEqual(environment['NODE_HOME'], str(node_bin.parent))
            self.assertEqual(environment['npm_config_cache'], str(staged / 'npm-cache'))
            self.assertEqual(environment['npm_config_offline'], 'true')
            self.assertEqual(environment['PYTHONDONTWRITEBYTECODE'], '1')
            self.assertFalse(staged.exists())

    def test_missing_fixed_npm_is_not_replaced_by_system_tool(self):
        with tempfile.TemporaryDirectory(prefix='serial-node-missing-fixture-') as temporary:
            root = Path(temporary).resolve() / 'production'
            node_bin = root / NODE_RELATIVE_PATH / 'bin'
            node_bin.mkdir(parents=True)
            (node_bin / 'node').write_bytes(b'host fixture')
            with self.assertRaisesRegex(ValueError, 'npm'):
                build_environment(root, Path(temporary).resolve() / 'scratch')

    def test_refuses_npm_cache_in_production(self):
        with tempfile.TemporaryDirectory(prefix='serial-node-unowned-fixture-') as temporary:
            root = Path(temporary).resolve()
            with self.assertRaisesRegex(ValueError, 'independently owned'):
                build_environment(root, root / 'scratch')


class SerialMovedCmakeCacheFixtureTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='serial-cmake-cache-fixture-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve() / 'production'
        self.staged = Path(self.directory.name).resolve() / 'scratch'
        self.prior = Path(self.directory.name).resolve() / 'stopped-prior'
        self.relative = Path('arm64_virt/clang_x64/third_party/flatbuffers')
        self.binary = self.staged / 'out' / self.relative
        self.binary.mkdir(parents=True)
        self.cache = self.binary / 'CMakeCache.txt'
        self.original = ('CMAKE_CACHEFILE_DIR:INTERNAL=' + str(self.prior / 'out' / self.relative) + '\n').encode()
        self.cache.write_bytes(self.original)
        (self.binary / 'flatc').write_bytes(b'fixture cache artifact, not compile evidence')
        self.other = self.staged / 'out/arm64_virt/obj/keep.o'
        self.other.parent.mkdir(parents=True)
        self.other.write_bytes(b'preserved unrelated owned incremental output')

    def test_archives_exact_path_bound_cache_without_rewriting_or_deleting(self):
        records = quarantine_moved_cmake_caches(self.root, self.staged, self.prior)
        self.assertEqual(len(records), 1)
        self.assertFalse(self.binary.exists())
        archived = Path(records[0]['quarantine_directory'])
        self.assertEqual((archived / 'CMakeCache.txt').read_bytes(), self.original)
        self.assertEqual((archived / 'flatc').read_bytes(), b'fixture cache artifact, not compile evidence')
        self.assertEqual(records[0]['cmake_cache_sha256'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(self.other.read_bytes(), b'preserved unrelated owned incremental output')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            quarantine_moved_cmake_caches(self.root, self.staged, self.prior)

    def test_current_cache_is_left_in_place(self):
        current = ('CMAKE_CACHEFILE_DIR:INTERNAL=' + str(self.binary) + '\n').encode()
        self.cache.write_bytes(current)
        self.assertEqual(quarantine_moved_cmake_caches(self.root, self.staged, self.prior), [])
        self.assertEqual(self.cache.read_bytes(), current)

    def test_foreign_or_symlink_cache_is_refused_without_mutation(self):
        self.cache.write_bytes(b'CMAKE_CACHEFILE_DIR:INTERNAL=/other/cache\n')
        with self.assertRaisesRegex(ValueError, 'prior scratch'):
            quarantine_moved_cmake_caches(self.root, self.staged, self.prior)
        self.assertTrue((self.binary / 'flatc').exists())
        self.cache.unlink()
        self.cache.symlink_to(self.other)
        with self.assertRaisesRegex(ValueError, 'escape'):
            quarantine_moved_cmake_caches(self.root, self.staged, self.prior)
        self.assertEqual(self.other.read_bytes(), b'preserved unrelated owned incremental output')

    def test_production_and_broad_product_root_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'independent'):
            quarantine_moved_cmake_caches(self.staged, self.staged, self.prior)
        broad = self.staged / 'out/arm64_virt/CMakeCache.txt'
        broad.write_text('CMAKE_CACHEFILE_DIR:INTERNAL=' + str(self.prior / 'out/arm64_virt') + '\n')
        with self.assertRaisesRegex(ValueError, 'broad product'):
            quarantine_moved_cmake_caches(self.root, self.staged, self.prior)
        self.assertEqual(self.cache.read_bytes(), self.original)


class SerialProfileIsolationFixtureTest(unittest.TestCase):
    def test_disable_all_existing_phone_abis_before_shared_pc_parameters(self):
        with tempfile.TemporaryDirectory(prefix='serial-profile-fixture-') as temporary:
            staged = Path(temporary)
            for relative in PRODUCT_PATHS.values():
                target = staged / 'vendor/ohemu' / relative / 'config.json'
                target.parent.mkdir(parents=True)
                target.write_text('{}')
            with patch('compile_serial_component.subprocess.run') as invoked:
                configure_serial_profile(Path('/repo'), staged, 'armv7a_virt')
            first, second = [entry.args[0] for entry in invoked.call_args_list]
            self.assertIn('--disable', first)
            for name in PRODUCT_PATHS:
                self.assertIn(name, first)
            self.assertEqual(second[-2:], ['--product', 'armv7a_virt'])

    def test_missing_selected_product_is_not_invented(self):
        with tempfile.TemporaryDirectory(prefix='serial-profile-missing-fixture-') as temporary:
            with self.assertRaisesRegex(ValueError, 'missing'):
                configure_serial_profile(Path('/repo'), Path(temporary), 'x86_64_virt')


if __name__ == '__main__':
    unittest.main()
