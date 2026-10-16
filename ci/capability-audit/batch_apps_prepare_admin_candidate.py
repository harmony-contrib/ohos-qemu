#!/usr/bin/env python3
"""Maintainer-only patch generator from fixed compressed fixtures; no live source writes."""
from pathlib import Path
import base64,difflib,gzip,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
FIX=ROOT/'ci/capability-audit/fixtures/batch_apps/admin_provider'
META=json.loads((FIX/'provenance.json').read_text())

def original(project,relative):
    return gzip.decompress(base64.b64decode((FIX/META['projects'][project]['files'][relative]['fixture']).read_bytes())).decode()

admin='applications/standard/admin_provisioning'
files={p:original(admin,p) for p in META['projects'][admin]['files'] if p!='entry/src/main/module.json'}
files={p:text.replace('\r\n','\n') for p,text in files.items()}
after=dict(files)
after['BUILD.gn']='''# Copyright (c) 2026 Harmony Contrib
# SPDX-License-Identifier: Apache-2.0
import("//build/ohos.gni")

# Compile the real provisioning UI; GN app_sign retains its existing OS profile.
ohos_app("adminprovisioning_hap") {
  deps = []
  certificate_profile = "signature/adminprovisioning.p7b"
  hap_name = "adminprovisioning"
  subsystem_name = "applications"
  part_name = "prebuilt_hap"
  module_install_dir = "app/com.ohos.adminprovisioning"
  sdk_home = "//prebuilts/ohos-sdk/linux"
  sdk_type_name = [ "sdk.dir" ]
  assemble_type = "assembleHap"
  build_level = "module"
  build_modules = [ "adminprovisioning" ]
  js_build_mode = "release"
}
'''
after['build-profile.json5']=json.dumps({'app':{'products':[{'name':'default','compileSdkVersion':'26.0.0','compatibleSdkVersion':11,'targetSdkVersion':'26.0.0','runtimeOS':'OpenHarmony'}]},'modules':[{'name':'adminprovisioning','srcPath':'./entry','targets':[{'name':'default','applyToProducts':['default']}]}]},indent=2)+'\n'
after['oh-package.json5']=json.dumps({'modelVersion':'6.0.0','name':'adminprovisioning','version':'1.0.1','dependencies':{},'devDependencies':{}},indent=2)+'\n'
after['entry/oh-package.json5']=json.dumps({'name':'adminprovisioning','version':'1.0.1','dependencies':{}},indent=2)+'\n'
after['hvigor/hvigor-config.json5']=json.dumps({'modelVersion':'6.0.0','dependencies':{},'execution':{'daemon':False,'parallel':False}},indent=2)+'\n'
for name,task in (('hvigorfile.js','appTasks'),('entry/hvigorfile.js','hapTasks')):
    after[name]=after[name].replace("module.exports = require('@ohos/hvigor-ohos-plugin')."+task+";", "module.exports = { system: require('@ohos/hvigor-ohos-plugin')."+task+", plugins: [] };")
p='entry/src/main/module.json5'; doc=json.loads(after[p]); legacy=json.loads(original(admin,'entry/src/main/module.json'))
byod=next(x for x in legacy['module']['abilities'] if x['name']=='ByodAdminProvisionAbility');assert all(x['name']!=byod['name'] for x in doc['module']['abilities']);doc['module']['abilities'].append(byod)
module=doc['module'];module['srcEntry']=module.pop('srcEntrance');module.pop('uiSyntax',None)
for entry in module['abilities']+module['extensionAbilities']:
    entry['srcEntry']=entry.pop('srcEntrance')
    if entry.get('type')=='ui':entry['type']='sys/commonUI'
