/* SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { SeedRequest } from '../model/SeedStore';

export default class EntryAbility extends UIAbility {
  // Per-Ability storage; never share a nonce through process-global AppStorage.
  private storage: LocalStorage = new LocalStorage();
  private publish(want: Want): void {
    const request = new SeedRequest();
    request.runId = want.parameters?.runId as string ?? '';
    request.operationId = want.parameters?.operationId as string ?? '';
    request.mode = want.parameters?.mode as string ?? '';
    this.storage.setOrCreate('seedRequest', JSON.stringify(request));
  }
  onCreate(want: Want): void { this.publish(want); }
  onNewWant(want: Want): void { this.publish(want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index', this.storage); }
}
