/* SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
export default class EntryAbility extends UIAbility {
  private storage: LocalStorage = new LocalStorage();
  private request(want: Want): void {
    this.storage.setOrCreate<string>('calendarRequest', want.parameters?.request as string ?? '');
  }
  onCreate(want: Want): void { this.request(want); }
  onNewWant(want: Want): void { this.request(want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index', this.storage); }
}
