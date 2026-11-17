/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import UIAbility from '@ohos.app.ability.UIAbility';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import { ChoosePickerController } from './ChoosePickerController';

export default class ChoosePickerAbility extends UIAbility {
  private controller: ChoosePickerController | undefined = undefined;
  private active: boolean = true;

  onCreate(want: Want): void {
    try {
      this.controller = new ChoosePickerController(want, this.context);
    } catch (error) {
      console.error(`Cannot open native picker session: ${(error as Error).message}`);
      this.closeInvalid();
    }
  }

  async onWindowStageCreate(stage: window.WindowStage): Promise<void> {
    if (!this.active || this.controller === undefined) {
      return;
    }
    const controller = this.controller;
    const storage: LocalStorage = new LocalStorage();
    storage.setOrCreate('chooseController', controller);
    try {
      await stage.loadContent('pages/ChoosePicker', storage);
    } catch (error) {
      if (this.active && this.controller === controller) {
        console.error(`Cannot load picker page: ${(error as Error).message}`);
        await controller.cancel();
      }
    }
  }

  onNewWant(): void {
    // Standard instances isolate each native session. Never replace an
    // existing controller with a different untrusted Want/session identity.
    this.controller?.cancel();
  }

  onBackPressed(): boolean {
    this.controller?.cancel();
    return true;
  }

  onWindowStageDestroy(): void {
    this.controller?.dispose();
    this.active = false;
  }

  onDestroy(): void {
    this.controller?.dispose();
    this.controller = undefined;
    this.active = false;
  }

  private async closeInvalid(): Promise<void> {
    try {
      await this.context.terminateSelf();
    } catch (error) {
      console.error(`Cannot close invalid picker: ${(error as Error).message}`);
    }
  }
}
