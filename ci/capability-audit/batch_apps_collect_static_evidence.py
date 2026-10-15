#!/usr/bin/env python3
"""Read fixed source/staging metadata only; this never proves image or guest behavior."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

SOURCE_PATHS = [
    'applications/standard/hap/BUILD.gn',
    'applications/standard/settings/common/src/main/ets/utils/SettingsDataUtils.ts',
    'foundation/ability/ability_runtime/frameworks/native/appkit/ability_runtime/service_extension_context.cpp',
    'applications/standard/settings/BUILD.gn',
    'applications/standard/settings/product/phone/src/main/module.json5',
    'applications/standard/settings/product/phone/src/main/ets/Setting/Accessibility/service/IgnoreRepeatClickService.ets',
    'applications/standard/contacts/entry/src/main/module.json5',
    'applications/standard/camera/product/picker/src/main/module.json5',
    'applications/standard/photos/product/phone/src/main/module.json5',
    'applications/standard/admin_provisioning/BUILD.gn',
    'applications/standard/admin_provisioning/entry/src/main/module.json',
    'applications/standard/theme/product/phone/src/main/module.json5',
    'applications/standard/launcher/product/phone/src/main/module.json5',
    'applications/standard/user_certificate_manager/certmanager/src/main/module.json5',
    'foundation/barrierfree/accessibility/services/aams_ext/src/accessibility_notification_helper.cpp',
    'prebuilts/ohos-sdk/linux/26.0.0/ets/api/@ohos.accessibility.config.d.ts',
    'prebuilts/ohos-sdk/linux/26.0.0/ets/api/application/ServiceExtensionContext.d.ts',
]
SELECTED_BUNDLES = {
    'com.ohos.settings', 'com.ohos.contacts', 'com.ohos.camera', 'com.ohos.photos',
    'com.ohos.adminprovisioning', 'com.ohos.wallpaper', 'com.ohos.launcher',
    'com.ohos.screenreader', 'com.ohos.hmos.screenreader', 'com.ohos.vassistant',
    'com.ohos.sharepickerdialog', 'com.ohos.mediacontroller', 'com.hmos.mediacontroller',
    'com.ohos.dhardwareui', 'com.ohos.certmanager', 'com.ohos.bluetooth',
    'com.ohos.locationdialog', 'com.huawei.hmos.location', 'com.ohos.vpndialog',
    'com.ohos.communicationsetting', 'com.ohos.callsetting', 'com.wifiservice.portallogin',
    'com.ohos.sceneboard', 'com.numberidentity', 'com.spamshield', 'com.hmos.hsdr',
    'com.ohos.intelligentscene',
}
TOKENS = ('SettingsExtService', 'IgnoreRepeatClickExtService', 'disableIgnoreRepeatClick',
          'disableNotificaiton', 'disableTransitionAnimationsNotification', 'reOpenTransitionAnimations',
          'ignoreRepeatClick.set', 'animationOff.set', 'terminateSelf(', 'set(value: T)',
          'adminprovisioning_hap', 'product_name ==', 'setSecureValue(', 'setSettingsData(', 'setValueSync(', 'TerminateAbility(', '"source"', 'source =', 'hap_src_dir')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collect(source_root, system_root):
    result = {'evidence_scope': 'read-only fixed source and mutable build staging; no archive/guest acceptance',
              'source_root': str(source_root), 'system_root': str(system_root), 'source_files': {},
              'staged_haps': [], 'staged_missing_bundles': [], 'staged_libraries': {}}
    for relative in SOURCE_PATHS:
        path = source_root / relative
        if not path.exists():
            result['source_files'][relative] = {'exists': False}
            continue
        data = path.read_bytes()
        text = data.decode()
        row = {'exists': True, 'sha256': digest(data)}
        if path.name.startswith('module.json'):
            row['name_tokens'] = re.findall(r'"name"\s*:\s*"([^\"]+)"', text)
        else:
            row['selected_lines'] = [{'line': i, 'text': line} for i, line in enumerate(text.splitlines(), 1)
                                     if any(token in line for token in TOKENS)]
        result['source_files'][relative] = row
    seen = set()
    for path in sorted((system_root / 'app').glob('*/*.hap')):
        with zipfile.ZipFile(path) as archive:
            if 'module.json' not in archive.namelist():
                continue
            module = json.loads(archive.read('module.json'))
        bundle = module.get('app', {}).get('bundleName')
        if bundle not in SELECTED_BUNDLES:
            continue
        seen.add(bundle)
        entry = module.get('module', {})
        result['staged_haps'].append({'bundle': bundle, 'path': str(path.relative_to(system_root)),
            'module': entry.get('name'),
            'abilities': [r.get('name') for r in entry.get('abilities', [])],
            'extensions': [{'name': r.get('name'), 'type': r.get('type'),
                            'permissions': r.get('permissions', [])} for r in entry.get('extensionAbilities', [])]})
    result['staged_missing_bundles'] = sorted(SELECTED_BUNDLES - seen)
    for name in ('expanded_menu/libexpanded_menu.z.so', 'libsystemshare_innerkits.z.so',
                 'libai_text_translation_innerapi.z.so', 'libai_text_analyzer_innerapi.z.so'):
        result['staged_libraries'][name] = {lib: (system_root / lib / name).exists() for lib in ('lib', 'lib64')}
    for relative in ('etc/app/install_list.json', 'etc/syscap.json',
                     'etc/multimodalinput/ability_launch_config.json'):
        path = system_root / relative
        data = path.read_bytes()
        result[relative] = {'sha256': digest(data), 'content': json.loads(data)}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--system-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.source_root, args.system_root), ensure_ascii=False, indent=2))
