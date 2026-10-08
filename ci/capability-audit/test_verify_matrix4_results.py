"""Synthetic verifier/wiring fixtures, not guest Matrix4 success."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from run_normal_hap_probe import PERSONAS, verifier_arguments
from run_root_probe import digest
from verify_gap_closure import behavior_results
from verify_matrix4_results import EXPECTED, TEMPLATE, verify, verify_inputs

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {'uid': 20010023, 'appPrivilegeLevel': 'normal', 'isSystemApp': False}})


def rows():
    return [dict(name=name, values=values[:], error='', runId=RUN) for name, values in EXPECTED.items()]


def render(values):
    return '\n'.join(map(json.dumps, values))


class Matrix4VerifierTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def inputs(self):
        page = self.root / 'Index.ets'
        page.write_text(TEMPLATE.read_text().replace('__MATRIX_RUN_ID__', RUN))
        declaration = self.root / '@ohos.matrix4.d.ts'
        declaration.write_text('synthetic SDK fixture, NOT real compilation')
        return dict(run_id=RUN, arch='arm64', role='ordinary_app', scope='real_typed_matrix4_helpers_only',
                    request_permissions=[], template_sha256=digest(TEMPLATE), generated_source=str(page),
                    generated_source_sha256=digest(page), sdk_declaration=str(declaration),
                    sdk_declaration_sha256=digest(declaration))

    def test_complete_arithmetic_and_float_roundoff_fixture_only(self):
        self.assertEqual(len(verify(render(rows()), RUN, IDENTITY)), 17)
        changed = rows()
        changed[6]['values'][0] = -4.371138828673793e-8
        verify(render(changed), RUN, IDENTITY)

    def test_all_values_and_exact_boundary_count_flags_matter(self):
        for index, row in enumerate(rows()):
            for position in range(len(row['values'])):
                for bad in (row['values'][position] + 1, True, '0', float('nan'), float('inf')):
                    changed = rows()
                    changed[index]['values'][position] = bad
                    with self.subTest(index=index, position=position, bad=bad), self.assertRaises(ValueError):
                        verify(render(changed), RUN, IDENTITY)
        for name, position in (('summary', 0), ('summary', 1), ('repeat.isolation', 0),
                               ('root.boundary.missing', 0), ('root.boundary.type', 0), ('root.boundary.point', 0)):
            changed = rows()
            next(row for row in changed if row['name'] == name)['values'][position] += 0.00001
            with self.assertRaises(ValueError):
                verify(render(changed), RUN, IDENTITY)

    def test_stale_missing_extra_reordered_failure_or_wrong_persona_is_rejected(self):
        for changed in (rows()[:-1], rows() * 2, list(reversed(rows())), [None] * 17):
            with self.assertRaises(ValueError):
                verify(render(changed), RUN, IDENTITY)
        for index in range(17):
            for key, value in (('runId', 'b' * 32), ('error', 'real exception'), ('values', [])):
                changed = rows()
                changed[index][key] = value
                with self.assertRaises(ValueError):
                    verify(render(changed), RUN, IDENTITY)
        for key, value in (('uid', 10001), ('isSystemApp', True), ('appPrivilegeLevel', 'system_basic')):
            identity = json.loads(IDENTITY)
            identity['applicationInfo'][key] = value
            with self.assertRaises(ValueError):
                verify(render(rows()), RUN, json.dumps(identity))

    def test_current_page_sdk_and_no_permission_contract_are_bound(self):
        document = self.inputs()
        verify_inputs(document, RUN, 'arm64')
        for key, value in (('arch', 'x86_64'), ('run_id', 'b' * 32), ('role', 'system'),
                           ('scope', 'all_ArkUI'), ('request_permissions', ['new permission']),
                           ('template_sha256', '0' * 64), ('sdk_declaration_sha256', '0' * 64)):
            with self.assertRaises(ValueError):
                verify_inputs(dict(document, **{key: value}), RUN, 'arm64')
        page = Path(document['generated_source'])
        page.write_text(page.read_text() + '\n// changed fixture\n')
        document['generated_source_sha256'] = digest(page)
        with self.assertRaises(ValueError):
            verify_inputs(document, RUN, 'arm64')

    def test_default_suite_preserves_typed_calls_not_a_native_fake_or_compiler_bypass(self):
        self.assertEqual(PERSONAS['matrix4'][0], '--matrix4-only')
        arguments = verifier_arguments('matrix4', Path('archive'), Path('raw'), Path('identity'),
                                       RUN, 'arm64', Path('result'))
        for field in ('--arch', '--run-id', '--application-identity'):
            self.assertIn(field, arguments)
        self.assertIn("'matrix4'", Path(__file__).with_name('run_packaged_qemu_suite.py').read_text())
        source = TEMPLATE.read_text()
        for method in ('copy', 'combine', 'invert', 'translate', 'scale', 'rotate', 'transformPoint'):
            self.assertIn('matrix4.' + method + '(', source)
        for forbidden in ('requireNapi', 'libmatrix', '// @ts-ignore', 'matrix4 as object'):
            self.assertNotIn(forbidden, source)

    def test_real_builder_permission_expression_remains_empty_for_pure_callers(self):
        tree = ast.parse(Path(__file__).with_name('build_hap_probe.py').read_text())
        expressions = [value for node in ast.walk(tree) if isinstance(node, ast.Dict)
                       for key, value in zip(node.keys, node.values)
                       if isinstance(key, ast.Constant) and key.value == 'requestPermissions'
                       and isinstance(value, ast.IfExp)]
        self.assertEqual(len(expressions), 1)
        expression = compile(ast.Expression(expressions[0]), 'actual-builder-permissions', 'eval')
        flags = ('camera_only', 'const_enum_only', 'arkts_exports_only', 'matrix4_only',
                 'factory_objects_only', 'web_factory_only', 'contact_sync_mode_only', 'runtime_enum_only')
        for name in (*flags[1:], 'worker_only'):
            args = SimpleNamespace(**{flag: flag == name for flag in flags})
            self.assertEqual(eval(expression, {'args': args, 'worker_only': name == 'worker_only'}), [])

    def test_registered_closure_is_only_seven_helpers_bound_to_new_archive_boot(self):
        document = self.inputs()
        work = self.root / 'matrix4'
        work.mkdir()
        raw, identity, inputs, result = (work / name for name in
            ('results.log', 'application-identity.json', 'inputs.json', 'verified.json'))
        raw.write_text(render(rows()))
        identity.write_text(IDENTITY)
        inputs.write_text(json.dumps(document))
        result.write_text(json.dumps(dict(status='pass', results=rows(), run_id=RUN, arch='arm64',
            archive_sha256='c' * 64, inputs_sha256=digest(inputs), results_sha256=digest(raw),
            application_identity_sha256=digest(identity))))
        evidence = dict(status='pass', persona='matrix4', boot_id='fixture-not-a-boot', archive_sha256='c' * 64,
            run_id=RUN, arch='arm64', result=str(result), result_sha256=digest(result),
            compiled_contract_inputs=str(inputs), compiled_contract_inputs_sha256=digest(inputs),
            raw_results_sha256=digest(raw), ordinary_identity_sha256=digest(identity))
        outer = work / 'evidence.json'
        outer.write_text(json.dumps(evidence))
        closed = behavior_results(self.root, 'fixture-not-a-boot', 'c' * 64)
        self.assertEqual(set(closed), {'arkts_export:@ohos.matrix4:' + name for name in
            ('combine', 'copy', 'invert', 'rotate', 'scale', 'transformPoint', 'translate')})
        self.assertEqual(behavior_results(self.root, 'wrong-boot', 'c' * 64), {})
        self.assertEqual(behavior_results(self.root, 'fixture-not-a-boot', 'd' * 64), {})
        changed = rows()
        changed[0]['values'][0] = 100
        raw.write_text(render(changed))
        evidence['raw_results_sha256'] = digest(raw)
        outer.write_text(json.dumps(evidence))
        with self.assertRaises(ValueError):
            behavior_results(self.root, 'fixture-not-a-boot', 'c' * 64)


if __name__ == '__main__':
    unittest.main()
