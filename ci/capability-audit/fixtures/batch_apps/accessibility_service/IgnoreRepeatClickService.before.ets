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
 
import Want from '@ohos.app.ability.Want';
import config from '@ohos.accessibility.config';
import { ServiceExtensionAbility } from '@kit.AbilityKit';
import { LogUtil } from '@ohos/settings.common/src/main/ets/utils/LogUtil';
import { SettingsDataUtils } from '@ohos/settings.common/src/main/ets/utils/SettingsDataUtils';
import { HiSysEventUtil } from '@ohos/settings.common/src/main/ets/systemEvent/HiSysEventUtil';
import { HiSysAccessibilityEventGroup } from '@ohos/settings.common/src/main/ets/systemEvent/BehaviorEventConsts';
import { CLICK_SWITCH_OFF } from '../constant/Constants';
import { IgnoreRepeatedStateModel } from '../utils/AccessibilityIgnoreRepeatedModel';

/* instrument ignore file */
const TAG: string = 'IgnoreRepeatClickService';
const DISABLE_IGNORE_REPEAT_CLICK_SWITCH: string = 'disableIgnoreRepeatClick';
const DISABLE_IGNORE_REPEAT_CLICK_NOTIFICATION: string = 'disableNotificaiton';
const DISABLE_IGNORE_REPEAT_CLICK_NOTIFICATION_KEY: string = 'ignore_repeat_click_notification';
const REOPEN_TRANSITION_ANIMATIONS_SWITCH: string = 'reOpenTransitionAnimations';
const DISABLE_TRANSITION_ANIMATIONS_NOTIFICATION: string = 'disableTransitionAnimationsNotification';
const DISABLE_TRANSITION_ANIMATIONS_NOTIFICATION_KEY: string = 'transition_animations_notification';
 
export default class IgnoreRepeatClickService extends ServiceExtensionAbility {
  async onCreate(want: Want) {
    LogUtil.showInfo(TAG, 'onCreate');
  }
 
  onRequest(want: Want, startId: number) {
    LogUtil.showInfo(TAG, `onRequest abilityName:${want?.abilityName} bundleName:${want?.bundleName} action:${want?.action?.toString()}`);
    if (want?.action?.toString() === DISABLE_IGNORE_REPEAT_CLICK_SWITCH) {
      this.disableIgnoreRepeatClickSwitch();
      LogUtil.warn(`${TAG} disableIgnoreRepeatClickSwitch`);
    } else if (want?.action?.toString() === DISABLE_IGNORE_REPEAT_CLICK_NOTIFICATION) {
      this.disableIgnoreRepeatClickNotification();
      LogUtil.warn(`${TAG} disableIgnoreRepeatClickNotification`);
    } else if (want?.action?.toString() === REOPEN_TRANSITION_ANIMATIONS_SWITCH) {
      this.reopenTransitionAnimationsSwitch();
      LogUtil.warn(`${TAG} reOpenTransitionAnimations`);
    } else if (want?.action?.toString() === DISABLE_TRANSITION_ANIMATIONS_NOTIFICATION) {
      this.disableTransitionAnimationsNotification();
      LogUtil.warn(`${TAG} disableTransitionAnimationsNotification`);
    } else {
      LogUtil.warn(`${TAG} no suitable action`);
    }
  }
 
  onDisconnect(want: Want) {
    LogUtil.showInfo(TAG, 'onDisconnect');
  }
 
  onDestroy() {
    LogUtil.showInfo(TAG, 'onDestroy');
  }
 
  private disableIgnoreRepeatClickSwitch() {
    try {
      IgnoreRepeatedStateModel.getInstance().ignoreRepeatClick = false;
      config.ignoreRepeatClick.set(false);
      HiSysEventUtil.reportDefaultBehaviorEventByUE(
        HiSysAccessibilityEventGroup.IGNORE_REPEAT_TOUCHES_SWITCH, 'off');
      LogUtil.info(`${TAG} ignoreRepeatClick set off success`);
      return true;
    } catch (e) {
      LogUtil.error(`${TAG} ignoreRepeatClick set off failed, code: ${e?.code} message: ${e?.message}`);
      return false;
    }
  }
 
  private disableIgnoreRepeatClickNotification() {
    SettingsDataUtils.setSecureValue(DISABLE_IGNORE_REPEAT_CLICK_NOTIFICATION_KEY, CLICK_SWITCH_OFF);
  }

  private reopenTransitionAnimationsSwitch() {
    try {
      config.animationOff.set(false);
      HiSysEventUtil.reportDefaultBehaviorEventByUE(
        HiSysAccessibilityEventGroup.TRANSITION_ANIMATIONS_STATE, 'on');
      LogUtil.info(`${TAG} animationOff set false success`);
      return true;
    } catch (e) {
      LogUtil.error(`${TAG} animationOff set false failed, code: ${e?.code} message: ${e?.message}`);
      return false;
    }
  }
 
  private disableTransitionAnimationsNotification() {
    SettingsDataUtils.setSecureValue(DISABLE_TRANSITION_ANIMATIONS_NOTIFICATION_KEY, CLICK_SWITCH_OFF);
  }
}
