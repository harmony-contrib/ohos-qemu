"""Bind the ordinary Photos caller to its actual public API26 SDK and source."""
import json
from pathlib import Path
import re

from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('photos_recent_probe.ets')
SCOPE = 'actual_Photos_metadata_defaults_reused_options_and_picker_parameter_rejection_NOT_assets_or_cloud'


def inputs(project, sdk, arch, run_id):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh Photos caller nonce required')
    project, sdk = Path(project), Path(sdk)
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    declaration = sdk / 'ets/api/@ohos.file.photoAccessHelper.d.ts'
    if json.loads(module.read_text())['module'].get('requestPermissions', []) != []:
        raise ValueError('Photos metadata caller must not receive privileged permissions')
    return {'schema_version': 1, 'role': 'ordinary_app', 'scope': SCOPE,
        'request_permissions': [], 'run_id': run_id, 'arch': arch,
        'sdk': str(sdk.resolve()), 'sdk_declaration_sha256': digest(declaration),
        'template_sha256': digest(TEMPLATE), 'generated_source': str(page),
        'generated_source_sha256': digest(page), 'module_sha256': digest(module),
        'contract_sha256': digest(Path(__file__))}


def verify_inputs(value, run_id, arch):
    page = Path(value['generated_source'])
    if (page.is_symlink() or not page.is_file() or
            value != inputs(page.parents[5], value['sdk'], arch, run_id) or
            page.read_text() != TEMPLATE.read_text().replace('__PHOTO_RUN__', run_id)):
        raise ValueError('original compiled Photos public caller or SDK changed')
