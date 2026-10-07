"""Compiler-command integrity fixtures, never actual product compilation."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check_serial_grant_objects as checker
from prepare_serial_grant_inputs import allowed_input, quarantine_empty_jsoncpp_placeholder


class SerialGrantObjectCommandTest(unittest.TestCase):
    def commands(self):
        return '\n'.join('/fixed/clang++ -Werror -fsanitize=cfi -c /candidate/source.cpp -o ' + target
                         for target in checker.TARGETS)

    def test_one_actual_graph_query_retains_every_real_compiler_flag(self):
        with patch.object(checker.subprocess, 'run') as invoked:
            invoked.return_value = subprocess.CompletedProcess([], 0, self.commands(), '')
            query, selected = checker.actual_commands(Path('/fixed/ninja'), Path('/scratch/out/arm64_virt'))
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(query[-3:], list(checker.TARGETS))
        self.assertEqual(set(selected), set(checker.TARGETS))
        for _, command in selected.values():
            self.assertIn('-Werror', command)
            self.assertIn('-fsanitize=cfi', command)

    def test_missing_duplicate_or_link_command_cannot_be_a_compilation_pass(self):
        commands = self.commands().splitlines()
        for output in ('\n'.join(commands[:-1]), '\n'.join(commands + [commands[0]]), '/fixed/ld.lld -o fake.so'):
            with self.subTest(output=output), patch.object(checker.subprocess, 'run') as invoked:
                invoked.return_value = subprocess.CompletedProcess([], 0, output, '')
                with self.assertRaises(ValueError):
                    checker.actual_commands(Path('/fixed/ninja'), Path('/scratch/out/arm64_virt'))

    def test_generated_inputs_cannot_select_objects_components_or_escape(self):
        for target in ('musl_headers', 'gen/foundation/ability/idl/some_proxy.h',
                       'gen/third_party/jsoncpp/jsoncpp-1.9.6/src/lib_json/json_reader.cpp'):
            self.assertTrue(allowed_input(target))
        for target in ('serial_manager', 'all', 'obj/generated.o', 'gen/../outside.h', '/gen/foreign.h',
                       'gen/fake.cpp', 'gen/header.h;echo'):
            self.assertFalse(allowed_input(target))

    def test_empty_gn_skeleton_is_preserved_but_even_empty_file_is_refused(self):
        with tempfile.TemporaryDirectory(prefix='serial-placeholder-fixture-') as temporary:
            staged = Path(temporary).resolve()
            product = staged / 'out/armv7a_virt'
            tree = product / 'gen/third_party/jsoncpp/jsoncpp-1.9.6'
            (tree / 'src/lib_json').mkdir(parents=True)
            unknown = tree / 'src/lib_json/user-empty.txt'
            unknown.touch()
            destination = staged / 'quarantine'
            with self.assertRaisesRegex(ValueError, 'directory-only'):
                quarantine_empty_jsoncpp_placeholder(staged, product, destination)
            self.assertTrue(unknown.is_file())
            unknown.unlink()
            record = quarantine_empty_jsoncpp_placeholder(staged, product, destination)
            self.assertEqual(record['regular_file_count'], 0)
            self.assertEqual(record['directories'], ['.', 'src', 'src/lib_json'])
            self.assertTrue((destination / 'src/lib_json').is_dir())
            self.assertFalse(tree.exists())


if __name__ == '__main__':
    unittest.main()
