#!/usr/bin/env python3
"""Verify CalendarData source/provider/signing wiring, not runtime behavior."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

BUNDLE = 'com.ohos.calendardata'
SIGNATURE = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
ACLS = {'ohos.permission.NOTIFICATION_AGENT_CONTROLLER', 'ohos.permission.NOTIFICATION_CONTROLLER',
        'ohos.permission.PERMISSION_USED_STATS'}
AUTHORITIES = {
    'DataShareLowerExtAbility': ('datashare://calendardata', 'ohos.permission.READ_CALENDAR',
                               'ohos.permission.WRITE_CALENDAR'),
    'DataShareHighExtAbility': ('datashare://calendardata_whole', 'ohos.permission.READ_WHOLE_CALENDAR',
                              'ohos.permission.WRITE_WHOLE_CALENDAR'),
}
EDITOR = {'name': 'EditorUIExtensionAbility', 'srcEntry': './ets/EditorUIExtensionAbility.ets',
          'type': 'sys/commonUI', 'exported': True, 'extensionProcessMode': 'instance'}


def validate(module, profile, capabilities, fingerprint, platform_fingerprint, require_editor=False):
    if fingerprint != SIGNATURE or platform_fingerprint != SIGNATURE:
        raise ValueError('CalendarData profile/platform certificate does not match pinned source signing policy')
    bundle = profile.get('bundle-info', {})
    acls = profile.get('acls', {}).get('allowed-acls')
    if (bundle.get('bundle-name') != BUNDLE or bundle.get('apl') != 'system_core' or
            bundle.get('app-feature') != 'hos_system_app' or
            not isinstance(acls, list) or len(acls) != 3 or set(acls) != ACLS or
            profile.get('permissions', {}).get('restricted-permissions') != []):
        raise ValueError('CalendarData OS profile or ACL policy unexpectedly changed')
    entries = [entry for entry in capabilities.get('install_list', []) if entry.get('bundleName') == BUNDLE]
    if entries != [{'bundleName': BUNDLE, 'app_signature': [SIGNATURE],
                    'allowAppDesktopIconHide': True, 'allowAppUsePrivilegeExtension': True}]:
        raise ValueError('CalendarData must use an exact, non-wildcard matching certificate entry')
    extensions = module.get('extensionAbilities', [])
    names = [entry.get('name') for entry in extensions]
    # Keep the fixed SDK's declaration; QEMU has an explicit BMS compatibility
    # profile. Do not invent SDK SysCap sets to force new module device labels.
    original = set(AUTHORITIES) | {'ReminderCallbackExtAbility'}
    has_editor = 'EditorUIExtensionAbility' in names
    expected = original | ({'EditorUIExtensionAbility'} if has_editor else set())
    if (len(names) != len(set(names)) or module.get('deviceTypes') != ['default', 'tablet'] or
            set(names) != expected or (require_editor and not has_editor)):
        raise ValueError('unexpected or incomplete CalendarData provider/device surface')
    if has_editor:
        editor = next(entry for entry in extensions if entry['name'] == 'EditorUIExtensionAbility')
        if editor != EDITOR or editor.get('exported') is not True:
            raise ValueError('CalendarData editor must use the exact per-session common UI extension')
        for permission in ('ohos.permission.READ_WHOLE_CALENDAR', 'ohos.permission.WRITE_WHOLE_CALENDAR'):
            grants = [entry for entry in module.get('requestPermissions', []) if entry.get('name') == permission]
            if (len(grants) != 1 or grants[0].get('usedScene') != {
                    'abilities': ['DataShareLowerExtAbility', 'DataShareHighExtAbility',
                                  'ReminderCallbackExtAbility', 'EditorUIExtensionAbility'],
                    'when': 'inuse'}):
                raise ValueError('CalendarData editor requires the exact existing in-use permission scene')
    for name, (uri, read, write) in AUTHORITIES.items():
        entry = next(entry for entry in extensions if entry['name'] == name)
        if (entry.get('type') != 'dataShare' or entry.get('exported') is not True or entry.get('uri') != uri or
                entry.get('readPermission') != read or entry.get('writePermission') != write):
            raise ValueError('CalendarData authority/permission boundary differs: ' + name)
    reminder = next(entry for entry in extensions if entry['name'] == 'ReminderCallbackExtAbility')
    if (reminder.get('type') != 'service' or reminder.get('exported') is not True or
            reminder.get('permissions') != ['ohos.permission.UPDATE_CALENDAR_RRULE']):
        raise ValueError('CalendarData reminder service authorization unexpectedly changed')


def certificate_fingerprint(certificate):
    pem = subprocess.run(['openssl', 'x509', '-outform', 'DER'], input=certificate,
                         capture_output=True, check=True).stdout
    return hashlib.sha256(pem).hexdigest().upper()


def platform_leaf_fingerprint(chain):
    # The standard platform PEM is root -> intermediate -> application.
    # openssl x509 alone reads only the first (root) certificate.
    certificates = re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', chain, re.S)
    if len(certificates) != 3:
        raise ValueError('unexpected platform application certificate chain')
    return certificate_fingerprint(certificates[-1])


def verify(root, require_editor=False):
    source = root / 'applications/standard/calendardata'
    source_build = (source / 'BUILD.gn').read_text()
    if (source_build.count('ohos_app("calendardata_hap")') != 1 or
            not re.search(r'\bdeps\s*=\s*\[\s*\]', source_build) or
            'ohos_resources(' in source_build or 'ohos_js_assets(' in source_build or
            'assemble_type = "assembleHap"' not in source_build):
        raise ValueError('CalendarData Stage HAP must use Hvigor, not legacy resource actions')
    # Verify the existing CMS signature before extracting its policy. Its
    # pinned checkout and exact certificate pin are the build-time baseline;
    # BMS must additionally accept the signed HAP in the newly packaged guest.
    raw = subprocess.run(['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify',
                          '-in', str(source / 'signature/Calendardata.p7b')],
                         capture_output=True, check=True).stdout
    profile = json.loads(raw)
    certificate = profile['bundle-info']['distribution-certificate'].encode()
    platform = (root / 'developtools/hapsigner/dist/OpenHarmonyApplication.pem').read_bytes()
    module = json.loads((source / 'entry/src/main/module.json5').read_text())['module']
    capabilities = json.loads((root / 'vendor/ohemu/virt/preinstall-config/install_list_capability.json').read_text())
    validate(module, profile, capabilities, certificate_fingerprint(certificate),
             platform_leaf_fingerprint(platform), require_editor)
    if require_editor:
        page = 'pages/EventEditor'
        pages = json.loads((source / 'entry/src/main/resources/base/profile/main_pages.json').read_text())['src']
        if (pages.count(page) != 1 or
                not (source / 'entry/src/main/ets/EditorUIExtensionAbility.ets').is_file() or
                not (source / 'entry/src/main/ets/pages/EventEditor.ets').is_file()):
            raise ValueError('CalendarData editor source/page is missing from the real HAP')
    build = (root / 'applications/standard/hap/BUILD.gn').read_text()
    if re.search(r'calendarData_hap|CalendarData\.hap', build):
        raise ValueError('stale CalendarData prebuilt still exists in the HAP build graph')
    components = json.loads((source / 'bundle.json').read_text())['component']['build']['group_type']['service_group']
    if components.count('//applications/standard/calendardata:calendardata_hap') != 1:
        raise ValueError('CalendarData source provider missing/duplicated in its part graph')
    print('CalendarData source/signing preflight passed; CRUD/reminder/editor behavior NOT validated')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-editor', action='store_true')
    args = parser.parse_args()
    verify(args.source_root, args.require_editor)


if __name__ == '__main__':
    main()
