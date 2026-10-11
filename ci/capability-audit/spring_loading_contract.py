"""Bind the exact ordinary typed caller; physical-input proof is separate."""
import json
from pathlib import Path
import re
from run_root_probe import digest

SCOPE = 'real_spring_loading_class_hover_BEGIN_config_abort_CANCEL_and_reentry'
TEMPLATE = Path(__file__).with_name('spring_loading_probe.ets')


def source(run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh spring-loading nonce required')
    return TEMPLATE.read_text().replace('__RUN__', run_id)


def inputs(project, sdk, arch, run_id):
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    if arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('actual supported spring ABI required')
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    pages = project / 'entry/src/main/resources/base/profile/main_pages.json'
    declarations = {name: sdk / name for name in (
        'ets/api/@ohos.arkui.dragController.d.ts', 'ets/api/@ohos.data.unifiedDataChannel.d.ts',
        'ets/component/common.d.ts')}
    drag = declarations['ets/api/@ohos.arkui.dragController.d.ts'].read_text()
    if (page.is_symlink() or page.read_text() != source(run_id) or
            json.loads(module.read_text())['module'].get('requestPermissions', []) != [] or
            json.loads(pages.read_text()) != {'src': ['pages/Index']} or
            'class SpringLoadingContext {' not in drag or 'abort(): void;' not in drag or
            'updateConfiguration(config: DragSpringLoadingConfiguration): void;' not in drag):
        raise ValueError('actual ordinary spring-loading caller or SDK changed')
    return dict(schema_version=1, scope=SCOPE, run_id=run_id, arch=arch, project=str(project), sdk=str(sdk),
        generated_sha256=digest(page), module_sha256=digest(module), pages_sha256=digest(pages),
        contract_sha256=digest(Path(__file__)), template_sha256=digest(TEMPLATE),
        sdk_declarations_sha256={name: digest(path) for name, path in declarations.items()},
        request_permissions=[], requires_real_input=True, first_artifact_behavior_gate_passed=False)


def verify_inputs(value, run_id, arch):
    if value != inputs(value['project'], value['sdk'], arch, run_id):
        raise ValueError('original spring-loading caller inputs changed')
