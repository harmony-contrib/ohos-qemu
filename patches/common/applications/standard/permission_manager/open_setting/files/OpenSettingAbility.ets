/* Copyright (c) 2026 OpenHarmony QEMU contributors. Licensed under Apache-2.0. */
import UIExtensionAbility from '@ohos.app.ability.UIExtensionAbility';
import UIExtensionContentSession from '@ohos.app.ability.UIExtensionContentSession';
import Want from '@ohos.app.ability.Want';
import window from '@ohos.window';
import display from '@ohos.display';
import { INTERNAL_ERROR, OpenSettingRequest } from './OpenSettingRequest';

export default class OpenSettingAbility extends UIExtensionAbility {
  private dialogWindow: window.Window | null = null;
  private request: OpenSettingRequest | null = null;
  private session: UIExtensionContentSession | null = null;
  private creating: boolean = false;
  private destroyed: boolean = false;

  async onSessionCreate(want: Want, session: UIExtensionContentSession): Promise<void> {
    if (this.creating || this.request !== null) {
      this.returnError(session);
      return;
    }
    this.destroyed = false;
    this.session = session;
    this.creating = true;
    this.request = new OpenSettingRequest(want);
    try {
      const proxy = session.getUIExtensionHostWindowProxy();
      if (!proxy) {
        throw new Error('Missing UI extension host window');
      }
      // Do not fall back to an unparented/nonmodal grant window.
      this.dialogWindow = await proxy.createSubWindowWithOptions('ManualPermission' + Date.now(),
        { title: '', decorEnabled: false, isModal: true });
      if (this.destroyed) {
        await this.destroyWindow();
        return;
      }
      const screen = display.getDefaultDisplaySync();
      await this.dialogWindow.resize(screen.width, screen.height);
      this.dialogWindow.setWindowBackgroundColor('#00000000');
      this.dialogWindow.hideNonSystemFloatingWindows(true);
      const entries: Record<string, Object> = { 'manualRequest': this.request, 'manualSession': session };
      const storage = new LocalStorage(entries);
      await this.dialogWindow.loadContent('OpenSetting/OpenSettingDialog', storage);
      if (!this.destroyed) {
        await this.dialogWindow.showWindow();
      }
    } catch (error) {
      if (!this.destroyed) {
        this.returnError(session);
      }
      await this.destroyWindow();
    } finally {
      this.creating = false;
    }
  }

  private returnError(session: UIExtensionContentSession): void {
    session.terminateSelfWithResult({ resultCode: 0,
      want: { parameters: { 'ohos.open.setting.result_code': INTERNAL_ERROR } } });
  }

  private async destroyWindow(): Promise<void> {
    const dialog = this.dialogWindow;
    this.dialogWindow = null;
    if (dialog) {
      try {
        dialog.hideNonSystemFloatingWindows(false);
      } finally {
        await dialog.destroyWindow();
      }
    }
  }

  private async closeSession(): Promise<void> {
    this.destroyed = true;
    if (this.request) {
      this.request.active = false;
    }
    this.request = null;
    this.session = null;
    await this.destroyWindow();
  }

  async onSessionDestroy(session: UIExtensionContentSession): Promise<void> {
    // Closing a rejected concurrent session must not close the original one.
    if (session === this.session) {
      await this.closeSession();
    }
  }

  async onDestroy(): Promise<void> {
    await this.closeSession();
  }
}
