import hashlib
import importlib.util
import json
import os
import shutil
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('camera_component_compile',
                                             Path(__file__).with_name('compile_camera_component.py'))
COMPILER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPILER)


class CameraCompileIsolationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name).resolve()
        self.root = self.base / 'production'
        self.staged = self.base / 'scratch'
        (self.root / 'out').mkdir(parents=True)
        for relative in ('build', 'vendor', 'drivers', 'out/arm64_virt'):
            (self.staged / relative).mkdir(parents=True)
        library = self.staged / 'out/arm64_virt/dsp.so'
        library.write_bytes(b'actual-library-fixture')
        self.evidence = {'scratch_source': str(self.staged), 'product': 'arm64_virt',
                         'gn_exit_code': 0, 'link_exit_code': 0, 'library': str(library),
                         'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest()}
        self.write_evidence()

    def write_evidence(self):
        (self.staged / 'audio-dsp-build-evidence.json').write_text(json.dumps(self.evidence))

    def validate(self, readonly=True):
        class Stat:
            f_flag = os.ST_RDONLY if readonly else 0
        with patch.object(COMPILER.os, 'statvfs', return_value=Stat()):
            return COMPILER.validate_tree(self.root, self.staged, 'arm64_virt')

    def test_accepts_matching_completed_owned_scratch_with_ro_production(self):
        self.assertEqual(self.validate(), self.evidence)

    def test_rejects_writable_production_and_overlapping_scratch(self):
        with self.assertRaisesRegex(ValueError, 'read-only'):
            self.validate(False)
        for staged in (self.root, self.root / 'other', self.root.parent):
            with self.subTest(staged=staged), self.assertRaisesRegex(ValueError, 'separate'):
                COMPILER.validate_tree(self.root, staged, 'arm64_virt')

    def test_rejects_failed_wrong_product_and_changed_actual_library(self):
        for field, value in (('link_exit_code', 1), ('gn_exit_code', 1),
                             ('product', 'x86_64_virt'), ('library_sha256', '0' * 64)):
            with self.subTest(field=field):
                original = self.evidence[field]
                self.evidence[field] = value
                self.write_evidence()
                with self.assertRaises(ValueError):
                    self.validate()
                self.evidence[field] = original
                self.write_evidence()

    def test_rejects_symlinked_writable_component(self):
        (self.staged / 'drivers').rmdir()
        (self.staged / 'drivers').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'real directory'):
            self.validate()

    def test_elf_identity_requires_actual_matching_shared_object(self):
        library = self.base / 'camera.so'
        for product, elf_class, machine in (('arm64_virt', 2, 183), ('armv7a_virt', 1, 40),
                                             ('x86_64_virt', 2, 62)):
            header = bytearray(64)
            header[:6] = b'\x7fELF' + bytes((elf_class, 1))
            struct.pack_into('<HH', header, 16, 3, machine)
            library.write_bytes(header)
            self.assertEqual(COMPILER.elf_identity(library, product)['elf_machine'], machine)
            for bad in (b'', b'not an elf', bytes(header[:4]) + bytes((3,)) + bytes(header[5:])):
                library.write_bytes(bad)
                with self.assertRaises(ValueError):
                    COMPILER.elf_identity(library, product)
            struct.pack_into('<HH', header, 16, 2, machine)
            library.write_bytes(header)
            with self.assertRaises(ValueError):
                COMPILER.elf_identity(library, product)

    def test_materializes_only_identical_source_idl_without_changing_production(self):
        source = self.root / 'base/startup/init/source.idl'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'interface Source {}\n')
        other = source.with_suffix('.cpp')
        other.write_bytes(b'// source remains read-only linked\n')
        other_component = self.root / 'base/configpolicy/source/bundle.json'
        other_component.parent.mkdir(parents=True)
        other_component.write_bytes(b'{"name":"config_policy"}\n')
        (self.staged / 'base').symlink_to(self.root / 'base', target_is_directory=True)
        records = COMPILER.materialize_idl_inputs(self.root, self.staged)
        target = self.staged / 'base/startup/init/source.idl'
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertTrue((self.staged / 'base/startup/init/source.cpp').is_symlink())
        for relative in ('base', 'base/configpolicy', 'base/configpolicy/source'):
            self.assertTrue((self.staged / relative).is_dir())
            self.assertFalse((self.staged / relative).is_symlink())
        self.assertTrue((self.staged / 'base/configpolicy/source/bundle.json').is_symlink())
        self.assertEqual(records, [{'source': 'base/startup/init/source.idl', 'sha256': COMPILER.sha(source)}])
        self.assertEqual(COMPILER.materialize_idl_inputs(self.root, self.staged), records)
        target.write_bytes(b'edited IDL\n')
        with self.assertRaisesRegex(ValueError, 'differs'):
            COMPILER.materialize_idl_inputs(self.root, self.staged)
        self.assertEqual(source.read_bytes(), b'interface Source {}\n')

    def test_tls_check_inspects_actual_32_and_64_bit_program_headers(self):
        library = self.base / 'turbojpeg.so'
        for elf_class, header_size, program_size in ((1, 52, 32), (2, 64, 56)):
            with self.subTest(elf_class=elf_class):
                data = bytearray(header_size + program_size)
                data[:6] = b'\x7fELF' + bytes((elf_class, 1))
                if elf_class == 1:
                    struct.pack_into('<I', data, 28, header_size)
                    struct.pack_into('<HH', data, 42, program_size, 1)
                else:
                    struct.pack_into('<Q', data, 32, header_size)
                    struct.pack_into('<HH', data, 54, program_size, 1)
                struct.pack_into('<I', data, header_size, 7)
                library.write_bytes(data)
                self.assertEqual(COMPILER.elf_tls_segments(library), 1)
                struct.pack_into('<I', data, header_size, 1)
                library.write_bytes(data)
                self.assertEqual(COMPILER.elf_tls_segments(library), 0)
                library.write_bytes(data[:-1])
                with self.assertRaisesRegex(ValueError, 'truncated program headers'):
                    COMPILER.elf_tls_segments(library)

    def test_generated_jpeg_headers_match_strict_source_and_same_archive_template(self):
        source = self.staged / 'third_party/libjpeg-turbo'
        generated = self.staged / 'out/arm64_virt/gen/third_party/libjpeg-turbo/libjpeg-turbo-3.1.0'
        source.mkdir(parents=True)
        (generated / 'src').mkdir(parents=True)
        for name in ('jconfig.h', 'jconfigint.h'):
            (source / name).write_bytes(b'fixed input\n')
            (generated / 'src' / name).write_bytes(b'fixed input\n')
        (generated / 'CMakeLists.txt').write_text('set(COPYRIGHT_YEAR "1991-2024")\n')
        (generated / 'src/jversion.h.in').write_bytes(b'Copyright @COPYRIGHT_YEAR@\n')
        (generated / 'src/jversion.h').write_bytes(b'Copyright 1991-2024\n')
        headers = COMPILER.jpeg_generated_headers(self.staged, self.staged / 'out/arm64_virt')
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[-1]['copyright_year'], '1991-2024')
        (generated / 'src/jversion.h').write_bytes(b'stale version\n')
        with self.assertRaisesRegex(ValueError, 'same-archive'):
            COMPILER.jpeg_generated_headers(self.staged, self.staged / 'out/arm64_virt')

    def test_emutls_symbol_check_requires_definition_kind_and_binding(self):
        table = (' 1939: 000000000006cda0 32 OBJECT LOCAL DEFAULT 23 __emutls_v.errStr\n'
                 ' 40: 0000000000000000 0 FUNC GLOBAL DEFAULT UND __emutls_get_address\n'
                 ' 2281: 0000000000128888 464 FUNC WEAK DEFAULT 15 __emutls_get_address\n')
        self.assertTrue(COMPILER.symbol_present(table, '__emutls_v.errStr', 'OBJECT', True, {'LOCAL'}))
        self.assertTrue(COMPILER.symbol_present(table, '__emutls_get_address', 'FUNC', True, {'WEAK'}))
        self.assertTrue(COMPILER.symbol_present(table, '__emutls_get_address', 'FUNC', False, {'GLOBAL'}))
        self.assertFalse(COMPILER.symbol_present(table, '__emutls_v.errStr', 'TLS', True, {'LOCAL'}))
        self.assertFalse(COMPILER.symbol_present(table, '__emutls_v.errStr', 'OBJECT', False, {'LOCAL'}))

    def test_arm_plt_resolver_check_requires_exact_real_instruction_and_relocation_slot(self):
        accessor = ' 3fc36: f009 efbc blx 0x49bb0 <$a>\n'
        plt = (' 49bb0: e28fc600 add r12, pc, #0, #12\n'
               ' 49bb4: e28cca01 add r12, r12, #4096\n'
               ' 49bb8: e5bcf7b4 ldr pc, [r12, #1972]!\n')
        relocation = '0004b36c 00002816 R_ARM_JUMP_SLOT 00000000 __emutls_get_address\n'
        result = COMPILER.arm_plt_emutls_call(accessor, plt, relocation)
        self.assertEqual(result['resolved_PLT_GOT_slot'], '0x4b36c')
        for bad in (relocation.replace('0004b36c', '0004b370'),
                    relocation.replace('__emutls_get_address', 'different_function')):
            with self.assertRaisesRegex(ValueError, 'GOT slot'):
                COMPILER.arm_plt_emutls_call(accessor, plt, bad)
        with self.assertRaisesRegex(ValueError, 'ADD ip,pc'):
            COMPILER.arm_plt_emutls_call(accessor, plt.replace('e28cca01', 'e28dc001'), relocation)

    def test_postcheck_cannot_relabel_failed_build_or_changed_artifacts_as_pass(self):
        evidence = self.staged / 'camera-native-tls-validator.json'
        original = {'scratch_source': str(self.staged), 'product': 'arm64_virt',
                    'gn_exit_code': 0, 'link_exit_code': 0, 'installer_repeat_exit_code': 0,
                    'repeat_link_exit_code': 0, 'validation_exit_code': 1,
                    'error': 'actual linked TurboJPEG output lacks its required real TLS segment',
                    'artifacts': [{'path': self.evidence['library'],
                                   'sha256': self.evidence['library_sha256']}],
                    'component_payload_sha256': {}, 'input_pipeline_config_before': {}}
        for field, value in (('gn_exit_code', 1), ('repeat_link_exit_code', 1),
                             ('error', 'actual compiler failure')):
            bad = dict(original, **{field: value})
            evidence.write_text(json.dumps(bad))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'only correct'):
                COMPILER.postcheck_completed_build(self.root, self.base, self.staged,
                                                   'arm64_virt', 'test-correction', evidence)
        evidence.write_text(json.dumps(original))
        Path(self.evidence['library']).write_bytes(b'changed real artifact\n')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            COMPILER.postcheck_completed_build(self.root, self.base, self.staged,
                                               'arm64_virt', 'test-correction', evidence)

    def test_mutating_installer_receives_owned_copy_and_prior_inputs_are_preserved(self):
        source = self.root / 'third_party/libjpeg-turbo'
        source.mkdir(parents=True)
        (source / 'jmorecfg.h').write_bytes(b'original header\n')
        other = self.root / 'third_party/other_component/source/bundle.json'
        other.parent.mkdir(parents=True)
        other.write_bytes(b'{"name":"other_component"}\n')
        (self.staged / 'third_party').symlink_to(self.root / 'third_party', target_is_directory=True)
        evidence = COMPILER.copy_libjpeg_inputs(self.root, self.staged, 'test-01')
        copied = self.staged / 'third_party/libjpeg-turbo/jmorecfg.h'
        self.assertFalse(copied.is_symlink())
        copied.write_bytes(b'generated header\n')
        self.assertEqual((source / 'jmorecfg.h').read_bytes(), b'original header\n')
        self.assertTrue(Path(evidence['prior_owned_inputs_preserved']).is_dir())
        self.assertFalse((self.staged / 'third_party/other_component/source').is_symlink())
        self.assertTrue((self.staged / 'third_party/other_component/source/bundle.json').is_symlink())
        with self.assertRaisesRegex(ValueError, 'unknown libjpeg'):
            COMPILER.copy_libjpeg_inputs(self.root, self.staged, 'test-01')

    def test_clone_preserves_original_evidence_and_remaps_internal_links(self):
        destination = self.base / 'new-scratch'
        original_evidence_bytes = (self.staged / 'audio-dsp-build-evidence.json').read_bytes()
        original_library = Path(self.evidence['library'])
        (self.staged / 'out/alias.so').symlink_to(original_library)

        def copy_command(command, check):
            self.assertEqual(command[:3], ['cp', '--archive', '--reflink=auto'])
            shutil.copytree(self.staged, destination, dirs_exist_ok=True, symlinks=True)

        class Stat:
            f_flag = os.ST_RDONLY
        with patch.object(COMPILER.os, 'statvfs', return_value=Stat()), \
                patch.object(COMPILER, 'assert_seed_inactive'), \
                patch.object(COMPILER.subprocess, 'run', side_effect=copy_command):
            provenance = COMPILER.clone_stopped_scratch(self.root, self.staged, destination, 'arm64_virt')
            self.assertEqual(COMPILER.validate_tree(self.root, destination, 'arm64_virt'), self.evidence)
            self.assertEqual((destination / 'audio-dsp-build-evidence.json').read_bytes(), original_evidence_bytes)
            self.assertEqual((destination / 'out/alias.so').resolve(), destination / 'out/arm64_virt/dsp.so')
            self.assertEqual(provenance['remapped_internal_symlinks'], ['out/alias.so'])
            self.assertEqual((self.staged / 'audio-dsp-build-evidence.json').read_bytes(), original_evidence_bytes)
            Path(self.evidence['library']).write_bytes(b'seed changed later\n')
            self.assertEqual((destination / 'out/arm64_virt/dsp.so').read_bytes(), b'actual-library-fixture')
            (destination / COMPILER.CLONE_PROVENANCE).write_text('{}')
            with self.assertRaisesRegex(ValueError, 'clone provenance'):
                COMPILER.validate_tree(self.root, destination, 'arm64_virt')

    def test_clone_guard_rejects_active_build_tools(self):
        proc = self.base / 'proc'
        process = proc / '1234'
        process.mkdir(parents=True)
        (process / 'cmdline').write_bytes(b'ninja\0-C\0' + str(self.staged / 'out/arm64_virt').encode() + b'\0')
        with self.assertRaisesRegex(ValueError, 'active build tool'):
            COMPILER.assert_seed_inactive(self.staged, proc)
        (process / 'cmdline').write_bytes(b'ninja\0-C\0/another-owned-source/out/product\0')
        COMPILER.assert_seed_inactive(self.staged, proc)
        (process / 'cmdline').write_bytes(b'ninja\0-j\0' + b'2\0')
        (process / 'cwd').symlink_to(self.staged / 'out/arm64_virt', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'active build tool'):
            COMPILER.assert_seed_inactive(self.staged, proc)


if __name__ == '__main__':
    unittest.main()
