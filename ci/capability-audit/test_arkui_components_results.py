"""Synthetic rejection fixtures only; never real guest/factory/paint evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw

from arkui_components_contract import CONTRACTS, SCOPE, ability_source, inputs, source
from arkui_components_ui import BUNDLE, IDS, exercise, verify_actions
from guest_ui import select_node
from run_root_probe import digest
import verify_arkui_components_results as verifier

NONCE = 'ad9e3b2cbce840118f9149e6af10cdae'
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal',
    'isSystemApp': False, 'uid': 20010001}})


def fixture():
    rows = []
    def add(name, phase, values=None):
        rows.append(dict(runId=NONCE, name=name, phase=phase, chained=True, values=values or [], error=''))
    add('ready', 0); add('ready.row', 1)
    for name in ('arc-list', 'arc-item', 'arc-bar', 'dynamic'): add('modifier.' + name, 1)
    add('arc.index', 1, [0, 2, 0])
    add('scroll.request', 1); add('arc.index', 1, [5, 7, 7])
    add('child.clicked', 1, [1, 41, 42]); add('switch.column', 2, [1])
    add('child.clicked', 2, [2, 41, 42])
    return rows


def text(rows): return ''.join(json.dumps(row) + '\n' for row in rows)


def node(identifier, rect, label=''):
    x, y, w, h = rect
    return dict(attributes=dict(id=identifier, bundleName=BUNDLE, text=label, visible='true',
        enabled='true', clickable='true', bounds=f'[{x},{y}][{x+w},{y+h}]'), children=[])


def evidence(root):
    root.mkdir(parents=True)
    value = dict(run_id=NONCE, scope='actual_Arc_scroll_and_dynamic_row_column_UI_NOT_full_gate',
                 first_artifact_behavior_gate_passed=False, captures=[], attempts=[], clicks=[])
    controls = [('components-start', 'components-start-real-factories'),
                ('components-scroll', 'components-real-scroll-to-last'),
                ('components-child-a', 'components-row-child-click'),
                ('components-switch', 'components-real-algorithm-switch'),
                ('components-child-a', 'components-column-preserved-child-click')]
    for index, (identifier, label) in enumerate(controls):
        layout = node(identifier, [20, 20, 200, 30])
        path = root / f'click-{index}.json'; path.write_text(json.dumps(layout))
        value['clicks'].append(dict(identifier=identifier, label=label, layout=str(path),
            layout_sha256=digest(path), selected_node=select_node(layout, BUNDLE, identifier=identifier)))
    for index, (phase, counter, end) in enumerate(((1, 0, 7), (1, 1, 10), (2, 1, 11), (2, 2, 12))):
        rects = dict(parent=[20, 300, 260, 150], a=[20, 300, 100, 50],
            b=[120, 300, 100, 50] if phase == 1 else [20, 350, 100, 50],
            list=[20, 50, 220, 180], bar=[260, 50, 24, 180], item=[30, 70, 150, 20])
        ids = dict(IDS, item='components-item-' + ('0' if counter == 0 else '7'))
        labels = dict(a=NONCE + ' child A ' + str(counter), b=NONCE + ' child B',
                      item=NONCE + ' item ' + ('0' if counter == 0 else '7'))
        layout = dict(attributes={}, children=[node(ids[key], rect, labels.get(key, '')) for key, rect in rects.items()])
        path = root / f'capture-{index}.json'; path.write_text(json.dumps(layout))
        nodes = {key: select_node(layout, BUNDLE, identifier=identifier) for key, identifier in ids.items()}
        screen = root / f'capture-{index}.png'
        image = Image.new('RGB', (800, 600), (16, 16, 16)); draw = ImageDraw.Draw(image)
        for key, color in (('a', '#b03020'), ('b', '#20a030'), ('item', '#306020')):
            x, y, w, h = rects[key]; draw.rectangle((x, y, x+w-1, y+h-1), fill=color)
        draw.rectangle((262, 60, 266, 100), fill='#ffffff'); image.save(screen)
        native = root / f'native-{index}.log'; native.write_text(text(fixture()[:end]))
        row = dict(phase=phase, counter=counter, status='painted', nodes=nodes)
        for key, file in (('layout', path), ('screenshot', screen), ('native', native)):
            row[key] = str(file); row[key + '_sha256'] = digest(file)
        value['captures'].append(row); value['attempts'].append(row)
    return value


def project_inputs(root):
    project, sdk = root / 'project', root / 'sdk'
    plugin = root / 'tools/hvigor-ohos-plugin'; plugin.mkdir(parents=True)
    (plugin / 'package.json').write_text(json.dumps({'name': '@ohos/hvigor-ohos-plugin', 'version': 'synthetic'}))
    files = {'entry/src/main/ets/pages/Index.ets': source(NONCE),
        'entry/src/main/ets/entryability/EntryAbility.ets': ability_source(NONCE),
        'entry/src/main/module.json5': json.dumps({'module': {'requestPermissions': [], 'deviceTypes': ['default']}}),
        'entry/src/main/resources/base/profile/main_pages.json': json.dumps({'src': ['pages/Index']}),
        'build-profile.json5': json.dumps({'app': {'products': [dict(name='default', compileSdkVersion='26.0.0',
            targetSdkVersion='26.0.0', compatibleSdkVersion='26.0.0', runtimeOS='OpenHarmony')]}}),
        'entry/build-profile.json5': json.dumps({'apiType': 'stageMode'}),
        'hvigorfile.ts': f"import {{ appTasks }} from '{plugin}';\nexport default {{ system: appTasks, plugins: [] }};\n",
        'entry/hvigorfile.ts': f"import {{ hapTasks }} from '{plugin}';\nexport default {{ system: hapTasks, plugins: [] }};\n",
        'hvigor/hvigor-config.json5': json.dumps(dict(modelVersion='6.0.0', dependencies={},
            execution=dict(daemon=False, parallel=False), logging=dict(level='info')))}
    for relative, content in files.items():
        path = project / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
    declarations = {'@ohos.arkui.ArcList.d.ts': ('ArcList', 'ArcListItem'),
        '@ohos.arkui.ArcScrollBar.d.ts': ('ArcScrollBar',),
        '@ohos.arkui.components.ArkDynamicLayout.d.ts': ('DynamicLayout',)}
    for relative, names in declarations.items():
        path = sdk / 'ets/api' / relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(f'export declare class {name}Attribute extends CommonMethod<{name}Attribute> {{}}\n'
                               f'export declare const {name}Instance: {name}Attribute;\n' for name in names))
    for relative in ('ets/api/arkui/LayoutAlgorithm.d.ts', 'ets/component/common.d.ts'):
        path = sdk / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('// synthetic SDK fixture')
    return inputs(project, sdk, 'arm64', NONCE)


class ArkuiComponentTests(unittest.TestCase):
    def test_real_constructor_failure_is_observable_and_ability_is_input_bound(self):
        page = source(NONCE)
        self.assertIn('LayoutAlgorithm | undefined = undefined', page)
        self.assertIn('@ComponentV2', page)
        self.assertIn('@Local private algorithm:', page)
        self.assertNotIn('@State private algorithm:', page)
        self.assertIn('this.algorithm = new RowLayoutAlgorithm();', page)
        self.assertIn("Capture.record('failed', false, [], String(error))", page)
        self.assertNotIn('as LayoutAlgorithm', page)
        with tempfile.TemporaryDirectory() as directory:
            value = project_inputs(Path(directory))
            self.assertIn('ability', value['generated_sha256'])
            ability = Path(value['project']) / 'entry/src/main/ets/entryability/EntryAbility.ets'
            ability.write_text(ability.read_text().replace('loadContent.callback', 'fake.success'))
            with self.assertRaises(ValueError):
                inputs(value['project'], value['sdk'], 'arm64', NONCE)

    def test_typed_factory_lifecycle_fixture_is_narrow_not_global_constructor_aliases(self):
        result = verifier.verify(text(fixture()), NONCE, IDENTITY)
        self.assertEqual(result['closed'], CONTRACTS)
        self.assertEqual(result['typed_native_factories'], 4)
        self.assertIn('NOT_constructor_shims', result['resolution'])
        self.assertIn('standalone_global_Instance', result['not_claimed'])

    def test_native_callback_chaining_phase_indices_state_ids_and_identity_fail_closed(self):
        for index, field, value in ((2, 'chained', False), (2, 'name', 'modifier.fake'),
            (8, 'values', [7, 7, 8]), (8, 'phase', 2), (9, 'values', [1, 0, 42]),
            (11, 'values', [2, 43, 42]), (11, 'values', [1, 41, 42]),
            (11, 'runId', '0'*32), (11, 'error', 'backend unavailable')):
            rows = fixture(); rows[index][field] = value
            with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                verifier.verify(text(rows), NONCE, IDENTITY)
        for rows in (fixture()[1:], fixture()[:-1], [row for row in fixture() if row['name'] != 'modifier.arc-bar']):
            with self.assertRaises(ValueError): verifier.verify(text(rows), NONCE, IDENTITY)
        identity = json.loads(IDENTITY); identity['applicationInfo']['isSystemApp'] = True
        with self.assertRaises(ValueError): verifier.verify(text(fixture()), NONCE, json.dumps(identity))

    def test_actual_ui_capture_geometry_paint_and_raw_prefixes_are_independently_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            actions = evidence(Path(directory) / 'ui'); raw = text(fixture())
            self.assertEqual(verify_actions(actions, NONCE, raw)['actual_compositor_captures'], 4)
            for key in ('layout', 'screenshot', 'native'):
                path = Path(actions['captures'][0][key]); original = path.read_bytes()
                path.write_bytes(original + b' changed')
                with self.subTest(key=key), self.assertRaises(ValueError): verify_actions(actions, NONCE, raw)
                path.write_bytes(original)
            mutations = []
            changed = copy.deepcopy(actions); changed['captures'][2]['nodes']['b']['rect'][1] = 300; mutations.append(changed)
            changed = copy.deepcopy(actions); changed['captures'].reverse(); mutations.append(changed)
            changed = copy.deepcopy(actions); changed['clicks'][1]['identifier'] = 'components-start'; mutations.append(changed)
            changed = copy.deepcopy(actions); changed['captures'][0]['native'] = actions['captures'][3]['native']
            changed['captures'][0]['native_sha256'] = actions['captures'][3]['native_sha256']; mutations.append(changed)
            for changed in mutations:
                with self.assertRaises(ValueError): verify_actions(changed, NONCE, raw)
            screen = Path(actions['captures'][0]['screenshot'])
            Image.new('RGB', (800, 600), '#101010').save(screen)
            actions['captures'][0]['screenshot_sha256'] = digest(screen)
            with self.assertRaises(ValueError): verify_actions(actions, NONCE, raw)

    def test_failed_real_caller_preserves_partial_ui_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'actions.json'
            class UI: output = Path(directory)
            row = fixture()[0]; row['error'] = 'synthetic native failure'
            with self.assertRaises(ValueError): exercise(UI(), lambda: text([row]), NONCE, 1, path)
            self.assertEqual(json.loads(path.read_text())['captures'], [])

    def test_terminal_constructor_failure_after_real_start_does_not_wait_for_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'actions.json'
            layout = node('components-start', [20, 20, 150, 30])
            click_path = root / 'actual-fixture-click.json'
            click_path.write_text(json.dumps(layout))
            class UI:
                output = root
                def click(self, bundle, **kwargs):
                    return dict(layout=str(click_path), selected_node=select_node(
                        layout, BUNDLE, identifier='components-start', clickable=True))
                def layout(self, **kwargs):
                    raise AssertionError('terminal native failure must not poll geometry')
            failed = dict(fixture()[0], name='failed', chained=False, error='synthetic actual-constructor failure')
            observations = iter((text(fixture()[:1]), text([fixture()[0], failed])))
            with self.assertRaisesRegex(ValueError, 'factory/caller failed: layout'):
                exercise(UI(), lambda: next(observations), NONCE, 1, path)
            actions = json.loads(path.read_text())
            self.assertEqual(len(actions['clicks']), 1)
            self.assertEqual(actions['captures'], [])
        with tempfile.TemporaryDirectory() as directory:
            class UI: output = Path(directory)
            with self.assertRaises(ValueError):
                exercise(UI(), lambda: '[]\n', NONCE, 1, Path(directory) / 'actions.json')

    def test_factory_compilation_inputs_cannot_disable_sdk_checker_or_add_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project_inputs(root)
            for relative, replacement in (
                ('hvigor/hvigor-config.json5', '{}'),
                ('hvigorfile.ts', 'export default { system: undefined, plugins: [] };\n'),
                ('entry/src/main/module.json5', json.dumps({'module': {'requestPermissions':
                    [{'name': 'ohos.permission.MANAGE_BLUETOOTH'}], 'deviceTypes': ['default']}})),
                ('entry/build-profile.json5', json.dumps({'apiType': 'faMode'}))):
                path = root / 'project' / relative; original = path.read_text(); path.write_text(replacement)
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    inputs(root / 'project', root / 'sdk', 'arm64', NONCE)
                path.write_text(original)

    def test_full_bound_evidence_rehashes_inputs_and_rejects_foreign_package_boot_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); actions = evidence(root / 'ui')
            paths = dict(result=root / 'verified-result.json', raw_results=root / 'results.log',
                ordinary_identity=root / 'application-identity.json', hap=root / 'ordinary-probe-signed.hap',
                compiled_contract_inputs=root / 'project/arkui-components-probe-inputs.json',
                arkui_components_actions=root / 'arkui-components-actions.json')
            caller = project_inputs(root); paths['compiled_contract_inputs'].write_text(json.dumps(caller))
            raw = text(fixture()); paths['raw_results'].write_text(raw)
            paths['ordinary_identity'].write_text(IDENTITY); paths['hap'].write_text('synthetic NOT signed HAP')
            paths['arkui_components_actions'].write_text(json.dumps(actions))
            result = verifier.verify(raw, NONCE, IDENTITY); result['actual_UI'] = verify_actions(actions, NONCE, raw)
            report = dict(status='pass', scope=SCOPE, failures=[], archive_sha256='archive', arch='arm64',
                run_id=NONCE, first_artifact_behavior_gate_passed=False, verifier_sha256=digest(Path(verifier.__file__)),
                result=result, results_sha256=digest(paths['raw_results']),
                application_identity_sha256=digest(paths['ordinary_identity']),
                compiled_inputs_sha256=digest(paths['compiled_contract_inputs']),
                actions_sha256=digest(paths['arkui_components_actions']))
            paths['result'].write_text(json.dumps(report))
            document = dict(status='pass', persona='arkui-components', archive_sha256='archive', boot_id='boot',
                arch='arm64', device='phone', target='owned', failures=[], run_id=NONCE, ordinary_uid=20010001,
                first_artifact_behavior_gate_passed=False, result=str(paths['result']))
            for key, path in paths.items(): document[key + '_sha256'] = digest(path)
            self.assertEqual(verifier.verify_evidence(document, 'archive', 'boot', 'arm64', 'phone', 'owned'), result)
            for key, value in (('archive_sha256', 'old'), ('boot_id', 'old'), ('arch', 'x86_64'),
                ('device', '2in1'), ('target', 'foreign'), ('ordinary_uid', 0)):
                changed = copy.deepcopy(document); changed[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    verifier.verify_evidence(changed, 'archive', 'boot', 'arm64', 'phone', 'owned')
            for path in (*paths.values(), root / 'project/entry/src/main/ets/pages/Index.ets'):
                original = path.read_bytes(); path.write_bytes(original + b' changed')
                with self.subTest(path=path), self.assertRaises(ValueError):
                    verifier.verify_evidence(document, 'archive', 'boot', 'arm64')
                path.write_bytes(original)
            from verify_gap_closure import behavior_results
            runtime = root / 'runtime'; (runtime / 'arkui-components').mkdir(parents=True)
            (runtime / 'boot').mkdir()
            (runtime / 'arkui-components/evidence.json').write_text(json.dumps(document))
            boot = dict(status='pass', purpose='acceptance',
                scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate', archive_sha256='archive',
                test_environment=dict(boot_id='boot', guest_arch='arm64', device_type='phone',
                                      target='owned', external_keepalive=False))
            boot_path = runtime / 'boot/boot.json'; boot_path.write_text(json.dumps(boot))
            self.assertEqual(set(behavior_results(runtime, 'boot', 'archive', 'phone')), set(CONTRACTS))
            boot['purpose'] = 'diagnostic'; boot_path.write_text(json.dumps(boot))
            with self.assertRaises(ValueError): behavior_results(runtime, 'boot', 'archive', 'phone')

    def test_suite_gate_use_actual_typed_caller_not_export_only(self):
        from run_normal_hap_probe import PERSONAS, verifier_arguments
        root = Path(__file__).resolve().parents[2]
        suite = (root / 'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        gate = (root / 'scripts/verify_first_artifact_gate.py').read_text()
        builder = (root / 'ci/capability-audit/build_hap_probe.py').read_text()
        self.assertEqual(PERSONAS['arkui-components'][0], '--arkui-components-only')
        self.assertIn("check('arkui-components', path, [record])", suite)
        self.assertIn('"arkui-components"', gate.split('DEVICE_CHECKS', 1)[0])
        self.assertIn('from verify_arkui_components_results import verify_evidence', gate)
        self.assertIn('args.arkui_components_only', builder)
        args = verifier_arguments('arkui-components', 'archive', 'raw', 'identity', NONCE, 'arm64', 'output')
        self.assertIn('--application-identity', args); self.assertIn('--arch', args)


if __name__ == '__main__': unittest.main()
