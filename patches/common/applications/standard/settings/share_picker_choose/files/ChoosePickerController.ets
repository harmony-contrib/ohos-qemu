/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import Want from '@ohos.app.ability.Want';
import common from '@ohos.app.ability.common';
import dialogSession from '@ohos.app.ability.dialogSession';
import bundleManager from '@ohos.bundle.bundleManager';

export interface ChooseTarget {
  key: string;
  bundleName: string;
  moduleName: string;
  abilityName: string;
  label: string;
}

export class ChoosePickerController {
  targets: ChooseTarget[] = [];
  error: string = '';
  loading: boolean = false;
  busy: boolean = false;
  accepted: boolean = false;
  cancelled: boolean = false;
  private active: boolean = true;
  private completed: boolean = false;
  private revision: number = 0;
  private context: common.UIAbilityContext;
  private sessionId: string;

  constructor(want: Want, context: common.UIAbilityContext) {
    const id = want.parameters?.['dialogSessionId'];
    if (typeof id !== 'string' || !/^legacy_picker_[0-9]+_[0-9]+_[0-9]+_[0-9]+$/.test(id) || id.length > 200) {
      throw new Error('Missing native picker session');
    }
    this.sessionId = id;
    this.context = context;
    // Verify the binding already made by AMS AttachAbilityThread, before any
    // page-load failure, Back action or cancellation can occur.
    dialogSession.getDialogSessionInfo(this.sessionId);
    // No Want payload, reserved caller identity, remote token, requestCode,
    // URI grant or caller-provided component crosses this boundary. AMS owns
    // the complete original Want and returns only matched component identities.
  }

  async load(): Promise<void> {
    if (!this.active || this.loading || this.busy || this.completed || this.accepted || this.cancelled) {
      return;
    }
    this.loading = true;
    this.error = '';
    const revision = ++this.revision;
    try {
      const info = dialogSession.getDialogSessionInfo(this.sessionId);
      const targets: ChooseTarget[] = [];
      const seen: Set<string> = new Set();
      for (const target of info.targetAbilityInfos) {
        if (!target.visible || target.appIndex !== 0 || !target.bundleName || !target.moduleName || !target.abilityName) {
          continue;
        }
        const key: string = `${target.bundleName}/${target.moduleName}/${target.abilityName}`;
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        let label: string = `${target.bundleName}: ${target.abilityName}`;
        try {
          label = await bundleManager.getAbilityLabel(target.bundleName, target.moduleName, target.abilityName);
        } catch (error) {
          // A failed label lookup does not substitute a different handler.
        }
        if (!this.active || revision !== this.revision) {
          return;
        }
        targets.push({ key: key, bundleName: target.bundleName, moduleName: target.moduleName,
          abilityName: target.abilityName, label: label });
      }
      if (this.active && revision === this.revision) {
        this.targets = targets;
      }
    } catch (error) {
      if (this.active && revision === this.revision) {
        this.targets = [];
        this.error = `无法查询应用：${(error as Error).message}`;
      }
    } finally {
      if (revision === this.revision) {
        this.loading = false;
      }
    }
  }

  async choose(key: string): Promise<void> {
    if (!this.active || this.loading || this.busy || this.completed) {
      return;
    }
    this.busy = true;
    this.error = '';
    try {
      if (!this.accepted && !this.cancelled) {
        const target = this.targets.find((item: ChooseTarget) => item.key === key);
        if (target === undefined) {
          throw new Error('请选择当前列表中的应用');
        }
        // AMS authenticates this dialog process/session, requeries the original
        // action-cleared MIME/URI/entities and launches with its stored caller
        // token/requestCode. It ignores all UI-supplied payload and flags.
        await dialogSession.sendDialogResult(this.sessionId, { bundleName: target.bundleName,
          moduleName: target.moduleName, abilityName: target.abilityName }, true);
        this.accepted = true;
      }
      if (this.active) {
        await this.close();
      }
    } catch (error) {
      if (this.active) {
        this.error = `无法打开应用：${(error as Error).message}`;
      }
    } finally {
      this.busy = false;
    }
  }

  async cancel(): Promise<void> {
    if (!this.active || this.busy || this.completed) {
      return;
    }
    this.busy = true;
    this.error = '';
    ++this.revision;
    this.loading = false;
    try {
      if (!this.accepted && !this.cancelled) {
        await dialogSession.sendDialogResult(this.sessionId, {}, false);
        this.cancelled = true;
      }
    } catch (error) {
      if (this.active) {
        this.error = `无法关闭选择窗口：${(error as Error).message}`;
      }
    } finally {
      // A failed native cancellation is not a successful cancellation. Still
      // allow exit; AMS verified-close/death/deadline cleans its owned session.
      if (this.active) {
        try {
          await this.close();
        } catch (closeError) {
          this.error += `；${(closeError as Error).message}`;
        }
      }
      this.busy = false;
    }
  }

  private async close(): Promise<void> {
    // The picker was started normally. A fabricated terminateSelfWithResult
    // would not return to the original caller; native dialogSession owns that.
    await this.context.terminateSelf();
    this.completed = true;
  }

  dispose(): void {
    this.active = false;
    ++this.revision;
    this.targets = [];
    // Native OnAbilityDied/verified close/timeout owns reliable cancellation.
    // Never start another asynchronous launch or use a released context here.
  }
}
