"""Fixed system-provider source inputs for root's original product preparation.

This module never builds, signs, downloads, installs or starts any resource.
The resulting real signed HAP is a selected package input to the platform GN
entry; runtime rejects a data-installed demonstration in place of that provider.
"""
from pathlib import Path
import json
import re

BUNDLE = 'com.ohos.vassistant'
ABILITY = 'AiCaptionServiceExtAbility'
PERMISSIONS = ['ohos.permission.MANAGE_SETTINGS', 'ohos.permission.SYSTEM_FLOAT_WINDOW',
               'ohos.permission.WRITE_ACCESSIBILITY_CONFIG', 'ohos.permission.MANAGE_SECURE_SETTINGS']
ROOT = Path(__file__).with_name('livecaptions579_provider')


def bundle(case, role):
    if (case, role) != ('english', 'provider'):
        raise ValueError('one fixed actual English-caption system provider required')
    return BUNDLE


def module_fields(case, role, parameters=None):
    bundle(case, role)
    return json.loads((ROOT / 'entry/src/main/module.json5').read_text())['module']


def source_files(case, run, role, parameters=None):
    bundle(case, role)
    if parameters != {} or re.fullmatch('[a-f0-9]{32}', run or '') is None:
        raise ValueError('fixed product preparation parameters required')
    names = ('entry/src/main/ets/common/CaptionActions.ets', 'entry/src/main/ets/common/CaptionProtocol.ets',
        'entry/src/main/ets/common/CaptionTrace.ets', 'entry/src/main/ets/common/CaptionSession.ets',
        'entry/src/main/ets/common/ModelProfile.ets', 'entry/src/main/ets/pages/Captions.ets',
        'entry/src/main/ets/service/AiCaptionServiceExtAbility.ets', 'entry/src/main/ets/workers/CaptionWorker.ets',
        'entry/src/main/module.json5', 'entry/src/main/resources/base/profile/main_pages.json',
        'entry/build-profile.json5', 'entry/oh-package.json5')
    return {name: (ROOT / name).read_text() for name in names}


def configure_profile(case):
    bundle(case, 'provider')
    def configure(profile, role, udid, compiled):
        bundle(case, role)
        if compiled['app']['bundleName'] != BUNDLE or re.fullmatch('[a-fA-F0-9]{64}', udid or '') is None:
            raise ValueError('real original product signer identity differs')
        actual = compiled['module']; wanted = module_fields(case, role)
        if actual.get('requestPermissions') != wanted['requestPermissions'] or actual.get('abilities', []) or \
           len(actual.get('extensionAbilities', [])) != 1 or actual['extensionAbilities'][0].get('name') != ABILITY or \
           actual['extensionAbilities'][0].get('type') != 'service' or actual['extensionAbilities'][0].get('permissions') != ['ohos.permission.WRITE_ACCESSIBILITY_CONFIG']:
            raise ValueError('real fixed provider type/permissions differs')
        profile['bundle-info'].update({'bundle-name': BUNDLE, 'apl': 'system_basic', 'app-feature': 'hos_system_app'})
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = list(PERMISSIONS)
        profile['permissions']['restricted-permissions'] = list(PERMISSIONS)
        return profile
    return configure


def asset_destinations():
    return {'encoder': 'entry/src/main/resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-encoder.int8.onnx',
        'decoder': 'entry/src/main/resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-decoder.int8.onnx',
        'tokens': 'entry/src/main/resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-tokens.txt',
        'vad': 'entry/src/main/resources/rawfile/silero_vad.onnx',
        'notices': 'entry/src/main/resources/rawfile/LIVE_CAPTIONS_NOTICES.txt',
        'har': 'sherpa_onnx-1.11.2.har'}


def gn_entry():
    return {'source': 'applications/standard/hap/vassistant_livecaptions579.hap',
        'label': '//applications/standard/hap:vassistant_livecaptions579',
        'install_dir': 'app/VAssistant', 'part_name': 'prebuilt_hap', 'subsystem_name': 'applications'}
