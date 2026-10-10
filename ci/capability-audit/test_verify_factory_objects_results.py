import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from verify_factory_objects_results import CONTRACTS, NAMES, TEMPLATE, verify, verify_inputs
from run_root_probe import digest
from run_normal_hap_probe import PERSONAS, verifier_arguments
from verify_gap_closure import behavior_results

RUN = '0123456789abcdef0123456789abcdef'
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False,
                                         'uid': 20010001}})


def observations():
    rows = []
    for name in NAMES:
        row = {'name': name, 'values': [], 'text': '', 'tasks': [], 'threads': [], 'error': '', 'runId': RUN}
        if name.startswith('configuration.'):
            row.update(values=[1, 0, 160, 1, 0, 0], text='en-Latn-US')
        elif name.startswith('capability.'):
            row['values'] = [0, 160]
        elif name == 'summary':
            row['values'] = [14, 0]
        else:
            generation = int(name[-1])
            ids = [100 + generation * 4 + index for index in range(4)]
            row['values'] = ids
            if '.live.' in name:
                row['tasks'] = [{'taskId': value, 'name': 'factory-' + str(generation) + '-' + str(index),
                                 'state': 2 if index == 0 else 1, 'duration': 15 if index == 0 else 0}
                                for index, value in enumerate(ids)]
                row['threads'] = [{'tid': 30, 'priority': 1, 'taskIds': [ids[0]]}]
            elif '.complete.' in name:
                row['values'] = [(int(RUN[:4], 16) + generation * 8 + index + 32640) & 0xffff
                                 for index in range(4)]
            else:
                row['threads'] = [{'tid': 30, 'priority': 1, 'taskIds': []}]
        rows.append(row)
    return rows


def serialize(rows):
    return '\n'.join(map(json.dumps, rows))


def input_fixture(root):
    page = root / 'Index.ets'
    page.write_text(TEMPLATE.read_text().replace('__FACTORY_RUN_ID__', RUN))
    declarations = {}
    for module, contracts in CONTRACTS.items():
        declaration = root / (module + '.d.ts')
        declaration.write_text('\n'.join('class ' + name + ' { field: number; }' for name in contracts))
        declarations[declaration.name] = {'path': str(declaration), 'sha256': digest(declaration)}
    return {'run_id': RUN, 'arch': 'arm64', 'role': 'ordinary_app', 'request_permissions': [],
            'scope': 'five_real_factory_returned_types_only', 'template_sha256': digest(TEMPLATE),
            'generated_source': str(page), 'generated_source_sha256': digest(page),
            'sdk_declarations': declarations}


