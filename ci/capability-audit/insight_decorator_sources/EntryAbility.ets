import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import AbilityConstant from '@ohos.app.ability.AbilityConstant';
import window from '@ohos.window';
import fs from '@ohos.file.fs';
import process from '@ohos.process';

export default class EntryAbility extends UIAbility {
  private record(name: string, want: Want): void {
    const file = fs.openSync('/data/storage/el2/base/files/insight-target-__INTENT_RUN__-results.log',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    try {
      fs.writeSync(file.fd, JSON.stringify({ runId: '__INTENT_RUN__', name,
        uid: process.uid, pid: process.pid, want }) + '\n');
    } finally { fs.closeSync(file); }
    AppStorage.setOrCreate('auditIntentUri', want.uri || '');
  }
  onCreate(want: Want, launch: AbilityConstant.LaunchParam): void { this.record('create', want); }
  onNewWant(want: Want, launch: AbilityConstant.LaunchParam): void { this.record('newWant', want); }
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
