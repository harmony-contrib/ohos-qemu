"""SDK AST / strict result fixtures, never guest or full-gate evidence."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from const_enum_contracts import LEDGER, generate, sha256, validate_inputs
from verify_const_enum_results import verify

RUN = 'a' * 32
HERE = Path(__file__).resolve().parent
TS = os.environ.get('OHOS_AUDIT_TYPESCRIPT',
                    '/Applications/DevEco-Studio.app/Contents/plugins/openharmony/ace-server/node_modules/typescript')


class ConstEnumTests(unittest.TestCase):
    def test_actual_compiler_resolves_ambient_named_arithmetic_and_string_constants(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '@ohos.fixture.d.ts').write_text('''
declare namespace fixture { const enum Mode { ZERO=0, NEXT, MASK=1<<4, VALUE=MASK+2 } }
export default fixture;
export const enum Top { HEX=0x40, NEXT }
export const enum Text { VALUE="real" }
''')
            requested = [{'module': '@ohos.fixture', 'contracts': [{'name': 'Mode'}, {'name': 'Top'}, {'name': 'Text'}]}]
            (root / 'requested.json').write_text(json.dumps(requested))
            script = "const fs=require('fs');const m=require(process.argv[1]);process.stdout.write(JSON.stringify(m.extract(require(process.argv[2]),process.argv[3],JSON.parse(fs.readFileSync(process.argv[4])))));"
            result = subprocess.run(['node', '-e', script, str(HERE / 'extract_const_enum_contracts.cjs'),
                TS, str(root), str(root / 'requested.json')], capture_output=True, text=True, check=True)
            rows = json.loads(result.stdout)
            self.assertEqual([member['value'] for member in rows[0]['members']], [0, 1, 16, 18])
            self.assertEqual([member['value'] for member in rows[1]['members']], [64, 65])
            self.assertEqual(rows[2]['members'][0]['value'], 'real')
            self.assertEqual([row['import_kind'] for row in rows], ['default_namespace', 'named', 'named'])
            (root / '@ohos.fixture.d.ts').write_text('declare namespace fixture { enum Mode { ZERO=0 } }\nexport default fixture;')
            failed = subprocess.run(['node', '-e', script, str(HERE / 'extract_const_enum_contracts.cjs'),
                TS, str(root), str(root / 'requested.json')], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            (root / '@ohos.fixture.d.ts').write_text('declare namespace fixture { const enum Mode { MASK=1<<4, TEXT="real" } }\nexport default fixture;')
            failed = subprocess.run(['node', '-e', script, str(HERE / 'extract_const_enum_contracts.cjs'),
                TS, str(root), str(root / 'requested.json')], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)

    def inputs(self, root):
        declarations = root / 'declarations.d.ts'
        declarations.write_text('/* owned constant verification fixture, not a real SDK */')
        compiler = root / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'
        compiler.parent.mkdir(parents=True)
        compiler.write_text('/* owned SDK identity fixture */')
        rows = json.loads(LEDGER.read_text())['devices']['phone']['arkts11_compiled_constant_enum_contracts']
        contracts = [{'module': row['module'], 'name': contract['name'], 'import_kind': 'named',
                      'members': [{'name': 'ZERO', 'value': 0}], 'sdk_declaration': str(declarations),
                      'sdk_declaration_sha256': sha256(declarations)}
                     for row in rows for contract in row['contracts']]
        page = root / 'Index.ets'
        page.write_text(generate(contracts, RUN))
        return {'role': 'ordinary_app', 'scope': 'compiled_const_enum_contracts_only', 'run_id': RUN,
                'arch': 'arm64', 'sdk': str(root), 'typescript_sha256': sha256(compiler),
                'audit_baseline_sha256': sha256(LEDGER), 'contracts': contracts,
                'generated_source': str(page), 'generated_source_sha256': sha256(page)}

    def test_strict_complete_member_values_nonce_arch_order_and_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs = self.inputs(Path(temporary))
            rows = [{'name': 'const_enum:' + row['module'] + ':' + row['name'] + ':ZERO',
                     'value': 0, 'runId': RUN} for row in inputs['contracts']]
            rows.append({'name': 'summary', 'value': len(rows), 'runId': RUN})
            def text(value):
                return '\n'.join(map(json.dumps, value)) + '\n'
            with patch('const_enum_contracts.expected_contracts', return_value=inputs['contracts']):
                self.assertEqual(verify(text(rows), inputs, RUN, 'arm64')['contract_count'], 16)
                for invalid in (rows[:-1], rows[::-1], rows + [rows[0]]):
                    with self.assertRaises(ValueError):
                        verify(text(invalid), inputs, RUN, 'arm64')
                for key, value in (('value', False), ('value', 1), ('runId', 'b' * 32), ('extra', 'mock')):
                    changed = json.loads(json.dumps(rows))
                    changed[0][key] = value
                    with self.assertRaises(ValueError):
                        verify(text(changed), inputs, RUN, 'arm64')
                with self.assertRaises(ValueError):
                    verify(text(rows), inputs, RUN, 'x86_64')

    def test_declaration_compiler_baseline_and_typed_caller_cannot_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs = self.inputs(Path(temporary))
            with patch('const_enum_contracts.expected_contracts', return_value=inputs['contracts']):
                self.assertEqual(validate_inputs(inputs), inputs['contracts'])
                for key, value in (('audit_baseline_sha256', '0' * 64), ('typescript_sha256', '0' * 64),
                                   ('contracts', inputs['contracts'][:-1]), ('scope', 'full_backend')):
                    changed = dict(inputs, **{key: value})
                    with self.assertRaises(ValueError):
                        validate_inputs(changed)
                page = Path(inputs['generated_source'])
                page.write_text(page.read_text().replace('Contract0.ZERO', '0'))
                inputs['generated_source_sha256'] = sha256(page)
                with self.assertRaises(ValueError):
                    validate_inputs(inputs)

    def test_default_suite_runs_real_typed_caller_before_complete_ledger_gate(self):
        suite = (HERE / 'run_packaged_qemu_suite.py').read_text()
        self.assertIn("'const-enum'", suite)
        self.assertIn("'verify_gap_closure.py'", suite)
        source = (HERE / 'build_hap_probe.py').read_text()
        self.assertIn("contracts = expected_contracts(args.sdk)", source)
        self.assertIn("generate(contracts, challenge)", source)
        # Check the actual permission expression instead of a brittle source
        # substring whose first flag changes when another pure caller is added.
        import ast
        from types import SimpleNamespace
        tree = ast.parse(source)
        expressions = [value for node in ast.walk(tree) if isinstance(node, ast.Dict)
                       for key, value in zip(node.keys, node.values)
                       if isinstance(key, ast.Constant) and key.value == 'requestPermissions'
                       and isinstance(value, ast.IfExp)]
        self.assertEqual(len(expressions), 1)
        flags = {node.attr for node in ast.walk(expressions[0]) if isinstance(node, ast.Attribute)
                 and isinstance(node.value, ast.Name) and node.value.id == 'args'}
        arguments = SimpleNamespace(**{name: name == 'const_enum_only' for name in flags})
        expression = compile(ast.Expression(expressions[0]), 'actual-const-enum-permissions', 'eval')
        self.assertEqual(eval(expression, {'args': arguments, 'worker_only': False,
                                           'dedicated_contract_only': False}), [])


if __name__ == '__main__':
    unittest.main()