after[p]=json.dumps(doc,indent=2)+'\n'
p='entry/src/main/ets/MainAbility/MainAbility.ts';t=after[p].replace("import Logger from '../common/logger';", "import Logger from '../common/logger';\nimport Want from '@ohos.app.ability.Want';\nimport window from '@ohos.window';")
t=t.replace('  private localStorage: LocalStorage = new LocalStorage();','  private localStorage: LocalStorage = new LocalStorage();\n  private windowStage: window.WindowStage | undefined = undefined;')
t=t.replace('  onCreate(want, launchParam): void {','  onCreate(want: Want): void {')
t=t.replace('  onWindowStageCreate(windowStage): void {','  onNewWant(want: Want): void {\n    this.localStorage.setOrCreate(\'adminProvisioningWant\', want);\n    this.loadPage();\n  }\n\n  private loadPage(): void {\n    this.windowStage?.loadContent(\'pages/applicationInfo\', this.localStorage).catch(error => {\n      Logger.info(TAG, \'Provisioning page could not load: \' + error?.message);\n    });\n  }\n\n  onWindowStageCreate(windowStage: window.WindowStage): void {')
t=t.replace("    windowStage.setUIContent(this.context, 'pages/applicationInfo', this.localStorage);", '    this.windowStage = windowStage;\n    this.loadPage();')
t=t.replace('  onWindowStageDestroy(): void {','  onWindowStageDestroy(): void {\n    this.windowStage = undefined;');after[p]=t
p='entry/src/main/ets/pages/applicationInfo.ets';t=after[p].replace('@Entry\n','@Entry({ useSharedStorage: true })\n');t=t.replace("  @State isEnableButton: boolean = false;", "  @State isEnableButton: boolean = false;\n  @State operationPending: boolean = false;\n  @State operationError: string = '';\n  private pageActive: boolean = true;\n  private requestReady: boolean = false;\n  private request: Want | undefined = undefined;\n  private elementNameVal: Want = { bundleName: '', abilityName: '' };\n  private enterInfo: adminManager.EnterpriseInfo = { name: '', description: '' };")
t=t.replace("    Column() {\n      Column() {", "    Column() {\n      if (this.operationError.length > 0) {\n        Text(this.operationError).fontColor(Color.Red).id('admin-provisioning-error');\n      }\n      Column() {",1)
t=t.replace('.enabled(this.isEnableButton)', '.enabled(this.requestReady && this.isEnableButton && !this.operationPending)\n            .id(\'admin-provisioning-activate\')')
t=t.replace("            .onClick(() => {\n              logger.info(TAG, 'button cancel", "            .enabled(!this.operationPending)\n            .id(\'admin-provisioning-cancel\')\n            .onClick(() => {\n              logger.info(TAG, 'button cancel")
t=t.replace('  async aboutToAppear(): Promise<void> {', '  async aboutToAppear(): Promise<void> {\n    this.pageActive = true;')
t=t.replace('  aboutToDisappear(): void {', '  aboutToDisappear(): void {\n    this.pageActive = false;')
a=t.index('  onPageShow(): void {');b=t.index('  onPageHide()',a)
t=t[:a]+'''  async onPageShow(): Promise<void> {
    try {
      await this.isAdminActive();
    } catch (error) {
      this.isEnableButton = false;
      this.operationError = `查询管理状态失败：${error?.message ?? '服务不可用'}`;
      logger.error(TAG, this.operationError);
    }
  }

'''+t[b:]
a=t.index('  async activateAdmin(');b=t.index('  async getSelfResourceVal(',a)
t=t[:a]+'''  async activateAdmin(adminType: adminManager.AdminType): Promise<void> {
    if (this.operationPending || !this.requestReady || !this.isCurrentRequest()) {
      return;
    }
    this.operationPending = true;
    this.operationError = '';
    try {
      const want: Want = {
        bundleName: elementNameVal.bundleName,
        abilityName: elementNameVal.abilityName
      };
      const enterprise: adminManager.EnterpriseInfo = { name: enterInfo.name, description: enterInfo.description };
      if (!want.bundleName || !want.abilityName) {
        throw new Error('请选择有效的设备管理应用');
      }
      await this.isAdminActive();
      if (!this.isCurrentRequest()) {
        return;
      }
      if (!this.isEnableButton) {
        throw new Error('当前设备管理员不允许执行此操作');
      }
      const enable: boolean = !this.isShowActive;
      if (enable) {
        if (adminType !== edmEnterpriseDeviceManager.AdminType.ADMIN_TYPE_NORMAL) {
          throw new Error('此页面只支持普通设备管理员激活');
        }
        await edmEnterpriseDeviceManager.enableAdmin(want,
          enterprise,
          edmEnterpriseDeviceManager.AdminType.ADMIN_TYPE_NORMAL);
      } else {
        await edmEnterpriseDeviceManager.disableAdmin(want);
      }
      const actual: boolean = await edmEnterpriseDeviceManager.isAdminEnabled(want);
      if (actual !== enable) {
        throw new Error('设备管理服务未确认请求的状态');
      }
      // A new singleton Want may already have replaced this page.
      if (this.isCurrentRequest()) {
        this.isShowActive = actual;
        await appDetailData.terminateAbilityPage();
      }
    } catch (error) {
      this.operationError = `操作失败：${error?.message ?? '设备管理服务不可用'}`;
      logger.error(TAG, this.operationError);
    } finally {
      this.operationPending = false;
    }
  }

'''+t[b:]
# Isolate fields per page; old async work must not retarget a singleton's new Want.
import re
for declaration in ('let appInfo: MyApplicationInfo;\n','let elementNameVal: Want;\n',
                    'let isAdminTypeVal: adminManager.AdminType;\n','let isActiveState: boolean;\n',
                    'let enterInfo: adminManager.EnterpriseInfo;\n'):
    t=t.replace(declaration,'')
