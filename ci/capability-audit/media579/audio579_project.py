"""Finite caller overlay for the original API26 SDK/signer; never runs tools."""
from pathlib import Path
import re
import json

HERE = Path(__file__).resolve().parent
ROLES = ('ordinary', 'system', 'denied', 'observer')
PERMISSIONS = ('ohos.permission.MICROPHONE', 'ohos.permission.MANAGE_SYSTEM_AUDIO_EFFECTS',
               'ohos.permission.MANAGE_INTELLIGENT_VOICE', 'ohos.permission.CAPTURE_AUDIO_OUTPUT')


def need(ok, message):
    if not ok: raise ValueError(message)


def bundle(case, role):
    need(case == 'original-audio10' and role in ROLES, 'fixed Audio10 case and role')
    return 'org.harmonycontrib.media579.audio.' + role


def permissions(role):
    need(role in ROLES, 'four original caller roles')
    if role == 'ordinary': return ['ohos.permission.MICROPHONE']
    if role == 'denied': return []
    return list(PERMISSIONS)


def module_fields(case, role, parameters=None):
    bundle(case, role)
    need(parameters in (None, {}), 'no executable, permission or action from input data')
    return dict(requestPermissions=[dict(name=p, reason='$string:audio579_permission',
        usedScene=dict(abilities=['EntryAbility'], when='inuse')) for p in permissions(role)],
        abilities=[dict(name='EntryAbility', srcEntry='./ets/entryability/EntryAbility.ets', exported=True,
                        launchType='singleton')], extensionAbilities=[])


def configure_profile(case):
    need(case == 'original-audio10', 'one fixed supplemental normal SDK/signing case')
    def configure(profile, role, udid, compiled):
        need(role in ROLES and re.fullmatch('[a-fA-F0-9]{64}', udid or '') and
             compiled['app']['bundleName'] == bundle(case, role), 'actual compiled fixed bundle and same guest UDID')
        fields = compiled['module']; wanted = module_fields(case, role)
        need([item['name'] for item in fields.get('requestPermissions', [])] == permissions(role) and
             fields.get('extensionAbilities', []) == [] and len(fields.get('abilities', [])) == 1 and
             fields['abilities'][0]['name'] == 'EntryAbility' and fields['abilities'][0]['launchType'] == 'singleton' and
             fields['abilities'][0]['exported'] is True, 'actual compiled four-role permissions and singleton entry')
        profile['bundle-info'].update({'bundle-name': bundle(case, role),
            'apl': 'normal' if role == 'ordinary' else 'system_core',
            'app-feature': 'hos_normal_app' if role == 'ordinary' else 'hos_system_app'})
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = permissions(role)
        profile['permissions']['restricted-permissions'] = permissions(role)
        return profile
    return configure


def source_files(case, run, role, parameters=None):
    bundle(case, role)
    need(re.fullmatch('[a-f0-9]{32}', run) and parameters in (None, {}), 'actual fixed nonce caller overlay')
    names = {'AudioAudit.ets': 'entry/src/main/ets/entryability/AudioAudit.ets',
             'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
             'Index.ets': 'entry/src/main/ets/pages/Index.ets'}
    result = {}
    for name, target in names.items():
        text = (HERE / 'audio579' / name).read_text()
        if name == 'AudioAudit.ets':
            need(text.count('__AUDIO579_RUN__') == text.count('__AUDIO579_ROLE__') == 1, 'fixed caller source markers')
            text = text.replace('__AUDIO579_RUN__', run).replace('__AUDIO579_ROLE__', role)
        result[target] = text
    result['entry/src/main/resources/base/profile/main_pages.json'] = '{"src":["pages/Index"]}\n'
    result['entry/src/main/resources/base/element/audio579.json'] = '{"string":[{"name":"audio579_permission","value":"Validate actual QEMU audio data and restore audio state"}]}\n'
    result['entry/src/main/cpp/types/libaudio579midi/index.d.ts'] = 'export const run: (run: string, operation: string, filesDir: string) => boolean;\n'
    result['entry/src/main/cpp/types/libaudio579midi/oh-package.json5'] = json.dumps({
        'name': 'libaudio579midi.so', 'version': '1.0.0', 'types': './index.d.ts'}) + '\n'
    result['entry/oh-package.json5'] = json.dumps({'name': 'entry', 'version': '1.0.0',
        'dependencies': {'libaudio579midi.so': 'file:./src/main/cpp/types/libaudio579midi'}}) + '\n'
    return result


def prepare_native(io, project):
    from audio579_native import prepare_native as build
    return build(io, project)


def verify_native_hap(hap, native):
    from audio579_native import verify_native_hap as verify
    return verify(hap, native)


def configure_profile(case):
    def configure(profile, role, udid, compiled):
        wanted = bundle(case, role)
        need(re.fullmatch('[A-Fa-f0-9]{64}', udid) and compiled['app']['bundleName'] == wanted,
             'real same-boot signed caller and UDID')
        need([row['name'] for row in compiled['module'].get('requestPermissions', [])] == permissions(role),
             'actual compiled permission set')
        normal = role == 'ordinary'
        profile['bundle-info'].update({'bundle-name': wanted, 'apl': 'normal' if normal else 'system_core',
            'app-feature': 'hos_normal_app' if normal else 'hos_system_app'})
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = permissions(role)
        profile['permissions']['restricted-permissions'] = permissions(role)
        return profile
    return configure
