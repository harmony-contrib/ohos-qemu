import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { BusinessError } from '@ohos.base';
import { Journal, CASE, HOST, OTHER_HOST, RUN } from '../common/Journal';
import { Driver } from '../common/Driver';

export default class EntryAbility extends UIAbility {
  private pending?: Want;
  private ready: boolean = false;
  private accept(want: Want): void {
    // Only an OS-delivered App Linking Want reaches this branch. The caller
    // never supplies a bundle name or a private registry transaction.
    if (CASE === 'domain' && (want.uri?.startsWith('https://' + HOST + '/') ||
      want.uri?.startsWith('http://' + HOST + '/') || want.uri?.startsWith('https://' + OTHER_HOST + '/'))) {
      const parts = (want.uri ?? '').split('/');
      if (parts.length !== 6 || parts[3] !== 'services578' || parts[4] !== RUN ||
        !/^[a-z0-9_-]{1,64}$/.test(parts[5])) {
        Journal.record('route-invalid', -1, JSON.stringify(want));
        return;
      }
      Journal.record('routed', 0, JSON.stringify(want), parts[5], 'route');
      return;
    }
    this.pending = want;
    if (this.ready) { this.dispatch(); }
  }
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
  onCreate(want: Want): void { Journal.record('ability-create'); this.accept(want); }
  onNewWant(want: Want): void { this.accept(want); }
  onWindowStageCreate(stage: window.WindowStage): void {
    Driver.stage = stage;
    stage.loadContent('pages/Index', (error: BusinessError) => {
      if (error.code) { Journal.fail('page-error', error); return; }
      this.ready = true;
      Journal.record('page-ready');
      this.dispatch();
    });
  }
  onForeground(): void { Journal.record('foreground'); }
  onBackground(): void { Journal.record('background'); }
  onWindowStageDestroy(): void { Journal.record('stage-destroy'); }
  onDestroy(): void { Journal.record('ability-destroy'); }
}
