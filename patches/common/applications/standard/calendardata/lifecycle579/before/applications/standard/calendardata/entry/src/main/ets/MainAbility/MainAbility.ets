/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';

export default class MainAbility extends UIAbility {
  private storage: LocalStorage = new LocalStorage();
  private revision: number = 0;
  private visible: boolean = false;

  onCreate(want: Want): void {
    this.storage.setOrCreate<boolean>('calendarForeground', false);
    this.storage.setOrCreate<string>('calendarRoute', want.uri ?? '');
    this.storage.setOrCreate<number>('calendarRevision', ++this.revision);
  }

  onNewWant(want: Want): void {
    this.storage.setOrCreate<string>('calendarRoute', want.uri ?? '');
    this.storage.setOrCreate<number>('calendarRevision', ++this.revision);
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    this.storage.setOrCreate<boolean>('calendarForeground', this.visible);
    this.storage.setOrCreate<number>('calendarRevision', ++this.revision);
    windowStage.loadContent('pages/index', this.storage);
  }

  onForeground(): void {
    this.visible = true;
    this.storage.setOrCreate<boolean>('calendarForeground', true);
    this.storage.setOrCreate<number>('calendarRevision', ++this.revision);
  }

  onBackground(): void {
    this.visible = false;
    this.storage.setOrCreate<boolean>('calendarForeground', false);
    this.storage.setOrCreate<number>('calendarRevision', ++this.revision);
  }

  onWindowStageDestroy(): void {
    this.storage.setOrCreate<boolean>('calendarForeground', false);
    this.storage.setOrCreate<number>('calendarRevision', ++this.revision);
  }

  onDestroy(): void {
    this.visible = false;
    this.storage.setOrCreate<boolean>('calendarForeground', false);
    this.storage.setOrCreate<string>('calendarRoute', '');
    this.storage.setOrCreate<number>('calendarRevision', ++this.revision);
  }
}
