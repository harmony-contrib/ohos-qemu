"""Fixed two-HAP overlays for the original platform builder/signature path."""
from pathlib import Path
import json
import re

ASSETS = Path(__file__).with_name('settings_idle579')
BUNDLES = {role: 'org.harmonycontrib.settingsidle579.' + role for role in ('system', 'foreign')}


def check(case, role):
    if case != 'conditional' or role not in BUNDLES:
        raise ValueError('Fixed real conditional-service fixture required')


def bundle(case, role):
    check(case, role)
    return BUNDLES[role]


def module_fields(case, role, parameters=None):
    check(case, role)
    service = 'IdleService' if role == 'system' else 'PeerService'
    return {'requestPermissions': [],
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
            'exported': True, 'launchType': 'singleton'}],
        'extensionAbilities': [{'name': service, 'srcEntry': './ets/audit/' + service + '.ets',
            'type': 'service', 'exported': role == 'foreign'}]}


def source_files(case, run, role, parameters=None):
    check(case, role)
    if re.fullmatch('[a-f0-9]{32}', run or '') is None or parameters != {}:
        raise ValueError('Actual parent run ID and fixed no-options recipe required')
    mapping = {'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
        'Index.ets': 'entry/src/main/ets/pages/Index.ets',
        'IdleService.ets': 'entry/src/main/ets/audit/IdleService.ets',
        'PeerService.ets': 'entry/src/main/ets/audit/PeerService.ets',
        'NativeFixture.ets': 'entry/src/main/ets/audit/NativeFixture.ets',
        'Journal.ets': 'entry/src/main/ets/audit/Journal.ets',
        'ParameterBoundary.js': 'entry/src/main/ets/audit/ParameterBoundary.js',
        'native/index.d.ts': 'entry/src/main/cpp/types/libsettings_idle579/index.d.ts'}
    out = {}
    for source, destination in mapping.items():
        text = (ASSETS / source).read_text()
        if source == 'Journal.ets':
            markers = {'__SETTINGS_IDLE579_RUN__': run, '__SETTINGS_IDLE579_BUNDLE__': BUNDLES[role],
                       '__SETTINGS_IDLE579_SERVICE__': 'IdleService' if role == 'system' else 'PeerService'}
            for marker, value in markers.items():
                if text.count(marker) != 1:
                    raise ValueError('Exact source markers required')
                text = text.replace(marker, value)
        out[destination] = text
    out['entry/src/main/resources/base/profile/main_pages.json'] = '{"src":["pages/Index"]}\n'
    out['entry/oh-package.json5'] = json.dumps({'name': 'entry', 'version': '1.0.0',
        'dependencies': {'libsettings_idle579.so': 'file:./src/main/cpp/types/libsettings_idle579'}}) + '\n'
    out['entry/src/main/cpp/types/libsettings_idle579/oh-package.json5'] = json.dumps({
        'name': 'libsettings_idle579.so', 'version': '1.0.0', 'types': './index.d.ts'}) + '\n'
    return out


def native_artifact_destination():
    # The parent copies its platform-built actual ELF BEFORE compile/sign. A Ref
    # cannot select code or a destination. Both roles consume identical bytes.
    return 'entry/libs/arm64-v8a/libsettings_idle579.so'


def configure_profile(case):
    check(case, 'system')
    def configure(profile, role, udid, compiled):
        check(case, role)
        if re.fullmatch('[a-fA-F0-9]{64}', udid or '') is None or compiled['app']['bundleName'] != BUNDLES[role]:
            raise ValueError('Actual same-boot UDID/compiled bundle required')
        actual = compiled['module']; wanted = module_fields(case, role)
        extensions = actual.get('extensionAbilities', []); abilities = actual.get('abilities', [])
        if actual.get('requestPermissions', []) != [] or len(extensions) != 1 or len(abilities) != 1:
            raise ValueError('Exact actual SERVICE fixture manifest required')
        if not all(extensions[0].get(key) == value for key, value in wanted['extensionAbilities'][0].items()) or \
                extensions[0].get('permissions') or abilities[0].get('name') != 'EntryAbility' or \
                abilities[0].get('launchType') != 'singleton':
            raise ValueError('Actual extension type/identity/visibility or singleton differs')
        profile['bundle-info']['bundle-name'] = BUNDLES[role]
        profile['bundle-info']['apl'] = 'system_core'
        profile['bundle-info']['app-feature'] = 'hos_system_app'
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = []
        profile['permissions']['restricted-permissions'] = []
        return profile
    return configure
