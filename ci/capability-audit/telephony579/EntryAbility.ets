import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import TelephonyAudit from './TelephonyAudit';

export default class EntryAbility extends UIAbility {
  private audit: TelephonyAudit | undefined;
  onCreate(want: Want): void {
    this.audit = new TelephonyAudit(this.context);
    this.audit.accept(want.parameters?.request);
  }
  onNewWant(want: Want): void { this.audit?.accept(want.parameters?.request); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
