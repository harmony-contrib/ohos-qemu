"""One real signed public SIM/data controller; no fake SIM state/storage access."""
from pathlib import Path
import re

BUNDLE='org.harmonycontrib.apn579.control'
PERMISSIONS=['ohos.permission.GET_TELEPHONY_STATE','ohos.permission.SET_TELEPHONY_STATE','ohos.permission.MANAGE_APN_SETTING']
ROOT=Path(__file__).with_name('apn579')

def check(case,role):
    if (case,role)!=('virtual-sim','control'): raise ValueError('fixed actual SIM caller required')

def bundle(case,role):
    check(case,role);return BUNDLE

def module_fields(case,role,parameters=None):
    check(case,role)
    return {'requestPermissions':[{'name':name} for name in PERMISSIONS],
        'abilities':[{'name':'EntryAbility','srcEntry':'./ets/audit/EntryAbility.ets','exported':True,'launchType':'singleton'}],
        'extensionAbilities':[]}

def source_files(case,run,role,parameters=None):
    check(case,role)
    if parameters!={} or re.fullmatch('[a-f0-9]{32}',run or '') is None: raise ValueError('fixed fresh original run required')
    result={}
    for name in ('Journal.ets','EntryAbility.ets','Probe.ets','ApnRead.ets'):
        text=(ROOT/name).read_text()
        if name=='Journal.ets':
            for key,value in {'__APN_SIM579_RUN__':run,'__APN_SIM579_BUNDLE__':BUNDLE,'__APN_SIM579_ROLE__':role}.items():
                if text.count(key)!=1: raise ValueError('one fixed real journal marker required')
                text=text.replace(key,value)
        result['entry/src/main/ets/audit/'+name]=text
    result['entry/src/main/ets/pages/Index.ets']=(ROOT/'Index.ets').read_text()
    result['entry/src/main/resources/base/profile/main_pages.json']='{"src":["pages/Index"]}\n'
    return result

def configure_profile(case):
    check(case,'control')
    def configure(profile,role,udid,compiled):
        check(case,role)
        permissions=compiled['module'].get('requestPermissions',[])
        abilities=compiled['module'].get('abilities',[])
        if re.fullmatch('[a-fA-F0-9]{64}',udid or '') is None or compiled['app']['bundleName']!=BUNDLE or \
            type(permissions) is not list or [p.get('name') for p in permissions]!=PERMISSIONS or \
            compiled['module'].get('extensionAbilities',[]) or len(abilities)!=1 or \
            any(abilities[0].get(key)!=value for key,value in module_fields(case,role)['abilities'][0].items()):
            raise ValueError('real typed caller/profile boundary differs')
        profile['bundle-info'].update({'bundle-name':BUNDLE,'apl':'system_basic','app-feature':'hos_system_app'})
        profile['debug-info']['device-ids']=[udid]
        profile['acls']['allowed-acls']=list(PERMISSIONS)
        profile['permissions']['restricted-permissions']=list(PERMISSIONS)
        return profile
    return configure
