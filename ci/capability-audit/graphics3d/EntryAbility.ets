// SPDX-License-Identifier: Apache-2.0
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { graphics3d } from '../graphics3d/GraphicsController';

export default class EntryAbility extends UIAbility {
  private accept(want: Want): void {
    const request = want.parameters?.request;
    if (typeof request !== 'string') { throw new Error('Original Owner request required'); }
    graphics3d.accept(request);
  }
  onCreate(want: Want): void {
    graphics3d.filesDir = this.context.filesDir;
    this.accept(want);
  }
  onNewWant(want: Want): void { this.accept(want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
