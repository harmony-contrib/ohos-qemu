"""Freeze exact SDK attribute/instance typed callers; no constructor shims."""
import json
from pathlib import Path
import re
from run_root_probe import digest

SCOPE = 'ordinary_typed_Arc_factories_scroll_and_dynamic_layout_switch_preserving_child_state'
TEMPLATE = Path(__file__).with_name('arkui_components_probe.ets')
ABILITY_TEMPLATE = """import { UIAbility } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import window from '@ohos.window';
import fs from '@ohos.file.fs';

export default class EntryAbility extends UIAbility {
  private journal(event: string, code: number = 0, message: string = ''): void {
    const path: string = '/data/storage/el2/base/files/arkui-components-__RUN__-startup.log';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try {
      fs.writeSync(file.fd, JSON.stringify({ runId: '__RUN__', event, code, message }) + '\\n');
    } finally { fs.closeSync(file); }
  }
  onWindowStageCreate(stage: window.WindowStage): void {
    this.journal('stage.created');
    stage.loadContent('pages/Index', (error: BusinessError) => {
      this.journal('loadContent.callback', error?.code ?? 0, error?.message ?? '');
    });
  }
}
"""
CONTRACTS = [
    *('arkts_export:@ohos.arkui.ArcList:' + name for name in
      ('ArcListAttribute', 'ArcListInstance', 'ArcListItemAttribute', 'ArcListItemInstance')),
    *('arkts_export:@ohos.arkui.ArcScrollBar:' + name for name in
      ('ArcScrollBarAttribute', 'ArcScrollBarInstance')),
    *('arkts_export:@ohos.arkui.components.ArkDynamicLayout:' + name for name in
      ('DynamicLayoutAttribute', 'DynamicLayoutInstance')),
]


def source(run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh real component probe nonce required')
    return TEMPLATE.read_text().replace('__RUN__', run_id)


def ability_source(run_id):
    # Reuse the same nonce validation as the page; this journal is diagnostic,
    # never a substitute for the native callbacks and actual compositor proof.
    source(run_id)
    return ABILITY_TEMPLATE.replace('__RUN__', run_id)


def inputs(project, sdk, arch, run_id):
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    if arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('actual component caller ABI required')
    paths = dict(page=project / 'entry/src/main/ets/pages/Index.ets',
        ability=project / 'entry/src/main/ets/entryability/EntryAbility.ets',
        module=project / 'entry/src/main/module.json5',
        pages=project / 'entry/src/main/resources/base/profile/main_pages.json',
        build_profile=project / 'build-profile.json5', entry_profile=project / 'entry/build-profile.json5',
        hvigorfile=project / 'hvigorfile.ts', entry_hvigorfile=project / 'entry/hvigorfile.ts',
        compiler_config=project / 'hvigor/hvigor-config.json5')
    if (any(path.is_symlink() for path in paths.values()) or paths['page'].read_text() != source(run_id) or
            paths['ability'].read_text() != ability_source(run_id) or
            json.loads(paths['module'].read_text())['module'].get('requestPermissions', []) != [] or
            json.loads(paths['module'].read_text())['module'].get('deviceTypes') != ['default'] or
            json.loads(paths['pages'].read_text()) != {'src': ['pages/Index']}):
        raise ValueError('actual permission-free component caller inputs changed')
    products = json.loads(paths['build_profile'].read_text())['app']['products']
    if (products != [dict(name='default', compileSdkVersion='26.0.0', targetSdkVersion='26.0.0',
                         compatibleSdkVersion='26.0.0', runtimeOS='OpenHarmony')] or
            json.loads(paths['entry_profile'].read_text()).get('apiType') != 'stageMode'):
        raise ValueError('actual API26 OpenHarmony Stage compiler profile required')
    plugin = None
    for key, task in (('hvigorfile', 'appTasks'), ('entry_hvigorfile', 'hapTasks')):
        match = re.fullmatch("import \\{ " + task + " \\} from '([^'\\n]+/hvigor-ohos-plugin)';\\n"
                             "export default \\{ system: " + task + ", plugins: \\[\\] \\};\\n", paths[key].read_text())
        if not match or not Path(match[1]).is_absolute() or (plugin is not None and plugin != Path(match[1])):
            raise ValueError('only actual standard Hvigor tasks without compiler override/plugins are allowed')
        plugin = Path(match[1])
    if json.loads(paths['compiler_config'].read_text()) != dict(modelVersion='6.0.0', dependencies={},
            execution=dict(daemon=False, parallel=False), logging=dict(level='info')):
        raise ValueError('standard ArkTS checking cannot be disabled or replaced')
    plugin_manifest = plugin / 'package.json'
    if plugin_manifest.is_symlink() or json.loads(plugin_manifest.read_text()).get('name') != '@ohos/hvigor-ohos-plugin':
        raise ValueError('real official OHOS Hvigor plugin identity required')
    declarations = ('ets/api/@ohos.arkui.ArcList.d.ts', 'ets/api/@ohos.arkui.ArcScrollBar.d.ts',
        'ets/api/@ohos.arkui.components.ArkDynamicLayout.d.ts', 'ets/api/arkui/LayoutAlgorithm.d.ts',
        'ets/component/common.d.ts')
    for relative, names in ((declarations[0], ('ArcList', 'ArcListItem')),
                            (declarations[1], ('ArcScrollBar',)), (declarations[2], ('DynamicLayout',))):
        text = (sdk / relative).read_text()
        for name in names:
            if (f'export declare class {name}Attribute extends CommonMethod<{name}Attribute>' not in text or
                    f'export declare const {name}Instance: {name}Attribute;' not in text):
                raise ValueError('real SDK component attribute/instance declaration changed')
    return dict(schema_version=1, scope=SCOPE, arch=arch, run_id=run_id, project=str(project), sdk=str(sdk),
        generated_sha256={name: digest(path) for name, path in paths.items()},
        sdk_declarations_sha256={name: digest(sdk / name) for name in declarations},
        hvigor_plugin_manifest=str(plugin_manifest), hvigor_plugin_manifest_sha256=digest(plugin_manifest),
        contract_sha256=digest(Path(__file__)), template_sha256=digest(TEMPLATE),
        request_permissions=[], requires_real_UI_and_compositor=True,
        first_artifact_behavior_gate_passed=False)


def verify_inputs(value, run_id, arch):
    if value != inputs(value['project'], value['sdk'], arch, run_id):
        raise ValueError('exact typed component caller or real SDK inputs changed')
