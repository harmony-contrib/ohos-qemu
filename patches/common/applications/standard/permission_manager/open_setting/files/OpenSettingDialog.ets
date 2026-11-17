/* Copyright (c) 2026 OpenHarmony QEMU contributors. Licensed under Apache-2.0. */
import UIExtensionContentSession from '@ohos.app.ability.UIExtensionContentSession';
import { OpenSettingRequest, USER_OPENED, USER_REJECTED, INTERNAL_ERROR } from './OpenSettingRequest';

@Entry({ useSharedStorage: true })
@Component
struct OpenSettingDialog {
  @LocalStorageLink('manualRequest') request: OpenSettingRequest | null = null;
  @LocalStorageLink('manualSession') session: UIExtensionContentSession | null = null;
  @State ready: boolean = false;
  @State pending: boolean = false;
  @State bundleName: string = '';
  @State permissionName: string = '';
  private completed: boolean = false;

  async aboutToAppear(): Promise<void> {
    if (!this.request || !this.session) {
      this.finish(INTERNAL_ERROR);
      return;
    }
    const status = await this.request.prepare();
    if (this.completed || !this.request.active) {
      return;
    }
    if (status !== USER_OPENED) {
      this.finish(status);
      return;
    }
    this.bundleName = this.request.bundleName;
    this.permissionName = this.request.permission;
    this.ready = true;
  }

  private finish(selected: number): void {
    if (this.completed) {
      return;
    }
    this.completed = true;
    if (this.request) {
      this.request.active = false;
    }
    this.session?.terminateSelfWithResult({ resultCode: 0,
      want: { parameters: { 'ohos.open.setting.result_code': selected } } });
  }

  onBackPress(): boolean {
    if (!this.pending) {
      this.finish(USER_REJECTED);
    }
    return true;
  }

  build() {
    Column() {
      Column({ space: 16 }) {
        Text('Manual permission settings').fontSize(22)
        Text(this.bundleName).fontSize(18)
        Text(this.permissionName).fontSize(16)
        Text('Allow this application to use the requested permission?').fontSize(16)
        Row({ space: 16 }) {
          Button('Cancel').id('qemu_manual_permission_deny')
            .enabled(!this.pending)
            .onClick(() => this.finish(USER_REJECTED))
          Button('Allow').id('qemu_manual_permission_allow')
            .enabled(this.ready && !this.pending)
            .onClick(async () => {
              this.pending = true;
              const result = this.request ? await this.request.confirm() : INTERNAL_ERROR;
              this.finish(result);
            })
        }
      }.padding(24).width('90%').constraintSize({ maxWidth: 560 })
        .backgroundColor(Color.White).borderRadius(24)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center)
      .backgroundColor('#66000000')
  }
}
