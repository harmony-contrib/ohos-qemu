#!/usr/bin/env python3
"""Bind actual source SystemUI modules to the existing OS signer; no Owner."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from calendar_provider import SIGNATURE, certificate_fingerprint
from mms_provider import SIGNING_INPUTS, read, unique, cms, certificates, replace
from preinstall_selection import entry as selected_entry, same_json

PROJECT = 'applications/standard/systemui'
REVISION = 'd0f84037f1975dd9bf13ccbd279bd2d9b56e8a01'
HAP_REVISION = 'f2e956a5dd26102f85c86e91d2bfd7c0998534f8'
PROFILE_SHA = 'e20d7466a9fcd8536ad83ca7e192ab24ac31af706f1ad8146c388c8e7397b891'
LEGACY_HAP_SHA = '73940797880d284873c91b2c88eae074aa85beac4fb8a9b5f1b334a31ffbe2f5'
BLOCKS_SHA = '3a13681f2c487c2bbc3bce3bd9d2f863dbdef263841417b4ddfaa36b1819da4c'
ACLS = ['ohos.permission.CAPTURE_SCREEN', 'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION',
        'ohos.permission.MANAGE_WIFI_CONNECTION', 'ohos.permission.NOTIFICATION_CONTROLLER',
        'ohos.permission.START_INVISIBLE_ABILITY']
# Original ACLS remains the exact original signed-profile guard.
CAPTION_ACLS = ACLS + ['ohos.permission.MANAGE_AUDIO_CONFIG',
                       'ohos.permission.GET_BUNDLE_INFO_PRIVILEGED',
                       'ohos.permission.CONTROL_LOCATION_SWITCH',
                       'ohos.permission.SYSTEM_FLOAT_WINDOW']
CAPABILITY = {'bundleName': 'com.ohos.systemui', 'singleton': True, 'keepAlive': True,
    'runningResourcesApply': False, 'app_signature': [SIGNATURE], 'associatedWakeUp': False,
    'allowAppUsePrivilegeExtension': True}
GRANTS = {'bundleName': 'com.ohos.systemui', 'app_signature': [SIGNATURE], 'permissions': [
    {'name': 'ohos.permission.DISTRIBUTED_DATASYNC', 'userCancellable': False},
    {'name': 'ohos.permission.GET_INSTALLED_BUNDLE_LIST', 'userCancellable': False},
    {'name': 'ohos.permission.ACCESS_BLUETOOTH', 'userCancellable': False}]}
PATCH_ROOT = Path(__file__).resolve().parents[1]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def component(name):
    path = PATCH_ROOT / 'common/applications/standard' / name / 'verify_source.py'
    spec = importlib.util.spec_from_file_location('systemui_' + name.replace('/', '_'), path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def hap_blocks():
    raw = read(PATCH_ROOT / 'common/applications/standard/hap/systemui_provider/blocks.json')
    if digest(raw) != BLOCKS_SHA: raise ValueError('fixed seven SystemUI edits changed')
    value = json.loads(raw, object_pairs_hook=unique)
    if value['schema_version'] != 1 or len(value['blocks']) != 7: raise ValueError('exact seven definitions required')
    return value['blocks']

def hap_state(raw):
    text = raw.decode(); states = []
    for row in hap_blocks():
        pair = text.count(row['before']), text.count(row['after'])
        if pair == (1, 0): states.append(False)
        elif pair == (0, 1): states.append(True)
        else: raise ValueError('unknown/duplicate SystemUI HAP definition: ' + row['target'])
    if len(set(states)) != 1: raise ValueError('partial SystemUI HAP graph')
    return states[0]

def normalize_hap_build(raw):
    """Optional parent hook: exact inverse only; legacy whole-file guards still apply."""
    composed = PATCH_ROOT / 'common/applications/standard/hap/qemu_provider_sources'
    states = json.loads(read(composed / 'source_states.json'), object_pairs_hook=unique)
    pair = states['files']['applications/standard/hap/BUILD.gn']
    if digest(raw) == pair[1]:
        prefix = read(composed / 'before/BUILD.gn')
        if digest(prefix) != pair[0]:
            raise ValueError('complete QEMU source-HAP predecessor changed')
        raw = prefix
    if not hap_state(raw): return raw
    text = raw.decode()
    for row in reversed(hap_blocks()): text = text.replace(row['after'], row['before'])
    return text.encode()

def apply_hap(root):
    project = root / 'applications/standard/hap'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != HAP_REVISION:
        raise ValueError('fixed HAP project required')
    component('systemui/source_provider').validate(root, require_patched=True)
    path = project / 'BUILD.gn'; before = read(path)
    if digest(normalize_hap_build(before)) != LEGACY_HAP_SHA:
        raise ValueError('unknown prior complete Admin/MMS/ContactsTheme HAP graph')
    if not hap_state(before):
        text = before.decode()
        for row in hap_blocks(): text = text.replace(row['before'], row['after'])
        after = text.encode()
        if normalize_hap_build(after) != before or read(path) != before: raise ValueError('HAP bytes changed before write')
        replace(path, after)
    if not hap_state(read(path)): raise ValueError('SystemUI source selection absent')
    return {'scope': 'seven exact definitions; ScreenLock and other bytes unchanged', 'actual_compilation': False}

def original_inputs(root):
    project = root / PROJECT; dist = root / 'developtools/hapsigner/dist'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('fixed SystemUI source project required')
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:signature/systemui.p7b'])
    if digest(original) != PROFILE_SHA: raise ValueError('original SystemUI profile changed')
    for name, expected in SIGNING_INPUTS.items():
        if digest(read(dist / name)) != expected: raise ValueError('fixed OS signing input changed: ' + name)
    application = certificates(read(dist / 'OpenHarmonyApplication.pem'))
    issuer = certificates(read(dist / 'OpenHarmonyProfileRelease.pem'))
    if len(application) != 3 or len(issuer) != 3 or certificate_fingerprint(application[-1]) != SIGNATURE:
        raise ValueError('existing OS signer chain changed')
    return project, dist, original, application, issuer

def desired_profile(original):
    bundle = original.get('bundle-info', {})
    if (bundle.get('bundle-name') != 'com.ohos.systemui' or bundle.get('apl') != 'system_basic' or
        bundle.get('app-feature') != 'hos_system_app' or original.get('type') != 'release' or
        original.get('app-distribution-type') != 'os_integration' or
        certificate_fingerprint(bundle['distribution-certificate'].encode()) != SIGNATURE or
        original.get('acls', {}).get('allowed-acls') != ACLS):
        raise ValueError('fixed SystemUI identity/APL/ACL/signature changed')
    result = copy.deepcopy(original); result['validity']['not-after'] = 2208988800
    result['acls']['allowed-acls'] = list(CAPTION_ACLS)
    return result

def unchanged_policies(root):
    directory = root / 'vendor/ohemu/virt/preinstall-config'; result = {}
    for name, expected in [('install_list_capability.json', CAPABILITY), ('install_list_permissions.json', GRANTS)]:
        value = json.loads(read(directory / name), object_pairs_hook=unique)
        rows = value['install_list'] if isinstance(value, dict) else value
        actual = [row for row in rows if row.get('bundleName') == 'com.ohos.systemui']
        if not same_json(actual, [expected]): raise ValueError('original SystemUI policy changed: ' + name)
        result[name] = actual[0]
    selected_entry(read(directory / 'install_list.json'), 'com.ohos.systemui')
    return result

def ensure_runtime_fixes(root):
    """Apply the five reviewed runtime diffs, accepting each patched block as-is."""
    fixes = (
        (PROJECT + '/common/src/main/ets/default/SingleInstanceHelper.ts', (
            ("""const AUDIO_MANAGER_KEY = 'MultiMediaAudioManager';

