"""Generation-isolation contract fixtures, not actual Rust/RS compilation."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('rs_generated_inputs_compile',
                                             Path(__file__).with_name('compile_render_connection_reply.py'))
COMPILER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPILER)


class RsGeneratedInputsTests(unittest.TestCase):
    def test_owned_header_overlay_preserves_original_include_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root, staged = base / 'production', base / 'owned'
            cwd = root / 'out/arm64_virt'
            cwd.mkdir(parents=True)
            relative = Path('foundation/communication/ipc/ipc/native/src/core/invoker/include')
            (root / relative).mkdir(parents=True)
            (staged / relative).mkdir(parents=True)
            original = '-I../../' + str(relative)
            command = ['clang++', original, '-Igen', '-I' + str(base / 'unrelated'), '-Wall']
            revised = COMPILER.overlay_patched_include_directories(command, cwd, root, staged)
            self.assertEqual(revised, ['clang++', '-I' + str(staged / relative), *command[1:]])
            self.assertEqual(command[1], original)
            self.assertFalse((cwd / 'gen').exists())

    def test_owned_overlay_also_matches_completed_seed_lexical_source_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root, staged, seed = base / 'production', base / 'owned', base / 'completed'
            cwd = seed / 'out/arm64_virt'
            cwd.mkdir(parents=True)
            relative = Path('foundation/graphic/graphic_2d/rosen/modules/render_service_base/include')
            (seed / relative).mkdir(parents=True)
            (root / relative).mkdir(parents=True)
            (staged / relative).mkdir(parents=True)
            original = '-I../../' + str(relative)
            command = ['clang++', original, '-Igen', '-Wall']
            revised = COMPILER.overlay_patched_include_directories(command, cwd, root, staged)
            self.assertEqual(revised, ['clang++', '-I' + str(staged / relative), *command[1:]])
            self.assertEqual(command[1], original)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root, self.seed = self.base / 'production', self.base / 'completed'
        self.cwd = self.seed / 'out/arm64_virt'
        self.cwd.mkdir(parents=True)
        self.output = self.base / 'owned'
        self.output.mkdir()
        self.script = Path('build/templates/rust/rust_cxxbridge.py')
        self.source = Path('foundation/graphic/graphic_2d/rosen/modules/render_service_base/rust/src/lib.rs')
        for root in (self.root, self.seed):
            for relative in (self.script, self.source):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'pinned fixture input\n')
        cargo = self.root / 'third_party/rust/crates/cxx/gen/cmd/Cargo.toml'
        cargo.parent.mkdir(parents=True)
        cargo.write_text('version = "1.0.130"\n')
        tool = self.root / 'out/arm64_virt/clang_x64/thirdparty/rust_cxx/cxxbridge'
        tool.parent.mkdir(parents=True)
        tool.write_bytes(b'host-tool fixture, not an executable\n')
        generated = 'gen/foundation/graphic/graphic_2d/rosen/modules/render_service_base/rust/src/lib.rs'
        self.argv = ['/usr/bin/env', '../../' + str(self.script), '--cxxbridge',
                     'clang_x64/thirdparty/rust_cxx/cxxbridge', '--cc', generated + '.cc',
                     '--header', generated + '.h', '--', '../../' + str(self.source)]

    def run_fixture(self, argv=None, version='cxxbridge 1.0.130', produce=True):
        def execute(command, **kwargs):
            if command[-1] == '--version':
                return subprocess.CompletedProcess(command, 0, stdout=version, stderr='')
            self.assertEqual(kwargs['cwd'], self.cwd)
            self.assertEqual(command[-1], str(self.root / self.source))
            if produce:
                for option in ('--cc', '--header'):
                    path = Path(command[command.index(option) + 1])
                    self.assertTrue(path.is_relative_to(self.output))
                    path.write_bytes(b'generated test fixture\n')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(COMPILER.subprocess, 'run', side_effect=execute):
            return COMPILER.prepare_missing_rust_cxx(
                self.root, self.cwd, argv or self.argv, self.output, 0, 'actual-action fixture')

    def test_isolates_both_outputs_and_records_real_input_and_output_hashes(self):
        record = self.run_fixture()
        self.assertEqual(record['kind'], 'rust_cxxbridge')
        self.assertEqual(len(record['generated_sha256']), 2)
        self.assertEqual(len(record['input_sha256']), 4)
        self.assertFalse((self.cwd / 'gen').exists())
        self.assertEqual((self.seed / self.source).read_bytes(), b'pinned fixture input\n')

    def test_rejects_changed_seed_generator_or_rust_source(self):
        for relative in (self.script, self.source):
            with self.subTest(relative=relative):
                path = self.seed / relative
                path.write_bytes(b'changed fixture\n')
                with self.assertRaisesRegex(ValueError, 'differs'):
                    self.run_fixture()
                path.write_bytes(b'pinned fixture input\n')

    def test_accepts_readonly_source_symlink_without_using_a_foreign_file(self):
        source = self.seed / self.source
        source.unlink()
        source.symlink_to(self.root / self.source)
        record = self.run_fixture()
        self.assertEqual(record['kind'], 'rust_cxxbridge')
        self.assertEqual(record['owned_command'][-1], str(self.root / self.source))
        self.assertTrue(source.is_symlink())

    def test_rejects_wrong_host_tool_version_before_generation(self):
        with self.assertRaisesRegex(ValueError, 'fixed source version'):
            self.run_fixture(version='cxxbridge 1.0.131')
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_output_escape_or_prior_output_without_overwriting(self):
        argv = list(self.argv)
        argv[argv.index('--cc') + 1] = '../outside.cc'
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.run_fixture(argv)
        destination = self.output / self.argv[self.argv.index('--cc') + 1]
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'preserve previous evidence\n')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            self.run_fixture()
        self.assertEqual(destination.read_bytes(), b'preserve previous evidence\n')

    def test_rejects_swallowed_success_without_both_generated_files(self):
        with self.assertRaisesRegex(RuntimeError, 'generation failed'):
            self.run_fixture(produce=False)


if __name__ == '__main__':
    unittest.main()
