/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import UIExtensionAbility from '@ohos.app.ability.UIExtensionAbility';
import UIExtensionContentSession from '@ohos.app.ability.UIExtensionContentSession';
import Want from '@ohos.app.ability.Want';
import { SharePickerController } from './SharePickerController';

export default class SharePickerExtension extends UIExtensionAbility {
  private opened: Set<UIExtensionContentSession> = new Set();
  private sessions: Map<UIExtensionContentSession, SharePickerController> = new Map();

  async onSessionCreate(want: Want, session: UIExtensionContentSession): Promise<void> {
    if (this.opened.has(session)) {
      return;
    }
    this.opened.add(session);
    let failureCode: number = 401;
    try {
      const controller = new SharePickerController(want, session);
      this.sessions.set(session, controller);
      failureCode = 16000050;
      const storage: LocalStorage = new LocalStorage();
      storage.setOrCreate('shareController', controller);
      await session.loadContent('pages/SharePicker', storage);
    } catch (error) {
      this.sessions.get(session)?.dispose();
      this.sessions.delete(session);
      if (!this.opened.has(session)) {
        return;
      }
      try {
        await session.terminateSelfWithResult({ resultCode: failureCode,
          want: { parameters: { outcome: failureCode === 401 ? 'invalid' : 'error', message: (error as Error).message } } });
      } catch (deliveryError) {
        console.error('Cannot return share picker error');
      }
    }
  }

  onSessionDestroy(session: UIExtensionContentSession): void {
    this.sessions.get(session)?.dispose();
    this.sessions.delete(session);
    this.opened.delete(session);
  }

  onDestroy(): void {
    this.sessions.forEach((controller: SharePickerController) => controller.dispose());
    this.sessions.clear();
    this.opened.clear();
  }
}