export default function createOrGet<T>(objectClass: { new(): T }, storageKey: string): T {
  if (!globalThis[storageKey]) {
    globalThis[storageKey] = new objectClass();
    Log.showInfo(TAG, `Create key of ${storageKey}`);
  }
  return globalThis[storageKey];
}
""", """const AUDIO_MANAGER_KEY = '__systemui_source__MultiMediaAudioManager';

export default function createOrGet<T>(objectClass: { new(): T }, storageKey: string): T {
  const realKey = '__systemui_source__' + storageKey;
  if (!globalThis[realKey]) {
    globalThis[realKey] = new objectClass();
    Log.showInfo(TAG, `Create key of ${storageKey}`);
  }
  return globalThis[realKey];
}
"""),
        )),
        (PROJECT + '/common/src/main/ets/default/WindowManager.ts', (
            ("""const SYSTEM_WINDOW_TYPE_MAP: { [key in WindowType]: Window.WindowType } = {
  SystemUi_StatusBar: Window.WindowType.TYPE_STATUS_BAR,
  SystemUi_NavigationBar: Window.WindowType.TYPE_NAVIGATION_BAR,
  SystemUi_DropdownPanel: Window.WindowType.TYPE_PANEL,
  SystemUi_NotificationPanel: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_ControlPanel: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_VolumePanel: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_BannerNotice: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_SplitBar: Window.WindowType.TYPE_DIVIDER,
  SystemUi_PrivacyIndicator: Window.WindowType.TYPE_VOLUME_OVERLAY
};
""", """const SYSTEM_WINDOW_TYPE_MAP: { [key in WindowType]: Window.WindowType } = {
  SystemUi_StatusBar: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_NavigationBar: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_DropdownPanel: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_NotificationPanel: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_ControlPanel: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_VolumePanel: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_BannerNotice: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_SplitBar: Window.WindowType.TYPE_VOLUME_OVERLAY,
  SystemUi_PrivacyIndicator: Window.WindowType.TYPE_VOLUME_OVERLAY
};
"""),
            ("""    await winHandle.moveTo(rect.left, rect.top);
    await winHandle.resetSize(rect.width, rect.height);
