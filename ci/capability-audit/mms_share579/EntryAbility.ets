/* SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { Journal, Request } from '../common/Journal';

export default class EntryAbility extends UIAbility {
  private storage: LocalStorage = new LocalStorage();
  private current: Request | undefined = undefined;
  private publish(want: Want): void {
    Journal.context = this.context;
    Journal.filesDir = this.context.getApplicationContext().filesDir;
    const r = Journal.request(want);
    Journal.current = r;
    this.current = r;
    Journal.record(r, 'request', JSON.stringify(want));
    this.storage.setOrCreate<string>('uri579Want', JSON.stringify(want));
  }
  onCreate(want: Want): void { this.publish(want); }
  onNewWant(want: Want): void { this.publish(want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index', this.storage); }
  onDestroy(): void { if (this.current !== undefined) { Journal.record(this.current, 'ability.destroyed'); } }
}