t=t.replace("  @StorageLink('applicationInfo') applicationInfo",'  @State applicationInfo')
t=t.replace("  @StorageLink('activeType') isAdminType",'  @State isAdminType')
t=t.replace('async getAbilityWantVal(appInfo: MyApplicationInfo, elementNameVal: Want, adminType: adminManager.AdminType)', 'async getAbilityWantVal(appInfo: MyApplicationInfo)')
t=t.replace('async getCheckAbilityList(appInfo: MyApplicationInfo, elementNameVal: Want, adminType: adminManager.AdminType)', 'async getCheckAbilityList(appInfo: MyApplicationInfo)')
t=t.replace('this.getCheckAbilityList(this.applicationInfo, elementNameVal, isAdminTypeVal)', 'this.getCheckAbilityList(this.applicationInfo)')
t=t.replace('this.getAbilityWantVal(appInfo, elementNameVal, adminType)', 'this.getAbilityWantVal(appInfo)')
t=t.replace('    isAdminTypeVal = 0;\n','').replace('    isActiveState = this.isShowActive;\n','')
t=t.replace("isAdminTypeVal +", "this.isAdminType +")
for name in ('elementNameVal','enterInfo'):
    t=re.sub(r'(?<![.\w])'+name+r'\b', 'this.'+name, t)
    t=t.replace('private this.'+name, 'private '+name)
