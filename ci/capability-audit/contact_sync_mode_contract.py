"""Bind a permission-free typed/native enum observation to actual SDK inputs."""
import json
from pathlib import Path
import re
import subprocess

from const_enum_contracts import LEDGER, sha256

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / 'contact_sync_mode_probe.ets'
NATIVE = HERE / 'contact_sync_mode_hap_probe.cpp'
CONTRACT = 'arkts_export:@ohos.contact:ContactSyncMode'
AUDIO_CONTRACT = 'arkts_export:@ohos.multimedia.audio:DeviceBlockStatus'
PHOTO_CONTRACT = 'arkts_export:@ohos.file.photoAccessHelper:FusionAssetType'
SCOPE = 'actual_contact_and_state_record_constructors_and_enums_NOT_provider_or_persistence_behavior'
STATE_RECORD_CLASSES = ('ConnectOptions', 'ConnectOptionsCollections')
RECORD_CLASSES = ('ContactAttributes', 'Group', 'Holder', 'Name', 'NickName', 'Note',
                  'Organization', 'Portrait', 'Website')


def expected_enum(sdk, module, name, members):
    sdk = Path(sdk).resolve()
    compiler = sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'
    resolver = HERE / 'extract_const_enum_contracts.cjs'
    script = "const m=require(process.argv[1]);process.stdout.write(JSON.stringify(m.extract(require(process.argv[2]),process.argv[3],[{module:'@ohos.contact',contracts:[{name:'ContactSyncMode'}]}],false)));"
    script = script.replace("[{module:'@ohos.contact',contracts:[{name:'ContactSyncMode'}]}]",
                            json.dumps([{'module': module, 'contracts': [{'name': name}]}]))
    process = subprocess.run(['node', '-e', script, str(resolver), str(compiler), str(sdk / 'ets/api')],
                             text=True, capture_output=True, check=True)
    contracts = json.loads(process.stdout)
    if len(contracts) != 1 or contracts[0]['members'] != members:
        raise ValueError('actual SDK regular enum members differ from this API26 repair: ' + name)
    return contracts[0]


def expected(sdk):
    return expected_enum(sdk, '@ohos.contact', 'ContactSyncMode', [
        {'name': 'MODE_INCREMENTAL', 'value': 1}, {'name': 'MODE_CLOUD_BASED', 'value': 2}])


def expected_audio(sdk):
    return expected_enum(sdk, '@ohos.multimedia.audio', 'DeviceBlockStatus', [
        {'name': 'UNBLOCKED', 'value': 0}, {'name': 'BLOCKED', 'value': 1}])


def expected_photo(sdk):
    return expected_enum(sdk, '@ohos.file.photoAccessHelper', 'FusionAssetType', [
        {'name': 'COMPATIBLE_ASSET', 'value': 0}])


def inputs(project, sdk, arch, run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh ContactSyncMode challenge required')
    page = Path(project) / 'entry/src/main/ets/pages/Index.ets'
    sdk = Path(sdk).resolve()
    return {'schema_version': 1, 'role': 'ordinary_app', 'scope': SCOPE,
            'run_id': run_id, 'arch': arch, 'request_permissions': [], 'sdk': str(sdk),
            'contract': expected(sdk), 'audio_contract': expected_audio(sdk), 'photo_contract': expected_photo(sdk),
            'audit_baseline_sha256': sha256(LEDGER), 'generated_source': str(page),
            'generated_source_sha256': sha256(page), 'template_sha256': sha256(TEMPLATE),
            'native_source_sha256': sha256(NATIVE), 'resolver_sha256': sha256(HERE / 'extract_const_enum_contracts.cjs'),
            'contact_declaration_sha256': sha256(sdk / 'ets/api/@ohos.contact.d.ts'),
            'state_declaration_sha256': sha256(sdk / 'ets/api/@ohos.arkui.StateManagement.d.ts'),
            'typescript_sha256': sha256(sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js')}


def verify_inputs(value, run_id, arch):
    page = Path(value['generated_source'])
    if (type(value.get('schema_version')) is not int or value.get('schema_version') != 1 or value.get('role') != 'ordinary_app' or value.get('scope') !=
            SCOPE or value.get('run_id') != run_id or
            value.get('arch') != arch or value.get('request_permissions') != [] or
            value.get('audit_baseline_sha256') != sha256(LEDGER) or page.is_symlink() or
            sha256(page) != value.get('generated_source_sha256') or
            page.read_text() != TEMPLATE.read_text().replace('__RUN__', run_id) or
            sha256(TEMPLATE) != value.get('template_sha256') or sha256(NATIVE) != value.get('native_source_sha256') or
            sha256(HERE / 'extract_const_enum_contracts.cjs') != value.get('resolver_sha256') or
            sha256(Path(value['sdk']) / 'ets/api/@ohos.contact.d.ts') != value.get('contact_declaration_sha256') or
            sha256(Path(value['sdk']) / 'ets/api/@ohos.arkui.StateManagement.d.ts') != value.get('state_declaration_sha256') or
            sha256(Path(value['sdk']) / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js') !=
            value.get('typescript_sha256') or expected(value['sdk']) != value.get('contract') or
            expected_audio(value['sdk']) != value.get('audio_contract') or
            expected_photo(value['sdk']) != value.get('photo_contract')):
        raise ValueError('ContactSyncMode caller/compiler/SDK must match current actual inputs')
