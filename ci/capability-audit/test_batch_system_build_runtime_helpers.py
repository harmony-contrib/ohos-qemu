#!/usr/bin/env python3
"""Parser/control-flow unit tests only. Never invokes a native compiler/Ninja."""
import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_system_build_runtime_helpers as b


class RuntimeHelperBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.build = self.root / 'out/arm64_virt'; self.build.mkdir(parents=True)
        self.compiler = self.root / 'toolchain/clang++'
        self.source = self.root / 'actual/component.cpp'
        self.flags = ['--target=aarch64-linux-ohos', '--sysroot=obj/third_party/musl', '-std=c++17',
            '-flto=thin', '-flto=full', '-fno-exceptions', '-fno-rtti', '-fsanitize=cfi', '-fsanitize-cfi-cross-dso']

    def command(self):
        import shlex
        return shlex.join(['/usr/bin/ccache', str(self.compiler), '-MMD', '-MF', 'original.d',
            '-DREAL_PRODUCT', '-I../../actual', *self.flags, '-c', str(self.source), '-o', 'original.o'])

    def test_actual_compile_options_are_retained(self):
        result = b.compile_flags(self.command(), self.compiler, self.source, self.build)
        self.assertEqual(result, ['-DREAL_PRODUCT', '-I../../actual', *self.flags])
        b.validate_flags(result)
        self.assertNotIn('-o', result); self.assertNotIn('original.d', result)

    def test_compiler_command_rejects_mutation_and_shell_syntax(self):
        for command in [self.command() + ' && touch /tmp/anything', self.command() + ' @unknown.rsp',
                        self.command().replace(str(self.source), '/different.cpp'),
                        self.command().replace('/usr/bin/ccache', '/untrusted/launcher'),
                        self.command() + ' -D_LIBCPP_ABI_NAMESPACE=__h', self.command() + ' -save-temps']:
            with self.assertRaises(ValueError): b.compile_flags(command, self.compiler, self.source, self.build)

    def test_wallpaper_selected_cfi_categories_are_not_lost(self):
        selected = self.flags + ['-fno-sanitize=cfi', '-fsanitize=cfi-vcall', '-fsanitize=cfi-icall']
        self.assertTrue(b.effective_cfi(selected)); b.validate_flags(selected)
        self.assertFalse(b.effective_cfi(selected + ['-fno-sanitize=cfi']))
        self.assertIn('-fvisibility=default', b.cfi_flags(['-fvisibility=default', '-flto=full', '-Wno-error']))
        self.assertNotIn('-Wno-error', b.cfi_flags(['-Wno-error']))
        self.assertNotIn('-flto=full', b.cfi_flags(['-flto=full']))

    def test_required_product_safety_and_arch_flags_fail_closed(self):
        for flags in [self.flags + ['-fexceptions'], self.flags + ['-fno-lto'],
                      [f for f in self.flags if not f.startswith('--sysroot=')],
                      [f for f in self.flags if 'cfi' not in f],
                      [f.replace('aarch64-linux-ohos', 'aarch64-linux-android') for f in self.flags]]:
            with self.assertRaises(ValueError): b.validate_flags(flags)

    def test_private_link_adaptation_preserves_cfi_lto_and_warnings(self):
        original = ['-flto=full', '-fsanitize=cfi', '-fsanitize-cfi-cross-dso', '-Werror',
            '-Wl,--version-script=../../component/export.map',
            '-Wl,--version-script=../../build/config/sanitizers/cfi.versionscript',
            '-Wl,--thinlto-jobs=16', '-Wl,--thinlto-cache-dir=thinlto-cache']
        flags, removed = b.link_flags(original, self.root / 'private')
        self.assertEqual(removed, [original[4]])
        self.assertIn(original[5], flags); self.assertIn('-flto=full', flags); self.assertIn('-Werror', flags)
        self.assertIn('-Wl,--thinlto-jobs=2', flags)
        self.assertIn('-Wl,--thinlto-cache-dir=' + str(self.root / 'private/lto-cache'), flags)

    def test_actual_graph_variables_missing_ambiguous_or_unexpanded_rejected(self):
        text = 'include_dirs = -I../../public\n  ldflags = -flto -fsanitize=cfi\n  libs = -lc++ -lc\n'
        self.assertEqual(b.variables(text)['libs'], ['-lc++', '-lc'])
        for wrong in [text + 'libs = -ldl\n', text.replace('-lc++ -lc', '$unknown'), 'libs = -lc\n']:
            with self.assertRaises(ValueError): b.variables(wrong)

    def test_only_actual_selected_DSO_inputs_and_not_proxy_libc(self):
        graph = ('build own.so unstripped/own.so: solink first.o public/libreal.z.so '
                 'obj/third_party/musl/sp/libc.so private/libactual.so | implicit/unused.so || later.stamp\n')
        self.assertEqual(b.selected_shared_dependencies(graph), ['public/libreal.z.so', 'private/libactual.so'])
        for wrong in ['', graph + graph]:
            with self.assertRaises(ValueError): b.selected_shared_dependencies(wrong)

    def test_actual_depfile_escapes_and_continuations(self):
        path = self.root / 'headers.d'
        path.write_text('private.o: ../../public\\ file.h \\\n ../../header.h ../../public\\ file.h\n')
        self.assertEqual(b.dep_paths(path, self.build), [self.root / 'public file.h', self.root / 'header.h'])
        path.write_text('not a depfile')
        with self.assertRaises(ValueError): b.dep_paths(path, self.build)

    def test_read_only_inputs_are_enforced_before_output_creation(self):
        with patch.object(os, 'statvfs', return_value=SimpleNamespace(f_flag=0)):
            with self.assertRaisesRegex(ValueError, 'read-only'):
                b.Builder(self.root, self.root / 'new-output', list(b.HELPERS))
        self.assertFalse((self.root / 'new-output').exists())
        with patch.object(os, 'statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
            b.require_ro(self.root)

    def test_private_output_cannot_overlap_read_only_source(self):
        with patch.object(os, 'statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
            with self.assertRaisesRegex(ValueError, 'outside source/out'):
                b.Builder(self.root, self.root / 'forbidden-output', list(b.HELPERS))
        self.assertFalse((self.root / 'forbidden-output').exists())

    def test_command_launch_failure_preserves_real_error_log(self):
        builder = b.Builder.__new__(b.Builder)
        builder.output = self.root / 'private'; builder.output.mkdir()
        builder.build = self.build; builder.environment = {}; builder.report = {'commands': []}
        with patch('batch_system_build_runtime_helpers.subprocess.Popen', side_effect=OSError('unit launch failure')):
            with self.assertRaisesRegex(ValueError, 'actual command failed'):
                builder.command(['never-executed-unit-placeholder'], 'unit-launch')
        row = builder.report['commands'][0]
        self.assertEqual(row['exit_code'], 127)
        self.assertEqual(row['sha256'], b.sha(row['log']))
        self.assertIn('unit launch failure', Path(row['log']).read_text())

    def test_all_three_failed_helpers_are_collected_without_compiling(self):
        builder = b.Builder.__new__(b.Builder)
        builder.output = self.root / 'private'; builder.output.mkdir()
        builder.helpers = list(b.HELPERS); builder.inputs = {}; builder.plan_only = False
        builder.report = {'commands': [], 'helpers': {}, 'status': 'fail'}
        with patch.object(builder, 'remember', side_effect=ValueError('actual input absent')), \
             patch.object(builder, 'command', side_effect=AssertionError('must not run native or Ninja')):
            result = builder.run()
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(set(result['helpers']), set(b.HELPERS))
        self.assertTrue(all(r['status'] == 'fail' and 'actual input absent' in r['error'] for r in result['helpers'].values()))
        self.assertEqual(result['commands'], [])

    def test_link_trace_records_archive_and_real_paths(self):
        a, d = self.build / 'real.a', self.build / 'real.so'; a.write_bytes(b'parser test'); d.write_bytes(b'parser test')
        self.assertEqual(b.trace_link_inputs('real.a(member.o)\n' + str(d) + '\nignored diagnostic\n', self.build), [a, d])

    def test_elf_symbol_must_be_defined_not_just_mentioned(self):
        self.assertFalse(b.defined_symbol('4: 0000000000 0 FUNC GLOBAL DEFAULT UND __cfi_check', '__cfi_check'))
        self.assertTrue(b.defined_symbol('4: 0000001000 4096 FUNC GLOBAL DEFAULT 12 __cfi_check', '__cfi_check'))
        self.assertFalse(b.defined_symbol('failure: expected __cfi_check', '__cfi_check'))

    def test_synthetic_elf_parser_boundaries_never_claim_product_proof(self):
        path = self.root / 'ELF-parser-only'
        data = bytearray(64); data[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<HH', data, 16, 3, 183); path.write_bytes(data)
        self.assertEqual(b.elf_header(path)['machine'], 183)
        with self.assertRaises(ValueError): b.elf_header(path, executable=True)
        for position, value in [(4, 1), (5, 2), (18, 62), (16, 1)]:
            wrong = data[:]; wrong[position] = value; path.write_bytes(wrong)
            with self.assertRaises(ValueError): b.elf_header(path)


if __name__ == '__main__': unittest.main()
