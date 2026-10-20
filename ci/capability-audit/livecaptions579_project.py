"""Original owned SDK builder overlays for real guest-only audio fixtures."""
from pathlib import Path
import json
import re

ASSETS = Path(__file__).with_name('livecaptions579')
BUNDLES = {role: 'org.harmonycontrib.livecaptions579.' + role for role in ('control', 'media', 'private', 'ordinary')}


def check(case, role):
    if case != 'end-to-end' or role not in BUNDLES:
        raise ValueError('fixed Live Captions fixture case/role required')


def bundle(case, role):
    check(case, role)
    return BUNDLES[role]


def permissions(role):
    return ['ohos.permission.READ_ACCESSIBILITY_CONFIG', 'ohos.permission.WRITE_ACCESSIBILITY_CONFIG'] if role == 'control' else []


def module_fields(case, role, parameters=None):
    check(case, role)
    return {'requestPermissions': [{'name': name} for name in permissions(role)],
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/audit/EntryAbility.ets',
            'exported': True, 'launchType': 'singleton'}], 'extensionAbilities': []}


def source_files(case, run, role, parameters=None):
    check(case, role)
    if re.fullmatch('[a-f0-9]{32}', run or '') is None or parameters != {}:
        raise ValueError('fresh parent run and fixed no-options source recipe required')
    out = {}
    for name in ('EntryAbility.ets', 'Probe.ets', 'Journal.ets'):
        text = (ASSETS / name).read_text()
        if name == 'Journal.ets':
            for marker, value in {'__LIVE_CAPTIONS579_RUN__': run, '__LIVE_CAPTIONS579_BUNDLE__': BUNDLES[role], '__LIVE_CAPTIONS579_ROLE__': role}.items():
                if text.count(marker) != 1:
                    raise ValueError('fixed exact journal markers required')
                text = text.replace(marker, value)
        out['entry/src/main/ets/audit/' + name] = text
    out['entry/src/main/ets/pages/Index.ets'] = (ASSETS / 'Index.ets').read_text()
    out['entry/src/main/resources/base/profile/main_pages.json'] = '{"src":["pages/Index"]}\n'
    return out


def asset_destinations(case, role):
    check(case, role)
    # Parent's original pre-compile fixture adapter copies the admitted audio
    # bytes to these fixed data paths. JSON cannot select a code/source path.
    if role not in ('media','private'): return {}
    return {'a':'entry/src/main/resources/rawfile/caption-a.wav',
            'b':'entry/src/main/resources/rawfile/caption-b.wav',
            'license_a':'entry/src/main/resources/rawfile/caption-a-LICENSE.txt',
            'license_b':'entry/src/main/resources/rawfile/caption-b-LICENSE.txt'}


def configure_profile(case):
    check(case, 'control')
    def configure(profile, role, udid, compiled):
        check(case, role)
        if compiled['app']['bundleName'] != BUNDLES[role] or re.fullmatch('[a-fA-F0-9]{64}', udid or '') is None:
            raise ValueError('same-boot actual caller identity required')
        wanted = module_fields(case, role)
        if compiled['module'].get('requestPermissions', []) != wanted['requestPermissions'] or compiled['module'].get('extensionAbilities', []):
            raise ValueError('real fixture permission/type differs')
        profile['bundle-info'].update({'bundle-name': BUNDLES[role], 'apl': 'system_basic' if role == 'control' else 'normal',
            'app-feature': 'hos_system_app' if role == 'control' else 'hos_normal_app'})
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = permissions(role)
        profile['permissions']['restricted-permissions'] = permissions(role)
        return profile
    return configure