class FactoryObjectsTests(unittest.TestCase):
    def test_complete_actual_shape_and_two_profiles(self):
        rows = observations()
        self.assertEqual(verify(serialize(rows), RUN, IDENTITY), rows)
        for row in rows:
            if row['name'].startswith('configuration.'):
                row['values'][1] = 7
            elif row['name'].startswith('capability.'):
                row['values'][0] = 7
        self.assertEqual(verify(serialize(rows), RUN, IDENTITY), rows)

    def test_order_nonce_identity_summary_and_errors_fail_closed(self):
        bad = []
        for field, value in (('runId', '0' * 32), ('error', 'native failure'), ('extra', True)):
            rows = observations(); rows[0][field] = value; bad.append(rows)
        rows = observations(); rows[-1]['values'] = [14, 1]; bad.append(rows)
        bad += [observations()[1:], observations() + [observations()[0]], observations()[::-1]]
        for rows in bad:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                verify(serialize(rows), RUN, IDENTITY)
        with self.assertRaises(ValueError):
            verify(serialize(observations()), RUN, IDENTITY.replace('normal', 'system_basic'))

    def test_all_resource_fields_async_and_isolation_are_required(self):
        for index in range(8):
            rows = observations(); rows[index]['values'][0] = 99
            with self.subTest(index=index), self.assertRaises(ValueError):
                verify(serialize(rows), RUN, IDENTITY)
        for value in (True, float('nan'), float('inf'), -1, 1.25):
            rows = observations(); rows[0]['values'][4] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                verify(serialize(rows), RUN, IDENTITY)
        rows = observations(); rows[6]['text'] = 'qemu-factory-isolation'
        with self.assertRaises(ValueError):
            verify(serialize(rows), RUN, IDENTITY)

    def test_live_ids_names_threads_results_and_cleanup_are_required(self):
        mutations = [
            lambda rows: rows[8].update(values=[100] * 4),
            lambda rows: rows[8]['tasks'].pop(),
            lambda rows: rows[8]['tasks'][0].update(name='fake'),
            lambda rows: rows[8]['tasks'][0].update(state=1),
            lambda rows: rows[8]['tasks'][0].update(duration=-1),
            lambda rows: rows[8].update(threads=[]),
            lambda rows: rows[8]['threads'][0].update(taskIds=[999]),
            lambda rows: rows[8]['threads'][0].update(tid=0),
            lambda rows: rows[8]['threads'][0].update(priority=9),
            lambda rows: rows[9].update(values=[0] * 4),
            lambda rows: rows[10].update(tasks=copy.deepcopy(rows[8]['tasks'])),
            lambda rows: rows[10]['threads'][0].update(taskIds=[100]),
            lambda rows: rows[11]['tasks'][0].update(state=4),
        ]
        for change in mutations:
            rows = observations(); change(rows)
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify(serialize(rows), RUN, IDENTITY)

    def test_inputs_bind_current_typed_source_sdk_and_no_constructor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = input_fixture(root)
            verify_inputs(inputs, RUN, 'arm64')
            for field, value in (('request_permissions', ['ohos.permission.INTERNET']),
                                 ('template_sha256', '0' * 64), ('generated_source_sha256', '0' * 64)):
                bad = copy.deepcopy(inputs); bad[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    verify_inputs(bad, RUN, 'arm64')
            declaration = root / '@ohos.taskpool.d.ts'
            declaration.write_text(declaration.read_text().replace('field: number;', 'constructor();'))
            inputs['sdk_declarations'][declaration.name]['sha256'] = digest(declaration)
            with self.assertRaises(ValueError):
                verify_inputs(inputs, RUN, 'arm64')

    def test_source_uses_real_factories_without_runtime_export_shims(self):
        page = TEMPLATE.read_text()
        for contract in ('resourceManager.Configuration', 'resourceManager.DeviceCapability',
                         'taskpool.TaskInfo', 'taskpool.ThreadInfo', 'taskpool.TaskPoolInfo'):
            self.assertIn(contract, page)
        for call in ('getConfigurationSync()', 'getDeviceCapabilitySync()', 'getConfiguration()',
                     'getDeviceCapability()', 'getTaskPoolInfo()', 'taskpool.execute(', 'Promise.all(pending)'):
            self.assertIn(call, page)
        for bad in ('@ts-ignore', 'napi', 'requireNapi', 'new taskpool.TaskInfo',
                    'new resourceManager.Configuration'):
            self.assertNotIn(bad, page)
        self.assertEqual(sum(map(len, CONTRACTS.values())), 5)

    def test_actual_builder_permissions_and_default_runner_are_wired(self):
        self.assertEqual(PERSONAS['factory-objects'][0], '--factory-objects-only')
        arguments = verifier_arguments('factory-objects', Path('archive'), Path('raw'), Path('identity'),
                                       RUN, 'arm64', Path('output'))
        for argument in ('--arch', '--run-id', '--application-identity'):
            self.assertIn(argument, arguments)
        self.assertIn("'factory-objects'", Path(__file__).with_name('run_packaged_qemu_suite.py').read_text())
        tree = ast.parse(Path(__file__).with_name('build_hap_probe.py').read_text())
        expressions = [value for node in ast.walk(tree) if isinstance(node, ast.Dict)
                       for key, value in zip(node.keys, node.values)
                       if isinstance(key, ast.Constant) and key.value == 'requestPermissions'
                       and isinstance(value, ast.IfExp)]
        self.assertEqual(len(expressions), 1)
        flags = ('camera_only', 'const_enum_only', 'arkts_exports_only', 'matrix4_only', 'factory_objects_only')
        args = SimpleNamespace(router_observer_only=False, network_accounting_only=False, wifi_scan_only=False,
                               **{flag: flag == 'factory_objects_only' for flag in flags})
        expression = compile(ast.Expression(expressions[0]), 'actual-builder-permissions', 'eval')
        self.assertEqual(eval(expression, {'args': args, 'worker_only': False}), [])

    def test_closure_only_five_factory_contracts_same_archive_boot_and_full_actual_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = input_fixture(root)
            work = root / 'factory-objects'; work.mkdir()
            raw, identity, inputs, result = (work / name for name in
                ('results.log', 'application-identity.json', 'inputs.json', 'verified.json'))
            raw.write_text(serialize(observations())); identity.write_text(IDENTITY)
            inputs.write_text(json.dumps(document))
            result.write_text(json.dumps(dict(status='pass', scope='five_real_factory_returned_types_only',
                results=observations(), run_id=RUN, arch='arm64', archive_sha256='c' * 64,
                inputs_sha256=digest(inputs), results_sha256=digest(raw),
                application_identity_sha256=digest(identity))))
            evidence = dict(status='pass', persona='factory-objects', boot_id='fixture-not-a-boot',
                archive_sha256='c' * 64, run_id=RUN, arch='arm64', result=str(result),
                result_sha256=digest(result), compiled_contract_inputs=str(inputs),
                compiled_contract_inputs_sha256=digest(inputs), raw_results_sha256=digest(raw),
                ordinary_identity_sha256=digest(identity))
            outer = work / 'evidence.json'; outer.write_text(json.dumps(evidence))
            closed = behavior_results(root, 'fixture-not-a-boot', 'c' * 64)
            self.assertEqual(set(closed), {'arkts_export:' + module + ':' + name
                for module, names in CONTRACTS.items() for name in names})
            self.assertTrue(all(row['resolution'] == 'factory_return_contract_verified_NOT_runtime_constructor'
                                for row in closed.values()))
            self.assertEqual(behavior_results(root, 'wrong-boot', 'c' * 64), {})
            self.assertEqual(behavior_results(root, 'fixture-not-a-boot', 'd' * 64), {})
            changed = observations(); changed[8]['tasks'][0]['taskId'] = 12345
            raw.write_text(serialize(changed)); evidence['raw_results_sha256'] = digest(raw)
            outer.write_text(json.dumps(evidence))
            with self.assertRaises(ValueError):
                behavior_results(root, 'fixture-not-a-boot', 'c' * 64)


if __name__ == '__main__':
    unittest.main()
