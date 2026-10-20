"""Exact new caller sources for the parent's existing API26 build/sign path.

This module writes no files and launches no tool. Callers remain source-only
until the parent supplies actual build, signature and fresh-image receipts.
"""
from pathlib import Path
import re

ASSETS = Path(__file__).with_name('system_services578')
ROLES = {'domain': ('target', 'other', 'normal', 'grant', 'denied'),
         'session': ('normal', 'grant', 'denied'), 'ads': ('normal',)}
IDS = {'domain': 'behavior:app-domain-verification-extension-missing',
       'session': 'behavior:session-manager-profile-gap',
       'ads': 'behavior:advertising-service-provider-missing'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(case, run_id, role, hosts=None):
    require(case in ROLES and role in ROLES[case], 'fixed services578 case/role required')
    require(re.fullmatch(r'[a-f0-9]{32}', run_id or ''), 'actual fresh 128-bit run nonce required')
    if case == 'domain':
        require(type(hosts) is dict and set(hosts) == {'host', 'other_host'}, 'two actual owned DNS names required')
        require(all(re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', v)
                    for v in hosts.values()) and hosts['host'] != hosts['other_host'], 'distinct real FQDNs required')


def bundle(case, role):
    require(case in ROLES and role in ROLES[case], 'fixed role required')
    return 'org.ohos.qemu.services578.' + case + '.' + role


def permissions(case, role):
    if role == 'grant' and case == 'domain':
        return ['ohos.permission.GET_APP_DOMAIN_BUNDLE_INFO']
    if role == 'grant' and case == 'session':
        return ['ohos.permission.USE_FLOAT_BALL', 'ohos.permission.FLOAT_VIEW']
    return []


def module_fields(case, role, hosts=None):
    require(case in ROLES and role in ROLES[case], 'fixed caller role required')
    fields = {'requestPermissions': [{'name': p} for p in permissions(case, role)]}
    if case == 'domain' and role in ('target', 'other'):
        require(type(hosts) is dict and set(hosts) == {'host', 'other_host'}, 'actual DNS pair required')
        fields['abilities'] = [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
            'exported': True, 'launchType': 'singleton', 'skills': [
                {'actions': ['ohos.want.action.viewData'], 'entities': ['entity.system.browsable'],
                 'domainVerify': True, 'uris': [{'scheme': scheme, 'host': host, 'pathStartWith': 'services578/'}
                    for host in hosts.values() for scheme in ('https', 'http')]}]}]
    return fields


def source_files(case, run_id, role, hosts=None):
    validate(case, run_id, role, hosts)
    values = {'__SERVICES578_RUN__': run_id, '__SERVICES578_CASE__': case, '__SERVICES578_ROLE__': role,
              '__SERVICES578_BUNDLE__': bundle(case, role),
              '__SERVICES578_HOST__': (hosts or {}).get('host', 'unused.invalid'),
              '__SERVICES578_OTHER_HOST__': (hosts or {}).get('other_host', 'other.invalid')}
    names = {'Journal.ets': 'entry/src/main/ets/common/Journal.ets',
        'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
        {'domain': 'DomainDriver.ets', 'session': 'SessionDriver.ets', 'ads': 'AdsDriver.ets'}[case]:
            'entry/src/main/ets/common/Driver.ets',
        ('SessionPage.ets' if case == 'session' else 'PlainPage.ets'): 'entry/src/main/ets/pages/Index.ets',
        'ChildPage.ets': 'entry/src/main/ets/pages/Child.ets'}
    out = {}
    for name, dest in names.items():
        content = (ASSETS / name).read_text()
        for marker, value in values.items():
            content = content.replace(marker, value)
        out[dest] = content
    out['entry/src/main/resources/base/profile/main_pages.json'] = '{"src":["pages/Index","pages/Child"]}\n'
    return out


def configure_profile(case):
    require(case in ROLES, 'fixed case required')

    def configure(profile, role, udid, compiled):
        require(role in ROLES[case] and re.fullmatch('[0-9a-fA-F]{64}', udid or ''), 'same fresh guest UDID required')
        require(compiled['app']['bundleName'] == bundle(case, role), 'compiled bundle mismatch')
        normal = role in ('normal', 'target', 'other')
        profile['bundle-info']['bundle-name'] = bundle(case, role)
        profile['bundle-info']['apl'] = 'normal' if normal else 'system_core'
        profile['bundle-info']['app-feature'] = 'hos_normal_app' if normal else 'hos_system_app'
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = permissions(case, role)
        profile['permissions']['restricted-permissions'] = permissions(case, role)
        return profile
    return configure
