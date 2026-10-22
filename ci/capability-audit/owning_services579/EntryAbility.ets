import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { BusinessError } from '@ohos.base';
import { Journal } from '../common/Journal';
import { Driver } from '../common/Driver';

export default class EntryAbility extends UIAbility {
  private pending?: Want;
  private ready: boolean = false;
  private dispatch(): void {
    const want = this.pending;
    this.pending = undefined;
    if (!want) { return; }
    try {
      Journal.request(want);
      const id = Journal.requestId;
      const action = Journal.action;
      Driver.execute(action, this.context).catch((error: BusinessError) => Journal.fail('error', error, id, action));
    } catch (error) { Journal.fail('request-error', error as BusinessError); }
  }
  onCreate(want: Want): void { Journal.record('ability-create'); this.pending = want; }
  onNewWant(want: Want): void { this.pending = want; if (this.ready) { this.dispatch(); } }
  onWindowStageCreate(stage: window.WindowStage): void {
    Driver.stage = stage;
    stage.loadContent('pages/Index', (error: BusinessError) => {
      if (error.code) { Journal.fail('page-error', error); return; }
      this.ready = true; Journal.record('page-ready'); this.dispatch();
    });
  }
  onForeground(): void { Journal.record('foreground'); }
  onBackground(): void { Journal.record('background'); }
  onWindowStageDestroy(): void { Journal.record('stage-destroy'); }
  onDestroy(): void { Journal.record('ability-destroy'); }
}
