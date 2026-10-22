// Copyright (c) 2026 OpenHarmony contributors. Licensed under Apache-2.0.
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { UsbAudit } from './UsbAudit';

export default class EntryAbility extends UIAbility {
  private audit: UsbAudit | undefined = undefined;
  onCreate(want: Want): void { this.audit = new UsbAudit(this.context); this.accept(want); }
  onNewWant(want: Want): void { this.accept(want); }
  private accept(want: Want): void {
    const request = want.parameters?.request;
    if (typeof request !== 'string' || this.audit === undefined) { throw new Error('Actual USB request required'); }
    this.audit.accept(request);
  }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
