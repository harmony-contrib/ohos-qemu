"""Actual ordinary RPC abstract-class, object round-trip and request contract."""
import json
from pathlib import Path
import re
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('rpc_runtime_probe.ets')
SCOPE = 'ordinary_ArkTS_native_RPC_base_objects_and_local_request_completions_NOT_remote_death_or_DBinder'
DECLARATION = '@ohos.rpc.d.ts'


def source(run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh RPC nonce required')
    return TEMPLATE.read_text().replace('__RPC_RUN_ID__', run_id)


def inputs(project, sdk, arch, run_id):
    source(run_id)
    if arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('supported RPC ABI required')
    project, sdk = Path(project), Path(sdk).resolve()
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    if json.loads(module.read_text())['module'].get('requestPermissions', []) != []:
        raise ValueError('RPC caller must request no permissions')
    declaration = sdk / 'ets/api' / DECLARATION
    for signature in ('abstract class IRemoteObject {', 'class RemoteObject extends IRemoteObject {',
                      'class RemoteProxy extends IRemoteObject {', 'callback: AsyncCallback<RequestResult>'):
        if signature not in declaration.read_text():
            raise ValueError('actual SDK RPC contract changed')
    base = sdk / 'ets/api/@ohos.base.d.ts'
    if '(err: BusinessError<E>, data: T): void;' not in base.read_text():
        raise ValueError('actual AsyncCallback SDK contract changed')
    return {'schema_version': 1, 'scope': SCOPE, 'role': 'ordinary_app', 'request_permissions': [],
        'sdk': str(sdk), 'arch': arch, 'run_id': run_id,
        'sdk_declaration_sha256': digest(declaration), 'sdk_callback_declaration_sha256': digest(base),
        'template_sha256': digest(TEMPLATE), 'contract_sha256': digest(Path(__file__)),
        'module_sha256': digest(module), 'generated_source': str(page), 'generated_source_sha256': digest(page)}


def verify_inputs(value, run_id, arch):
    page = Path(value['generated_source'])
    if (page.is_symlink() or not page.is_file() or
            value != inputs(page.parents[5], value['sdk'], arch, run_id) or page.read_text() != source(run_id)):
        raise ValueError('actual compiled RPC caller changed or belongs to another run')
