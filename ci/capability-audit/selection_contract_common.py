"""Keep clipboard reader provisioning, user consent and UI proof separate."""
import copy
import json
import zipfile
from build_arkui_selection_probe import BUNDLE, ROLES, PERMISSION, verify_inputs
from insight_contract_common import checked_file
from run_root_probe import digest
from sign_arkui_selection_probe import configure_profile


def identity(text, role):
    if role not in ROLES:
        raise ValueError('exact selection role required')
    if text.startswith(BUNDLE + ':\n'):
        text = text[len(BUNDLE) + 2:]
    value = json.loads(text)
    app = value['applicationInfo']
    requested = [PERMISSION] if role == 'reader' else []
    if (app.get('bundleName') != BUNDLE or app.get('isSystemApp') is not False or
            app.get('appPrivilegeLevel') != ('normal' if role == 'normal' else 'system_basic') or
            type(app.get('uid')) is not int or app['uid'] // 200000 != 100 or
            value.get('uid') != app['uid'] or value.get('reqPermissions') != requested):
        raise ValueError('selection caller BMS identity, account or exact permissions differ')
    return app['uid']


def verify_application(record, nonce, role, arch, udid):
    paths = {name: checked_file(record[name]) for name in (
        'inputs', 'application_identity', 'signed_hap', 'unsigned_hap', 'signing_receipt')}
    inputs = json.loads(paths['inputs'].read_text())
    verify_inputs(inputs)
    if (inputs['role'] != role or inputs['run_id'] != nonce or inputs['arch'] != arch or
            inputs['project'] != record['project']):
        raise ValueError('selection caller source role, nonce or ABI differs')
    receipt = json.loads(paths['signing_receipt'].read_text())
    with zipfile.ZipFile(paths['unsigned_hap']) as unsigned, zipfile.ZipFile(paths['signed_hap']) as signed:
        if (len(signed.namelist()) != len(set(signed.namelist())) or
                len(unsigned.namelist()) != len(set(unsigned.namelist())) or
                set(signed.namelist()) != set(unsigned.namelist()) | {'.pages.info'} or
                not signed.read('.pages.info') or len(signed.read('.pages.info')) % 8):
            raise ValueError('selection signed HAP file set or page bitmap differs')
        for name in unsigned.namelist():
            if unsigned.read(name) != signed.read(name):
                raise ValueError('signing changed the compiled selection caller')
        compiled = json.loads(signed.read('module.json'))
        if compiled['module'].get('deviceTypes') != ['default'] or len(signed.read('ets/modules.abc')) < 1000:
            raise ValueError('actual selection compiled ABC or device profile missing')
    profile = receipt.get('verified_profile', {})
    if (receipt.get('status') != 'pass' or receipt.get('role') != role or
            receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
            receipt.get('signed_sha256') != digest(paths['signed_hap']) or
            receipt.get('unsigned_sha256') != digest(paths['unsigned_hap']) or
            configure_profile(copy.deepcopy(profile), role, udid, compiled) != profile):
        raise ValueError('exact ordinary selection signature and device provisioning required')
    uid = identity(paths['application_identity'].read_text(), role)
    if record['actual_uid'] != uid:
        raise ValueError('selection summary lost its installed UID')
    return uid
