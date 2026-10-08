/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2024-2025. All rights reserved.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import lazy { DialogCallback } from '../../model/common/DialogUtil';
import lazy { AlertDialog } from '@ohos.arkui.advanced.Dialog';
import lazy { Log } from '../../utils/Log';
import lazy { TAG } from '@ohos/hypium/src/main/Constant';

@CustomDialog
  /* instrument ignore file */
export struct NetworkConnectionSwitchDialog {
  @Consume dialogCallback?: DialogCallback;
  public controller?: CustomDialogController;
  @Consume headTitle: Resource;
  @Consume subTitle: Resource;
  @Consume confirmText: Resource;
  private head: Resource = $r('app.string.common_place_holder', '');
  private content: Resource = $r('app.string.common_place_holder', '');
  private secondButtonText: Resource = $r('app.string.common_place_holder', '');

  aboutToAppear(): void {
    this.head = this.headTitle;
    this.content = this.subTitle;
    this.secondButtonText = this.confirmText;
  }

  build() {
    AlertDialog({
      primaryTitle: this.head,
      content: this.content,
      primaryButton: {
        value: $r('app.string.no'),
        action: () => {
          Log.info(TAG, 'primaryButton onclick');
          this.dialogCallback && (this.dialogCallback as DialogCallback)?.cancelCallback?.();
          this.controller?.close();
        }
      },
      secondaryButton: {
        value: this.secondButtonText,
        action: () => {
          Log.info(TAG, 'secondaryButton onclick');
          this.dialogCallback && this.dialogCallback?.confirmCallback?.();
          this.controller?.close();
        }
      }
    })
  }
}
