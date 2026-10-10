"""Host isolation boundaries, not a substitute for real IDL generation."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from compile_render_connection_reply import prepare_missing_idl


class ReadonlyIdlInputTests(unittest.TestCase):
    def test_real_input_copies_and_import_siblings_never_modify_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source'
            cwd = root / 'out/armv7a_virt'
            cwd.mkdir(parents=True)
            output = Path(directory) / 'owned'
            output.mkdir()
            script = root / 'build/config/components/idl_tool/idl.py'
            script.parent.mkdir(parents=True)
            script.write_text('# unit fixture, not a production generator\n')
            source = root / 'foundation/example/IExample.idl'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'interface IExample {}\n')
            sibling = source.with_name('Peer.idl')
            sibling.write_bytes(b'interface Peer {}\n')
            tool = cwd / 'clang_x64/ability/idl_tool/idl'
            tool.parent.mkdir(parents=True)
            tool.write_bytes(b'unit generator identity')
            generated = cwd / 'gen/foundation/example/iexample.h'
            (cwd / 'toolchain.ninja').write_text(
                'build gen/foundation/example/iexample.h: fixture\n')
            action = ['/usr/bin/env', '../../build/config/components/idl_tool/idl.py',
                '--src-idl', str(source), '--dst-path', str(generated.parent),
                '--dst-file', str(generated), '--idl-tool-path', str(tool.parent)]
            originals = {path: path.read_bytes() for path in (source, sibling, script, tool)}
            calls = []

            def execute(argv, **kwargs):
                calls.append(argv)
                if '-t' in argv:
                    return subprocess.CompletedProcess(argv, 0, shlex.join(action) + '\n', '')
                copied = Path(argv[argv.index('--src-idl') + 1])
                self.assertNotEqual(copied, source)
                self.assertTrue(copied.is_relative_to(output))
                self.assertEqual(copied.read_bytes(), originals[source])
                self.assertEqual(copied.with_name('Peer.idl').read_bytes(), originals[sibling])
                destination = Path(argv[argv.index('--dst-file') + 1])
                self.assertTrue(destination.is_relative_to(output))
                destination.parent.mkdir(parents=True)
                destination.write_text('// unit-generated header\n')
                return subprocess.CompletedProcess(argv, 0)

            with patch('compile_render_connection_reply.subprocess.run', side_effect=execute):
                command, records = prepare_missing_idl(root, cwd,
                    ['clang++', '-Igen/foundation/example'], output, copy_readonly_inputs=True)
            self.assertEqual(len(calls), 2)
            self.assertEqual(command, ['clang++', '-I' + str(output / 'gen/foundation/example'),
                                       '-Igen/foundation/example'])
            self.assertEqual(len(records), 1)
            self.assertEqual(len(records[0]['owned_actual_idl_input_sha256']), 2)
            self.assertEqual({path: path.read_bytes() for path in originals}, originals)
            self.assertFalse(generated.exists())

    def test_no_missing_generated_input_does_not_copy_or_invoke_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cwd = root / 'out/arm64_virt'
            cwd.mkdir(parents=True)
            (cwd / 'toolchain.ninja').write_text('')
            output = root / 'owned'
            output.mkdir()
            with patch('compile_render_connection_reply.subprocess.run') as execute:
                command, records = prepare_missing_idl(root, cwd, ['clang++'], output,
                                                        copy_readonly_inputs=True)
            execute.assert_not_called()
            self.assertEqual((command, records), (['clang++'], []))
            self.assertEqual(list(output.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
