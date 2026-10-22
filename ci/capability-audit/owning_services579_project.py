"""Fixed callers of six EXISTING owning services, not six retired syscaps."""
from pathlib import Path
import json
import re
ASSETS=Path(__file__).with_name('owning_services579')
ROLES=('normal','grant','denied')
CASES=('local','dfs')
PERMISSIONS=('ohos.permission.DUMP','ohos.permission.ACCESS_DEVAUTH_CRED_MGR',
 'ohos.permission.ACCESS_DEVAUTH_CRED_AUTH','ohos.permission.ACCESS_PIN_AUTH',
 'ohos.permission.MANAGE_USER_IDM','ohos.permission.USE_USER_IDM',
 'ohos.permission.ACCESS_USER_AUTH_INTERNAL','ohos.permission.MANAGE_LOCAL_ACCOUNTS',
 'ohos.permission.DISTRIBUTED_DATASYNC')

def check(case,role):
 if case not in CASES or role not in ROLES:raise ValueError('finite service fixture')
def bundle(case,role):
 check(case,role);return 'org.ohos.qemu.services579.'+case+'.'+role
def module_fields(case,role,parameters=None):
 check(case,role)
 return {'deviceTypes':['default'],'requestPermissions':[
  dict(name=p,**({'reason':'$string:services579_permission','usedScene':{'abilities':['EntryAbility'],'when':'inuse'}}
   if p=='ohos.permission.DISTRIBUTED_DATASYNC' else {})) for p in PERMISSIONS] if role=='grant' else []}
def source_files(case,run,role,parameters=None):
 check(case,role)
 if re.fullmatch('[a-f0-9]{32}',run or '') is None or parameters!={'profile':'phone'}:raise ValueError('fresh fixed phone recipe')
 out={}
 for source,dest in {'Journal.ets':'entry/src/main/ets/common/Journal.ets',
  'EntryAbility.ets':'entry/src/main/ets/entryability/EntryAbility.ets','Index.ets':'entry/src/main/ets/pages/Index.ets',
  'Driver.ets':'entry/src/main/ets/common/Driver.ets','Native.d.ts':'entry/src/main/cpp/types/libowning_services579/index.d.ts'}.items():
  text=(ASSETS/source).read_text()
  for a,b in {'__SERVICES579_RUN__':run,'__SERVICES579_CASE__':case,'__SERVICES579_ROLE__':role,'__SERVICES579_BUNDLE__':bundle(case,role)}.items():text=text.replace(a,b)
  out[dest]=text
 out['entry/oh-package.json5']=json.dumps({'name':'entry','version':'1.0.0','dependencies':{'libowning_services579.so':'file:./src/main/cpp/types/libowning_services579'}})+'\n'
 out['entry/src/main/cpp/types/libowning_services579/oh-package.json5']=json.dumps({'name':'libowning_services579.so','version':'1.0.0','types':'./index.d.ts'})+'\n'
 out['entry/src/main/resources/base/element/services579.json']=json.dumps({'string':[{'name':'services579_permission','value':'Exercise owned distributed file fixture and restore it'}]})+'\n'
 out['AppScope/resources/base/element/string.json']=json.dumps({'string':[{'name':'app_name','value':'Services579 '+case+' '+role+' '+run[:8]}]})+'\n'
 return out

def native_artifact_destination(arch):
 return 'entry/libs/'+{'arm64':'arm64-v8a','armv7a':'armeabi-v7a','x86_64':'x86_64'}[arch]+'/libowning_services579.so'
def configure_profile(case):
 def configure(profile,role,udid,compiled):
  check(case,role)
  if re.fullmatch('[a-fA-F0-9]{64}',udid or '') is None or compiled['app']['bundleName']!=bundle(case,role):raise ValueError('actual compiled caller/boot UDID')
  system=role!='normal';permissions=list(PERMISSIONS) if role=='grant' else []
  if [p['name'] for p in compiled['module'].get('requestPermissions',[])]!=permissions:raise ValueError('exact permission declaration')
  profile['bundle-info'].update({'bundle-name':bundle(case,role),'apl':'system_core' if system else 'normal','app-feature':'hos_system_app' if system else 'hos_normal_app'})
  profile['debug-info']['device-ids']=[udid];profile['acls']['allowed-acls']=permissions;profile['permissions']['restricted-permissions']=permissions
  return profile
 return configure
