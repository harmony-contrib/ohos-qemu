"""Exact compiled ordinary ArkTS constructor contract, not service callbacks."""
import json
from pathlib import Path
import re
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('completion_handler_probe.ets')
SCOPE = 'ordinary_ArkTS_completion_handler_constructor_fields_NOT_service_start_or_IPC'
DECLARATION = '@ohos.app.ability.CompletionHandlerForAbilityStartCallback.d.ts'


def inputs(project, sdk, arch, run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id) is None or arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('fresh constructor nonce and supported ABI required')
    project, sdk = Path(project), Path(sdk).resolve()
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    declaration = sdk / 'ets/api' / DECLARATION
    if json.loads(module.read_text())['module'].get('requestPermissions', []) != []:
        raise ValueError('constructor caller must request no permissions')
    text = declaration.read_text()
    for signature in ('export class CompletionHandlerForAbilityStartCallback {',
                      'onRequestSuccess?: OnRequestSuccessFn;', 'onRequestFailure?: OnRequestFailureFn;',
                      'FAILURE_CODE_SYSTEM_MALFUNCTION = 0', 'FAILURE_CODE_USER_CANCEL = 1'):
        if signature not in text:
            raise ValueError('actual SDK constructor contract changed')
    return {'schema_version': 1, 'scope': SCOPE, 'role': 'ordinary_app', 'request_permissions': [],
        'sdk': str(sdk), 'arch': arch, 'run_id': run_id,
        'sdk_declaration_sha256': digest(declaration), 'template_sha256': digest(TEMPLATE),
        'contract_sha256': digest(Path(__file__)), 'module_sha256': digest(module),
        'generated_source': str(page), 'generated_source_sha256': digest(page)}


def verify_inputs(value, run_id, arch):
    page = Path(value['generated_source'])
    if (page.is_symlink() or not page.is_file() or
            value != inputs(page.parents[5], value['sdk'], arch, run_id) or
            page.read_text() != TEMPLATE.read_text().replace('__COMPLETION_RUN_ID__', run_id)):
        raise ValueError('actual compiled constructor caller changed')
