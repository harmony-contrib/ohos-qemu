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

import { window } from '@kit.ArkUI';
import { BusinessError } from '@kit.BasicServicesKit';
import { LengthMetrics } from '@ohos.arkui.node';
import display from '@ohos.display';
import Common from '@ohos.app.ability.common';
import MediaQuery from '@ohos.mediaquery';
import emitter from '@ohos.events.emitter';
import { NavEntryKey } from '@ohos/settings.common/src/main/ets/utils/Consts';
import { PageStartReason } from '@ohos/settings.common/src/main/ets/data/types';
import { DynamicLoader } from '@ohos/settings.common/src/main/ets/utils/DynamicLoader';
import { LogUtil } from '@ohos/settings.common/src/main/ets/utils/LogUtil';
import { PageLifecycleOwner } from '@ohos/settings.common/src/main/ets/core/lifecycle/Lifecycle';
import { PageRoot } from '@ohos/settings.common/src/main/ets/core/viewmodel/PageViewModel';
import { Params, PushParam } from '@ohos/settings.common/src/main/ets/core/controller/Controller';
import { pageNavTitle } from '@ohos/settings.common/src/main/ets/framework/view/SettingPage';
import { PageParams } from '@ohos/settings.common/src/main/ets/framework/common/PageLoader';
import { HiSysEventUtil } from '@ohos/settings.common/src/main/ets/systemEvent/HiSysEventUtil';
import { DeviceUtil } from '@ohos/settings.common/src/main/ets/utils/BaseUtils';
import { DisplayUtils } from '@ohos/settings.common/src/main/ets/utils/DisplayUtils';
import { ResourceUtil } from '@ohos/settings.common/src/main/ets/utils/ResourceUtil';
import { MenuPcPageComponent } from '@ohos/settings.uikit/src/main/ets/component/MenuPageComponent';
import { REFRESH_DESKTOP_AND_PERSONAL_PAGE } from '@ohos/settings.common/src/main/ets/event/types';
import { ThemePagePc } from './model/ThemePagePc';
import { CommonUtils } from '@ohos/settings.common/src/main/ets/utils/CommonUtils';
import { SettingsDataUtils } from '@ohos/settings.common/src/main/ets/utils/SettingsDataUtils';
import { HiSysDisplayEventGroup } from '@ohos/settings.common/src/main/ets/systemEvent/BehaviorEventConsts';

/* instrument ignore file */
const TAG: string = 'ThemeSettings : ';
const IS_DEVICE_PAD: boolean = DeviceUtil.isDevicePad();
const IS_DEVICE_PC: boolean = DeviceUtil.isDevicePc();
const THEME_SETTINGS_WINDOW_MOD: string = 'themeSettings.windowMode';

@Builder
export function ThemeSettingsLoader($$: Params): void {
  if (LogUtil.printBuilderLog(`${TAG} theme settings loader`)) {
    ThemeSettings({ params: $$ as Object as PushParam });
  }
}

@Component
export struct ThemeSettings {
  pageRoot: PageRoot = new PageRoot(new PageLifecycleOwner());
  @Consume('pathInfos') pathInfos: NavPathStack;
  @StorageLink('isPortraitOrientation') isPortraitOrientation: boolean = false;
  @StorageLink('settingsThemePage') themeGalleryProxy: UIExtensionProxy | null = null;
  private orientationListener: MediaQuery.MediaQueryListener | undefined = undefined;
  pagePaddingStart: LengthMetrics | undefined = LengthMetrics.vp(24);
  title: string =
    DeviceUtil.isSmallFoldProduct() ? ResourceUtil.getStringSync($r('app.string.covertheme_settings_title'))
      : ResourceUtil.getStringSync($r('app.string.theme_settings_title'));
  private context = getContext(this) as Common.UIAbilityContext;
  isFromExternal: boolean = false;
  @State params: PushParam | null = null;
  @State isFromSearch: boolean = false;
  @State routerName: string = 'settingsThemePage';
  @StorageProp('navDesDynamicPadding') navDesDynamicPadding: number = AppStorage.get<number>('navDesDynamicPadding') as number;

  build() {
    NavDestination() {
      if (IS_DEVICE_PC) {
        MenuPcPageComponent({ menuPage: this.pageRoot.menuPage })
      }
    }
    .hideTitleBar(!IS_DEVICE_PC)
    .title(DeviceUtil.isDevicePc() ? this.title : pageNavTitle(this.title, this.pagePaddingStart))
    .backgroundColor(DeviceUtil.isDevicePc() ? Color.Transparent : $r('sys.color.ohos_id_color_titlebar_sub_bg'))
    .onShown(() => {
      this.onPageShow();
    })
    .onHidden(() => {
      this.onPageHide();
    })
    .onBackPressed(() => {
      if (this.isFromExternal) {
        LogUtil.info(`${TAG} onBackPressed`);
        this.termiteAbility();
        return true;
      }
      return false;
    })
    .padding({
      left: CommonUtils.getSettingsPagePadding(this.navDesDynamicPadding),
      right: CommonUtils.getSettingsPagePadding(this.navDesDynamicPadding)
    });
  }

