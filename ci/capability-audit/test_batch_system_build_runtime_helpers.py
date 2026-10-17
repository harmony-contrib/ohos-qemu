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

    def test_actual_gnss_literal_colon_include_keeps_unknown_variables_rejected(self):
        # Actual product graph contains a target-style include path with Ninja's $: escape.
        include = '-I../../base/telephony/sms_mms$:tel_sms_mms_config'
        text = 'include_dirs = ' + include + '\nldflags = -flto\nlibs = -lc++\n'
        self.assertEqual(b.variables(text)['include_dirs'],
                         ['-I../../base/telephony/sms_mms:tel_sms_mms_config'])
        for unknown in ('$name', '${name}', '$:suffix$name', '$$:', '$ '):
            with self.subTest(unknown=unknown), self.assertRaises(ValueError):
                b.variables(text.replace(include, '-I' + unknown))

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

    def test_actual_batch01_LLVM_structured_output_and_needed(self):
        directory = b.ROOT / 'docs/capability-audit/parallel/system/round10-runtime-helpers/tool-repair-02'
        receipt = json.loads((directory / 'original-receipt.json').read_text())
        self.assertEqual(receipt['original_report']['status'], 'fail')
        for name, record in receipt['logs'].items():
            snippet = directory / record['snippet']; self.assertEqual(b.sha(snippet), record['snippet_sha256'])
            text = snippet.read_text()
            self.assertTrue(b.defined_symbol(text, '__cfi_check'))
            self.assertIn('std::__h::', text); self.assertNotIn('std::__n1::', text)
            self.assertLessEqual({Path(p).name for p in b.HELPERS[name]['libraries']}, b.dynamic_needed(text))
            undefined = text.replace('Section: .text ', 'Section: Undefined ')
            self.assertFalse(b.defined_symbol(undefined, '__cfi_check'))
            no_section = '\n'.join(line for line in text.splitlines() if 'Section:' not in line)
            self.assertFalse(b.defined_symbol(no_section, '__cfi_check'))
            self.assertFalse(b.defined_symbol(text.replace('Name: __cfi_check ', 'Name: different '), '__cfi_check'))

    def test_GNU_and_LLVM_needed_require_actual_dynamic_row(self):
        self.assertEqual(b.dynamic_needed('  0x0000000000000001 (NEEDED) Shared library: [libreal.so]\n'), {'libreal.so'})
        self.assertEqual(b.dynamic_needed('  0x0000000000000001 NEEDED Shared library: [libreal.so]\n'), {'libreal.so'})
        for text in ['expected (NEEDED) [libreal.so]', 'Name: NEEDED Shared library: [libreal.so]',
                     '0x0000000000000001 SONAME Shared library: [libreal.so]', 'NEEDED libreal.so']:
            self.assertEqual(b.dynamic_needed(text), set())

    def test_tool_symlink_argv0_preserved_but_input_target_hashed(self):
        actual = self.root / 'llvm-readobj'; actual.write_bytes(b'unit path selector only, never executed')
        selector = self.root / 'llvm-readelf'; selector.symlink_to(actual.name)
        self.assertEqual(b.regular(selector), selector)
        self.assertNotEqual(b.regular(selector), actual)
        with patch.object(b, 'require_ro'):
            self.assertEqual(b.input_record(selector)['path'], str(actual))
            self.assertEqual(b.input_record(selector)['sha256'], b.sha(actual))

    def test_recorded_argument_must_be_present_exactly_once(self):
        self.assertEqual(b.argument(['clang++', '-o', 'private.o'], '-o'), 'private.o')
        for command in [[], ['clang++', '-o'], ['-o', 'one', '-o', 'two'], 'clang++ -o one']:
            with self.assertRaises(ValueError): b.argument(command, '-o')

    def test_existing_report_hash_must_match_before_output_or_native_command(self):
        report = self.root / 'original.json'; report.write_text('{}')
        with patch.object(b, 'require_ro'), patch.object(b.Builder, '__init__', side_effect=AssertionError('no builder yet')):
            for wrong in ['bad', '0' * 64]:
                with self.assertRaisesRegex(ValueError, 'report SHA256 mismatch'):
                    b.ExistingVerifier(self.root, self.root / 'output', list(b.HELPERS), report, wrong)
        self.assertFalse((self.root / 'output').exists())

    def test_existing_artifact_hash_prefix_and_symlink_escape(self):
        verifier = b.ExistingVerifier.__new__(b.ExistingVerifier)
        verifier.artifact_origin = Path('/original/private')
        verifier.previous_root = self.root / 'original'; verifier.previous_root.mkdir()
        artifact = verifier.previous_root / 'object.o'; artifact.write_bytes(b'unit artifact binding')
        verifier.root = self.root / 'source'; verifier.inputs = {}
        with patch.object(b, 'require_ro'):
            row = verifier.bound_artifact('/original/private/object.o', b.sha(artifact))
            self.assertEqual(row['path'], str(artifact))
            for path, expected in [('/elsewhere/object.o', None), ('/original/private/../escape', None),
                                   ('relative.o', None), ('/original/private/object.o', '0' * 64)]:
                with self.assertRaises(ValueError): verifier.bound_artifact(path, expected)
            outside = self.root / 'outside'; outside.write_bytes(b'unit path escape')
            (verifier.previous_root / 'escape').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlink escapes'):
                verifier.bound_artifact('/original/private/escape')

    def test_existing_mode_forbids_Ninja_compiler_linker_or_guest_execution(self):
        verifier = b.ExistingVerifier.__new__(b.ExistingVerifier); verifier.readelf = Path('/actual/llvm-readelf')
        with patch.object(b.Builder, 'command', side_effect=AssertionError('native must not launch')):
            for argv in [['clang++', '-c', 'file.cpp'], ['ninja', '-t', 'commands'], ['guest-helper'],
                         ['/actual/llvm-readelf', '--arbitrary-option', 'file']]:
                with self.assertRaisesRegex(ValueError, 'only read-only actual ELF'):
                    verifier.command(argv, 'unit forbidden')

    def test_existing_receipt_commands_must_match_full_argv(self):
        verifier = b.ExistingVerifier.__new__(b.ExistingVerifier)
        verifier.previous = {'commands': [{'label': 'unit', 'argv': ['original', 'arguments']}]}
        self.assertEqual(verifier.prior_command('unit', ['original', 'arguments'])['label'], 'unit')
        for label, argv in [('absent', None), ('unit', ['changed'])]:
            with self.assertRaises(ValueError): verifier.prior_command(label, argv)
        verifier.previous['commands'] *= 2
        with self.assertRaises(ValueError): verifier.prior_command('unit')

    def test_shared_ELF_contract_reaches_linked_DSO_checks_and_keeps_CFI_gate(self):
        # Only parser/control flow: recorded real text, no ELF/native execution.
        directory = b.ROOT / 'docs/capability-audit/parallel/system/round10-runtime-helpers/tool-repair-02'
        name = 'wallpaper_token_query'; text = (directory / ('llvm-01-' + name + '.txt')).read_text()
        builder = b.Builder.__new__(b.Builder); builder.readelf = Path('/actual/llvm-readelf')
        direct = [Path('/actual/libaccesstoken_sdk.z.so')]
        for library_text, should_pass in [(text, True), (text.replace('Section: .text ', 'Section: Undefined '), False)]:
            row = {}
            with patch.object(b, 'elf_header', return_value={'unit': 'parser seam, not real ELF proof'}), \
                 patch.object(builder, 'command', side_effect=[text, library_text]) as command:
                if should_pass: builder.check_elf(name, Path('/unit/helper'), direct, row)
                else:
                    with self.assertRaisesRegex(ValueError, 'AccessToken DSO lacks'):
                        builder.check_elf(name, Path('/unit/helper'), direct, row)
                self.assertEqual(command.call_count, 2)
                self.assertEqual(command.call_args.args[1], name + '-linked-libaccesstoken_sdk.z.so')

    def test_shared_ELF_contract_rejects_missing_needed_and_SDK_ABI(self):
        directory = b.ROOT / 'docs/capability-audit/parallel/system/round10-runtime-helpers/tool-repair-02'
        name = 'wallpaper_token_query'; text = (directory / ('llvm-01-' + name + '.txt')).read_text()
        builder = b.Builder.__new__(b.Builder); builder.readelf = Path('/actual/llvm-readelf')
        for wrong in [text.replace('std::__h::', 'std::__n1::'), text.replace('NEEDED', 'SONAME'),
                      text.replace('libaccesstoken_sdk.z.so', 'different.so')]:
            with patch.object(b, 'elf_header', return_value={'unit': 'parser seam, not real ELF proof'}), \
                 patch.object(builder, 'command', return_value=wrong):
                with self.assertRaises(ValueError): builder.check_elf(name, Path('/unit/helper'), [], {})

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
