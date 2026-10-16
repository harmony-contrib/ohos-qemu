"""Pure Python Contacts witness contracts; constructed inputs are never builds."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import qemu_contacts_build_witness as G


class ContactsWitnessTests(unittest.TestCase):
    def graph(self, source='/source', product='arm64_virt'):
        triple = G.PRODUCTS[product][1]
        cfi = '--sysroot=obj/third_party/musl -flto=thin -fsanitize=cfi -fsanitize-cfi-cross-dso --target=' + triple + '-linux-ohos'
        text = '\n'.join(['defines = -DCONTACTS', 'include_dirs =', 'cflags = ' + cfi,
            'cflags_cc = -std=c++17 -fno-exceptions -fno-rtti', 'root_out_dir = .',
            'output_dir = applications/contacts_data', 'target_output_name = libcontact', 'output_extension = .z.so',
            'solibs =', 'libs = -lc++ -lc']) + '\n'
        text += '\n'.join('build ' + unit + ': cxx ../../' + src for unit, src in G.UNITS.items()) + '\n'
        text += 'build ' + G.LINKED + ' ./' + G.UNSTRIPPED + ': solink ' + ' '.join([*G.UNITS, G.JS_OBJECT, G.ABC_OBJECT]) + '\n'
        text += '  ldflags = ' + cfi + '\n'
        rules = '\n'.join([
            'rule cxx', '  command = /usr/bin/ccache ../../' + G.CLANG + ' ${defines} ${include_dirs} ${cflags} ${cflags_cc} -c ${in} -o ${out}',
            'rule solink', '  command = /usr/bin/env "../../build/toolchain/gcc_solink_wrapper.py" --sofile="${root_out_dir}/lib.unstripped/${output_dir}/${target_output_name}${output_extension}" --output="${output_dir}/${target_output_name}${output_extension}" -- ../../' + G.CLANG + ' -shared ${ldflags} -o "${root_out_dir}/lib.unstripped/${output_dir}/${target_output_name}${output_extension}" @"${output_dir}/${target_output_name}${output_extension}.rsp" -Wl,-soname="${target_output_name}${output_extension}"',
            '  rspfile_content = -Wl,--whole-archive ${in} ${solibs} -Wl,--no-whole-archive ${libs}',
            'rule solink_module', '  command = must_not_select_this_rule']) + '\n'
        build = source + '/out/' + product
        for label, target, command, inputs in [
            ('gen_contact_abc', G.ABC, '/usr/bin/env ../../build/scripts/generate_js_bytecode.py --src-js ' + source + '/' + G.JS + ' --dst-file ' + build + '/' + G.ABC + ' --frontend-tool-path ' + build + '/clang_x64/arkcompiler/ets_frontend --module', ['../../build/scripts/generate_js_bytecode.py', '../../' + G.JS, 'clang_x64/arkcompiler/ets_frontend/es2abc']),
            ('gen_js_obj_contact_js', G.JS_OBJECT, '/usr/bin/env ../../build/scripts/run_objcopy.py --objcopy ' + source + '/prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-objcopy --input ' + source + '/' + G.JS + ' --output ' + build + '/' + G.JS_OBJECT + ' --arch ' + G.PRODUCTS[product][2], ['../../build/scripts/run_objcopy.py', '../../' + G.JS, G.OBJ + '/gen_contact_abc.stamp']),
            ('gen_js_obj_contact_abc', G.ABC_OBJECT, '/usr/bin/env ../../build/scripts/run_objcopy.py --objcopy ' + source + '/prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-objcopy --input ' + build + '/' + G.ABC + ' --output ' + build + '/' + G.ABC_OBJECT + ' --arch ' + G.PRODUCTS[product][2], ['../../build/scripts/run_objcopy.py', G.ABC, G.OBJ + '/gen_contact_abc.stamp'])]:
            rules += 'rule example_' + label + '\n  command = ' + command + '\n  description = ACTION //' + G.BASE + ':' + label + '(//build/toolchain/ohos:ohos_clang_' + G.PRODUCTS[product][2] + ')\n\n'
            rules += 'build ' + target + ': example_' + label + ' | ' + ' '.join(inputs) + '\n\n'
        return text, rules

    def argv(self, product='arm64_virt'):
        return ['./build.sh', '--product-name', product, '--build-target', 'images', '--build-only-load=false', '--fast-rebuild=false']

    def log(self, source='/source', product='arm64_virt'):
        lines = ['[OHOS INFO] [NINJA] [1/999] CXX ' + unit for unit in G.UNITS]
        lines += ['[OHOS INFO] [NINJA] ACTION //' + G.BASE + ':' + label + '(//build/toolchain/ohos:ohos_clang_' + G.PRODUCTS[product][2] + ')' for label in ('gen_contact_abc', 'gen_js_obj_contact_js', 'gen_js_obj_contact_abc')]
        lines += ['[OHOS INFO] [NINJA] ./ets_frontend/es2abc --output ' + source + '/out/' + product + '/' + G.ABC + ' --module ' + source + '/' + G.JS + ' --target-api-sub-version=beta3 | execution_path: ' + source + '/out/' + product + '/clang_x64/arkcompiler']
        lines += ['[OHOS INFO] [NINJA] SOLINK ' + G.LINKED, '[OHOS INFO]  ' + product + ' build success']
        return '\n'.join(lines) + '\n'

    def test_all_three_actual_abi_graph_contracts_without_executing_tools(self):
        for product in G.PRODUCTS:
            selected = G.graph_commands(*self.graph(product=product), '/source', product)
            self.assertEqual(set(selected['commands']), {*G.UNITS, G.ABC, G.JS_OBJECT, G.ABC_OBJECT, G.LINKED})
            G.build_log_check(self.log(product=product), selected, '/source', product)
            G.full_build_argv(self.argv(product), product)

    def test_missing_or_duplicate_native_edges_and_wrong_source_are_rejected(self):
        graph, rules = self.graph(); unit = next(iter(G.UNITS))
        for changed in (graph.replace('build ' + unit + ':', 'build elsewhere.o:'),
                        graph + 'build ' + unit + ': cxx ../../' + G.UNITS[unit],
                        graph.replace('contacts_api.cpp', 'unrelated.cpp'),
                        graph.replace(': solink ' + unit + ' ', ': solink '),
                        graph.replace(G.JS_OBJECT + ' ' + G.ABC_OBJECT, G.ABC_OBJECT),
                        graph.replace(G.ABC_OBJECT + '\n', G.ABC_OBJECT + ' ' + G.ABC_OBJECT + '\n')):
            with self.subTest(changed=changed[-100:]), self.assertRaises(ValueError): G.graph_commands(changed, rules, '/source', 'arm64_virt')

    def test_effective_final_compile_flags_and_unknown_ninja_bindings_fail_closed(self):
        graph, rules = self.graph()
        for flag in ('-fno-sanitize=cfi', '-fno-sanitize=all', '-fno-sanitize=cfi-icall', '-fno-sanitize-cfi-cross-dso', '-fno-lto', '-fexceptions', '-frtti'):
            # Final switches must occur after the existing disabling switches too.
            changed = graph.replace('cflags_cc = -std=c++17 -fno-exceptions -fno-rtti', 'cflags_cc = -std=c++17 -fno-exceptions -fno-rtti ' + flag)
            with self.subTest(flag=flag), self.assertRaises(ValueError): G.graph_commands(changed, rules, '/source', 'arm64_virt')
        G.graph_commands(graph.replace('-fsanitize=cfi ', '-fno-sanitize=cfi -fsanitize=cfi '), rules, '/source', 'arm64_virt')
        with self.assertRaises(ValueError): G.graph_commands(graph, rules.replace('${cflags}', '${unbound}'), '/source', 'arm64_virt')
        with self.assertRaises(ValueError): G.expand('$bad', {'bad': '$bad'})

    def test_link_cfi_and_both_blob_inputs_not_just_compile_flags(self):
        graph, rules = self.graph()
        for changed in (graph.replace('  ldflags = ', '  ldflags = -fno-lto '),
                        graph.replace('  ldflags = ', '  ldflags = -fno-sanitize=all ')):
            # An earlier disable is legitimately re-enabled. Test actual final disables below.
            G.graph_commands(changed, rules, '/source', 'arm64_virt')
        for flag in ('-fno-lto', '-fno-sanitize=cfi', '-fno-sanitize-cfi-cross-dso'):
            changed = graph.rstrip() + ' ' + flag + '\n'
            with self.assertRaises(ValueError): G.graph_commands(changed, rules, '/source', 'arm64_virt')
        for changed in (rules.replace(' -shared ', ' '), rules.replace('@"${output_dir}/${target_output_name}${output_extension}.rsp"', '@other.rsp'), rules.replace('${in} ${solibs}', '${solibs}')):
            with self.assertRaises(ValueError): G.graph_commands(graph, changed, '/source', 'arm64_virt')

    def test_response_flags_and_shell_comments_cannot_hide_protection_overrides(self):
        graph, rules = self.graph()
        for flag in ('-fno-lto', '-fno-sanitize=cfi', '-fno-sanitize-cfi-cross-dso'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                G.graph_commands(graph.replace('libs = -lc++ -lc', 'libs = -lc++ -lc ' + flag), rules, '/source', 'arm64_virt')
        for flag in ('# -flto', ';touch', '&&true', '`true`', '$(true)'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                G.graph_commands(graph.replace('cflags_cc = ', 'cflags_cc = ' + flag + ' '), rules, '/source', 'arm64_virt')
        with self.assertRaises(ValueError):
            G.graph_commands(graph.replace('libs = -lc++ -lc', 'libs = -lc++ -lc @hidden.rsp'), rules, '/source', 'arm64_virt')

    def test_action_uses_current_absolute_inputs_and_complete_dependencies(self):
        graph, rules = self.graph()
        for changed in (rules.replace('--module\n', '--commonjs\n'), rules.replace('/source/', '/old/'),
                        rules.replace(' --arch arm64', ' --arch x86_64'), rules.replace('run_objcopy.py', 'different.py'),
                        rules.replace('clang_x64/arkcompiler/ets_frontend/es2abc\n', '\n'),
                        rules.replace('  command = /usr/bin/env ../../build/scripts/generate_js_bytecode.py', '  command = /usr/bin/env ../../build/scripts/generate_js_bytecode.py --merge-abc')):
            with self.subTest(changed=changed[-60:]), self.assertRaises(ValueError): G.graph_commands(graph, changed, '/source', 'arm64_virt')

    def test_required_full_images_argv_and_single_explicit_boolean_values(self):
        raw = self.argv(); G.full_build_argv(raw, 'arm64_virt')
        for changed in (raw[:-1], raw + ['--fast-rebuild=true'], raw + ['--build-target', 'contact'],
                        [s.replace('images', 'contact') for s in raw], [s.replace('arm64_virt', 'x86_64_virt') for s in raw],
                        [s.replace('--build-only-load=false', '--build-only-load=true') for s in raw], {'argv': raw}):
            with self.assertRaises(ValueError): G.full_build_argv(changed, 'arm64_virt')

    def test_exact_hb_success_after_real_edges_and_real_es2abc_cwd(self):
        selected = G.graph_commands(*self.graph(), '/source', 'arm64_virt'); log = self.log()
        for changed in (log.replace('[OHOS INFO]  arm64_virt build success', 'build success'),
                        log.replace('arm64_virt build success', 'other build success'),
                        log.replace(' build success', ' build success then failed'),
                        log.replace('contacts_api.o\n', 'unrelated.o\n'),
                        log.replace('gen_contact_abc(', 'other('), log.replace(' --module ', ' --commonjs '),
                        log.replace('execution_path: /source/', 'execution_path: /old/'),
                        '[OHOS INFO]  arm64_virt build success\n' + log.replace('[OHOS INFO]  arm64_virt build success\n', ''),
                        log + 'FAILED: later.o\n', log + '[OHOS INFO]  arm64_virt build success\n'):
            with self.subTest(changed=changed[-100:]), self.assertRaises(ValueError): G.build_log_check(changed, selected, '/source', 'arm64_virt')

    def test_begin_moves_exact_18_outputs_plus_old_witness_and_retains_stamps(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary).resolve(); build = source / 'out/arm64_virt'
            gn = source / G.BASE / 'BUILD.gn'; gn.parent.mkdir(parents=True); gn.write_text('constructed fixture only')
            before = {}
            for name in [*G.outputs('arm64_virt'), G.WITNESS, G.OBJ + '/gen_contact_abc.stamp', 'other/native.o']:
                path = build / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(name.encode()); before[name] = path.read_bytes()
            with patch.object(G, 'sources', return_value={'fixture': 'not-a-real-build'}), patch.object(G, 'recipe', return_value={}):
                value = G.begin(source, 'arm64_virt')
            self.assertEqual(len(G.outputs('arm64_virt')), 18)
            self.assertEqual(set(value['preserved']), {*G.outputs('arm64_virt'), G.WITNESS})
            for name in value['preserved']:
                self.assertFalse((build / name).exists()); self.assertEqual(Path(value['preserved'][name]['path']).read_bytes(), before[name])
            self.assertEqual((build / 'other/native.o').read_bytes(), before['other/native.o'])
            self.assertTrue((build / G.OBJ / 'gen_contact_abc.stamp').exists())

    def test_begin_symlink_preflight_never_moves_other_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary).resolve(); build = source / 'out/arm64_virt'
            gn = source / G.BASE / 'BUILD.gn'; gn.parent.mkdir(parents=True); gn.write_text('fixture')
            first = build / G.ABC; first.parent.mkdir(parents=True); first.write_bytes(b'existing')
            (build / G.JS_OBJECT).symlink_to(first)
            with patch.object(G, 'sources', return_value={}), self.assertRaises(ValueError): G.begin(source, 'arm64_virt')
            self.assertEqual(first.read_bytes(), b'existing')

    def test_old_empty_or_future_output_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary).resolve(); first = build / G.ABC; first.parent.mkdir(parents=True); first.write_bytes(b'x')
            for bounds in ((first.stat().st_mtime_ns + 1, first.stat().st_mtime_ns + 10), (1, first.stat().st_mtime_ns - 1)):
                with self.assertRaises(ValueError): G.artifact_rows(build, 'arm64_virt', *bounds)
            first.write_bytes(b'')
            with self.assertRaises(ValueError): G.artifact_rows(build, 'arm64_virt', 1, 2**63)

    def test_source_map_rejects_stale_callback_JS_and_traversal(self):
        values = {**G.PINNED, **{name: 'a' * 64 for name in G.UNITS.values() if name not in G.PINNED}}
        G.source_map_check(values)
        for name in [G.JS, G.BASE + '/src/contacts_napi_utils.cpp', G.BASE + '/src/native_module.cpp']:
            changed = dict(values); changed[name] = '0' * 64
            with self.assertRaises(ValueError): G.source_map_check(changed)
        for name in ('../outside', G.BASE + '/include/../../else.h', '/absolute'):
            changed = dict(values); changed[name] = 'a' * 64
            with self.assertRaises(ValueError): G.source_map_check(changed)

    def test_header_only_ELF_or_self_reported_inventory_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve(); path = directory / 'fake.so'; path.write_bytes(b'ELF')
            with self.assertRaises(ValueError): G.cfi_check(path, 'arm64_virt')
            with self.assertRaises(ValueError): G.check_inventory({'product': 'arm64_virt', 'status': 'pass'}, 'arm64_virt', directory)

    def metadata_fixture(self, directory):
        # Synthetic metadata only. The real ELF/blob parser remains a separate
        # mandatory gate and is mocked only to isolate rejection before it.
        graph, toolchain = self.graph(); selected = G.graph_commands(graph, toolchain, '/source', 'arm64_virt')
        source = {name: ('synthetic source: ' + name).encode() for name in set(G.PINNED) | set(G.UNITS.values())}
        source_hashes = {name: G.sha(data) for name, data in source.items()}
        data = {'graph/contact.ninja': graph.encode(), 'graph/toolchain.ninja': toolchain.encode(),
                'graph/args.gn': b'fixture_only = true\n', 'build-log.txt': self.log().encode(),
                'build-argv.json': json.dumps(self.argv()).encode(),
                'commands.json': json.dumps(selected).encode(), 'link-response.txt': selected['link_response'].encode()}
        data.update({'source/' + name: raw for name, raw in source.items()})
        data.update({'outputs/' + name: ('not an ELF or bytecode: ' + name).encode() for name in G.outputs('arm64_virt')})
        witness = dict(schema_version=1, phase='completed', scope=G.SCOPE, product='arm64_virt', recipe={},
            nonce='a' * 32, source_root='/source', source_sha256=source_hashes, start_ns=10, finished_ns=30,
            build_exit_code=0, commands=selected, artifacts={name: dict(sha256=G.sha(data['outputs/' + name]),
                bytes=len(data['outputs/' + name]), mtime_ns=20) for name in G.outputs('arm64_virt')},
            graphs_sha256={name: G.sha(data['graph/' + name]) for name in ('contact.ninja', 'toolchain.ninja', 'args.gn')},
            build_log=dict(path='/log', sha256=G.sha(data['build-log.txt']), bytes=len(data['build-log.txt']), mtime_ns=20),
            build_argv=dict(path='/argv', sha256=G.sha(data['build-argv.json']), bytes=len(data['build-argv.json']), mtime_ns=15),
            tools={name: {'resolved_source_path': name, 'sha256': 'b' * 64} for name in [G.CLANG,
                'prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-objcopy', 'out/arm64_virt/clang_x64/arkcompiler/ets_frontend/es2abc']},
            payload_identity={'synthetic_metadata_test_only': True}, module_record_and_literal_binding_verified=False,
            public_runtime_execution_verified=False, first_artifact_behavior_gate_passed=False)
        data['witness.json'] = json.dumps(witness).encode()
        for name, raw in data.items():
            path = directory / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        inventory = dict(schema_version=1, scope=G.SCOPE, product='arm64_virt', recipe={}, source_sha256=source_hashes,
            files_sha256={name: G.sha(raw) for name, raw in data.items()}, first_artifact_behavior_gate_passed=False)
        return inventory, witness, {name: source_hashes[name] for name in G.PINNED}

    def test_offline_metadata_rejects_freshness_and_claims_without_original_source_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve(); inventory, witness, pins = self.metadata_fixture(directory)
            def update(changed):
                path = directory / 'witness.json'; path.write_text(json.dumps(changed))
                inventory['files_sha256']['witness.json'] = G.file_sha256(path)
            with patch.object(G, 'PINNED', pins), patch.object(G, 'recipe', return_value={}), patch.object(G, 'payload_check', return_value=witness['payload_identity']) as api:
                G.check_inventory(inventory, 'arm64_virt', directory)
                for change in ('old_output', 'future_output', 'nonzero_build', 'boolean_build', 'false_runtime', 'missing_output', 'stale_log'):
                    changed = json.loads(json.dumps(witness))
                    if change == 'old_output': changed['artifacts'][G.ABC]['mtime_ns'] = 9
                    elif change == 'future_output': changed['artifacts'][G.ABC]['mtime_ns'] = 31
                    elif change == 'nonzero_build': changed['build_exit_code'] = 1
                    elif change == 'boolean_build': changed['build_exit_code'] = False
                    elif change == 'false_runtime': changed['public_runtime_execution_verified'] = True
                    elif change == 'missing_output': del changed['artifacts'][G.JS_OBJECT]
                    elif change == 'stale_log': changed['build_log']['mtime_ns'] = 9
                    update(changed); before = api.call_count
                    with self.subTest(change=change), self.assertRaises(ValueError): G.check_inventory(inventory, 'arm64_virt', directory)
                    self.assertEqual(api.call_count, before)

    def test_offline_raw_bytes_rehash_still_does_not_bypass_graph_and_log_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve(); inventory, witness, pins = self.metadata_fixture(directory)
            with patch.object(G, 'PINNED', pins), patch.object(G, 'recipe', return_value={}), patch.object(G, 'payload_check', return_value=witness['payload_identity']) as api:
                (directory / 'extra.bin').write_bytes(b'extra')
                with self.assertRaises(ValueError): G.check_inventory(inventory, 'arm64_virt', directory)
                (directory / 'extra.bin').unlink()
                path = directory / 'outputs' / G.JS_OBJECT; original = path.read_bytes(); path.write_bytes(b'changed')
                with self.assertRaises(ValueError): G.check_inventory(inventory, 'arm64_virt', directory)
                path.write_bytes(original)
                path = directory / 'graph/contact.ninja'; path.write_text(path.read_text().replace('contacts_api.cpp', 'unrelated.cpp'))
                checksum = G.file_sha256(path); inventory['files_sha256']['graph/contact.ninja'] = checksum
                witness['graphs_sha256']['contact.ninja'] = checksum
                (directory / 'witness.json').write_text(json.dumps(witness))
                inventory['files_sha256']['witness.json'] = G.file_sha256(directory / 'witness.json')
                with self.assertRaises(ValueError): G.check_inventory(inventory, 'arm64_virt', directory)
                api.assert_not_called()

    def test_payload_report_paths_are_stable_when_publishing_private_scratch(self):
        def public_api(**kwargs):
            return {'artifacts': {key: {'path': str(path), 'sha256': 'a' * 64} for key, path in kwargs.items() if key != 'arch'},
                    'module_record_and_literal_binding_verified': False}
        class PublicApi:
            verify_payloads = staticmethod(public_api)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); reports = []
            for name in ('scratch', 'archive'):
                directory = base / name
                for path in ['source/' + G.JS] + ['outputs/' + item for item in [G.ABC, G.JS_OBJECT, G.ABC_OBJECT, G.UNSTRIPPED, G.LINKED, G.staged('arm64_virt')]]:
                    target = directory / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b'not real payload')
                with patch.object(G, 'cfi_check'), patch.object(G, 'payload_api', return_value=PublicApi):
                    reports.append(G.payload_check(directory, 'arm64_virt'))
            self.assertEqual(reports[0], reports[1])

    def test_no_native_GN_Ninja_or_guest_execution_in_tool(self):
        import ast
        tree = ast.parse(Path(G.__file__).read_text())
        self.assertFalse(any(isinstance(n, ast.Import) and any(a.name == 'subprocess' for a in n.names) for n in ast.walk(tree)))
        self.assertNotIn('os.system(', Path(G.__file__).read_text())


if __name__ == '__main__': unittest.main()
