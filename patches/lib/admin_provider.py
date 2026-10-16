#!/usr/bin/env python3
"""Bind AdminProvisioning's unchanged OS identity and ACLs to QEMU preinstall."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from calendar_provider import SIGNATURE, certificate_fingerprint, platform_leaf_fingerprint

BUNDLE = 'com.ohos.adminprovisioning'
ACLS = ('ohos.permission.MANAGE_LOCAL_ACCOUNTS',
        'ohos.permission.MANAGE_ENTERPRISE_DEVICE_ADMIN', 'ohos.permission.FACTORY_RESET')
REQUESTS = set(ACLS) | {'ohos.permission.GET_BUNDLE_INFO', 'ohos.permission.INTERNET'}
CAPABILITY = {'bundleName': BUNDLE, 'app_signature': [SIGNATURE],
              'allowAppDesktopIconHide': True, 'allowAppUsePrivilegeExtension': True}
GRANTS = {'bundleName': BUNDLE, 'app_signature': [SIGNATURE],
          'permissions': [{'name': name, 'userCancellable': False} for name in ACLS]}
POLICIES = {'install_list_capability.json': CAPABILITY, 'install_list_permissions.json': GRANTS}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate AdminProvisioning policy key')
        result[key] = value
    return result


def read(path):
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('regular AdminProvisioning input required: ' + str(path))
    return path.read_bytes()


def replace(path, data):
    descriptor, name = tempfile.mkstemp(prefix='.admin-provider-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, path.stat().st_mode & 0o777)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def policy_bytes(path, name, prepare=False):
    document = json.loads(read(path), object_pairs_hook=unique)
    rows = document['install_list'] if name == 'install_list_capability.json' else document
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('invalid AdminProvisioning preinstall policy')
    matches = [row for row in rows if row.get('bundleName') == BUNDLE]
    if matches and matches != [POLICIES[name]]:
        raise ValueError('unknown AdminProvisioning certificate/grants; preserving source')
    if not matches:
        if not prepare:
            raise ValueError('AdminProvisioning exact source signer/preinstall grants missing')
        rows.append(POLICIES[name])
    return (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode()


def validate(module, profile, fingerprint, platform_fingerprint):
    bundle = profile.get('bundle-info', {})
    acls = profile.get('acls', {}).get('allowed-acls', [])
    if (fingerprint != SIGNATURE or platform_fingerprint != SIGNATURE or
            bundle.get('bundle-name') != BUNDLE or bundle.get('apl') != 'normal' or
            bundle.get('app-feature') != 'hos_system_app' or len(acls) != 3 or set(acls) != set(ACLS) or
            profile.get('permissions', {}).get('restricted-permissions') != []):
        raise ValueError('AdminProvisioning source signing/APL/ACL policy differs')
    requests = module.get('requestPermissions', [])
    if len(requests) != 5 or {p.get('name') for p in requests} != REQUESTS:
        raise ValueError('AdminProvisioning declared permission boundary differs')
    if (module.get('name') != 'adminprovisioning' or module.get('type') != 'entry' or
            module.get('deviceTypes') != ['default', 'tablet', '2in1']):
        raise ValueError('AdminProvisioning module/device surface differs')
    abilities = module.get('abilities', [])
    names = [a.get('name') for a in abilities]
    expected = {'com.ohos.adminprovisioning.MainAbility': (False, []),
                'com.ohos.automanager.AutoManagerAbility': (True, ['ohos.permission.PROVISIONING_MESSAGE']),
                'ByodAdminProvisionAbility': (True, ['ohos.permission.START_PROVISIONING_MESSAGE'])}
    if len(names) != 3 or set(names) != set(expected):
        raise ValueError('AdminProvisioning actual ability surface differs')
    for ability in abilities:
        exported, permissions = expected[ability['name']]
        if (ability.get('exported', ability.get('visible')) is not exported or
                ability.get('permissions', []) != permissions or not ability.get('srcEntry') or
                ability.get('launchType') != 'singleton'):
            raise ValueError('AdminProvisioning caller permission/export boundary differs')
    extensions = module.get('extensionAbilities', [])
    if (len(extensions) != 1 or extensions[0].get('name') != 'MDMUIExtensionAbility' or
            extensions[0].get('type') != 'sys/commonUI' or extensions[0].get('exported') is not False or
            extensions[0].get('srcEntry') != './ets/MainAbility/UIExtensionAbility.ets'):
        raise ValueError('AdminProvisioning private UIExtension boundary differs')


def verify(root, prepare=False):
    source = root / 'applications/standard/admin_provisioning'
    profile = json.loads(subprocess.run(['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify',
        '-in', str(source / 'signature/adminprovisioning.p7b')], check=True, capture_output=True).stdout)
    module = json.loads(read(source / 'entry/src/main/module.json5'), object_pairs_hook=unique)['module']
    validate(module, profile,
        certificate_fingerprint(profile['bundle-info']['distribution-certificate'].encode()),
        platform_leaf_fingerprint(read(root / 'developtools/hapsigner/dist/OpenHarmonyApplication.pem')))
    build = read(source / 'BUILD.gn').decode()
    if (build.count('ohos_app("adminprovisioning_hap")') != 1 or
            'certificate_profile = "signature/adminprovisioning.p7b"' not in build or
            'module_install_dir = "app/com.ohos.adminprovisioning"' not in build or
            'assemble_type = "assembleHap"' not in build):
        raise ValueError('actual source-built signed AdminProvisioning target required')
    directory = root / 'vendor/ohemu/virt/preinstall-config'
    install = json.loads(read(directory / 'install_list.json'), object_pairs_hook=unique)
    matches = [row for row in install['install_list'] if row.get('app_dir') == '/system/app/' + BUNDLE]
    if matches != [{'app_dir': '/system/app/' + BUNDLE, 'removable': False}]:
        raise ValueError('unique original AdminProvisioning preinstall directory required')
    paths = {name: directory / name for name in POLICIES}
    before = {name: read(path) for name, path in paths.items()}
    planned = {name: policy_bytes(path, name, prepare) for name, path in paths.items()}
    # Both policy siblings are validated before publication; restore only this
    # attempt's own changes on failure.
    if prepare:
        written = []
        try:
            for name, path in paths.items():
                if read(path) != before[name]:
                    raise ValueError('AdminProvisioning policy changed after preflight')
                if before[name] != planned[name]:
                    replace(path, planned[name])
                    written.append(name)
        except BaseException:
            for name in reversed(written):
                replace(paths[name], before[name])
            raise
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    verify(args.source_root, args.prepare)
    print('AdminProvisioning source identity/ACL/preinstall checked; guest behavior NOT validated')
