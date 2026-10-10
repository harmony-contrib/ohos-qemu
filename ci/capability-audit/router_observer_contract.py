"""Freeze real typed observer callers and their two-page routing configuration."""
import json
from pathlib import Path
import re
from run_root_probe import digest

SCOPE = 'actual_router_callback_objects_and_unsubscribe_NOT_density_breakpoints_or_full_gate'
TEMPLATES = {'Index': 'router_observer_probe.ets', 'ObserverDetail': 'router_observer_detail.ets'}


def sources(run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh observer nonce required')
    return {name: Path(__file__).with_name(template).read_text().replace('__RUN__', run_id)
            for name, template in TEMPLATES.items()}


def inputs(project, sdk, arch, run_id):
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    if arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('actual supported ABI required')
    module = project / 'entry/src/main/module.json5'
    pages = project / 'entry/src/main/resources/base/profile/main_pages.json'
    if json.loads(module.read_text())['module'].get('requestPermissions', []) != []:
        raise ValueError('router observer must remain an ordinary permission-free caller')
    if json.loads(pages.read_text()) != {'src': ['pages/Index', 'pages/ObserverDetail']}:
        raise ValueError('actual registered second router page required')
    generated = {}
    for name, content in sources(run_id).items():
        path = project / ('entry/src/main/ets/pages/' + name + '.ets')
        if path.is_symlink() or path.read_text() != content:
            raise ValueError('actual compiled observer caller changed')
        generated[name] = digest(path)
    declaration = sdk / 'ets/api/@ohos.arkui.observer.d.ts'
    if 'export class RouterPageInfo {' not in declaration.read_text():
        raise ValueError('actual SDK callback-object declaration missing')
    return dict(schema_version=1, scope=SCOPE, run_id=run_id, arch=arch, project=str(project), sdk=str(sdk),
        generated_sha256=generated, module_sha256=digest(module), pages_sha256=digest(pages),
        contract_sha256=digest(Path(__file__)), sdk_declaration_sha256=digest(declaration),
        templates_sha256={name: digest(Path(__file__).with_name(template)) for name, template in TEMPLATES.items()},
        request_permissions=[])


def verify_inputs(value, run_id, arch):
    if value != inputs(value['project'], value['sdk'], arch, run_id):
        raise ValueError('original observer inputs changed')
