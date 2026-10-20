"""Fixed ordinary URI lifetime fixtures for the original held-Owner builder."""
from pathlib import Path
import json
import re

ASSETS = Path(__file__).with_name('mms_share579')
ROLES = ('owner', 'receiver', 'foreign')
BUNDLES = {role: 'org.harmonycontrib.urilifetime579.' + role for role in ROLES}
MIME = 'application/vnd.harmonycontrib.uri579'
CASES = ('share-close', 'share-write-close', 'share-receiver-death', 'share-owner-death',
    'mms-no-grant', 'mms-forged-owner', 'mms-cancel', 'mms-owner-death', 'mms-receiver-death')
ACTIONS = ('create', 'owner-read', 'share', 'mms', 'probe', 'consume', 'cleanup')


def require(value, message):
    if not value:
        raise ValueError(message)


def bundle(case, role):
    require(case == 'boundaries' and role in ROLES, 'fixed ordinary fixture role required')
    return BUNDLES[role]


def module_fields(case, role, parameters=None):
    bundle(case, role)
    ability = {'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
        'exported': True, 'launchType': 'singleton' if role == 'owner' else 'standard',
        'label': '$string:uri579_label'}
    if role != 'owner':
        ability['skills'] = [{'actions': ['ohos.want.action.sendData'], 'uris': [{'type': MIME}]}]
    return {'requestPermissions': [], 'extensionAbilities': [], 'abilities': [ability]}


def source_files(case, run, role, parameters=None):
    name = bundle(case, role)
    require(re.fullmatch('[a-f0-9]{32}', run or '') and parameters in ({}, None), 'fixed nonce DATA required')
    mapping = {'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
        'Journal.ets': 'entry/src/main/ets/common/Journal.ets',
        'Driver.ets': 'entry/src/main/ets/common/Driver.ets', 'Index.ets': 'entry/src/main/ets/pages/Index.ets'}
    result = {}
    for source, target in mapping.items():
        text = (ASSETS / source).read_text()
        for old, new in (('__RUN__', run), ('__ROLE__', role), ('__BUNDLE__', name)):
            text = text.replace(old, new)
        result[target] = text
    result['entry/src/main/resources/base/profile/main_pages.json'] = '{"src":["pages/Index"]}\n'
    result['AppScope/resources/base/element/uri579.json'] = json.dumps({
        'string': [{'name': 'uri579_label', 'value': 'URI579 ' + role + ' ' + run}]}) + '\n'
    return result


def configure_profile(case):
    require(case == 'boundaries', 'fixed lifetime case required')
    def configure(profile, role, udid, compiled):
        require(role in ROLES and re.fullmatch('[a-fA-F0-9]{64}', udid or '') and
            compiled['app']['bundleName'] == BUNDLES[role], 'real compiled role/guest identity required')
        profile['bundle-info'].update({'bundle-name': BUNDLES[role], 'apl': 'normal', 'app-feature': 'hos_normal_app'})
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = []
        profile['permissions']['restricted-permissions'] = []
        return profile
    return configure
