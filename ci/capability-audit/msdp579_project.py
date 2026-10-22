"""Public nine-modality HAPs plus a real product-ABI three-algorithm client supplement."""
from pathlib import Path
import json,re
ASSETS=Path(__file__).with_name('msdp579')
ROLES=('normal','grant','denied')
CASES=('local','sensor','cooperate')
PERMISSIONS=('ohos.permission.COOPERATE_MANAGER','ohos.permission.ACTIVITY_MOTION',
 'ohos.permission.DETECT_GESTURE','ohos.permission.ACCESS_SENSING_WITH_ULTRASOUND',
 'ohos.permission.GET_SCREEN_CONTENT','ohos.permission.SIMULATE_USER_INPUT',
 'ohos.permission.ONSCREEN_AWARENESS','ohos.permission.DISTRIBUTED_DATASYNC')
def check(case,role):
 if case not in CASES or role not in ROLES:raise ValueError('finite MSDP role/case')
def bundle(case,role):
 check(case,role);return 'org.ohos.qemu.msdp579.'+case+'.'+role
def module_fields(case,role,parameters=None):
 check(case,role)
 return {'deviceTypes':['default','2in1'],'abilities':[{'name':'EntryAbility','srcEntry':'./ets/entryability/EntryAbility.ets','launchType':'singleton','exported':True,'label':'$string:app_name','icon':'$media:app_icon','startWindowIcon':'$media:app_icon','startWindowBackground':'$color:start_window_background','skills':[{'actions':['ohos.want.action.home'],'entities':['entity.system.home']},{'actions':['ohos.want.action.viewData'],'entities':['entity.system.default','entity.system.browsable'],'uris':[{'scheme':'msdp579','host':bundle(case,role)}]}]}],'requestPermissions':[
  dict(name=p,**({'reason':'$string:msdp579_permission','usedScene':{'abilities':['EntryAbility'],'when':'inuse'}}
   if p in ('ohos.permission.ACTIVITY_MOTION','ohos.permission.DISTRIBUTED_DATASYNC') else {}))
  for p in (('ohos.permission.ACCELEROMETER',)+PERMISSIONS if role=='grant' else ('ohos.permission.ACCELEROMETER',))]}
def source_files(case,run,role,parameters=None):
 check(case,role)
 if re.fullmatch('[a-f0-9]{32}',run or '') is None or type(parameters) is not dict or parameters.get('profile') not in ('phone','2in1') or set(parameters)!={'profile'}:raise ValueError('actual profile and nonce required')
 out={}
 for n,dest in {'Journal.ets':'common/Journal.ets','Driver.ets':'common/Driver.ets','EntryAbility.ets':'entryability/EntryAbility.ets','Index.ets':'pages/Index.ets'}.items():
  t=(ASSETS/n).read_text()
  for a,b in {'__MSDP579_RUN__':run,'__MSDP579_CASE__':case,'__MSDP579_ROLE__':role,'__MSDP579_BUNDLE__':bundle(case,role)}.items():t=t.replace(a,b)
  out['entry/src/main/ets/'+dest]=t
 out['entry/src/main/cpp/types/libmsdp579/index.d.ts']=(ASSETS/'Native.d.ts').read_text()
 out['entry/src/main/cpp/types/libmsdp579/oh-package.json5']=json.dumps({'name':'libmsdp579.so','version':'1.0.0','types':'./index.d.ts'})+'\n'
 out['entry/oh-package.json5']=json.dumps({'name':'entry','version':'1.0.0','dependencies':{'libmsdp579.so':'file:./src/main/cpp/types/libmsdp579'}})+'\n'
 out['entry/src/main/resources/base/element/msdp579.json']=json.dumps({'string':[{'name':'msdp579_permission','value':'Observe this owned MSDP fixture with explicit consent'}]})+'\n'
 out['AppScope/resources/base/element/string.json']=json.dumps({'string':[{'name':'app_name','value':'MSDP579 '+case+' '+role+' '+run[:8]}]})+'\n'
 return out
def configure_profile(case):
 def configure(profile,role,udid,compiled):
  check(case,role)
  if re.fullmatch('[a-fA-F0-9]{64}',udid or '') is None or compiled['app']['bundleName']!=bundle(case,role):raise ValueError('actual UDID/HAP')
  permissions=['ohos.permission.ACCELEROMETER']+(list(PERMISSIONS) if role=='grant' else [])
  if [p['name'] for p in compiled['module'].get('requestPermissions',[])]!=permissions:raise ValueError('actual compiled permissions differ')
  profile['bundle-info'].update({'bundle-name':bundle(case,role),'apl':'normal' if role=='normal' else 'system_core','app-feature':'hos_normal_app' if role=='normal' else 'hos_system_app'})
  profile['debug-info']['device-ids']=[udid];profile['acls']['allowed-acls']=permissions;profile['permissions']['restricted-permissions']=permissions
  return profile
 return configure

def native_artifact_destination(arch):return 'entry/libs/'+{'arm64':'arm64-v8a','armv7a':'armeabi-v7a','x86_64':'x86_64'}[arch]+'/libmsdp579.so'