t=t.replace('    adminType = data.parameters?.activeType as adminManager.AdminType;', '    this.isAdminType = data.parameters?.activeType as adminManager.AdminType;')
t=t.replace("    AppStorage.SetOrCreate('activeType', adminType);\n",'')
t=t.replace('    this.pageActive = true;\n    this.elementNameVal', "    this.pageActive = true;\n    this.requestReady = false;\n    this.request = this.storage.get<Want>('adminProvisioningWant');\n    this.elementNameVal")
t=t.replace('    await this.getCheckAbilityList(this.applicationInfo);', "    try {\n      await this.getCheckAbilityList(this.applicationInfo);\n    } catch (error) {\n      this.isEnableButton = false;\n      this.operationError = `加载失败：${error?.message ?? '服务不可用'}`;\n    }")
t=t.replace('  async onPageShow(): Promise<void> {\n    try {', '  async onPageShow(): Promise<void> {\n    if (!this.requestReady || !this.isCurrentRequest()) {\n      return;\n    }\n    try {')
a=t.index('  onBackPress()');b=t.index('  async isAdminActive()',a)
t=t[:a]+'''  private isCurrentRequest(): boolean {
    return this.pageActive && this.storage.get<Want>('adminProvisioningWant') === this.request;
  }

  async cancelAdmin(): Promise<void> {
    if (!this.operationPending && this.isCurrentRequest()) {
      try {
        await appDetailData.terminateAbilityPage();
      } catch (error) {
        this.operationError = `取消失败：${error?.message ?? '界面退出失败'}`;
      }
    }
  }

  onBackPress(): boolean {
    this.cancelAdmin();
    return true;
  }

'''+t[b:]
t=t.replace('              appDetailData.terminateAbilityPage();', '              this.cancelAdmin();')
t=t.replace('    retSuperState = await edmEnterpriseDeviceManager.isSuperAdmin(name);', '    retSuperState = await edmEnterpriseDeviceManager.isSuperAdmin(wantTemp.bundleName);\n    if (!this.isCurrentRequest()) {\n      return;\n    }')
a=t.index('    let data = this.storage.get<Want>');b=t.index('    this.elementNameVal.abilityName',a)
t=t[:a]+'''    const data: Want | undefined = this.request;
    if (!data || !data.parameters || !this.isCurrentRequest()) {
      throw new Error('无效的设备管理请求');
    }
    const element = data.parameters.elementName as Record<string, string>;
    const enterprise = data.parameters.enterprise as Record<string, string>;
    if (!element || typeof element.bundleName !== 'string' || !element.bundleName ||
        typeof element.abilityName !== 'string' || !element.abilityName ||
        !enterprise || typeof enterprise.name !== 'string' || typeof enterprise.description !== 'string' ||
        (data.parameters.activeType !== adminManager.AdminType.ADMIN_TYPE_NORMAL &&
         data.parameters.activeType !== adminManager.AdminType.ADMIN_TYPE_SUPER)) {
      throw new Error('设备管理应用、类型或企业信息无效');
    }

'''+t[b:]
t=t.replace("      appDetailData.terminateAbilityPage();\n      return;", "      throw new Error('未找到有效的设备管理扩展');")
t=t.replace('    await this.isAdminActive();\n\n    if (appInfo.appBundleName)', '    await this.isAdminActive();\n    if (!this.isCurrentRequest()) {\n      return;\n    }\n\n    if (appInfo.appBundleName)')
t=t.replace('    try {\n      this.deviceAdminActive', '    if (!this.isCurrentRequest()) {\n      return;\n    }\n    try {\n      this.deviceAdminActive')
t=t.replace("    logger.info(TAG, 'getCheckAbilityList start enterpriseName='", "    if (!this.isCurrentRequest()) {\n      return;\n    }\n    logger.info(TAG, 'getCheckAbilityList start enterpriseName='")
t=t.replace("    logger.info(TAG, 'getCheckAbilityList enterpriseName='", "    this.requestReady = true;\n    logger.info(TAG, 'getCheckAbilityList enterpriseName='")
# Want fields are optional in the SDK: reject absent identity before querying.
t=t.replace('    let name: string = this.elementNameVal.bundleName;\n','')
t=t.replace('    retSuperState = await edmEnterpriseDeviceManager.isSuperAdmin(wantTemp.bundleName);',
            "    const name: string | undefined = wantTemp.bundleName;\n    if (typeof name !== 'string' || name.length === 0) {\n      throw new Error('设备管理应用名称缺失');\n    }\n    retSuperState = await edmEnterpriseDeviceManager.isSuperAdmin(name);")
after[p]=t
p='entry/src/main/ets/common/appManagement/appDetailData.ets';t=after[p];t=t.replace('  async checkAppItem(elementNameVal: Want) {','  async checkAppItem(elementNameVal: Want) {\n    this.ret = false;');t=t.replace("    logger.info(TAG, 'checkAppItem success');\n    return this.ret;", "    logger.info(TAG, 'checkAppItem success');\n    this.ret = true;\n    return true;");after[p]=t

