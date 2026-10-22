"""Fixed real HAP roles for L22, selected by the original serialized builder."""
from pathlib import Path
import re
from capability578_owned_io import require

CASE = 'whole-transactions'
ROLES = ('system', 'ordinary', 'denied')
ASSETS = Path(__file__).with_name('telephony579')
PUBLIC = ('ohos.permission.INTERNET', 'ohos.permission.GET_NETWORK_INFO')
SYSTEM = PUBLIC + ('ohos.permission.GET_TELEPHONY_STATE',
    'ohos.permission.SET_TELEPHONY_STATE', 'ohos.permission.PLACE_CALL',
    'ohos.permission.ANSWER_CALL', 'ohos.permission.SEND_MESSAGES')


def bundle(case, role):
    require(case == CASE and role in ROLES, 'fixed L22 role/case required')
    return 'org.harmonycontrib.telephony579.' + role


def permissions(case, role):
    bundle(case, role)
    return list(SYSTEM if role == 'system' else PUBLIC if role == 'ordinary' else ())


def module_fields(case, role, parameters=None):
    bundle(case, role)
    require(parameters is None or parameters == {}, 'no alternate L22 authority/endpoint parameters')
    return {'requestPermissions': [{'name': p, 'reason': '$string:telephony579_permission',
        'usedScene': {'abilities': ['EntryAbility'], 'when': 'inuse'}} for p in permissions(case, role)],
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
            'exported': True, 'launchType': 'singleton'}], 'extensionAbilities': []}


def source_files(case, run, role, parameters=None):
    module_fields(case, role, parameters)
    require(re.fullmatch('[a-f0-9]{32}', run), 'same original Owner fresh run required')
    mapping = {'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
        'TelephonyAudit.js': 'entry/src/main/ets/entryability/TelephonyAudit.js',
        'Index.ets': 'entry/src/main/ets/pages/Index.ets'}
    result = {}
    for name, destination in mapping.items():
        text = (ASSETS / name).read_text()
        if name == 'TelephonyAudit.js':
            require(text.count('__TELEPHONY579_RUN__') == text.count('__TELEPHONY579_ROLE__') == 1,
                'one exact compiled run/role marker required')
            text = text.replace('__TELEPHONY579_RUN__', run).replace('__TELEPHONY579_ROLE__', role)
        result[destination] = text
    result['entry/src/main/resources/base/profile/main_pages.json'] = '{"src":["pages/Index"]}\n'
    result['entry/src/main/resources/base/element/telephony579.json'] = (
        '{"string":[{"name":"telephony579_permission","value":"Validate actual telephony transactions on this image"}]}\n')
    return result


def configure_profile(case):
    require(case == CASE, 'fixed L22 case required')
    def configure(profile, role, udid, compiled):
        require(role in ROLES and re.fullmatch('[a-fA-F0-9]{64}', udid) and
            compiled['app']['bundleName'] == bundle(case, role), 'actual role, bundle and held UDID required')
        require([p['name'] for p in compiled['module'].get('requestPermissions', [])] == permissions(case, role),
            'compiled role permissions differ')
        profile['bundle-info']['bundle-name'] = bundle(case, role)
        profile['bundle-info']['apl'] = 'normal' if role == 'ordinary' else 'system_core'
        profile['bundle-info']['app-feature'] = 'hos_normal_app' if role == 'ordinary' else 'hos_system_app'
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = permissions(case, role)
        profile['permissions']['restricted-permissions'] = permissions(case, role)
        return profile
    return configure
