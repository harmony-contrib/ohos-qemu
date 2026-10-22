import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { AudioAudit } from './AudioAudit';

export default class EntryAbility extends UIAbility {
  private audit: AudioAudit | undefined = undefined;
  onCreate(want: Want): void {
    this.audit = new AudioAudit(this.context);
    this.accept(want);
  }
  onNewWant(want: Want): void { this.accept(want); }
  private accept(want: Want): void {
    const text = want.parameters?.request;
    if (typeof text !== 'string' || this.audit === undefined) { throw new Error('Original held request required'); }
    this.audit.accept(text);
  }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
