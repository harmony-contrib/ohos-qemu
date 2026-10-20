/* SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
export default class EntryAbility extends UIAbility {
  private storage: LocalStorage = new LocalStorage();
  private publish(want: Want): void {
    this.storage.setOrCreate<string>('share578Want', JSON.stringify(want));
  }
  onCreate(want: Want): void { this.publish(want); }
  onNewWant(want: Want): void { this.publish(want); }
  onWindowStageCreate(stage: window.WindowStage): void {
    stage.loadContent('pages/Index', this.storage);
  }
}
