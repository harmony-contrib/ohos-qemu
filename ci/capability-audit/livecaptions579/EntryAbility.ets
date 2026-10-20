import UIAbility from '@ohos.app.ability.UIAbility';
import { Want } from '@kit.AbilityKit';
import window from '@ohos.window';
import { run } from './Probe';
export default class EntryAbility extends UIAbility {
  private queue: Promise<void> = Promise.resolve();
  onCreate(want: Want): void { this.dispatch(want); }
  onNewWant(want: Want): void { this.dispatch(want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
  private dispatch(want: Want): void { this.queue = this.queue.then((): Promise<void> => run(this.context, want)); }
}
