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


/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
import image from '@ohos.multimedia.image';
import wallpaper from '@ohos.wallpaper';
import { BusinessError } from '@ohos.base';
import { SystemParamUtil } from '@ohos/settings.common/src/main/ets/utils/SystemParamUtil';
import { LogUtil } from '@ohos/settings.common/src/main/ets/utils/LogUtil';
import { DynamicLoader } from '@ohos/settings.common/src/main/ets/utils/DynamicLoader';
import { PageLifecycleOwner } from '@ohos/settings.common/src/main/ets/core/lifecycle/Lifecycle';
import { PageRoot } from '@ohos/settings.common/src/main/ets/core/viewmodel/PageViewModel';
import { Params, PushParam } from '@ohos/settings.common/src/main/ets/core/controller/Controller';
import { WallpaperPage } from './model/WallpaperPage';
import { WallpaperSelectionController, WallpaperSelectionPhase, WallpaperSelectionState } from './utils/WallpaperSelectionController';

@Builder
export function WallpaperPickerLoader(params: Params): void {
  WallpaperPicker({ params: params as Object as PushParam });
}

@Component
export struct WallpaperPicker {
  @State params: PushParam | null = null;
  @Consume('pathInfos') pathInfos: NavPathStack;
  @State isEnable: boolean = false;
  @State policyError: string = '';
  @State policyLoading: boolean = true;
  @State view: WallpaperSelectionState = { phase: WallpaperSelectionPhase.IDLE, busy: false,
    errorCode: 0, errorMessage: '' };
  pageRoot: PageRoot = new PageRoot(new PageLifecycleOwner());
  private controller?: WallpaperSelectionController;
  private appearance: number = 0;

  aboutToAppear(): void {
    const appearance = ++this.appearance;
    this.isEnable = false;
    this.policyLoading = true;
    this.policyError = '';
    this.controller = new WallpaperSelectionController((state: WallpaperSelectionState) => { this.view = state; });
    this.pageRoot.aboutToAppear(new WallpaperPage(this.pathInfos));
    SystemParamUtil.isModifyWallpaperDisable().then((disabled: boolean) => {
      if (appearance === this.appearance) { this.isEnable = !disabled; this.policyLoading = false; }
    }).catch((error: BusinessError) => {
      if (appearance === this.appearance) { this.policyError = error.message; this.policyLoading = false; }
      LogUtil.error(`WallpaperPicker policy query failed ${error.code}: ${error.message}`);
    });
  }

  aboutToDisappear(): void {
    ++this.appearance;
    this.controller?.dispose();
    this.pageRoot.aboutToDisappear();
  }

  private statusText(): Resource {
    switch (this.view.phase) {
      case WallpaperSelectionPhase.PREVIEW: return $r('app.string.wallpaper_preview_prompt');
      case WallpaperSelectionPhase.SAVED: return $r('app.string.wallpaper_saved');
      case WallpaperSelectionPhase.RESTORED: return $r('app.string.wallpaper_default_restored');
      case WallpaperSelectionPhase.CANCELLED: return $r('app.string.wallpaper_selection_cancelled');
      case WallpaperSelectionPhase.ERROR: return $r('app.string.wallpaper_operation_failed');
      case WallpaperSelectionPhase.SELECTING:
      case WallpaperSelectionPhase.APPLYING:
      case WallpaperSelectionPhase.RESTORING: return $r('app.string.wallpaper_busy');
      default: return $r('app.string.wallpaper_choose_prompt');
    }
  }

  private async cancelAndBack(): Promise<void> {
    if (this.controller !== undefined && await this.controller.cancel()) { this.pathInfos.pop(); }
  }

  build() {
    NavDestination() {
      Scroll() {
        Column({ space: 16 }) {
          if (this.policyLoading) {
            Text($r('app.string.wallpaper_busy'))
          } else if (!this.isEnable) {
            Text(this.policyError || $r('app.string.disable_modify_wallpaper_tips'))
              .id('wallpaper_policy_status')
          } else {
            Text(this.statusText()).id('wallpaper_status')
            if (this.view.errorMessage.length > 0) {
              Text(this.view.errorMessage).id('wallpaper_error_detail')
              if (this.view.errorCode !== 0) { Text(this.view.errorCode.toString()) }
            }
            Button($r('app.string.select_from_gallery')).id('wallpaper_choose_image')
              .enabled(!this.view.busy).onClick(() => { this.controller?.choose(); })
            if (this.view.preview !== undefined) {
              Image(this.view.preview as image.PixelMap).objectFit(ImageFit.Contain)
                .width('100%').height(280).id('wallpaper_preview')
              Button($r('app.string.wallpaper_apply_home')).id('wallpaper_apply_home')
                .enabled(!this.view.busy).onClick(() => {
                  this.controller?.apply(wallpaper.WallpaperType.WALLPAPER_SYSTEM);
                })
              Button($r('app.string.wallpaper_apply_lock')).id('wallpaper_apply_lock')
                .enabled(!this.view.busy).onClick(() => {
                  this.controller?.apply(wallpaper.WallpaperType.WALLPAPER_LOCKSCREEN);
                })
            }
            Button($r('app.string.wallpaper_restore_home')).id('wallpaper_restore_home')
              .enabled(!this.view.busy).onClick(() => {
                this.controller?.restore(wallpaper.WallpaperType.WALLPAPER_SYSTEM);
              })
            Button($r('app.string.wallpaper_restore_lock')).id('wallpaper_restore_lock')
              .enabled(!this.view.busy).onClick(() => {
                this.controller?.restore(wallpaper.WallpaperType.WALLPAPER_LOCKSCREEN);
              })
          }
          Button($r('app.string.dialog_cancel')).id('wallpaper_cancel')
            .enabled(this.view.phase !== WallpaperSelectionPhase.APPLYING &&
              this.view.phase !== WallpaperSelectionPhase.RESTORING)
            .onClick(() => { this.cancelAndBack(); })
        }.padding(24).width('100%')
      }.width('100%').height('100%')
    }
    .title($r('app.string.wallpaper_title'))
    .hideTitleBar(false)
    .backgroundColor($r('sys.color.ohos_id_color_titlebar_sub_bg'))
    .onShown(() => {
      this.pageRoot.onPageShow();
      DynamicLoader.getInstance().pageTransitionSuccess('WallpaperPicker');
    })
    .onHidden(() => { this.controller?.cancel(); this.pageRoot.onPageHide(); })
    .onBackPressed(() => { return this.controller?.isCommitting() ?? false; })
  }
}
