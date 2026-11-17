/* Copyright (c) 2025 Huawei Device Co., Ltd. SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';

export default class ByodAdminProvisionAbility extends UIAbility {
  private storage:LocalStorage=new LocalStorage();
  private publish(want:Want):void {
    // Publish each immutable framework-delivered request. The page owns its
    // own generation and cannot retarget an already-authorized backend write.
    this.storage.setOrCreate('byodWant',JSON.stringify(want));
  }
  onCreate(want:Want):void{this.publish(want);}
  onNewWant(want:Want):void{this.publish(want);}
  onWindowStageCreate(stage:window.WindowStage):void{
    stage.loadContent('pages/byod/byodActivationPage',this.storage);
  }
  onDestroy():void{this.storage.setOrCreate('byodWant','');}
}