p='entry/src/main/ets/MainAbility/UIExtensionAbility.ets';t=after[p].replace("import { BusinessError } from '@ohos.base';", "import { BusinessError } from '@ohos.base';\nimport baseData from '../common/baseData';")
a=t.index('export default class AutoDeployAbility');t=t[:a]+'''interface ProvisionAdmin {
  admin: Want;
  admin_type: string;
}
interface ProvisionEnterprise {
  organization_name: string;
  description: string;
}
interface ProvisionConfig {
  admin_info: ProvisionAdmin[];
  enterprise_info: ProvisionEnterprise;
}

export default class AutoDeployAbility extends UIExtensionAbility {
  private sessions: Set<UIExtensionContentSession> = new Set();

  async onSessionCreate(want: Want, session: UIExtensionContentSession): Promise<void> {
    if (this.sessions.has(session)) {
      return;
    }
    this.sessions.add(session);
    const storage: LocalStorage = new LocalStorage();
    try {
      const path: string = await configPolicy.getOneCfgFile('etc/edm/edm_provision_config.json');
      const config: ProvisionConfig = JSON.parse(fs.readTextSync(path)) as ProvisionConfig;
      if (!config || !Array.isArray(config.admin_info) || config.admin_info.length === 0 ||
          !config.admin_info[0] || !config.admin_info[0].admin ||
          typeof config.admin_info[0].admin.bundleName !== 'string' || !config.admin_info[0].admin.bundleName ||
          typeof config.admin_info[0].admin.abilityName !== 'string' || !config.admin_info[0].admin.abilityName ||
          config.admin_info[0].admin_type !== 'SDA' || !config.enterprise_info ||
          typeof config.enterprise_info.organization_name !== 'string' ||
          typeof config.enterprise_info.description !== 'string') {
        throw new Error('Invalid enterprise provisioning configuration');
      }
      if (!this.sessions.has(session)) {
        return;
      }
      storage.setOrCreate('adminInfo', config.admin_info[0].admin);
      storage.setOrCreate('enterpriseInfo', {
        name: config.enterprise_info.organization_name,
        description: config.enterprise_info.description
      } as adminManager.EnterpriseInfo);
      storage.setOrCreate('adminType', adminManager.AdminType.ADMIN_TYPE_SUPER);
      storage.setOrCreate('session', session);
      await session.loadContent('pages/custProvisioning/custProvisioning', storage);
    } catch (error) {
      logger.error(TAG, `Provisioning configuration/page failed: ${(error as BusinessError).message}`);
      if (this.sessions.has(session)) {
        try {
          await session.terminateSelfWithResult({ resultCode: baseData.ENABLE_ADMIN_FAILED });
        } catch (deliveryError) {
          logger.error(TAG, `Cannot deliver provisioning failure: ${(deliveryError as BusinessError).message}`);
        }
      }
    }
  }

  onSessionDestroy(session: UIExtensionContentSession): void {
    this.sessions.delete(session);
  }

  onDestroy(): void {
    this.sessions.clear();
  }
}
''';after[p]=t
p='entry/src/main/ets/pages/component/deployComponent.ets';t=after[p]
t=t.replace('  private session: UIExtensionContentSession | undefined;', '  private session: UIExtensionContentSession | undefined;\n  @State operationPending: boolean = false;\n  private pageActive: boolean = false;\n  private sessionFinished: boolean = false;')
t=t.replace('  aboutToAppear() {', '  aboutToAppear() {\n    this.pageActive = true;')
a=t.index('  private terminateAbility(');t=t[:a]+'''  aboutToDisappear(): void {
    this.pageActive = false;
  }

  private async terminateAbility(flag: number): Promise<void> {
    if (!this.pageActive || this.sessionFinished || !this.session ||
        (this.operationPending && flag === baseData.OOBE_PRE_STEP_CODE)) {
      return;
    }
    this.sessionFinished = true;
    try {
      await this.session.terminateSelfWithResult({ resultCode: flag, want: this.abilityInfo });
      this.storage.clear();
    } catch (error) {
      this.sessionFinished = false;
      logger.error(TAG, `Cannot deliver provisioning result: ${(error as BusinessError).message}`);
    }
  }

  private async EnableAdmin(): Promise<void> {
    if (this.operationPending || !this.pageActive || this.sessionFinished) {
      return;
    }
    this.operationPending = true;
    try {
      const admin: Want | undefined = this.abilityInfo;
      const enterprise: adminManager.EnterpriseInfo | undefined = this.enterpriseInfo;
      const type: adminManager.AdminType | undefined = this.adminType;
      if (!admin || !admin.bundleName || !admin.abilityName || !enterprise ||
          (type !== adminManager.AdminType.ADMIN_TYPE_NORMAL && type !== adminManager.AdminType.ADMIN_TYPE_SUPER)) {
        throw new Error('Missing administrator, enterprise or activation type');
      }
      const enabled: boolean = await adminManager.isAdminEnabled(admin);
      if (!this.pageActive) {
        return;
      }
      if (!enabled) {
        await adminManager.enableAdmin(admin, enterprise, type);
      }
      const actual: boolean = await adminManager.isAdminEnabled(admin);
      if (!actual) {
        throw new Error('Enterprise service did not confirm administrator activation');
      }
      await this.terminateAbility(baseData.OOBE_NEXT_STEP_CODE);
    } catch (error) {
      logger.error(TAG, `enableAdmin failed: ${(error as BusinessError).message}`);
      await this.terminateAbility(baseData.ENABLE_ADMIN_FAILED);
    } finally {
      this.operationPending = false;
    }
  }
}
''';after[p]=t
p='entry/src/main/ets/pages/autoManager/managerStart.ets';t=after[p];t=t.replace("    let data = this.storage.get<Want>('autoManagerAbilityWant');", "    const data: Want | undefined = this.storage.get<Want>('autoManagerAbilityWant');\n    if (!data || !data.parameters) {\n      logger.error(TAG, 'Missing auto-manager provisioning request');\n      (getContext(this) as common.UIAbilityContext).terminateSelf();\n      return;\n    }");after[p]=t
p='entry/src/main/ets/pages/custProvisioning/custProvisioning.ets';after[p]=after[p].replace('@Entry\n','@Entry({ useSharedStorage: true })\n')

