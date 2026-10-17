"""Wallpaper build/provenance guard negatives; no constructed fixture is a build."""
import json
import hashlib
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
        guard.selected_args('theme_service\n    Current value (from the default) = false\n      From //base/theme/wallpaper_mgr/wallpaper.gni:33\n')
        for text in ('theme_service=false', 'theme_service\nCurrent value = true\nDefault value = false',
                     'unrelated\nCurrent value = false', 'theme_service\nCurrent value = 0',
                     'theme_service\n Current value = true\nother_argument\n Current value = false',
                     'theme_service\n Current value = false\ntheme_service\n Current value = false'):
            with self.assertRaises(ValueError): guard.selected_args(text)

    def actual_args(self):
        raw = (Path(__file__).parent / 'fixtures/wallpaper/theme-service-args-phone.txt').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '0feac89cd94a126ab5b9912b4e45282459585c66a1fc617f1417e210bddaab6b')
        return raw

    def test_captured_actual_GN_diagnostics_are_not_parameter_headings(self):
        raw = self.actual_args().decode(); guard.selected_args(raw)
        for changed in (raw.replace('Current value (from the default) = false', 'Current value = true\n    Default value = false'),
                        raw + 'other_argument\n    Current value = false\n',
                        'other_argument\n    Current value = false\n' + raw,
                        'theme_service\n' + raw,
                        raw + '    Current value = true trailing text\n',
                        raw.replace('    Current value (from the default) = false\n', '    Default value = false\n'),
                        'ERROR at //bad/BUILD.gn:1:1: failed\n' + raw, raw + 'unexpected_terminal_text\n',
                        raw.replace('Current value (from the default)', 'Current value FORGED'),
                        raw.replace('      From //base/theme/wallpaper_mgr/wallpaper.gni:33\n', ''),
                        raw.replace('wallpaper.gni:33', 'unrelated.gni:33'),
                        raw + '    Default value = true\n', raw + '    ERROR at //bad: failure\n'):
            with self.subTest(tail=changed[-160:]), self.assertRaises(ValueError): guard.selected_args(changed)

    def test_each_query_binds_its_own_full_stdout_and_identical_actual_graph(self):
        build_raw = self.actual_args()
        package_raw = b'additional_component_diagnostic\n' + build_raw
        def binding(raw):
            return dict(graph_sha256='graph', compile_commands={'actual': 'command'},
                        selected_args_command=['actual', 'GN', 'argv'], selected_args_sha256=hashlib.sha256(raw).hexdigest())
        build, package = binding(build_raw), binding(package_raw)
        self.assertNotEqual(build['selected_args_sha256'], package['selected_args_sha256'])
        guard.query_binding(build, package, build_raw, package_raw)
        for changed in (dict(package, graph_sha256='changed'), dict(package, compile_commands={}),
                        dict(package, selected_args_command=['changed']), dict(package, selected_args_sha256=build['selected_args_sha256']),
                        dict(package, unexpected='field')):
            with self.assertRaises(ValueError): guard.query_binding(build, changed, build_raw, package_raw)
        with self.assertRaises(ValueError): guard.query_binding(build, package, package_raw, package_raw)
        bad = package_raw.replace(b'Current value (from the default) = false', b'Current value = true')
        with self.assertRaises(ValueError): guard.query_binding(build, binding(bad), build_raw, bad)

    def test_query_diagnostics_preserve_success_failure_and_timeout_raw(self):
        raw = self.actual_args().replace(b'root_out_dir=', b'root_out_dir=\r')
        for failure in (None, subprocess.CalledProcessError(1, ['gn'], output=b'actual failed stdout'),
                        subprocess.TimeoutExpired(['gn'], 900, output=b'actual partial stdout')):
            with tempfile.TemporaryDirectory() as temporary:
                diagnostics = Path(temporary) / 'actual-query'
                def invoke(argv, **kwargs):
                    self.assertNotIn('text', kwargs)
                    kwargs['stderr'].write(b'actual stderr')
                    if failure: raise failure
                    return raw
                with patch.object(guard.subprocess, 'check_output', invoke):
                    if failure:
                        with self.assertRaises(type(failure)): guard.args_output(['gn'], Path('/source'), 900, diagnostics)
                    else: self.assertEqual(guard.args_output(['gn'], Path('/source'), 900, diagnostics)[0], raw)
                data = json.loads((diagnostics / 'query.json').read_text())
                expected = failure.output if failure else raw
                if isinstance(expected, str): expected = expected.encode()
                self.assertEqual((diagnostics / 'stdout.txt').read_bytes(), expected)
                self.assertEqual((diagnostics / 'stderr.txt').read_bytes(), b'actual stderr')
                self.assertEqual(data['files_sha256']['stdout.txt'], hashlib.sha256(expected).hexdigest())
                self.assertEqual(data['exit_code'], None if isinstance(failure, subprocess.TimeoutExpired) else 1 if failure else 0)

    def test_offline_query_receipt_requires_actual_argv_exit_and_both_raw_hashes(self):
        raw, errors = self.actual_args(), b'actual stderr\r\n'
        argv = ['/usr/bin/qemu-x86_64-static', '-cpu', 'max', '/source/prebuilts/build-tools/linux-x86/bin/gn',
                'args', '/source/out/arm64_virt', '--list=theme_service']
        graph = dict(selected_args_command=argv)
        receipt = dict(argv=argv, cwd='/source', timeout_seconds=900, exit_code=0,
                       files_sha256={'stdout.txt': hashlib.sha256(raw).hexdigest(), 'stderr.txt': hashlib.sha256(errors).hexdigest()})
        guard.query_receipt(graph, raw, errors, json.dumps(receipt), 'arm64_virt')
        for changed in (dict(receipt, exit_code=False), dict(receipt, exit_code=1), dict(receipt, cwd='/other'),
                        dict(receipt, timeout_seconds=1), dict(receipt, files_sha256={}), dict(receipt, argv=argv[3:])):
            with self.assertRaises(ValueError): guard.query_receipt(graph, raw, errors, json.dumps(changed), 'arm64_virt')
        with self.assertRaises(ValueError): guard.query_receipt(graph, raw, b'changed stderr', json.dumps(receipt), 'arm64_virt')

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
                    if 'args' in argv: return args.encode()
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
