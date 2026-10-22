/* Copyright (c) 2025 Huawei Device Co., Ltd. SPDX-License-Identifier: Apache-2.0 */
import { BaseByodAdminPage, BottomButton } from './baseByodAdminPage';
import common from '@ohos.app.ability.common';
import Want from '@ohos.app.ability.Want';
import bundleManager from '@ohos.bundle.bundleManager';
import adminManager from '@ohos.enterprise.adminManager';
import process from '@ohos.process';
import { BusinessError } from '@ohos.base';

interface OwnedByodRequest {target:Want;callerUid:number;activateId:string;description:string;}
@Entry
@Component
struct ByodActivationPage {
  @LocalStorageProp('byodWant') @Watch('changed') encoded:string='';
  @State busy:boolean=false;
  @State status:string='';
  private generation:number=0;
  private active:boolean=false;
  private changed():void{this.generation++;this.busy=false;this.status='';}
  aboutToAppear():void{this.active=true;this.changed();}
  aboutToDisappear():void{this.active=false;this.generation++;}
  private request():OwnedByodRequest {
    const want=JSON.parse(this.encoded) as Want;
    const values=want.parameters;
    if(values===undefined)throw new Error('Missing provisioning request');
    const bundle=values['bundleName'];const ability=values['abilityName'];
    const caller=values['ohos.aafwk.param.callerBundleName'];const uid=values['ohos.aafwk.param.callerUid'];
    const activation=values['activateId'];const custom=values['customizedInfo'];
    if(typeof bundle!=='string'||!/^[A-Za-z][A-Za-z0-9_.]{3,127}$/.test(bundle)||typeof ability!=='string'||ability.length<1||ability.length>256||
       typeof caller!=='string'||caller!==bundle||typeof uid!=='number'||!Number.isInteger(uid)||uid%200000<10000||Math.floor(uid/200000)!==Math.floor(process.uid/200000)||
       typeof activation!=='string'||activation.length<32||activation.length>256||
       (custom!==undefined&&(typeof custom!=='string'||custom.length>1024))||values['localDeactivationPolicy']!==undefined) {
      throw new Error('Unsupported or foreign provisioning request');
    }
    return {target:{bundleName:bundle,abilityName:ability},callerUid:uid,activateId:activation,description:typeof custom==='string'?custom:''};
  }
  private async agree():Promise<void>{
    if(!this.active||this.busy)return;
    const epoch=this.generation;const encoded=this.encoded;this.busy=true;
    try{
      const request=this.request();
      const info=await bundleManager.getBundleInfo(request.target.bundleName as string,
        bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_APPLICATION|bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_HAP_MODULE|bundleManager.BundleFlag.GET_BUNDLE_INFO_WITH_EXTENSION_ABILITY);
      if(info.appInfo.uid!==request.callerUid||!info.hapModulesInfo.some((module)=>module.extensionAbilitiesInfo.some((entry)=>entry.name===request.target.abilityName&&entry.type===bundleManager.ExtensionAbilityType.ENTERPRISE_ADMIN))) {
        throw new Error('Actual caller enterprise extension differs');
      }
      if(!this.active||epoch!==this.generation||encoded!==this.encoded)return;
      if(await adminManager.isAdminEnabled(request.target))throw new Error('Administrator already enabled; preserve existing ownership');
      if(!this.active||epoch!==this.generation||encoded!==this.encoded)return;
      // This existing public authorized activation is the same EDM backend
      // used by normal administration. Keep the original APL/ACL/permissions.
      await adminManager.enableAdmin(request.target,{name:request.target.bundleName as string,description:request.description},adminManager.AdminType.ADMIN_TYPE_BYOD);
      if(!await adminManager.isAdminEnabled(request.target)||!adminManager.isByodAdmin(request.target))throw new Error('BYOD backend state did not commit');
      if(this.active&&epoch===this.generation&&encoded===this.encoded){
        this.status='BYOD activated';await (getContext(this) as common.UIAbilityContext).terminateSelf();
      }
    }catch(error){if(this.active&&epoch===this.generation&&encoded===this.encoded){const e=error as BusinessError;this.status=(e.code??-1).toString()+':'+e.message;}}
    finally{if(this.active&&epoch===this.generation&&encoded===this.encoded)this.busy=false;}
  }
  private cancel():void{
    // Cancel before authorization performs no backend write. A user-authorized
    // already-dispatched operation retains its immutable target if UI exits.
    this.active=false;this.generation++;(getContext(this) as common.UIAbilityContext).terminateSelf();
  }
  @Builder topBuilder(){Text($r('app.string.byodActivationPageTitle')).fontColor($r('sys.color.ohos_id_color_text_primary')).fontWeight(FontWeight.Bold).lineHeight('27vp').fontSize('20vp')}
  @Builder centerBuilder(){Text(this.status).id('byod-provisioning-status')}
  @Builder bottomBuilder(){Row({space:'12vp'}){
    BottomButton({description:$r('app.string.byodDisagree'),buttonWidth:'158vp',isEnabled:!this.busy}).onClick(()=>this.cancel())
    BottomButton({description:$r('app.string.byodAgree'),buttonWidth:'158vp',isEnabled:!this.busy}).onClick(()=>this.agree())
  }}
  build(){Column(){BaseByodAdminPage({topBuilderParam:()=>{this.topBuilder()},listTitle:'',centerBuilderParam:()=>{this.centerBuilder()},bottomBuilderParam:()=>{this.bottomBuilder()}})}}
}
