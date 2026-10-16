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


/* instrument ignore file */
import promptAction from '@ohos.promptAction';
import { SystemParamUtil } from '@ohos/settings.common/src/main/ets/utils/SystemParamUtil';
import { ObservedData, UiExtensionViewModel } from '@ohos/settings.common/src/main/ets/viewmodel/UiExtensionViewModel';
import { ExitAbnormallyComponent } from '@ohos/settings.common/src/main/ets/viewmodel/ExitAbnormallyComponent';
import { ExternalMenuPreloadManager } from '@ohos/settings.common/src/main/ets/externalmenu/ExternalMenuPreloadManager';
import { DynamicLoader } from '@ohos/settings.common/src/main/ets/utils/DynamicLoader';
import { LogUtil } from '@ohos/settings.common/src/main/ets/utils/LogUtil';
import { PageLifecycleOwner } from '@ohos/settings.common/src/main/ets/core/lifecycle/Lifecycle';
import { PageRoot } from '@ohos/settings.common/src/main/ets/core/viewmodel/PageViewModel';
import { Params, PushParam } from '@ohos/settings.common/src/main/ets/core/controller/Controller';
import { WallpaperPage } from './model/WallpaperPage';
import { PageParams } from '@ohos/settings.common/src/main/ets/framework/common/PageLoader';
import { PageStartReason } from '@ohos/settings.common/src/main/ets/data/types';

const TAG: string = 'WallpaperPicker : ';
const BUNDLE_NAME: string = 'com.ohos.sceneboard';
const ABILITY_NAME: string = 'SettingThemeComponentExtAbility';
const DEFAULT_NAV: string = 'wallpaperPicker';
const PC_NAV: string = 'pcWallpaperPicker';

@Builder
export function WallpaperPickerLoader(_$$: Params): void {
  WallpaperPicker({ params: _$$ as Object as PushParam });
}

@Component
export struct WallpaperPicker {
  @State params: PushParam | null = null;
  @State isFromSearch: boolean = false;
  pageRoot: PageRoot = new PageRoot(new PageLifecycleOwner());
  navDestination: string = DEFAULT_NAV;
  @Consume('pathInfos') pathInfos: NavPathStack;
  @State observedData: ObservedData = new ObservedData();
  @State isEnable: boolean = false;
  private viewModel: UiExtensionViewModel = new UiExtensionViewModel(this.observedData);

  recoverController: CustomDialogController = new CustomDialogController({
    builder: ExitAbnormallyComponent(),
  });

  build() {
    NavDestination() {
      if (this.isEnable) {
        UIExtensionComponent({
          bundleName: BUNDLE_NAME,
          abilityName: ABILITY_NAME,
          parameters: {
            'ability.want.params.uiExtensionType': 'sys/commonUI',
            'nav': PC_NAV,
            'isFull': true,
            'reconnect': this.observedData.reconnect,
            'isFromSearch': this.isFromSearch,
          }
        })
          .width('100%')
          .height('100%')
          .onError((error) => {
            LogUtil.info(`${TAG} UIExtensionComponent onError code: ${error?.code} message: ${error?.message}`);
            this.viewModel.refreshing(error, this.recoverController, BUNDLE_NAME, ABILITY_NAME);
          })
          .onTerminated(() => {
          })
          .onReceive(this.onReceiveSCBData)
          .id('wallpaper_picker_extension')
          .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.BOTTOM, SafeAreaEdge.TOP])
      }
    }
    .width('100%')
    .height('100%')
    .hideTitleBar(true)
    .backgroundColor($r('sys.color.ohos_id_color_titlebar_sub_bg'))
    .onShown(() => {
      this.onPageShow();
    })
    .onHidden(() => {
      this.onPageHide();
    })
    .padding({
      left: this.observedData.left, right: this.observedData.right
    })
  }

  aboutToAppear(): void {
    SystemParamUtil.isModifyWallpaperDisable().then((isDisable: boolean) => {
      this.isEnable = !isDisable;
      LogUtil.info(`${TAG} isEnable ${this.isEnable}`);
      if (this.isEnable) {
        return;
      }
      LogUtil.showInfo(TAG, 'modify wallpaper is disabled,show toast');
      try {
        promptAction.openToast({
          message: $r('app.string.disable_modify_wallpaper_tips')
        });
      } catch (e) {
        LogUtil.showError(TAG, `showToast fail, code: ${e?.code}, message: ${e?.message}`);
      }
    });
    this.isFromSearch = this.params?.startReason === PageStartReason.FROM_SEARCH;
    if (this.params && !this.isFromSearch) {
      try {
        let params = this.params as PageParams;
        if (params.param && params.param['startReason']) {
          this.isFromSearch = params.param['startReason'] as string === PageStartReason.FROM_SEARCH;
        }
      } catch (e) {
        LogUtil.info(`${TAG} get isFromSearch error ${e?.code}`);
      }
    }
    LogUtil.info(`${TAG} aboutToAppear`);
    this.viewModel.listening(this.recoverController);
    this.pageRoot.aboutToAppear(new WallpaperPage(this.pathInfos));
  }

  aboutToDisappear(): void {
    LogUtil.info(`${TAG} aboutToDisappear`);
    try {
      ExternalMenuPreloadManager.getInstance().preloadUIExtensionAbility(ABILITY_NAME, getContext());
    } catch (err) {
      LogUtil.warn(`${TAG} preload themeComponentExtAbilty failed, code: ${err?.code}, message: ${err?.message}`);
    }
    this.pageRoot.aboutToDisappear();
    this.viewModel.destroyListening();
  }

  onPageShow(): void {
    LogUtil.info(`${TAG} onPageShow`);
    this.pageRoot.onPageShow();
    DynamicLoader.getInstance().pageTransitionSuccess(TAG);
  }

  onPageHide(): void {
    LogUtil.info(`${TAG} onPageHide`);
    this.pageRoot.onPageHide();
  }

  private onReceiveSCBData: (data: object) => void = (data: object) => {
    LogUtil.info(`SCB UIExtension onReceive`);
    if (data['back'] !== undefined) {
      this.pathInfos.pop();
    }
  };
}
