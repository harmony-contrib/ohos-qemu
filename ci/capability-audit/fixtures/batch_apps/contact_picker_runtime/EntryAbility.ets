/* Copyright (c) 2026 Harmony Contrib
 * SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';

class LaunchEnvelope {
  runId: string = '';
  launchId: string = '';
  caseId: string = '';
  seedIdsJson: string = '[]';
  queryKey: string = '';
  sequence: number = 0;
}

export default class EntryAbility extends UIAbility {
  private storage: LocalStorage = new LocalStorage();
  private sequence: number = 0;
  private lifecycleSequence: number = 0;

  private publish(want: Want): void {
    const input = new LaunchEnvelope();
    input.runId = want.parameters?.runId as string ?? '';
    input.launchId = want.parameters?.launchId as string ?? '';
    input.caseId = want.parameters?.caseId as string ?? '';
    input.seedIdsJson = want.parameters?.seedIds as string ?? '[]';
    input.queryKey = want.parameters?.queryKey as string ?? '';
    input.sequence = ++this.sequence;
    this.storage.setOrCreate('requestJson', JSON.stringify(input));
  }

  onCreate(want: Want): void {
    this.storage.setOrCreate('lifecycleEvent', 'created/' + ++this.lifecycleSequence);
    this.publish(want);
  }
  onNewWant(want: Want): void { this.publish(want); }
  onWindowStageCreate(stage: window.WindowStage): void {
    stage.loadContent('pages/Index', this.storage);
  }
  onForeground(): void { this.storage.setOrCreate('lifecycleEvent', 'foreground/' + ++this.lifecycleSequence); }
  onBackground(): void { this.storage.setOrCreate('lifecycleEvent', 'background/' + ++this.lifecycleSequence); }
  onWindowStageDestroy(): void { this.storage.setOrCreate('lifecycleEvent', 'stage-destroy/' + ++this.lifecycleSequence); }
}
