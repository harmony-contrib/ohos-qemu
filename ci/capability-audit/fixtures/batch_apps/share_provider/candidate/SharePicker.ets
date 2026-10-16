/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import { SharePickerController, ShareTarget } from '../Setting/SharePicker/SharePickerController';

@Entry({ useSharedStorage: true })
@Component
struct SharePicker {
  @State targets: ShareTarget[] = [];
  @State error: string = '';
  @State busy: boolean = false;
  @State loading: boolean = false;
  @State launched: boolean = false;
  private controller: SharePickerController | undefined = undefined;
  private active: boolean = false;

  async aboutToAppear(): Promise<void> {
    this.active = true;
    this.controller = LocalStorage.getShared().get<SharePickerController>('shareController');
    await this.refresh();
  }

  aboutToDisappear(): void {
    this.active = false;
  }

  private async refresh(): Promise<void> {
    this.loading = true;
    await this.controller?.load();
    if (this.active) {
      this.targets = this.controller?.targets ?? [];
      this.error = this.controller?.error ?? '分享会话不可用';
      this.loading = false;
    }
  }

  private async choose(key: string): Promise<void> {
    this.busy = true;
    await this.controller?.choose(key);
    if (this.active) {
      this.error = this.controller?.error ?? '分享会话不可用';
      this.launched = this.controller?.launched ?? false;
      this.busy = false;
    }
  }

  private async cancel(): Promise<void> {
    this.busy = true;
    await this.controller?.cancel();
    if (this.active) {
      this.error = this.controller?.error ?? '分享会话不可用';
      this.busy = false;
    }
  }

  onBackPress(): boolean {
    if (!this.busy) {
      this.cancel();
    }
    return true;
  }

  build() {
    Column({ space: 16 }) {
      Text('分享').fontSize(24).id('system-share-title');
      Text('请选择接收应用；打开接收应用后，是否发送由接收应用继续确认。');
      if (this.error.length > 0) {
        Text(this.error).fontColor(Color.Red).id('system-share-error');
      }
      if (this.targets.length === 0 && !this.loading) {
        Text('没有可用的分享目标').id('system-share-empty');
      }
      List() {
        ForEach(this.targets, (target: ShareTarget) => {
          ListItem() {
            Button(target.label).id(`system-share-target-${target.key}`)
              .enabled(!this.busy && !this.loading && !this.launched).onClick(() => this.choose(target.key));
          }
        }, (target: ShareTarget) => target.key);
      }.layoutWeight(1).width('100%');
      Button('刷新').id('system-share-refresh').enabled(!this.busy && !this.loading && !this.launched)
        .onClick(() => this.refresh());
      Button(this.launched ? '重试返回结果' : '取消').id('system-share-cancel').enabled(!this.busy)
        .onClick(() => this.cancel());
    }.padding(24).width('100%').height('100%').backgroundColor(Color.White);
  }
}