def emit(project,originals,changed,component):
    target=ROOT/component;target.mkdir(parents=True,exist_ok=True);patch='';states=[]
    crlf=[]
    for path,text in changed.items():
        before=original(project,path) if path in originals else '';rel=project+'/'+path
        text=text.replace('\r\n','\n')
        if '\r\n' in before:
            crlf.append(rel)
            text=text.replace('\n','\r\n')
        patch+='diff --git a/'+rel+' b/'+rel+'\n'
        if path not in originals:patch+='new file mode 100644\n'
        for line in difflib.unified_diff(before.splitlines(True),text.splitlines(True),fromfile='a/'+rel if path in originals else '/dev/null',tofile='b/'+rel):
            patch+=line if line.endswith('\n') else line+'\n\\ No newline at end of file\n'
        states.append((path,hashlib.sha256(before.encode()).hexdigest() if path in originals else None,hashlib.sha256(text.encode()).hexdigest()))
    (target/'0001-build-real-admin-provider-and-verify-user-actions.patch').write_text(patch)
    (target/'verify_source.py').write_text('''#!/usr/bin/env python3
"""Pinned source composition; unknown edits fail before mutation."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = '''+repr(project)+'\nREVISION = '+repr(META['projects'][project]['revision'])+'\nFILES = '+repr(tuple(states))+'\n# Patch hunks retain exact CRLF bytes, including original no-final-newline cases.\nCRLF_FILES = '+repr(())+'''

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
''')
    (target/'apply.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_ROOT="$(cd "${COMPONENT_DIR}/../../../../.." && pwd)"
exec python3 "${PATCH_ROOT}/lib/apply_exact_component.py" --component-dir "${COMPONENT_DIR}" "$@"
''');(target/'apply.sh').chmod(0o755)
    return {p:sha for p,_,sha in states}
META['projects'][admin]['patched_sha256']=emit(admin,files,after,'patches/common/applications/standard/admin_provisioning/source_provider')
hap='applications/standard/hap'; before=original(hap,'BUILD.gn').replace('\r\n','\n');suffix='''
  # QEMU's configured provisioning provider must have a real source-built HAP.
  if (defined(product_name) &&
      (product_name == "arm64_virt" || product_name == "armv7a_virt" ||
       product_name == "x86_64_virt")) {
    deps += [ "//applications/standard/admin_provisioning:adminprovisioning_hap" ]
  }
''';a=before.rfind('\n}');assert a>0;after_hap=before[:a]+suffix+before[a:]
META['projects'][hap]['patched_sha256']=emit(hap,{'BUILD.gn':before},{'BUILD.gn':after_hap},'patches/common/applications/standard/hap/admin_provider')
(FIX/'provenance.json').write_text(json.dumps(META,indent=2)+'\n')
print('generated admin and HAP components')
