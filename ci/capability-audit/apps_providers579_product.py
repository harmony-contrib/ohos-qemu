"""Pure candidate generation against root-exported actual after-source.

No apply/CLI, builder, subprocess, signer or source-tree mutation. Root reviews
the exact before/after bytes, serializes the independent component and hooks it
into the next batched representative attempt. Runtime acceptance stays false.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile

INSTALL = 'vendor/ohemu/virt/preinstall-config/install_list.json'
CAPABILITY = 'vendor/ohemu/virt/preinstall-config/install_list_capability.json'
PREIMAGE = {
    INSTALL: 'c373f96100e8b7263bd51d057f17b695d1a48890c3c48bc84f458a026b6c9ea5',
    CAPABILITY: '2ce081c3d8b929070f4ced1a46298c7d019afcba0e83a6c1e6973cd1df653701'}
PROVIDERS = {
    'com.ohos.locationdialog': ('/system/app/LocationDialog',
        ('LocationPrivacyExtAbility', 'WifiUIExtAbility', 'WifiServiceAbility', 'HotSpotServiceAbility')),
    'com.wifiservice.portallogin': ('/system/app/com.wifiservice.portallogin', ('EntryAbility',)),
    'com.hmos.mediacontroller': ('/system/app/com.hmos.mediacontroller', ('UIExtAbility', 'AVVolumeExtension'))}
MEDIA_HAP = '1118c178e106bfd49bcff5de099daa8f24166595acac24941077e4cde60cd2d3'
CAST_CONSUMER = 'foundation/multimedia/av_session/frameworks/js/napi/session/src/napi_avcast_picker_helper.cpp'
CAST_PREIMAGE = '5628c4663bd33525aaa624491e207a01a8b742360fb8b6b4a91a32df0cb548dc'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def raw(ref):
    require(type(ref) is dict and set(ref) == {'path', 'sha256'}, 'actual raw Ref required')
    path = Path(ref['path'])
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'absolute regular raw file required')
    body = path.read_bytes()
    require(hashlib.sha256(body).hexdigest() == ref['sha256'], 'actual raw bytes changed')
    return body


def candidates(source_root, signer_records):
    """Return exact product bytes; execute only in root's source preparation.

    signer_records[bundle] has hap:Ref, verify_stdout:Ref, verify_stderr:Ref,
    verify_argv:[str,...], verify_exit:int and verified_profile:Ref. They must
    come from real cryptographic verify-app of the exact delivered provider.
    Public certificates are used only for that exact bundle privilege entry.
    """
    source = Path(source_root)
    require(set(signer_records) == set(PROVIDERS), 'three exact actual provider signer records required')
    before = {name: (source / name).read_bytes() for name in PREIMAGE}
    require(all(hashlib.sha256(body).hexdigest() == PREIMAGE[name] for name, body in before.items()),
            'actual current product predecessor differs; request root rebase, never overwrite')
    signatures = {}
    for bundle, record in signer_records.items():
        hap = raw(record['hap'])
        output = raw(record['verify_stdout']).decode()
        raw(record['verify_stderr'])
        require(type(record['verify_exit']) is int and record['verify_exit'] == 0 and
                type(record['verify_argv']) is list and 'verify-app' in record['verify_argv'],
                'actual cryptographic verify-app argv/status required')
        # Use the verified signing leaf, never a guessed signer/profile field.
        leaf = re.search(r'certificate\s*#0\b(?:(?!certificate\s*#\d).)*?SHA256:\s*([A-Fa-f0-9:]{64,95})', output, re.S)
        require(leaf is not None, 'actual verify-app leaf fingerprint missing')
        fingerprint = leaf[1].replace(':', '').upper()
        require(re.fullmatch('[0-9A-F]{64}', fingerprint), 'actual SHA256 signer required')
        profile = json.loads(raw(record['verified_profile']))
        require(profile['bundle-info']['bundle-name'] == bundle and
                profile['bundle-info']['app-feature'] == 'hos_system_app', 'actual system-provider profile differs')
        with zipfile.ZipFile(record['hap']['path']) as archive:
            module = json.loads(archive.read('module.json'))
            require(archive.read('ets/modules.abc'), 'actual provider ABC missing')
        require(module['app']['bundleName'] == bundle, 'actual provider compiled bundle differs')
        names = {entry['name'] for key in ('abilities', 'extensionAbilities') for entry in module['module'].get(key, [])}
        require(set(PROVIDERS[bundle][1]) <= names, 'actual delivered provider lacks its required entrypoint')
        if bundle == 'com.hmos.mediacontroller':
            require(hashlib.sha256(hap).hexdigest() == MEDIA_HAP, 'unreviewed MediaController payload')
        signatures[bundle] = fingerprint
    install = json.loads(before[INSTALL])
    require(type(install.get('install_list')) is list, 'exact upstream preinstall document required')
    paths = [item['app_dir'] for item in install['install_list']]
    require(len(paths) == len(set(paths)), 'duplicate existing preinstall entry')
    for bundle, (directory, _names) in PROVIDERS.items():
        require(directory not in paths, 'expected unactivated provider already changed; root must inspect new predecessor')
        install['install_list'].append({'app_dir': directory, 'removable': False})
    capabilities = json.loads(before[CAPABILITY])
    # The actual source schema is an object with a single provider array. Do
    # not silently accept a guessed schema or grant unrelated privilege flags.
    arrays = [value for value in capabilities.values() if type(value) is list]
    require(len(arrays) == 1, 'actual privilege-config array is ambiguous')
    entries = arrays[0]
    require(not any(item.get('bundleName') in PROVIDERS for item in entries), 'provider privilege predecessor changed')
    for bundle in PROVIDERS:
        entries.append({'bundleName': bundle, 'app_signature': [signatures[bundle]],
                        'allowAppUsePrivilegeExtension': True})
    return {'scope': 'exact_product_candidate_NOT_build_or_runtime', 'runtime_pass': False,
        'first_artifact_behavior_gate_passed': False,
        'targets': {name: {'before': body, 'after': (json.dumps(value, indent=2) + '\n').encode()}
                    for name, body, value in ((INSTALL, before[INSTALL], install),
                                              (CAPABILITY, before[CAPABILITY], capabilities))},
        'signer_records': signer_records,
        'not_included': ['AVCast protocol adapter is an independent cast_candidate component',
                         'AVInputCastPickerAbility absent from reviewed MediaController module',
                         'Camera already has actual SceneBoard picker payload/build/preinstall path']}


def cast_candidate(source_root):
    """Exact complete-HAP NAPI adapter with per-session event delivery guards.

    The two implementation fragments are reviewed source, never JSON-selected
    executable paths. Both actual source predecessors are pinned. Remote proxy
    readiness is distinct from the provider's actual state=0 panel notification.
    """
    header = 'foundation/multimedia/av_session/frameworks/js/napi/session/include/napi_avcast_picker_helper.h'
    source = Path(source_root)
    before = {CAST_CONSUMER: (source / CAST_CONSUMER).read_bytes(), header: (source / header).read_bytes()}
    require(hashlib.sha256(before[CAST_CONSUMER]).hexdigest() == CAST_PREIMAGE and
            hashlib.sha256(before[header]).hexdigest() == 'e99955010b9e4e071077fed66724234dc98d61986e45c6e7d73b4ed3dd869ab6',
            'actual NAPI source/header predecessor changed')
    assets = Path(__file__).with_name('apps_providers579')
    text = before[CAST_CONSUMER].decode()
    changes = [
        ('static const std::string ABILITY_WANT_ELEMENT_NAME = "com.ohos.mediacontroller";',
         'static const std::string ABILITY_WANT_ELEMENT_NAME = "com.hmos.mediacontroller";'),
        ('std::string targetType = "sysPicker/mediaControl";', 'std::string targetType = "sys/commonUI";'),
        ('request.SetParam("isAVCastPickerHelper", true);',
         'request.SetParam("isAVCastPickerHelper", true);\n    request.SetParam("isCustomPicker", false);'),
        ('config.isProhibitBack = true;', 'config.isProhibitBack = false;')]
    for old, new in changes:
        require(text.count(old) == 1, 'exact consumer request source changed')
        text = text.replace(old, new)
    marker = '    static const std::string callBackName = "NapiAVCastPickerHelper::SelectAVPicker";'
    start = text.index(marker, text.index('Ace::ModalUIExtensionCallbacks NapiAVCastPickerHelper::CreateExtensionCallback('))
    end = text.index('\n}\n\nnapi_value NapiAVCastPickerHelper::ResetCommunicationDevice', start)
    text = text[:start] + (assets / 'AVCastSessionCallbacks.inc').read_text() + text[end:]
    start = text.index('void NapiAVCastPickerHelper::HandleEvent(')
    end = text.index('\nnapi_status NapiAVCastPickerHelper::AddCallback(', start)
    text = text[:start] + (assets / 'AVCastHandleEvent.inc').read_text() + text[end:]
    htext = before[header].decode()
    for old, new in [
        ('#include "napi/native_api.h"', '#include <atomic>\n#include <cstdint>\n#include <memory>\n\n#include "napi/native_api.h"'),
        ('    std::shared_ptr<bool> isValid_;', '    std::shared_ptr<bool> isValid_;\n'
         '    std::shared_ptr<std::atomic<uint64_t>> pickerGeneration_ = std::make_shared<std::atomic<uint64_t>>(0);'),
        ('void HandleEvent(int32_t event, std::string callBackName, const T& param);',
         'void HandleEvent(int32_t event, std::string callBackName, const T& param, uint64_t generation);')]:
        require(htext.count(old) == 1, 'exact consumer header source changed')
        htext = htext.replace(old, new)
    return {'scope': 'actual_HAP_per_session_source_candidate_NOT_runtime', 'runtime_pass': False,
        'first_artifact_behavior_gate_passed': False,
        'targets': {CAST_CONSUMER: {'before': before[CAST_CONSUMER], 'after': text.encode()},
                    header: {'before': before[header], 'after': htext.encode()}},
        'provider_hap_sha256': MEDIA_HAP,
        'provider_abc_sha256': '51192c8a4ed177b5c11a411e38342abae712468d26f386cd94ddf7b0fbaf44dc',
        'not_included': ['Taihe/static helper independently pinned adapter and actual runtime required',
                         'AVInputCastPickerAbility absent; do not relabel the complete output-cast provider']}


def volume_candidate(source_root):
    relative = 'foundation/multimedia/av_session/avvolumepanel/avvolumepanel.js'
    before = (Path(source_root) / relative).read_bytes()
    require(hashlib.sha256(before).hexdigest() == '40ce55a7070336ed768cdea5ef30b1cd05dab5242ecd5bc79cfd0809daf20885',
            'actual AVVolumePanel JS predecessor changed')
    old = b'this.__isDisabledByPanelLimit.purgeDependencyOnElmtId(a11);'
    require(before.count(old) == 1, 'one actual undefined identifier required')
    return {'scope': 'exact_actual_component_cleanup_candidate_NOT_runtime', 'runtime_pass': False,
        'first_artifact_behavior_gate_passed': False,
        'targets': {relative: {'before': before, 'after': before.replace(old,
            b'this.__isDisabledByPanelLimit.purgeDependencyOnElmtId(m);')}}}
