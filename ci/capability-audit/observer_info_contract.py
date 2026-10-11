"""Bind the real ordinary app's observer caller and its own WindowStage."""
import json
from pathlib import Path
import re
from run_root_probe import digest

SCOPE = 'real_density_context_and_breakpoint_class_instances_two_subscription_generations'
TEMPLATE = Path(__file__).with_name('observer_info_probe.ets')
ABILITY = """import { UIAbility } from '@kit.AbilityKit';
import window from '@ohos.window';

export default class EntryAbility extends UIAbility {
  onWindowStageCreate(stage: window.WindowStage): void {
    AppStorage.setOrCreate<window.WindowStage>('qemuObserverInfoStage', stage);
    stage.loadContent('pages/Index');
  }
  onWindowStageDestroy(): void {
    AppStorage.delete('qemuObserverInfoStage');
  }
}
"""


def source(run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh observer info nonce required')
    return TEMPLATE.read_text().replace('__RUN__', run_id)


def inputs(project, sdk, arch, run_id):
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    if arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('actual supported observer info ABI required')
    page = project / 'entry/src/main/ets/pages/Index.ets'
    ability = project / 'entry/src/main/ets/entryability/EntryAbility.ets'
    module = project / 'entry/src/main/module.json5'
    pages = project / 'entry/src/main/resources/base/profile/main_pages.json'
    declaration = sdk / 'ets/api/@ohos.arkui.observer.d.ts'
    if (page.is_symlink() or ability.is_symlink() or page.read_text() != source(run_id) or
            ability.read_text() != ABILITY or
            json.loads(module.read_text())['module'].get('requestPermissions', []) != [] or
            json.loads(pages.read_text()) != {'src': ['pages/Index']} or
            any('export class ' + name + ' {' not in declaration.read_text()
                for name in ('DensityInfo', 'WindowSizeLayoutBreakpointInfo'))):
        raise ValueError('actual permission-free observer info caller or SDK changed')
    return dict(schema_version=1, scope=SCOPE, run_id=run_id, arch=arch, project=str(project), sdk=str(sdk),
        generated_sha256={'page': digest(page), 'ability': digest(ability)},
        module_sha256=digest(module), pages_sha256=digest(pages),
        contract_sha256=digest(Path(__file__)), template_sha256=digest(TEMPLATE),
        sdk_declaration_sha256=digest(declaration), request_permissions=[])


def verify_inputs(value, run_id, arch):
    if value != inputs(value['project'], value['sdk'], arch, run_id):
        raise ValueError('original observer info inputs changed')
