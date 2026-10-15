"""Exact signed caller and SDK input provenance for dynamic intent regressions."""
import copy
import json
from pathlib import Path
import re
import zipfile
from run_root_probe import digest

EVIDENCE_SCOPE = 'all_seven_API26_dynamic_intent_decorators_real_registration_dispatch_widgets_routes_denials_NOT_complete_gate'


def identity(text, bundle, role):
    if role not in ('normal', 'system-denied', 'system'):
        raise ValueError('explicit intent caller role required')
    prefix = bundle + ':\n'
    if text.startswith(prefix): text = text[len(prefix):]
    document = json.loads(text)
    app = document['applicationInfo']
    if (app.get('bundleName') != bundle or type(app.get('uid')) is not int or app['uid'] // 200000 != 100 or
            app.get('isSystemApp') is not (role != 'normal') or
            app.get('appPrivilegeLevel') != ('normal' if role == 'normal' else 'system_core')):
        raise ValueError('actual intent BMS identity/profile/account differs')
    return app['uid']


def file_record(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('actual regular intent evidence file required')
    return dict(path=str(path.resolve()), sha256=digest(path))


def checked_file(value):
    if not isinstance(value, dict) or set(value) != {'path', 'sha256'}:
        raise ValueError('exact intent evidence path/hash required')
    path = Path(value['path'])
    if path.is_symlink() or not path.is_file() or digest(path) != value['sha256']:
        raise ValueError('intent evidence is missing, linked or changed')
    return path


def verify_application(record, builder, signer, nonce, role, arch, udid, target_nonce=None):
    paths = {name: checked_file(record[name]) for name in (
        'inputs', 'application_identity', 'signed_hap', 'unsigned_hap', 'signing_receipt')}
    value = json.loads(paths['inputs'].read_text())
    generated = Path(value['generated_source']); declaration = Path(value['sdk_declaration'])
    expected_page = builder.page(nonce, role, target_nonce) if target_nonce else builder.page(nonce, role)
    expected_declaration = ('@ohos.app.form.formHost.d.ts' if builder.__name__ == 'build_insight_form_host_probe'
                            else '@ohos.app.ability.insightIntentDriver.d.ts')
    if (value.get('schema_version') != 1 or value.get('bundle_name') != builder.BUNDLE or
            value.get('run_id') != nonce or value.get('role') != role or value.get('arch') != arch or
            value.get('scope') != builder.SCOPE or value.get('template_sha256') != digest(builder.TEMPLATE) or
            value.get('strict_mode') != {} or value.get('additional_input_sha256') != {} or
            generated.is_symlink() or not generated.is_file() or generated.read_text() != expected_page or
            digest(generated) != value.get('generated_source_sha256') or declaration.is_symlink() or
            not declaration.is_file() or declaration.name != expected_declaration or
            digest(declaration) != value.get('sdk_declaration_sha256') or
            value.get('request_permissions') != (list(builder.PERMISSIONS) if role == 'system' else [])):
        raise ValueError('intent caller must bind its exact current complete source, role, ABI and actual SDK')
    if builder.__name__ == 'build_insight_form_host_probe':
        sdk = declaration.parent.parent.parent
        expected = (builder.COMPONENT_DECLARATION, builder.LOADER_DECLARATION)
        if set(value.get('additional_sdk_declarations', {})) != set(expected):
            raise ValueError('actual system widget source and loader declarations required')
        component = sdk / builder.COMPONENT_DECLARATION
        loader = sdk / builder.LOADER_DECLARATION
        if (component.is_symlink() or loader.is_symlink() or digest(component) != builder.COMPONENT_SHA256 or
                loader.read_bytes() != component.read_bytes().replace(b"import('../api/", b"import('../../../api/") or
                any(digest(sdk / name) != value['additional_sdk_declarations'][name] for name in expected)):
            raise ValueError('pinned real widget declarations changed')
    elif value.get('additional_sdk_declarations'):
        raise ValueError('unexpected caller SDK substitutions')
    receipt = json.loads(paths['signing_receipt'].read_text())
    with zipfile.ZipFile(paths['signed_hap']) as hap, zipfile.ZipFile(paths['unsigned_hap']) as unsigned:
        if len(hap.namelist()) != len(set(hap.namelist())):
            raise ValueError('duplicate signed HAP entries')
        compiled = json.loads(hap.read('module.json'))
        if hap.read('module.json') != unsigned.read('module.json') or hap.read('ets/modules.abc') != unsigned.read('ets/modules.abc'):
            raise ValueError('signing changed the actual caller declaration or compiled ABC')
    profile = receipt.get('verified_profile', {})
    if (receipt.get('status') != 'pass' or receipt.get('role') != role or
            receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
            receipt.get('signed_sha256') != digest(paths['signed_hap']) or
            receipt.get('unsigned_sha256') != digest(paths['unsigned_hap']) or
            compiled['module'].get('requestPermissions') != builder.module(role)['module']['requestPermissions'] or
            signer.configure_profile(copy.deepcopy(profile), role, udid, compiled) != profile):
        raise ValueError('intent actual signed HAP/device/exact permission profile differs')
    uid = identity(paths['application_identity'].read_text(), builder.BUNDLE, role)
    if record.get('actual_uid') != uid: raise ValueError('intent summary lost the actual installed UID')
    return uid
