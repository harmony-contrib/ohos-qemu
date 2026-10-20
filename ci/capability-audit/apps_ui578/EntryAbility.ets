import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { Journal } from '../common/Journal';

export default class EntryAbility extends UIAbility {
  onCreate(want: Want): void {
    Journal.record('process.created', 0);
    Journal.request(want);
  }
  onNewWant(want: Want): void { Journal.request(want); }
  onWindowStageCreate(stage: window.WindowStage): void {
    stage.loadContent('pages/Index', (error) => {
      Journal.record('window.loaded', error?.code ?? 0);
    });
  }
  onForeground(): void { Journal.record('foreground', 0); }
  onBackground(): void { Journal.record('background', 0); }
  onDestroy(): void { Journal.record('process.destroyed', 0); }
}
