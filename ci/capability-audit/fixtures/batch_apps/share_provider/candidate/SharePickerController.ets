/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import Want from '@ohos.app.ability.Want';
import UIExtensionContentSession from '@ohos.app.ability.UIExtensionContentSession';
import bundleManager from '@ohos.bundle.bundleManager';
import wantConstant from '@ohos.app.ability.wantConstant';
import uri from '@ohos.uri';

export interface ShareTarget {
  key: string;
  bundleName: string;
  moduleName: string;
  abilityName: string;
  label: string;
}

export class SharePickerController {
  targets: ShareTarget[] = [];
  error: string = '';
  busy: boolean = false;
  loading: boolean = false;
  launched: boolean = false;
  private session: UIExtensionContentSession;
  private payload: Want;
  private active: boolean = true;
  private completed: boolean = false;
  private selected: ShareTarget | undefined = undefined;
  private revision: number = 0;

  constructor(want: Want, session: UIExtensionContentSession) {
    this.session = session;
    this.payload = this.parse(want);
  }

  private parse(want: Want): Want {
    const params: Record<string, Object> = want.parameters ?? {};
    const rawMime = params['type'] ?? want.type ?? 'text/plain';
    if (typeof rawMime !== 'string' || !/^[a-zA-Z0-9!#$&^_.+*-]+\/[a-zA-Z0-9!#$&^_.+*-]+$/.test(rawMime) || rawMime.length > 127) {
      throw new Error('Invalid share MIME type');
    }
    const mime: string = rawMime.toLowerCase();
    const subject = params['ability.subject'] ?? '';
    if (typeof subject !== 'string' || subject.length > 5000 || subject.includes('\u0000')) {
      throw new Error('Invalid share subject');
    }
    const uri = params['uri'] ?? want.uri ?? '';
    if (typeof uri !== 'string') {
      throw new Error('Invalid share URI');
    }
    let stream = params['ability.params.stream'];
    if (mime === 'text/plain' && uri.length === 0 && Array.isArray(stream) && stream.length === 1 &&
        typeof stream[0] === 'string' && !stream[0].startsWith('file://')) {
      stream = stream[0] as string;
    }
    const payload: Want = { action: 'ohos.want.action.sendData', type: mime, parameters: {} };
    if (uri.length > 0 || Array.isArray(stream)) {
      const uris: string[] = [];
      if (Array.isArray(stream)) {
        if (stream.length === 0 || stream.length > 300) {
          throw new Error('Invalid share file count');
        }
        const entries: Object[] = stream as Object[];
        for (let i = 0; i < entries.length; i++) {
          const item: Object = entries[i];
          if (typeof item !== 'string' || !this.isFileUri(item)) {
            throw new Error('Only file URIs are accepted as file streams');
          }
          uris.push(item);
        }
      } else if (uri.length > 0) {
        if (stream !== undefined) {
          throw new Error('URI payload must use an array of file streams');
        }
        uris.push(uri);
      }
      if (!this.isFileUri(uris[0]) || (uri.length > 0 && uri !== uris[0])) {
        throw new Error('Share URI and first stream disagree');
      }
      const read = wantConstant.Flags.FLAG_AUTH_READ_URI_PERMISSION;
      if (((want.flags ?? 0) & read) === 0) {
        throw new Error('Caller did not authorize URI read access');
      }
      payload.uri = uris[0];
      payload.flags = read;
      payload.parameters = { 'ability.params.stream': uris, 'ability.subject': subject };
    } else {
      if (stream !== undefined && typeof stream === 'string' && stream.length > 0 && !mime.startsWith('text/')) {
        throw new Error('Non-text MIME requires an authorized file URI');
      }
      if (stream !== undefined && (typeof stream !== 'string' || stream.length > 262144 || stream.includes('\u0000'))) {
        throw new Error('Invalid shared text');
      }
      payload.parameters = { 'ability.params.stream': stream ?? '', 'ability.subject': subject };
    }
    return payload;
  }

  private isFileUri(value: string): boolean {
    if (value.length > 8192 || /[\u0000\r\n\s\\]/.test(value) || /%(?![0-9a-fA-F]{2})/.test(value)) {
      return false;
    }
    try {
      const parsed = new uri.URI(value);
      return parsed.scheme === 'file' && parsed.authority.length > 0 && parsed.path.length > 1 &&
        parsed.userInfo.length === 0 && parsed.fragment.length === 0;
    } catch (error) {
      return false;
    }
  }

  private queryWant(): Want {
    // No caller-supplied component, caller identity, account or launch options.
    return { action: this.payload.action, type: this.payload.type, uri: this.payload.uri };
  }

  async load(): Promise<void> {
    if (!this.active || this.busy || this.loading || this.completed || this.launched) {
      return;
    }
    this.loading = true;
    this.error = '';
    const revision = ++this.revision;
    try {
      const infos = await bundleManager.queryAbilityInfo(this.queryWant(),
        bundleManager.AbilityFlag.GET_ABILITY_INFO_WITH_APPLICATION);
      const targets: ShareTarget[] = [];
      const seen: Set<string> = new Set();
      for (let i = 0; i < infos.length; i++) {
        if (!this.active || this.completed || revision !== this.revision) {
          return;
        }
        const info = infos[i];
        if (!info.exported || !info.enabled || !info.applicationInfo.enabled ||
            !info.bundleName || !info.moduleName || !info.name) {
          continue;
        }
        const key = `${info.bundleName}/${info.moduleName}/${info.name}`;
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        let label: string = `${info.bundleName}: ${info.name}`;
        try {
          label = await bundleManager.getAbilityLabel(info.bundleName, info.moduleName, info.name);
        } catch (error) {
          // A readable component identity still allows an informed choice.
        }
        targets.push({ key: key, bundleName: info.bundleName, moduleName: info.moduleName,
          abilityName: info.name, label: label });
      }
      if (this.active && revision === this.revision) {
        this.targets = targets;
      }
    } catch (error) {
      if (this.active && revision === this.revision) {
        this.targets = [];
        this.error = `无法查询分享目标：${(error as Error).message}`;
      }
    } finally {
      this.loading = false;
    }
  }

  async choose(key: string): Promise<void> {
    if (!this.active || this.busy || this.loading || this.completed) {
      return;
    }
    this.busy = true;
    this.error = '';
    try {
      if (!this.launched) {
        const target = this.targets.find((item: ShareTarget) => item.key === key);
        if (target === undefined) {
          throw new Error('请选择当前列表中的分享目标');
        }
        // An explicit launch would bypass intent-filter matching. Requery the
        // original action/MIME/URI after user choice before selecting its exact
        // component; stale, disabled and no-longer-matching targets must fail.
        const current = await bundleManager.queryAbilityInfo(this.queryWant(),
          bundleManager.AbilityFlag.GET_ABILITY_INFO_WITH_APPLICATION);
        if (!this.active) {
          return;
        }
        const valid = current.find((info: bundleManager.AbilityInfo) => info.exported && info.enabled &&
          info.applicationInfo.enabled && info.bundleName === target.bundleName &&
          info.moduleName === target.moduleName && info.name === target.abilityName);
        if (valid === undefined) {
          throw new Error('分享目标已移除、停用或不再接受此内容，请刷新列表');
        }
        const text = this.payload.parameters?.['ability.params.stream'];
        if (!this.payload.uri && text === '') {
          throw new Error('没有可分享的内容');
        }
        const want: Want = { action: this.payload.action, type: this.payload.type, uri: this.payload.uri,
          flags: this.payload.flags, parameters: this.payload.parameters, bundleName: target.bundleName,
          moduleName: target.moduleName, abilityName: target.abilityName };
        // The session's native source token supplies caller identity. Do not
        // open/copy files or grant access using Settings' privileged token.
        await this.session.startAbilityAsCaller(want);
        this.launched = true;
        this.selected = target;
      }
      if (this.active) {
        await this.finish(false);
      }
    } catch (error) {
      if (this.active) {
        this.error = `分享失败：${(error as Error).message}`;
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
    try {
      // If launch succeeded but result delivery failed, retry that truthful
      // outcome; neither relaunch nor report a cancellation after launch.
      await this.finish(!this.launched);
    } catch (error) {
      this.error = `无法返回分享结果：${(error as Error).message}`;
    } finally {
      this.busy = false;
    }
  }

  private async finish(cancelled: boolean): Promise<void> {
    const target = this.selected;
    ++this.revision;
    await this.session.terminateSelfWithResult({ resultCode: cancelled ? 1 : 0,
      want: { parameters: { outcome: cancelled ? 'cancelled' : 'launched',
        selectedBundleName: target?.bundleName ?? '', selectedModuleName: target?.moduleName ?? '',
        selectedAbilityName: target?.abilityName ?? '' } } });
    this.completed = true;
  }

  dispose(): void {
    this.active = false;
    ++this.revision;
    this.targets = [];
  }
}
