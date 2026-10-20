import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import CommunicationsAudit from './CommunicationsAudit';

export default class EntryAbility extends UIAbility {
  private audit: CommunicationsAudit | undefined;
  onCreate(want: Want): void {
    this.audit = new CommunicationsAudit(this.context);
    this.audit.accept(want.parameters?.request);
  }
  onNewWant(want: Want): void { this.audit?.accept(want.parameters?.request); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
