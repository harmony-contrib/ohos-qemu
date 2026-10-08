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
import mediaquery from '@ohos.mediaquery';
import { ScreenManager } from './ScreenManager';
import display from '@ohos.display';
import { HiLog } from './HiLog';
import { DeviceUtil } from './DeviceUtil';
import lazy { TAG } from '@ohos/hypium/src/main/Constant';
import { DEVICE_FOLD_STATUS, SCREEN_FOLD_ORIENTATION_PORTRAIT } from '../const';
import { BroadCastManager } from '@ohos/common/src/main/ets/default/model/common/BroadCastManager';

export class BreakPointSystem {
  public landscapeListener = mediaquery.matchMediaSync('(orientation: landscape)')
  public portraitListener = mediaquery.matchMediaSync('(orientation: portrait)')
  /* instrument ignore file */
  // 未正常注销监听
  private landscapeListenerCallBack: Callback<mediaquery.MediaQueryResult> =
    (mediaQueryResult: mediaquery.MediaQueryResult) => {
      if (mediaQueryResult.matches) {
        ScreenManager.getInstance().onDeviceRotationChanger(false);
        if (!AppStorage.get(DEVICE_FOLD_STATUS) as boolean && !ScreenManager.getInstance().getSmallWindowMode()) {
          BroadCastManager.getInstance().getBroadCast().emit('onFoldDeviceOrientationChange');
          HiLog.i(TAG, 'landscapeListenerCallBack onFoldDeviceOrientationChange');
          return;
        }
        // 横屏窗口/分屏模式显示上下布局
        if (ScreenManager.getInstance().isWindowMode() || (ScreenManager.getInstance().isSplitMode() &&
          (ScreenManager.getInstance().isPortraitLayout()))) {
          ScreenManager.getInstance().onRotationChanged(true);
          return;
        }
        ScreenManager.getInstance().onRotationChanged(false);
      }
    }
  private portraitListenerCallBack: Callback<mediaquery.MediaQueryResult> =
    (mediaQueryResult: mediaquery.MediaQueryResult) => {
      if (mediaQueryResult.matches) {
        ScreenManager.getInstance().onDeviceRotationChanger(true);
        if (!AppStorage.get(DEVICE_FOLD_STATUS) as boolean && !ScreenManager.getInstance().getSmallWindowMode()) {
          BroadCastManager.getInstance().getBroadCast().emit('onFoldDeviceOrientationChange');
          HiLog.i(TAG, 'portraitListenerCallBack onFoldDeviceOrientationChange');
          return;
        }
        if (ScreenManager.getInstance().isSplitMode() && ScreenManager.getInstance().isLandscapeLayout()) {
          ScreenManager.getInstance().onRotationChanged(false);
          return;
        }
        ScreenManager.getInstance().onRotationChanged(true);
      }
    }
  private foldStatusChangeCallback: Callback<display.FoldStatus> = (foldStatus: display.FoldStatus) => {
    if (foldStatus === display.FoldStatus.FOLD_STATUS_FOLDED ||
      foldStatus === display.FoldStatus.FOLD_STATUS_FOLDED_WITH_SECOND_EXPANDED ||
      foldStatus === display.FoldStatus.FOLD_STATUS_FOLDED_WITH_SECOND_HALF_FOLDED) {
      ScreenManager.getInstance().onFoldStatusChanged(true)
    } else if (foldStatus !== display.FoldStatus.FOLD_STATUS_UNKNOWN) {
      ScreenManager.getInstance().onFoldStatusChanged(false)
    }
  }

  private foldPortraitListenerCallBack: Callback<number> = (data: number) => {
    ScreenManager.getInstance().onFoldRotationChanged(DeviceUtil.isLandscape() as boolean);
  }

  private foldDisplayModeChangeCallBack: Callback<display.FoldDisplayMode> = (data: display.FoldDisplayMode) => {
    BroadCastManager.getInstance().getBroadCast().emit('onFoldDisplayModeChange');
  }

  public registerOrientationChange(): void {
    this.landscapeListener.on('change', this.landscapeListenerCallBack);
    this.portraitListener.on('change', this.portraitListenerCallBack);

    if (DeviceUtil.isFoldable()) {
      try {
        display.on('foldStatusChange', this.foldStatusChangeCallback);
        // foldDisplayModeChange在xxxxxx展开布局结束之后触发
        // 在这个回调中可以通过display.getDefaultDisplaySync获取到正确的窗口宽高
        display.on('foldDisplayModeChange', this.foldDisplayModeChangeCallBack);
      } catch (err) {
        HiLog.e(TAG, 'display.on foldStatusChange error');
      }
    }
  }

  public unregisterOrientationChange(): void {
    this.landscapeListener.off('change', this.landscapeListenerCallBack);
    this.portraitListener.off('change', this.portraitListenerCallBack);

    if (DeviceUtil.isFoldable()) {
      try {
        display.off('foldStatusChange', this.foldStatusChangeCallback);
        display.off('foldDisplayModeChange', this.foldDisplayModeChangeCallBack);
      } catch (err) {
        HiLog.e(TAG, 'display.off foldStatusChange error');
      }
    }
  }
}