  aboutToAppear(): void {
    LogUtil.info(`${TAG} aboutToAppear`);
    this.getSearchParams();
    this.setWindowStateValue();
    HiSysEventUtil.reportDefaultBehaviorEventByUE(HiSysDisplayEventGroup.THEME_ENTRY);
    // 添加平板页面横竖屏的监听器
    if (IS_DEVICE_PAD) {
      this.isPortraitOrientation = DisplayUtils.isScreenPortraitOrientation();
      this.addOrientationListener();
    }
    if (IS_DEVICE_PC) {
      this.pageRoot.aboutToAppear(new ThemePagePc(this.pathInfos, this.params as PushParam));
    }
  }

  private getSearchParams(): void {
    this.isFromSearch = this.params?.startReason === PageStartReason.FROM_SEARCH;
    if (!this.params) {
      LogUtil.info(`${TAG} no param, return`);
      return;
    }
    if (!this.isFromSearch) {
      try {
        let params = this.params as PageParams;
        if (params.param && params.param['startReason']) {
          this.isFromSearch = params.param['startReason'] as string === PageStartReason.FROM_SEARCH;
        }
      } catch (e) {
        LogUtil.info(`${TAG} get isFromSearch error ${e?.code}`);
      }
    }
    let routerName: string = this.params.config as string ?? '';
    if (routerName !== '') {
      this.routerName = routerName.split(',')[0];
      return;
    }
    try {
      let params = this.params as PageParams;
      if (params.param && params.param['config']) {
        routerName = params.param['config'] as string;
        this.routerName = routerName.split(',')[0];
        return;
      }
      if (this.params.subUri) {
        this.routerName = this.params.subUri;
        return;
      }
    } catch (e) {
      LogUtil.info(`${TAG} get routerName error ${e.code}`);
    }
  }

  private setWindowStateValue(): void {
    try {
      window.getLastWindow(getContext()).then((win) => {
        let windowStatus: window.WindowStatusType = window.WindowStatusType.UNDEFINED;
        const windowRect = win.getWindowProperties().windowRect;
        const displayRect = display.getDefaultDisplaySync();
        if (!windowRect || !displayRect) {
          LogUtil.error(`${TAG} windowRect or displayRect is undefined`);
          return;
        }
        LogUtil.info(`${TAG} windowWidth: ${windowRect.width}, displayWidth: ${displayRect.width}` +
          `windowHeight: ${windowRect.height}, displayHeight: ${displayRect.height}`);
        if (windowRect.width < displayRect.width || windowRect.height < displayRect.height) {
          windowStatus = window.WindowStatusType.FLOATING;
        }
        SettingsDataUtils.setSettingsData(THEME_SETTINGS_WINDOW_MOD, String(windowStatus));

        win.on('windowStatusChange', (windowStatusType: window.WindowStatusType) => {
          LogUtil.info(`${TAG} windowStatusChange, window type is ${windowStatusType}`);
          SettingsDataUtils.setSettingsData(THEME_SETTINGS_WINDOW_MOD, String(windowStatusType));
        })
      });
    } catch (err) {
      if (!err) {
        LogUtil.error(`${TAG} setWindowStateValue failed, but err is undefined`);
        return;
      }
      LogUtil.error(`${TAG} aboutToAppear failed, error reason: ${(err as BusinessError).message}`);
    }
  }

  aboutToDisappear(): void {
    LogUtil.info(`${TAG} aboutToDisappear`);
    this.pageRoot.aboutToDisappear();
    // 销毁平板页面横竖屏监听器
    if (IS_DEVICE_PAD) {
      this.orientationListener?.off('change');
    }
  }

  onPageShow(): void {
    LogUtil.info(`${TAG} onPageShow`);
    this.pageRoot.onPageShow();
    DynamicLoader.getInstance().pageTransitionSuccess(TAG);
    emitter.emit({
      eventId: REFRESH_DESKTOP_AND_PERSONAL_PAGE,
      priority: emitter.EventPriority.IMMEDIATE,
    }, {});
  }

  onPageHide(): void {
    LogUtil.info(`${TAG} onPageHide`);
    if (!IS_DEVICE_PC) {
      if (this.pathInfos.getParamByName(NavEntryKey.THEME_ENTRY)?.length !== 0) {
        LogUtil.info(`${TAG} just background`);
      } else {
        LogUtil.info(`${TAG} need to set status bar`);
        try {
          window.getLastWindow(getContext(this), (err, win) => {
            win?.setWindowSystemBarEnable(['status', 'navigation']);
            win?.setWindowLayoutFullScreen(false)
          });
        } catch (e) {
          LogUtil.error(`${TAG} set status bar fail ${e?.code} msg ${e?.message}`);
        }
      }
    }
    this.pageRoot.onPageHide();
  }

  private termiteAbility(): void {
    this.context.terminateSelf();
  }

  async addOrientationListener(): Promise<void> {
    this.orientationListener = MediaQuery.matchMediaSync('(orientation: landscape)');
    this.orientationListener.on('change', () => {
      if (!DisplayUtils.isScreenPortraitOrientation()) {
        AppStorage.setOrCreate('isPortraitOrientation', false);
      } else {
        AppStorage.setOrCreate('isPortraitOrientation', true);
      }
    })
  }
}