"""Bind the ordinary traffic caller to real SDK, endpoint and minimal permissions."""
import json
from pathlib import Path
import re
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('network_accounting_probe.ets')
SCOPE = 'ordinary_own_UID_HTTP_accounting_and_other_UID_denial_NOT_policy_or_complete_network_support'
PERMISSIONS = [{'name': 'ohos.permission.INTERNET'}]


def endpoint_port(endpoint, run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh network-accounting nonce required')
    match = re.fullmatch(r'http://10\.0\.2\.2:([1-9][0-9]{0,4})/' + run_id, endpoint or '')
    if not match or not 1024 <= int(match[1]) <= 65535:
        raise ValueError('owned QEMU host-loopback endpoint and matching nonce required')
    return int(match[1])


def generate(run_id, endpoint):
    endpoint_port(endpoint, run_id)
    return TEMPLATE.read_text().replace('__NETWORK_ACCOUNTING_RUN_ID__', run_id).replace(
        '__NETWORK_ACCOUNTING_ENDPOINT__', endpoint)


def inputs(project, sdk, arch, run_id, endpoint):
    endpoint_port(endpoint, run_id)
    if arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('supported actual ABI required')
    project, sdk = Path(project), Path(sdk).resolve()
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    if json.loads(module.read_text())['module'].get('requestPermissions') != PERMISSIONS:
        raise ValueError('ordinary accounting caller must have only INTERNET, no statistics privilege')
    declarations = {name: sdk / ('ets/api/@ohos.' + name + '.d.ts')
                    for name in ('net.http', 'net.statistics', 'process')}
    stats = declarations['net.statistics'].read_text()
    for signature in ('function getUidRxBytes(uid: number): Promise<number>;',
                      'function getUidTxBytes(uid: number): Promise<number>;',
                      'function getUidRxBytes(uid: number, callback: AsyncCallback<number>): void;',
                      'function getUidTxBytes(uid: number, callback: AsyncCallback<number>): void;'):
        if signature not in stats:
            raise ValueError('actual SDK network statistics contract changed')
    return dict(schema_version=1, scope=SCOPE, arch=arch, run_id=run_id, sdk=str(sdk),
        endpoint=endpoint, request_permissions=PERMISSIONS, template_sha256=digest(TEMPLATE),
        contract_sha256=digest(Path(__file__)), module_sha256=digest(module),
        sdk_declarations_sha256={name: digest(path) for name, path in declarations.items()},
        generated_source=str(page), generated_source_sha256=digest(page))


def verify_inputs(value, run_id, arch):
    page = Path(value['generated_source'])
    if (page.is_symlink() or not page.is_file() or value != inputs(
            page.parents[5], value['sdk'], arch, run_id, value['endpoint']) or
            page.read_text() != generate(run_id, value['endpoint'])):
        raise ValueError('actual compiled network accounting caller changed')
