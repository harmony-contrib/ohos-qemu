#!/usr/bin/env python3
"""Mock-tool/parser challenges only; no compiler, SDK or guest is executed."""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import build_watchdog_clock_probe as builder


def synthetic_elf(arch, *, needed=b'libc.so', loader=None):
    """An explicitly artificial, non-executable test fixture serialized in Python."""
    _, cls, machine, loader_name, _ = builder.ARCHES[arch]
    is64 = cls == 2
    eh, ph, sh = (64, 56, 64) if is64 else (52, 32, 40)
    data = bytearray(1024)
    data[:16] = b'\x7fELF' + bytes((cls, 1, 1)) + bytes(9)
    base = 0x10000
    interpreter = (loader or '/lib/ld-musl-' + loader_name + '.so.1').encode() + b'\0'
    data[400:400 + len(interpreter)] = interpreter
    strings = b'\0' + needed + b'\0'; data[480:480 + len(strings)] = strings
    tags = [(1, 1), (5, base + 480), (10, len(strings)), (0, 0)]
    dfmt = '<qQ' if is64 else '<iI'
    dsize = struct.calcsize(dfmt)
    for index, row in enumerate(tags):
        struct.pack_into(dfmt, data, 512 + index * dsize, *row)
    header = (3, machine, 1, base + 384, eh, 768, 0 if arch != 'armv7a' else 0x05000200,
              eh, ph, 3, sh, 2, 1)
    struct.pack_into('<HHIQQQIHHHHHH' if is64 else '<HHIIIIIHHHHHH', data, 16, *header)
    programs = [(1, 7, 0, base, base, len(data), len(data), 4096),
                (3, 4, 400, base + 400, base + 400, len(interpreter), len(interpreter), 1),
                (2, 6, 512, base + 512, base + 512, len(tags) * dsize, len(tags) * dsize, 8)]
    for index, (typ, flags, offset, addr, physical, size, memory, align) in enumerate(programs):
        values = (typ, flags, offset, addr, physical, size, memory, align) if is64 else (
            typ, offset, addr, physical, size, memory, flags, align)
        struct.pack_into('<IIQQQQQQ' if is64 else '<IIIIIIII', data, eh + index * ph, *values)
    return bytes(data)


def readelf_fixture(arch, data):
    elf = builder.elf_metadata(data, arch)
    machine = {'arm64': 'AArch64', 'armv7a': 'ARM', 'x86_64': 'Advanced Micro Devices X86-64'}[arch]
    return (f'ELF Header:\n  Class: ELF{64 if builder.ARCHES[arch][1] == 2 else 32}\n'
            f'  Machine: {machine}\nProgram Headers:\n  LOAD\n  INTERP\n  DYNAMIC\n'
            f'  [Requesting program interpreter: {elf["interpreter"]}]\nDynamic section fixture ONLY\n'
            '  0x1 (NEEDED) Shared library: [libc.so]\n')


class ClockBuilderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='mock-clock-builder-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.sdk = self.root / 'SDK39'
        (self.sdk / 'llvm/bin').mkdir(parents=True)
        (self.sdk / 'llvm/bin/clang-real').write_bytes(b'MOCK compiler bytes NEVER EXECUTED')
        (self.sdk / 'llvm/bin/clang').symlink_to('clang-real')
        (self.sdk / 'llvm/bin/llvm-readobj').write_bytes(b'MOCK readobj bytes NEVER EXECUTED')
        (self.sdk / 'llvm/bin/llvm-readelf').symlink_to('llvm-readobj')
        (self.sdk / 'llvm/bin/ld.lld').write_bytes(b'MOCK LLVM linker bytes NEVER EXECUTED')
        metadata = {'path': 'native', 'apiVersion': '26', 'version': '26.0.0.39', 'platformVersion': '26.0.0'}
        (self.sdk / 'oh-uni-package.json').write_text(json.dumps(metadata))
        toolchain = self.sdk / 'build/cmake/ohos.toolchain.cmake'; toolchain.parent.mkdir(parents=True)
        toolchain.write_text('set(OHOS_TOOLCHAIN_NAME arm-linux-ohos)\nlist(APPEND FLAGS -march=armv7a)\n')
        headers = self.sdk / 'sysroot/usr/include'; headers.mkdir(parents=True)
        self.headers = [headers / name for name in ('time.h', 'stdio.h', 'stdint.h', 'inttypes.h')]
        for header in self.headers:
            header.write_text('/* MOCK SDK header: ' + header.name + ' */\n')
        self.current = self.root / 'current-watchdog_clock_probe.c'
        self.current.write_text('/* MOCK source bytes; no C compilation proof */\n')
        self.source = self.root / 'frozen-watchdog_clock_probe.c'
        self.source.write_bytes(self.current.read_bytes())
        self.output = self.root / 'out'
        self.calls = []
        self.failure = None
        self.external_header = None
        self.patch_source = patch.object(builder, 'CURRENT_SOURCE', self.current)
        self.patch_source.start(); self.addCleanup(self.patch_source.stop)
        # This marks only simulated input mounts. No real SDK is mounted or used.
        ro = patch.object(builder.os, 'statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY))
        ro.start(); self.addCleanup(ro.stop)

    def fake_command(self, argv, directory, label):
        arch = directory.name
        self.calls.append((arch, label, list(argv)))
        log = directory / (label + '.log')
        code = 9 if self.failure == (arch, label) else 0
        if label == 'compile':
            obj = directory / 'watchdog_clock_probe.o'
            if code == 0:
                obj.write_bytes(b'MOCK object ' + arch.encode())
                paths = [self.source, *self.headers]
                if self.external_header:
                    paths.append(self.external_header)
                dep = ' '.join(str(path).replace(' ', '\\ ') for path in paths)
                (directory / 'dependencies.d').write_text(str(obj) + ': \\\n  ' + dep + '\n')
            text = 'MOCK clang version FIXTURE ONLY\n"-cc1" ' + str(self.source) + ' ' + str(self.sdk / 'sysroot') + '\n'
        elif label == 'link':
            if code == 0:
                (directory / 'watchdog_clock_probe').write_bytes(synthetic_elf(arch))
            text = ('MOCK clang version FIXTURE ONLY\n' + str(self.sdk / 'llvm/bin/ld.lld') + ' ' + str(directory / 'watchdog_clock_probe.o') +
                    ' -o ' + str(directory / 'watchdog_clock_probe') + '\n')
        else:
            text = readelf_fixture(arch, (directory / 'watchdog_clock_probe').read_bytes())
        log.write_text(text)
        return {'label': label, 'argv': argv, 'cwd': str(directory), 'exit_code': code, 'timed_out': False,
                'started_ns': 1 + len(self.calls) * 10, 'finished_ns': 2 + len(self.calls) * 10,
                'log': builder.artifact(log)}

    def build(self):
        with patch.object(builder, 'run_command', side_effect=self.fake_command):
            return builder.build(self.sdk, self.source, self.output)

    def receipt(self):
        return self.output / 'build.json'

    def verify(self, arch='arm64'):
        return builder.verify_build(self.output / arch / 'watchdog_clock_probe', self.receipt(), arch)

    def edit_report(self, mutator):
        value = builder.load(self.receipt()); mutator(value)
        self.receipt().write_text(json.dumps(value))

    def test_mock_batch_is_serial_preserves_argv0_and_never_claims_runtime(self):
        value = self.build()
        self.assertEqual(value['status'], 'pass_build_ONLY')
        self.assertEqual([(arch, label) for arch, label, _ in self.calls],
                         [(arch, label) for arch in builder.ARCHES for label in ('compile', 'link', 'readelf')])
        result = self.verify()
        self.assertIs(result['runtime_validated'], False)
        self.assertIs(result['SDK_tools_and_headers_re_read_on_host'], False)
        self.assertEqual(result['verified_build_arches'], list(builder.ARCHES))
        for arch, label, argv in self.calls:
            if label == 'readelf':
                self.assertEqual(Path(argv[0]).name, 'llvm-readelf')
                self.assertNotEqual(str(Path(argv[0]).resolve()), argv[0])
            if arch == 'armv7a' and label != 'readelf':
                self.assertTrue({'-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'} <= set(argv))

    def test_one_ABI_failure_is_preserved_and_remaining_ABIs_attempted(self):
        self.failure = ('armv7a', 'compile')
        value = self.build()
        self.assertEqual(value['status'], 'fail')
        self.assertEqual(value['architectures']['armv7a']['commands'][0]['exit_code'], 9)
        self.assertEqual(value['architectures']['x86_64']['status'], 'pass_build_ONLY')
        with self.assertRaisesRegex(ValueError, 'successful SDK-only'):
            self.verify()

    def test_wrong_SDK_version_preserves_all_three_blocked_rows(self):
        metadata = self.sdk / 'oh-uni-package.json'
        value = builder.load(metadata); value['version'] = '26.0.0.105'
        metadata.write_text(json.dumps(value))
        report = self.build()
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(self.calls, [])
        self.assertEqual(len(report['architectures']), 3)
        self.assertTrue(all(row['errors'] for row in report['architectures'].values()))

    def test_wrong_metadata_shape_is_recorded_instead_of_crashing_batch(self):
        (self.sdk / 'oh-uni-package.json').write_text('["not SDK metadata"]')
        report = self.build()
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(self.calls, [])
        self.assertEqual(len(report['architectures']), 3)
        self.assertIn('SDK 26.0.0.39 required', report['errors'][0])

    def test_arbitrary_source_is_not_built_even_with_matching_new_receipt(self):
        self.source.write_text('changed arbitrary C')
        self.assertEqual(self.build()['status'], 'fail')
        self.assertEqual(self.calls, [])

    def test_current_C_changed_after_build_rejected(self):
        self.build(); self.current.write_text('different current probe')
        with self.assertRaisesRegex(ValueError, 'current C source'):
            self.verify()

    def test_original_source_missing_or_changed_rejected(self):
        self.build(); self.source.unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_compile_log_changed_rejected(self):
        self.build(); (self.output / 'arm64/compile.log').write_text('self reported pass')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            self.verify()

    def test_self_consistent_empty_compile_log_rejected(self):
        self.build(); log = self.output / 'arm64/compile.log'; log.write_text('')
        self.edit_report(lambda value: value['architectures']['arm64']['commands'][0].update(log=builder.artifact(log)))
        with self.assertRaisesRegex(ValueError, 'verbose clang'):
            self.verify()

    def test_different_argv0_or_failed_command_rejected(self):
        self.build()
        self.edit_report(lambda value: value['architectures']['arm64']['commands'][2]['argv'].__setitem__(0, str(self.sdk / 'llvm/bin/llvm-readobj')))
        with self.assertRaisesRegex(ValueError, 'invocation differs'):
            self.verify()

    def test_header_list_mismatch_and_non_SDK_header_rejected(self):
        self.external_header = self.root / 'external.h'; self.external_header.write_text('mock external header')
        report = self.build()
        self.assertEqual(report['status'], 'fail')
        self.assertTrue(all('non-SDK' in row['errors'][0] for row in report['architectures'].values()))

    def test_host_verifier_does_not_require_original_SDK_mount(self):
        self.build()
        (self.sdk / 'llvm/bin/clang-real').unlink()
        for header in self.headers:
            header.unlink()
        # Source, output, frozen actual metadata and raw logs remain readable.
        # This passes only the simulated SDK receipt; it claims no host reread.
        self.assertIs(self.verify()['SDK_tools_and_headers_re_read_on_host'], False)

    def test_existing_output_is_never_overwritten(self):
        self.build()
        before = self.receipt().read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(self.receipt().read_bytes(), before)

    def test_compiler_drift_after_successful_mock_commands_fails_entire_batch(self):
        def drift(argv, directory, label):
            row = self.fake_command(argv, directory, label)
            if directory.name == 'x86_64' and label == 'readelf':
                (self.sdk / 'llvm/bin/clang-real').write_bytes(b'changed mock compiler')
            return row
        with patch.object(builder, 'run_command', side_effect=drift):
            value = builder.build(self.sdk, self.source, self.output)
        self.assertEqual(value['status'], 'fail')
        self.assertTrue(any('changed during batch' in text for text in value['errors']))
        with self.assertRaises(ValueError):
            self.verify()

    def test_writable_SDK_input_mount_fails_without_starting_commands(self):
        with patch.object(builder.os, 'statvfs', return_value=SimpleNamespace(f_flag=0)):
            value = self.build()
        self.assertEqual(value['status'], 'fail')
        self.assertEqual(self.calls, [])

    def test_another_ABI_binary_cannot_be_substituted(self):
        self.build()
        with self.assertRaisesRegex(ValueError, 'selected ABI output'):
            builder.verify_build(self.output / 'x86_64/watchdog_clock_probe', self.receipt(), 'arm64')

    def test_self_consistent_foreign_binary_is_independently_reparsed(self):
        self.build()
        binary = self.output / 'arm64/watchdog_clock_probe'
        binary.write_bytes(synthetic_elf('x86_64'))
        self.edit_report(lambda value: value['architectures']['arm64'].update(binary=builder.artifact(binary)))
        with self.assertRaisesRegex(ValueError, 'PIE ELF header'):
            self.verify()

    def test_dependency_parser_requires_actual_target_and_handles_spaces(self):
        self.assertEqual(builder.dependencies('/tmp/object: /tmp/a\\ b.h \\\n /sdk/time.h\n', Path('/tmp/object')),
                         ['/tmp/a b.h', '/sdk/time.h'])
        for text in ('wrong: /sdk/time.h', '/tmp/object: /sdk/time.h /sdk/time.h', '/tmp/object: $(HEADER)'):
            with self.assertRaises(ValueError):
                builder.dependencies(text, Path('/tmp/object'))

    def test_ELF_classes_complete_headers_interpreters_and_needed(self):
        for arch in builder.ARCHES:
            with self.subTest(arch=arch):
                result = builder.elf_metadata(synthetic_elf(arch), arch)
                self.assertEqual(len(result['ELF_header']), 14)
                self.assertEqual(len(result['program_headers']), 3)
                self.assertEqual(result['DT_NEEDED'], ['libc.so'])
                for data in (bytes(64), synthetic_elf(arch)[:100], synthetic_elf(arch, needed=b'libc++.so'),
                             synthetic_elf(arch, loader='/lib/wrong.so')):
                    with self.assertRaises(ValueError):
                        builder.elf_metadata(data, arch)

    def test_ELF_unbacked_entry_and_dynamic_VA_rejected(self):
        data = bytearray(synthetic_elf('arm64')); struct.pack_into('<Q', data, 24, 0x50000000)
        with self.assertRaisesRegex(ValueError, 'entry point'):
            builder.elf_metadata(data, 'arm64')
        data = bytearray(synthetic_elf('arm64')); struct.pack_into('<Q', data, 512 + 16 + 8, 0x50000000)
        with self.assertRaisesRegex(ValueError, 'PT_LOAD'):
            builder.elf_metadata(data, 'arm64')

    def test_timeout_terminates_actual_process_group_and_preserves_exit(self):
        directory = self.root / 'timeout'; directory.mkdir()
        proc = SimpleNamespace(pid=123456, wait=unittest.mock.Mock(side_effect=[subprocess.TimeoutExpired(['mock'], 120), 0]))
        with patch.object(builder.subprocess, 'Popen', return_value=proc), patch.object(builder.os, 'killpg') as kill:
            result = builder.run_command(['mock-NOT-a-tool'], directory, 'compile')
        self.assertEqual(result['exit_code'], 124)
        self.assertIs(result['timed_out'], True)
        kill.assert_called_once_with(proc.pid, builder.signal.SIGTERM)


if __name__ == '__main__':
    unittest.main()
