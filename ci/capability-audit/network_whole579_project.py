"""Normal SDK/signature adapter for two genuine SystemVpn owners, not a VPN extension."""
from pathlib import Path
import sys
for _name in ('network_whole579_records', 'network_whole579_sources', 'network_whole579_project', 'network_whole579_session', 'network_whole579_hook', 'network_whole579_p2p', 'network_whole579_replay', 'network_whole579_options_replay'):
    _old=sys.modules.get(_name)
    if _old is not None and Path(_old.__file__).resolve()!=Path(__file__).resolve().with_name(_name+'.py'):
        raise ValueError('foreign cached whole Network source '+_name)
import base64
import json
import re
from network_whole579_records import need, raw

ROLES = ('a', 'b', 'normal', 'denied', 'account')
ROOT = Path(__file__).with_name('network_whole579')
OPTIONS = {
    'persist': '\npersist-tun\n',
    'metric': '\nroute-metric 7\n',
    'splitdns': '\ndns server -3 address 10.73.0.1:53\ndns server -3 resolve-domains whole579.invalid\ndns server -2 address 10.73.0.1:5353\n',
    'dot': '\ndns server -2 address 10.73.0.1:853\ndns server -2 transport DoT\ndns server -2 sni qemu-owned-peer\n',
    'doh': '\ndns server -2 address 10.73.0.1:443\ndns server -2 transport DoH\ndns server -2 sni qemu-owned-peer\n',
    'dnsport': '\ndns server -2 address 10.73.0.1:5353\n',
    'badcert': '\ndns server -2 address 10.73.0.1:853\ndns server -2 transport DoT\ndns server -2 sni wrong-whole579-peer\n',
    'invalid': '\nscript-security 2\n'}


def profile_variant(parameters, variant='normal'):
    body=raw(parameters['peer_profile']).decode()
    if variant=='normal':return body
    if variant=='bad-peer-name':
        need(body.count('verify-x509-name qemu-owned-peer name')==1,'one normally generated real peer TLS name')
        return body.replace('verify-x509-name qemu-owned-peer name','verify-x509-name wrong-whole579-peer name')+'\ntls-exit\nhand-window 3\n'
    need(variant in OPTIONS,'fixed implemented/native-boundary profile variant');return body+OPTIONS[variant]



def bundle(case, role):
    need(case == 'systemvpn' and role in ROLES, 'fixed true SystemVpn diagnostic family')
    return 'org.ohos.qemu.networkwhole579.' + role


def permissions(role):
    if role == 'normal':
        return ['ohos.permission.INTERNET', 'ohos.permission.GET_NETWORK_INFO']
    if role == 'denied':
        return ['ohos.permission.INTERNET', 'ohos.permission.GET_NETWORK_INFO']
    if role == 'account':
        return ['ohos.permission.MANAGE_LOCAL_ACCOUNTS', 'ohos.permission.GET_LOCAL_ACCOUNTS',
                'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION']
    return ['ohos.permission.MANAGE_VPN', 'ohos.permission.INTERNET', 'ohos.permission.GET_NETWORK_INFO']


def module_fields(case, role, parameters=None):
    bundle(case, role)
    need(parameters['profile'] in ('phone', '2in1'), 'actual archive profile')
    return {'deviceTypes': ['2in1'] if parameters['profile'] == '2in1' else ['default'],
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
                       'exported': True, 'visible': True, 'launchType': 'singleton'}],
        'requestPermissions': [{'name': p} for p in permissions(role)]}


def source_files(case, run, role, parameters=None):
    name = bundle(case, role)
    need(re.fullmatch('[a-f0-9]{32}', run), 'actual normal production nonce')
    need(set(parameters) == {'profile', 'udid', 'peer_profile', 'peer_run'}, 'only literal original peer data')
    text = raw(parameters['peer_profile']).decode()
    need(text.endswith('# owned-peer-' + parameters['peer_run'] + '\n') and
         re.fullmatch('[a-f0-9]{32}', parameters['peer_run']) and
         all(text.count('<' + n + '>') == text.count('</' + n + '>') == 1 for n in ('ca', 'cert', 'key')),
         'actual normally generated original TLS credential/profile, never a fabricated profile')
    replacements = {'__APPS579_RUN__': run, '__APPS579_CASE__': case,
        '__APPS579_ROLE__': role, '__APPS579_BUNDLE__': name,
        '__PROFILE_BASE64__': base64.b64encode(text.encode()).decode(),
        '__PROFILE_TEXT_JSON__': json.dumps(text), '__OPTION_MAP_JSON__': json.dumps(OPTIONS), '__PEER_RUN__': parameters['peer_run']}
    files = {'Journal.ets': 'entry/src/main/ets/common/Journal.ets',
        'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
        ('AccountDriver.ets' if role == 'account' else 'VpnDriver.ets'): 'entry/src/main/ets/common/Driver.ets',
        'Index.ets': 'entry/src/main/ets/pages/Index.ets'}
    result = {}
    for source, target in files.items():
        value = (ROOT / source).read_text()
        for old, new in replacements.items():
            value = value.replace(old, new)
        result[target] = value
    return result


def configure_profile(case):
    def configure(profile, role, udid, compiled):
        need(re.fullmatch('[a-fA-F0-9]{64}', udid) and compiled['app']['bundleName'] == bundle(case, role),
             'actual same-boot UDID and exact compiled caller')
        system = role != 'normal'
        profile['bundle-info'].update({'bundle-name': bundle(case, role),
            'apl': 'system_core' if system else 'normal',
            'app-feature': 'hos_system_app' if system else 'hos_normal_app'})
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = permissions(role)
        profile['permissions']['restricted-permissions'] = permissions(role)
        return profile
    return configure
