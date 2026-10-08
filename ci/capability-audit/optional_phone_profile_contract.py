"""Fresh typed dynamic discovery caller inputs, not image or guest proof."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
from run_root_probe import digest
from verify_optional_phone_profile_results import SCOPE

TEMPLATE = Path(__file__).with_name('optional_phone_profile_probe.ets')


def inputs(project, sdk, arch, run_id):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh capability-discovery challenge required')
    declaration = Path(sdk) / 'ets/api/@internal/full/global.d.ts'
    if 'export declare function canIUse(syscap: string): boolean;' not in declaration.read_text():
        raise ValueError('actual public SDK dynamic canIUse signature changed')
    page = Path(project) / 'entry/src/main/ets/pages/Index.ets'
    module_path = Path(project) / 'entry/src/main/module.json5'
    module = json.loads(module_path.read_text())
    if module['module'].get('requestPermissions', []) != []:
        raise ValueError('actual ordinary discovery caller must be permission-free')
    return {'schema_version': 1, 'role': 'ordinary_app', 'device': 'phone',
        'request_permissions': [], 'scope': SCOPE, 'arch': arch, 'run_id': run_id,
        'sdk': str(Path(sdk).resolve()), 'sdk_declaration_sha256': digest(declaration),
        'generated_source': str(page), 'generated_source_sha256': digest(page),
        'module_sha256': digest(module_path),
        'template_sha256': digest(TEMPLATE), 'contract_sha256': digest(Path(__file__))}


def verify_inputs(value, arch, run_id):
    page = Path(value['generated_source'])
    if (page.is_symlink() or type(value.get('schema_version')) is not int or
        value != inputs(page.parents[5], value['sdk'], arch, run_id) or
        page.read_text() != TEMPLATE.read_text().replace('__PROFILE_RUN_ID__', run_id)):
        raise ValueError('complete ordinary discovery caller and actual SDK must be unchanged')