""", """    await winHandle.moveTo(Math.round(rect.left || 0), Math.round(rect.top || 0));
    await winHandle.resetSize(Math.max(1, Math.round(rect.width || 1)), Math.max(1, Math.round(rect.height || 1)));
"""),
            ("""  async resetSizeWindow(name: WindowType, rect: Rect): Promise<void> {
    let window = await Window.find(name);
    await window.moveTo(rect.left, rect.top);
    await window.resetSize(rect.width, rect.height);
""", """  async resetSizeWindow(name: WindowType, rect: Rect): Promise<void> {
    let window = await Window.find(name);
    await window.moveTo(Math.round(rect.left || 0), Math.round(rect.top || 0));
    if (Math.round(rect.width || 0) > 0 && Math.round(rect.height || 0) > 0) {
      await window.resetSize(Math.round(rect.width), Math.round(rect.height));
    }
"""),
            ("""  async moveTo(name: WindowType, rect: Rect): Promise<void> {
    Log.showInfo(TAG, `moveTo window[${name}] success, rect: ${JSON.stringify(rect)}.`);
    let window = await Window.find(name);
    await window.moveTo(rect.left, rect.top);
  }
""", """  async moveTo(name: WindowType, rect: Rect): Promise<void> {
    Log.showInfo(TAG, `moveTo window[${name}] success, rect: ${JSON.stringify(rect)}.`);
    let window = await Window.find(name);
    await window.moveTo(Math.round(rect.left || 0), Math.round(rect.top || 0));
  }
"""),
            ("""  async showWindow(name: WindowType): Promise<void> {
    let window = await Window.find(name);
    await window.show();
""", """  async showWindow(name: WindowType): Promise<void> {
    let window = await Window.find(name);
    if (name !== WindowType.PRIVACY_INDICATOR && name !== WindowType.NAVIGATION_BAR) {
      await window.show();
    }
"""),
        )),
        ('foundation/bundlemanager/bundle_framework/services/bundlemgr/src/bundle_mgr_service_event_handler.cpp', (
            ('    dataMgr->SetApplicationEnabled(ServiceConstants::SYSTEM_UI_BUNDLE_NAME, 0, !sceneBoardEnable,\n',
             '    dataMgr->SetApplicationEnabled(ServiceConstants::SYSTEM_UI_BUNDLE_NAME, 0, true,\n'),
        )),
        ('foundation/window/window_manager/interfaces/kits/napi/window_runtime/window_manager_napi/js_window_manager.cpp', (
            ("""    if (resultValue >= static_cast<uint32_t>(ApiWindowType::TYPE_BASE) &&
        resultValue < static_cast<uint32_t>(ApiWindowType::TYPE_END)) {
        winType = JS_TO_NATIVE_WINDOW_TYPE_MAP.at(static_cast<ApiWindowType>(resultValue));
    } else {
""", """    if (resultValue >= static_cast<uint32_t>(ApiWindowType::TYPE_BASE) &&
        resultValue < static_cast<uint32_t>(ApiWindowType::TYPE_END)) {
        winType = JS_TO_NATIVE_WINDOW_TYPE_MAP.at(static_cast<ApiWindowType>(resultValue));
    } else if (resultValue >= static_cast<uint32_t>(WindowType::SYSTEM_WINDOW_BASE) &&
        resultValue < static_cast<uint32_t>(WindowType::SYSTEM_WINDOW_END)) {
        winType = static_cast<WindowType>(resultValue);
    } else {
"""),
            ("""        if (winType >= static_cast<uint32_t>(ApiWindowType::TYPE_BASE) &&
            winType < static_cast<uint32_t>(ApiWindowType::TYPE_END)) {
            option.SetWindowType(JS_TO_NATIVE_WINDOW_TYPE_MAP.at(static_cast<ApiWindowType>(winType)));
        } else {
""", """        if (winType >= static_cast<uint32_t>(ApiWindowType::TYPE_BASE) &&
            winType < static_cast<uint32_t>(ApiWindowType::TYPE_END)) {
            option.SetWindowType(JS_TO_NATIVE_WINDOW_TYPE_MAP.at(static_cast<ApiWindowType>(winType)));
        } else if (winType >= static_cast<uint32_t>(WindowType::SYSTEM_WINDOW_BASE) &&
            winType < static_cast<uint32_t>(WindowType::SYSTEM_WINDOW_END)) {
            option.SetWindowType(static_cast<WindowType>(winType));
        } else {
"""),
        )),
        ('foundation/window/window_manager/wm/src/window_scene_session_impl.cpp', (
            ("""const std::unordered_set<WindowType> INVALID_SCB_WINDOW_TYPE = {
    WindowType::WINDOW_TYPE_WALLPAPER,
    WindowType::WINDOW_TYPE_DESKTOP,
    WindowType::WINDOW_TYPE_DOCK_SLICE,
    WindowType::WINDOW_TYPE_STATUS_BAR,
    WindowType::WINDOW_TYPE_KEYGUARD,
    WindowType::WINDOW_TYPE_NAVIGATION_BAR,
    WindowType::WINDOW_TYPE_LAUNCHER_RECENT,
    WindowType::WINDOW_TYPE_LAUNCHER_DOCK
};
""", """const std::unordered_set<WindowType> INVALID_SCB_WINDOW_TYPE = {
    WindowType::WINDOW_TYPE_WALLPAPER,
    WindowType::WINDOW_TYPE_DESKTOP,
    WindowType::WINDOW_TYPE_KEYGUARD,
    WindowType::WINDOW_TYPE_LAUNCHER_RECENT,
    WindowType::WINDOW_TYPE_LAUNCHER_DOCK
};
"""),
        )),
    )
    pending = []
    for relative, blocks in fixes:
        path = root / relative; before = read(path); after = before
        # The pinned NAPI source uses CRLF; retain the original source bytes.
        newline = b'\r\n' if b'\r\n' in before else b'\n'
        for old, new in blocks:
            old = old.encode().replace(b'\n', newline)
            new = new.encode().replace(b'\n', newline)
            pair = after.count(old), after.count(new)
            if pair == (1, 0): after = after.replace(old, new, 1)
            elif pair != (0, 1):
                raise ValueError('unknown/duplicate SystemUI runtime source: ' + relative)
        pending.append((path, before, after))
    # Validate every file before writing any of the runtime fixes.
    if any(read(path) != before for path, before, _ in pending):
        raise ValueError('SystemUI runtime source changed before write')
    for path, before, after in pending:
        if before != after: replace(path, after)

def source_ready(root):
    component('systemui/source_provider').validate(root, require_patched=True)
    from guarded_source_vector579 import load, heads, vector
    consent = PATCH_ROOT / 'common/applications/standard/systemui/playback_capture_consent579'
    consent_sources = load(consent)
    heads(root, consent_sources)
    if vector(root, consent_sources) != 'final':
        raise ValueError('complete actual playback-consent source required for SystemUI ACLs')
    live = component('systemui/screen_capture_live_view')
    live.validate(root, require_patched=True); live.prerequisites(root)
    hap = read(root / 'applications/standard/hap/BUILD.gn')
    if not hap_state(hap) or digest(normalize_hap_build(hap)) != LEGACY_HAP_SHA:
        raise ValueError('exact reviewed complete HAP graph with source SystemUI required')
    if digest(read(root / 'applications/standard/hap/SystemUI-ScreenLock.hap')) != \
            '7e6d99cf44f67a421e20ef2d7a86084d52b45dc1fc4c0ea0902dd4ede47c2cc9':
        raise ValueError('existing independent ScreenLock changed')
    import json5
    for path in (root / PROJECT).rglob('oh-package.json5'):
        if any(part in ('oh_modules', 'node_modules', 'build', '.hvigor') for part in path.relative_to(root / PROJECT).parts): continue
        value = json5.loads(read(path).decode(), allow_duplicate_keys=False)
        for group in ('dependencies', 'devDependencies', 'dynamicDependencies'):
            for name, uri in value.get(group, {}).items():
                if not isinstance(uri, str) or not uri.startswith('file:'): raise ValueError('nonlocal SystemUI dependency: ' + name)
                target = path.parent / uri[5:]
                if not target.is_dir() or not target.resolve().is_relative_to(root / PROJECT):
                    raise ValueError('missing/escaped SystemUI source dependency: ' + name)
    policies = unchanged_policies(root)
    ensure_runtime_fixes(root)
    return policies

def verify_profile(path, desired, issuer_fingerprint, scratch):
    signer = scratch / 'profile-issuer.pem'; actual = cms(path, signer); signers = certificates(read(signer))
    if actual != desired or len(signers) != 1 or certificate_fingerprint(signers[0]) != issuer_fingerprint:
        raise ValueError('SystemUI renewed profile/original OS issuer changed')
    return actual

def prepare(root, cache):
    source_ready(root); project, dist, raw, _, issuer = original_inputs(root)
    profile = project / 'signature/systemui.p7b'; before = read(profile); cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='systemui-profile-', dir=cache) as temporary:
        scratch = Path(temporary); original = scratch / 'original.p7b'; original.write_bytes(raw)
        desired = desired_profile(cms(original)); fingerprint = certificate_fingerprint(issuer[-1])
        resign = before == raw
        if before != raw:
            # Authenticate either complete renewed predecessor before upgrading.
            prior = copy.deepcopy(desired)
            prior['acls']['allowed-acls'] = list(ACLS)
            prior_caption = copy.deepcopy(desired)
            prior_caption['acls']['allowed-acls'] = ACLS + [
                'ohos.permission.MANAGE_AUDIO_CONFIG', 'ohos.permission.GET_BUNDLE_INFO_PRIVILEGED']
            observed = cms(profile)
            if observed == desired:
                verify_profile(profile, desired, fingerprint, scratch)
            elif observed in (prior, prior_caption):
                verify_profile(profile, observed, fingerprint, scratch)
                resign = True
            else:
                raise ValueError('unknown retained SystemUI profile preserved')
        if resign:
            template, signed = scratch / 'profile.json', scratch / 'renewed.p7b'
            template.write_text(json.dumps(desired, indent=2) + '\n')
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'],
                capture_output=True, check=True, timeout=120)
            verify_profile(signed, desired, fingerprint, scratch)
            if read(profile) != before: raise ValueError('SystemUI profile changed before installation')
            replace(profile, read(signed))
    return {'scope': 'fixed source/profile readiness ONLY; GN still must compile/sign actual modules',
        'source_revision': REVISION, 'profile_sha256': digest(read(profile)), 'signer': SIGNATURE,
        'APL_vendor_policies_unchanged': True, 'original_acls': list(ACLS),
        'desired_acls': list(CAPTION_ACLS), 'actual_compilation': False,
        'runtime_validated': False, 'first_artifact_behavior_gate_passed': False}

def verify(root):
    policies = source_ready(root); project, _, raw, _, issuer = original_inputs(root)
    with tempfile.TemporaryDirectory(prefix='systemui-profile-verify-') as temporary:
        scratch = Path(temporary); original = scratch / 'original.p7b'; original.write_bytes(raw)
        actual = verify_profile(project / 'signature/systemui.p7b', desired_profile(cms(original)),
                                certificate_fingerprint(issuer[-1]), scratch)
    return {'profile': actual, 'policies': policies}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path)
    parser.add_argument('--apply-hap', action='store_true')
    parser.add_argument('--prepare-profile', action='store_true')
    args = parser.parse_args(); root = args.source_root.resolve()
    if args.apply_hap:
        if args.prepare_profile or args.cache_root: raise ValueError('separate HAP application API required')
        result = apply_hap(root)
    elif args.prepare_profile:
        if args.cache_root is None: raise ValueError('owned preparation cache required')
        result = prepare(root, args.cache_root.resolve())
    else: result = verify(root)
    print(json.dumps(result, indent=2))
