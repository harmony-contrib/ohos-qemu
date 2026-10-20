"""Fixed source/sink typed callers on root's original per-boot builder."""
from pathlib import Path
import json
import re

HERE=Path(__file__).resolve().parent
ASSETS=HERE/'apps_paired579'
ROLES=('normal','grant','denied')
EXTERNAL_ROLES=('source_normal','source_grant','source_denied','sink_grant')
ACTIONS=('identity','permissions','local','network-before','network-config','network-state','network-restore',
    'dm-discover','dm-found','dm-select','dm-auth','dm-trusted','dm-unbind','dm-stop',
    'cast-create','cast-discover','cast-found','cast-select','cast-picker','cast-connect','cast-controller',
    'sink-observe','sink-attach','cast-start','cast-pause','cast-resume','cast-state','cast-stop','cast-cleanup',
    'mic-devices','mic-start','mic-state','mic-stop','mic-final','camera-devices','camera-start','camera-shutter','camera-state','camera-stop','cleanup','exit')


def require(ok, reason):
    if not ok:raise ValueError(reason)


def bundle(case, role):
    require(case=='pair' and role in ROLES,'fixed local pair role')
    return 'org.ohos.qemu.paired579.'+role


def permissions(case, role):
    bundle(case,role)
    if role!='grant':return []
    return ['ohos.permission.INTERNET','ohos.permission.GET_NETWORK_INFO','ohos.permission.CONNECTIVITY_INTERNAL',
        'ohos.permission.DISTRIBUTED_DATASYNC','ohos.permission.ACCESS_SERVICE_DM',
        'ohos.permission.MANAGE_MEDIA_RESOURCES','ohos.permission.ACCESS_DISTRIBUTED_HARDWARE',
        'ohos.permission.MICROPHONE','ohos.permission.CAMERA','ohos.permission.MANAGE_AUDIO_CONFIG']


def module_fields(case,role,parameters):
    require(set(parameters)=={'profile','udid','endpoint'} and parameters['profile'] in ('phone','2in1') and
            parameters['endpoint'] in ('source','sink'),'actual finite endpoint/profile input')
    request=[]
    for permission in permissions(case,role):
        row={'name':permission}
        if permission in ('ohos.permission.DISTRIBUTED_DATASYNC','ohos.permission.MICROPHONE','ohos.permission.CAMERA'):
            row.update(reason='$string:paired579_permission',usedScene={'abilities':['EntryAbility'],'when':'inuse'})
        request.append(row)
    return {'deviceTypes':['2in1'] if parameters['profile']=='2in1' else ['default'],'requestPermissions':request}


def source_files(case,run,role,parameters):
    bundle_name=bundle(case,role);module_fields(case,role,parameters)
    require(re.fullmatch('[a-f0-9]{32}',run),'actual nonce')
    replacements={'__APPS579_RUN__':run,'__APPS579_CASE__':'paired','__APPS579_ROLE__':parameters['endpoint']+'_'+role,
                  '__APPS579_BUNDLE__':bundle_name,'__PAIRED579_ENDPOINT__':parameters['endpoint']}
    names={'EntryAbility.ets':'entry/src/main/ets/entryability/EntryAbility.ets',
           'Journal.ets':'entry/src/main/ets/common/Journal.ets','PairDriver.ets':'entry/src/main/ets/common/Driver.ets',
           'PairPage.ets':'entry/src/main/ets/pages/Index.ets','RemoteCamera.ets':'entry/src/main/ets/common/RemoteCamera.ets'}
    result={}
    for name,destination in names.items():
        text=(ASSETS/name).read_text()
        for old,new in replacements.items():text=text.replace(old,new)
        result[destination]=text
    result['entry/src/main/resources/base/element/paired579.json']=json.dumps({'string':[{'name':'paired579_permission','value':'Exercise the owned paired-device workflow and restore it'}]})+'\n'
    result['AppScope/resources/base/element/string.json']=json.dumps({'string':[{'name':'app_name',
        'value':'Pair579 '+parameters['endpoint']+' '+role+' '+run[:8]}]})+'\n'
    return result


def configure_profile(case):
    require(case=='pair','fixed pair case')
    def configure(profile,role,udid,compiled):
        require(re.fullmatch('[a-fA-F0-9]{64}',udid) and compiled['app']['bundleName']==bundle(case,role),'actual endpoint UDID and compiled identity')
        system=role in ('grant','denied')
        profile['bundle-info'].update({'bundle-name':bundle(case,role),'apl':'system_core' if system else 'normal',
            'app-feature':'hos_system_app' if system else 'hos_normal_app'})
        profile['debug-info']['device-ids']=[udid]
        profile['acls']['allowed-acls']=permissions(case,role)
        profile['permissions']['restricted-permissions']=permissions(case,role)
        return profile
    return configure
