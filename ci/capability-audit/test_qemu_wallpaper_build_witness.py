"""Wallpaper build/provenance guard negatives; no constructed fixture is a build."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import qemu_wallpaper_build_witness as guard


class WallpaperBuildWitnessTests(unittest.TestCase):
    def graph(self):
        return '\n'.join(['defines = -DQEMU_WALLPAPER_RENDERER'] + [
            'build ' + unit + ': cxx ../../' + guard.BASE + '/services/src/' + Path(unit).stem + '.cpp'
            for unit in guard.UNITS] + ['build theme/wallpaper_mgr/' + guard.LIBRARY +
                ' ./lib.unstripped/theme/wallpaper_mgr/' + guard.LIBRARY + ': solink ' + ' '.join(guard.UNITS)])

    def command(self, product='arm64_virt'):
        unit = guard.UNITS[0]
        return '../../prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++ --target=' + guard.PRODUCTS[product][2] + '-linux-ohos ' + \
            '-DQEMU_WALLPAPER_RENDERER -fsanitize-cfi-cross-dso -fsanitize=cfi-vcall -fsanitize=cfi-icall ' + \
            '-fno-exceptions -fno-rtti -flto=thin -c ../../' + guard.BASE + '/services/src/wallpaper_service.cpp -o ' + unit

    def test_actual_graph_contract_requires_both_consumer_edges_and_fallback(self):
        raw = self.graph(); guard.graph_check(raw)
        for changed in (raw.replace('-DQEMU_WALLPAPER_RENDERER', ''), raw + '\ndefines = -DQEMU_WALLPAPER_RENDERER',
                        raw.replace('-DQEMU_WALLPAPER_RENDERER', '-DQEMU_WALLPAPER_RENDERER -DTHEME_SERVICE=0'),
                        raw.replace('wallpaper_service.cpp', 'unrelated.cpp'),
                        raw.replace(' solink ' + ' '.join(guard.UNITS), ' solink ' + guard.UNITS[0])):
            with self.assertRaises(ValueError): guard.graph_check(changed)

    def test_all_three_ABIs_preserve_actual_compiler_source_and_protection_contract(self):
        for product in guard.PRODUCTS: guard.compile_check(self.command(product), guard.UNITS[0], product)
        raw = self.command()
        for changed in (raw.replace('-DQEMU_WALLPAPER_RENDERER', ''), raw.replace('-flto=thin', ''),
                        raw.replace('-fno-exceptions', '-fexceptions'), raw + ' -fno-sanitize=cfi-icall',
                        raw + ' -DTHEME_SERVICE', raw + ' && pretend', raw.replace('aarch64-linux-ohos', 'x86_64-linux-ohos'),
                        raw.replace('wallpaper_service.cpp', 'unrelated.cpp'), raw.replace(guard.UNITS[0], 'elsewhere.o')):
            with self.assertRaises(ValueError): guard.compile_check(changed, guard.UNITS[0], 'arm64_virt')

    def test_GN_query_must_contain_selected_false_not_merely_default_false(self):
        guard.selected_args('theme_service\n    Current value (from the default) = false\n')
        for text in ('theme_service=false', 'theme_service\nCurrent value = true\nDefault value = false',
                     'unrelated\nCurrent value = false', 'theme_service\nCurrent value = 0',
                     'theme_service\n Current value = true\nother_argument\n Current value = false',
                     'theme_service\n Current value = false\ntheme_service\n Current value = false'):
            with self.assertRaises(ValueError): guard.selected_args(text)

    def test_final_ordered_protection_flags_override_earlier_membership(self):
        raw = self.command()
        for flag in ('-fno-sanitize=cfi', '-fno-sanitize=all', '-fno-sanitize=cfi-vcall,cfi-icall',
                     '-fno-sanitize-cfi-cross-dso', '-fno-lto', '-fexceptions', '-frtti'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                guard.compile_check(raw + ' ' + flag, guard.UNITS[0], 'arm64_virt')
        actual_order = raw.replace('-fsanitize=cfi-vcall', '-fsanitize=cfi -fno-sanitize=cfi -fsanitize=cfi-vcall')
        actual_order = actual_order.replace('-fno-exceptions', '-fexceptions -fno-exceptions')
        guard.compile_check(actual_order, guard.UNITS[0], 'arm64_virt')

    def test_query_argv_binds_only_theme_service_and_matching_build_product(self):
        argv = ['/source/prebuilts/build-tools/linux-x86/bin/gn', 'args', '/source/out/arm64_virt', '--list=theme_service']
        guard.selected_args_command(argv, 'arm64_virt')
        guard.selected_args_command(['/usr/bin/qemu-x86_64-static'] + argv, 'arm64_virt')
        for changed in (None, argv + ['--list=unrelated'], ['untrusted'] + argv[1:],
                        argv[:2] + ['/other/out/arm64_virt'] + argv[3:],
                        argv[:2] + ['/source/out/x86_64_virt'] + argv[3:], argv[:-1] + ['--list=other']):
            with self.assertRaises(ValueError): guard.selected_args_command(changed, 'arm64_virt')

    def test_begin_preserves_only_owned_outputs_and_old_witness(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); build = root / 'out/arm64_virt'; build.mkdir(parents=True)
            before = {}
            for name in guard.outputs('arm64_virt') + ['qemu-wallpaper-build-witness.json', 'other/component.o']:
                path = build / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(('unit-only:' + name).encode())
                before[name] = path.read_bytes()
            with patch.object(guard, 'source_check'):
                value = guard.begin(root, 'arm64_virt')
            self.assertEqual((build / 'other/component.o').read_bytes(), before['other/component.o'])
            self.assertEqual(set(value['preserved']), set(before) - {'other/component.o'})
            for name, row in value['preserved'].items():
                self.assertFalse((build / name).exists()); self.assertEqual(Path(row['path']).read_bytes(), before[name])
            self.assertEqual(json.loads((build / 'qemu-wallpaper-build-pending.json').read_text())['phase'], 'prepared')

    def test_synthetic_ELF_header_and_self_reported_inventory_never_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); data = bytearray(64); data[:7] = b'\x7fELF\x02\x01\x01'
            struct.pack_into('<HH', data, 16, 3, 183); path = root / guard.LIBRARY; path.write_bytes(data)
            with self.assertRaises(ValueError): guard.elf_check(path, 'arm64_virt')
            with self.assertRaises(ValueError): guard.check_inventory({'product': 'arm64_virt', 'status': 'pass'}, 'arm64_virt', root)


if __name__ == '__main__': unittest.main()
