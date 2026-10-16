/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { BusinessError } from '@ohos.base';
import { CalendarController, CalendarView } from '../calendar/CalendarController';

export default class MainAbility extends UIAbility {
  private controller: CalendarController | undefined = undefined;
  private storage: LocalStorage = new LocalStorage();
  private uri: string = '';
  private visible: boolean = false;

  private ensureController(): CalendarController {
    if (this.controller === undefined) {
      this.controller = new CalendarController(this.context, (view: CalendarView) => {
        this.storage.setOrCreate<CalendarView>('calendarView', view);
      });
      this.controller.setUri(this.uri);
      this.storage.setOrCreate<CalendarController>('calendarController', this.controller);
      this.storage.setOrCreate<CalendarView>('calendarView', new CalendarView());
    }
    return this.controller;
  }

  onCreate(want: Want): void {
    this.uri = want.uri ?? '';
  }

  onNewWant(want: Want): void {
    this.uri = want.uri ?? '';
    this.controller?.setUri(this.uri);
  }

  onWindowStageCreate(stage: window.WindowStage): void {
    let controller: CalendarController | undefined = undefined;
    try {
      controller = this.ensureController();
    } catch (error) {
      const view = new CalendarView();
      view.error = '日历初始化失败：' + (error as BusinessError).message;
      this.storage.setOrCreate<CalendarView>('calendarView', view);
    }
    try {
      stage.loadContent('pages/index', this.storage, (error: BusinessError) => {
        if (this.controller !== controller) {
          return;
        }
        if (error.code) {
          controller?.background();
          console.error('Calendar MainAbility loadContent failed: ' + error.code);
          return;
        }
        if (this.visible && this.controller === controller) {
          controller?.foreground();
        }
      });
    } catch (error) {
      console.error('Calendar MainAbility loadContent failed: ' + (error as BusinessError).message);
    }
  }

  onForeground(): void {
    this.visible = true;
    this.controller?.foreground();
  }

  onBackground(): void {
    this.visible = false;
    this.controller?.background();
  }

  onWindowStageDestroy(): void {
    this.controller?.dispose();
    this.controller = undefined;
    this.storage = new LocalStorage();
  }

  onDestroy(): void {
    this.visible = false;
    this.controller?.dispose();
    this.controller = undefined;
  }
}
