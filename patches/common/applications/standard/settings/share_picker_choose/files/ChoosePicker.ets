/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import { ChoosePickerController, ChooseTarget } from '../Setting/SharePicker/ChoosePickerController';

@Entry({ useSharedStorage: true })
@Component
struct ChoosePicker {
  @State targets: ChooseTarget[] = [];
  @State error: string = '';
  @State loading: boolean = false;
  @State busy: boolean = false;
  @State accepted: boolean = false;
  @State cancelled: boolean = false;
  private active: boolean = false;
  private controller: ChoosePickerController | undefined = undefined;

  async aboutToAppear(): Promise<void> {
    this.active = true;
    this.controller = LocalStorage.getShared().get<ChoosePickerController>('chooseController');
    await this.refresh();
  }

  aboutToDisappear(): void {
    this.active = false;
  }

  private sync(): void {
    if (this.active) {
      this.targets = this.controller?.targets ?? [];
      this.error = this.controller?.error ?? '应用选择会话不可用';
      this.accepted = this.controller?.accepted ?? false;
      this.cancelled = this.controller?.cancelled ?? false;
    }
  }

  private async refresh(): Promise<void> {
    this.loading = true;
    await this.controller?.load();
    this.sync();
    if (this.active) {
      this.loading = false;
    }
  }

  private async choose(key: string): Promise<void> {
    this.busy = true;
    await this.controller?.choose(key);
    this.sync();
    if (this.active) {
      this.busy = false;
    }
  }

  private async cancel(): Promise<void> {
    this.busy = true;
    await this.controller?.cancel();
    this.sync();
    if (this.active) {
      this.busy = false;
    }
  }

  onBackPress(): boolean {
    this.cancel();
    return true;
  }

  build() {
    Column({ space: 16 }) {
      Text('选择应用').fontSize(24).id('system-choose-title');
      Text('请选择用于打开此内容的应用。结果由所选应用返回。');
      if (this.error.length > 0) {
        Text(this.error).fontColor(Color.Red).id('system-choose-error');
      }
      if (this.targets.length === 0 && !this.loading) {
        Text('没有匹配的可用应用').id('system-choose-empty');
      }
      List() {
        ForEach(this.targets, (target: ChooseTarget) => {
          ListItem() {
            Button(target.label).id(`system-choose-target-${target.key}`)
              .enabled(!this.loading && !this.busy && !this.accepted && !this.cancelled)
              .onClick(() => this.choose(target.key));
          }
        }, (target: ChooseTarget) => target.key);
      }.layoutWeight(1).width('100%');
      Button('刷新').id('system-choose-refresh')
        .enabled(!this.loading && !this.busy && !this.accepted && !this.cancelled)
        .onClick(() => this.refresh());
      Button(this.accepted || this.cancelled ? '关闭窗口' : '取消').id('system-choose-cancel')
        .enabled(!this.busy).onClick(() => this.cancel());
    }.padding(24).width('100%').height('100%').backgroundColor(Color.White);
  }
}
