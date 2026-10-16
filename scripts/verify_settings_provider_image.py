#!/usr/bin/env python3
"""Verify the actual source Settings HAP; offline checks are not guest acceptance."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import tempfile
import zipfile

from ext_image_entries import dump_unique_file
from verify_preinstall_selection import verify_selection
from verify_alsa_config_image import debugfs_path, file_sha256

SIGNATURE = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
SIGNER_JAR_SHA = 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d'
ORIGINAL_PROFILE_SHA = '5c78cf766c6c3b72104c31a1faea54cee7d119c1b841be31f59297dfec880da6'
PROFILE_ISSUER_SHA = 'BF9771B891CF2DF55B50BDC7F1D583D842DC8CC68E99C381680BD6D25E7FFF20'
ABIS = {'armv7a': ('armeabi-v7a', 1, 40), 'arm64': ('arm64-v8a', 2, 183),
        'x86_64': ('x86_64', 2, 62)}
EXTENSIONS = {
    "SharePickerExtensionAbility": "sysPicker/share",
    "SettingsStatusReportSchedulerExtensionAbility": "workScheduler",
    "WifiUnSaveNetDialogAbility": "sysDialog/common",
    "BluetoothUIExtensionSettingsAbility": "sys/commonUI",
    "WifiUIExtensionSettingsAbility": "sys/commonUI",
    "NotDisturbUIExtensionSettingsAbility": "sys/commonUI",
    "OobeLocalUserAbility": "sys/commonUI",
    "ExternalCommonUIExtensionAbility": "sys/commonUI",
    "OpenNetworkUIExtensionAbility": "sys/commonUI",
    "BluetoothOppServiceUIExtensionAbility": "sys/commonUI",
    "IntelligentSceneAppSelectExtensionAbility": "sys/commonUI",
    "DarkModeExtensionSettingsAbility": "sys/commonUI",
    "HotspotExtensionAbility": "sys/commonUI",
    "SoundExtensionAbility": "sys/commonUI",
    "com.ohos.settings.OobeWifiSettingsExtensionAbility": "sys/commonUI",
    "WifiNotAvailableDialog": "sysDialog/common",
    "BluetoothPairDialog": "sysDialog/common",
    "BluetoothPbapPseDialog": "sysDialog/common",
    "BluetoothAutoPlayAuthDialog": "sysDialog/common",
    "BluetoothMapAuthDialog": "sysDialog/common",
    "BluetoothSwitchDialog": "sysDialog/common",
    "bluetooth": "sysDialog/common",
    "OOBEPasswordSettingExtensionAbility": "sysDialog/common",
    "PasswordSettingExtensionAbility": "sysDialog/common",
    "OobePasswordExtensionAbility": "sysDialog/common",
    "AccessibilityShortKeyDialog": "sysDialog/common",
    "AccessibilityReConfirmDialog": "sysDialog/common",
    "AccessibilityIgnoreConfirmDialog": "sysDialog/common",
    "USBDebugDialog": "sysDialog/common",
    "SettingsExtService": "service",
    "IgnoreRepeatClickExtService": "service",
    "SettingsInstantShareService": "service",
    "DisableToastService": "service",
    "com.ohos.settings.NotDisturbService": "service",
    "com.ohos.settings.ScheduledPowerOffService": "service",
    "com.ohos.settings.ScheduledPowerOffNowService": "service",
    "com.ohos.settings.ScheduledPowerOnService": "service",
    "com.ohos.settings.ScheduledPowerCheckService": "service",
    "ScheduledPowerOffDialogAbility": "sysDialog/common",
    "ResetLogoutLoadingAbility": "sysDialog/common",
    "com.ohos.settings.TimeChangeInitSubscriber": "staticSubscriber",
    "com.ohos.settings.SettingsDataRestoreFinishSubscriber": "staticSubscriber",
    "NotDisturbDialogAbility": "sysDialog/common",
    "DeveloperModeSettingsAbility": "sysDialog/common"
}


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate Settings metadata key: ' + name)
        result[name] = value
    return result


def inspect_hap(hap):
    with zipfile.ZipFile(hap) as archive:
        seen = set()
        if len(archive.infolist()) > 10000 or sum(item.file_size for item in archive.infolist()) > 512 * 1024 * 1024:
            raise ValueError('Settings HAP exceeds the bounded source provider size')
        for entry in archive.infolist():
            name = PurePosixPath(entry.filename)
            if (entry.filename in seen or name.is_absolute() or '..' in name.parts or
                    '\\' in entry.filename or name.as_posix() != entry.filename.rstrip('/') or
                    entry.flag_bits & 1 or entry.file_size > 256 * 1024 * 1024 or
                    ((entry.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('unsafe/duplicate/oversized Settings HAP member')
            seen.add(entry.filename)
        if not {'module.json', 'ets/modules.abc', 'resources.index'} <= seen:
            raise ValueError('Settings HAP lacks real compiled module/resources')
        if not archive.read('ets/modules.abc') or not archive.read('resources.index'):
            raise ValueError('empty compiled Settings provider')
        module = json.loads(archive.read('module.json'), object_pairs_hook=unique_object)
        if (module.get('app', {}).get('bundleName') != 'com.ohos.settings' or
                module.get('module', {}).get('name') != 'phone' or
                module['module'].get('type') != 'entry' or
                set(module['module'].get('deviceTypes', [])) != {'default', 'tablet'}):
            raise ValueError('unexpected Settings bundle/module/device profile')
        extensions = module['module'].get('extensionAbilities', [])
        actual = {entry['name']: entry['type'] for entry in extensions}
        if len(actual) != len(extensions) or actual != EXTENSIONS:
            raise ValueError('Settings provider extensions missing, duplicated or incompatible')
        for entry in extensions:
            if entry['name'] == 'SharePickerExtensionAbility' and (
                    entry.get('srcEntry') != './ets/Setting/SharePicker/SharePickerExtension.ets' or
                    entry.get('exported') is not True or entry.get('extensionProcessMode') != 'instance' or
                    entry.get('permissions', []) != []):
                raise ValueError('Settings real modal share picker contract changed')
            if entry['name'] in ('SettingsExtService', 'IgnoreRepeatClickExtService'):
                if entry.get('permissions') != ['ohos.permission.ACCESS_SYSTEM_SETTINGS']:
                    raise ValueError('Settings service permission changed')
            if entry['name'] == 'ExternalCommonUIExtensionAbility':
                if entry.get('exported') is not True or entry.get('extensionProcessMode') != 'instance':
                    raise ValueError('Settings external input session contract changed')
        machines = {}
        for abi, elf_class, machine in ABIS.values():
            for library in ('libnative.so', 'libc++_shared.so'):
                member = 'libs/' + abi + '/' + library
                raw = archive.read(member)
                if (len(raw) < 64 or raw[:7] != b'\x7fELF' + bytes((elf_class, 1, 1)) or
                        struct.unpack_from('<HH', raw, 16) != (3, machine)):
                    raise ValueError('Settings native library has wrong ABI/type: ' + member)
                machines[member] = {'elf_machine': machine, 'sha256': hashlib.sha256(raw).hexdigest()}
        return {'bundle': 'com.ohos.settings', 'extensions': actual, 'native_libraries': machines,
                'hap_sha256': file_sha256(hap)}


def verify_signature(hap, source, scratch):
    dist = source / 'developtools/hapsigner/dist'
    jar = dist / 'hap-sign-tool.jar'
    if file_sha256(jar) != SIGNER_JAR_SHA:
        raise ValueError('Settings signer tool does not match the fixed release')
    profile = scratch / 'embedded-profile.p7b'
    chain = scratch / 'app-chain.cer'
    completed = subprocess.run(['java', '-jar', str(jar), 'verify-app', '-inFile', str(hap),
                                '-outCertChain', str(chain), '-outProfile', str(profile)],
                               check=True, capture_output=True, text=True, timeout=120)
    output = completed.stdout + completed.stderr
    required = ('verify codesign success', 'Digest verify result: true',
                'verify permission sign success', 'verify-app success')
    leaf = re.split(r'certificate #0\b', output, maxsplit=1)
    if len(leaf) != 2:
        raise ValueError('Settings HAP verification lacks the actual signing leaf')
    match = re.search(r'SHA256:\s*([0-9A-Fa-f:]+)', re.split(r'certificate #1\b', leaf[1], maxsplit=1)[0])
    if (not all(marker in output for marker in required) or not match or
            match[1].replace(':', '').upper() != SIGNATURE or not chain.is_file() or
            profile.read_bytes() != (source / 'applications/standard/settings/signature/settings.p7b').read_bytes()):
        raise ValueError('Settings signature/digest/permissions or exact source profile mismatch')
    return {'application_signer_sha256': SIGNATURE, 'embedded_profile_sha256': file_sha256(profile),
            'digest_codesign_permission_verification': 'pass'}


def profile_invariants(original, actual):
    """Only the approved OS certificate and finite expiration may change."""
    value = json.loads(json.dumps(actual))
    bundle = value.get('bundle-info', {})
    if (bundle.get('bundle-name') != 'com.ohos.settings' or bundle.get('apl') != 'system_basic' or
            bundle.get('app-feature') != 'hos_system_app' or value.get('type') != 'release' or
            value.get('app-distribution-type') != 'os_integration' or
            value.get('validity', {}).get('not-after') != 2208988800):
        raise ValueError('Settings profile identity/APL/distribution or expiry changed')
    certificate = bundle['distribution-certificate'].encode()
    der = subprocess.check_output(['openssl', 'x509', '-outform', 'DER'], input=certificate, timeout=30)
    if hashlib.sha256(der).hexdigest().upper() != SIGNATURE:
        raise ValueError('Settings profile does not bind the fixed OS application signer')
    value['bundle-info']['distribution-certificate'] = original['bundle-info']['distribution-certificate']
    value['validity']['not-after'] = original['validity']['not-after']
    if value != original:
        raise ValueError('Settings original ACL/permission/profile policy changed')


def verify_profile_policy(source, scratch):
    project = source / 'applications/standard/settings'
    raw = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:signature/settings.p7b'], timeout=30)
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_PROFILE_SHA:
        raise ValueError('Settings original release profile is not pinned')
    original = json.loads(subprocess.check_output(
        ['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify'], input=raw, timeout=30),
        object_pairs_hook=unique_object)
    issuer = scratch / 'settings-profile-issuer.pem'
    profile = project / 'signature/settings.p7b'
    actual = json.loads(subprocess.check_output(
        ['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify', '-in', str(profile),
         '-signer', str(issuer)], timeout=30), object_pairs_hook=unique_object)
    if issuer.read_bytes().count(b'-----BEGIN CERTIFICATE-----') != 1:
        raise ValueError('Settings profile must have exactly the fixed OS profile signer')
    der = subprocess.check_output(['openssl', 'x509', '-in', str(issuer), '-outform', 'DER'], timeout=30)
    if hashlib.sha256(der).hexdigest().upper() != PROFILE_ISSUER_SHA:
        raise ValueError('Settings release profile issuer changed')
    profile_invariants(original, actual)
    return {'original_profile_sha256': ORIGINAL_PROFILE_SHA, 'profile_issuer_sha256': PROFILE_ISSUER_SHA,
            'apl': 'system_basic', 'original_acls_and_permissions': 'unchanged'}


def verify_source(source):
    verifier = Path(__file__).resolve().parents[1] / 'patches/common/applications/standard/settings/source_provider/verify_source.py'
    spec = importlib.util.spec_from_file_location('settings_source_guard', verifier)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.validate(source, require_patched=True)
    for component in ('accessibility_service_completion', 'external_input', 'input_2in1_navigation',
                      'refresh_rate_page', 'share_picker'):
        route_spec = importlib.util.spec_from_file_location('settings_guard_' + component,
            verifier.parent.parent / component / 'verify_source.py')
        route_guard = importlib.util.module_from_spec(route_spec)
        route_spec.loader.exec_module(route_guard)
        route_guard.validate(source, require_patched=True)
    policy = json.loads((source / 'vendor/ohemu/virt/preinstall-config/install_list_capability.json').read_text(),
                        object_pairs_hook=unique_object)
    entries = [item for item in policy['install_list'] if item.get('bundleName') == 'com.ohos.settings']
    if len(entries) != 1 or entries[0] != {'bundleName': 'com.ohos.settings', 'app_signature': [SIGNATURE],
                                                'allowAppUsePrivilegeExtension': True}:
        raise ValueError('Settings preinstall policy does not pin the exact OS signer')
    return guard.REVISION


def verify_preinstall_policies(source, image=None, scratch=None):
    """Check both certificate pins, including the actual image's grant file."""
    component = Path(__file__).resolve().parents[1] / 'patches/common/vendor/ohemu/virt/settings_provider/prepare.py'
    spec = importlib.util.spec_from_file_location('settings_preinstall_guard', component)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    result = {}
    for name, permissions in (('install_list_capability.json', False), ('install_list_permissions.json', True)):
        path = source / 'vendor/ohemu/virt/preinstall-config' / name
        canonical = guard.prepare(path, require_patched=True, permissions=permissions)
        item = {'source_sha256': file_sha256(path), 'application_signer_sha256': SIGNATURE}
        if image is not None:
            directory = scratch / name
            directory.mkdir()
            actual, identity = dump_unique_file(image, ('/etc/app/' + name, '/system/etc/app/' + name),
                                               directory, debugfs_path())
            if guard.prepare(actual, require_patched=True, permissions=permissions) != canonical:
                raise ValueError('actual packaged Settings preinstall policy differs from validated source: ' + name)
            item.update(identity)
            item['image_file_sha256'] = file_sha256(actual)
        result[name] = item
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--system-image', type=Path)
    group.add_argument('--hap', type=Path)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--arch', choices=tuple(ABIS), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline source Settings provider/ABI/signature only',
              'arch': args.arch, 'first_artifact_behavior_gate_passed': False,
              'provider_runtime_validated': False, 'cloud_provider_validated': False, 'failures': []}
    try:
        result['source_revision'] = verify_source(args.source_root)
        with tempfile.TemporaryDirectory(prefix='settings-image-') as directory:
            scratch = Path(directory)
            result['install_selection'] = verify_selection(args.source_root, 'com.ohos.settings', args.system_image, scratch)
            hap = args.hap
            if args.system_image:
                hap, identity = dump_unique_file(args.system_image,
                    ('/app/com.ohos.settings/Settings.hap', '/system/app/com.ohos.settings/Settings.hap'),
                    scratch, debugfs_path())
                result.update(identity)
                result['system_image_sha256'] = file_sha256(args.system_image)
            result.update(inspect_hap(hap))
            result.update(verify_signature(hap, args.source_root, scratch))
            result['profile_policy'] = verify_profile_policy(args.source_root, scratch)
            result['preinstall_policies'] = verify_preinstall_policies(args.source_root, args.system_image, scratch)
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, struct.error, zipfile.BadZipFile,
            subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'failures': result['failures']}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
