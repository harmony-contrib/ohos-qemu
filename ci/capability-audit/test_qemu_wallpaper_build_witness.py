"""Wallpaper build/provenance guard negatives; no constructed fixture is a build."""
import json
import os
import subprocess
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
        guard.selected_args_command(['/usr/bin/qemu-x86_64-static', '-cpu', 'max'] + argv, 'arm64_virt')
        for changed in (None, ['/usr/bin/qemu-x86_64-static'] + argv,
                        ['/usr/bin/qemu-x86_64-static', '-cpu', 'host'] + argv, argv + ['--list=unrelated'], ['untrusted'] + argv[1:],
                        argv[:2] + ['/other/out/arm64_virt'] + argv[3:],
                        argv[:2] + ['/source/out/x86_64_virt'] + argv[3:], argv[:-1] + ['--list=other']):
            with self.assertRaises(ValueError): guard.selected_args_command(changed, 'arm64_virt')

    def test_explicit_software_CPU_and_finite_budget_match_host_GN_policy(self):
        source = Path('/source')
        with patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '0'}):
            native, budget = guard.gn_query_command(source, 'arm64_virt')
            self.assertEqual(native[0], '/source/prebuilts/build-tools/linux-x86/bin/gn')
            self.assertEqual(budget, 180)
        with patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '1'}):
            emulated, budget = guard.gn_query_command(source, 'arm64_virt')
            self.assertEqual(emulated[:3], ['/usr/bin/qemu-x86_64-static', '-cpu', 'max'])
            self.assertEqual(emulated[3:], native); self.assertEqual(budget, 900)
        with patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '2'}), self.assertRaises(ValueError):
            guard.gn_query_command(source, 'arm64_virt')

    def test_timeout_is_fatal_and_never_reuses_a_selected_args_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary).resolve(); build = source / 'out/arm64_virt'
            graph = build / guard.GRAPH; graph.parent.mkdir(parents=True); graph.write_text(self.graph())
            (build / 'theme-service-args.txt').write_text('theme_service\n Current value = false\n')
            calls = []
            def query(argv, **kwargs):
                calls.append((argv, kwargs))
                if 'args' in argv: raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
                unit = argv[-1]
                return self.command().replace(guard.UNITS[0], unit).replace('wallpaper_service.cpp', Path(unit).stem + '.cpp') + '\n'
            with patch.object(guard, 'source_check'), patch.object(guard.subprocess, 'check_output', query), patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '1'}):
                with self.assertRaises(subprocess.TimeoutExpired): guard.query(source, 'arm64_virt')
            self.assertEqual(calls[-1][0][:3], ['/usr/bin/qemu-x86_64-static', '-cpu', 'max'])
            self.assertEqual(calls[-1][1]['timeout'], 900)
            self.assertEqual(sum('args' in argv for argv, _ in calls), 1)

    def test_longer_query_budget_cannot_accept_true_or_default_only_false(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary).resolve(); graph = source / 'out/arm64_virt' / guard.GRAPH
            graph.parent.mkdir(parents=True); graph.write_text(self.graph())
            for args in ('theme_service\n Current value = true\n Default value = false\n', 'theme_service = false\n'):
                def query(argv, **kwargs):
                    if 'args' in argv: return args
                    unit = argv[-1]
                    return self.command().replace(guard.UNITS[0], unit).replace('wallpaper_service.cpp', Path(unit).stem + '.cpp') + '\n'
                with patch.object(guard, 'source_check'), patch.object(guard.subprocess, 'check_output', query), patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '1'}):
                    with self.subTest(args=args), self.assertRaises(ValueError): guard.query(source, 'arm64_virt')

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
