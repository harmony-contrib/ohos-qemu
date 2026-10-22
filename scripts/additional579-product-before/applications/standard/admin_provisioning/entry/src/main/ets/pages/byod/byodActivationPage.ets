/*
 * Copyright (c) 2025 Huawei Device Co., Ltd.
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
import { BaseByodAdminPage, BottomButton } from './baseByodAdminPage';
import common from '@ohos.app.ability.common';

const TAG = 'ByodActivationPage';

@Entry
@Component
struct ByodActivationPage {

  @Builder
  topBuilder() {
    Text($r('app.string.byodActivationPageTitle'))
      .fontColor($r('sys.color.ohos_id_color_text_primary'))
      .fontWeight(FontWeight.Bold)
      .lineHeight('27vp')
      .fontSize('20vp')
  }

  @Builder
  centerBuilder() {
  }

  @Builder
  bottomBuilder() {
    Row({ space: '12vp' }) {
      BottomButton({
        description: $r('app.string.byodDisagree'),
        buttonWidth: '158vp',
        isEnabled: true
      })
        .onClick(() => {
          (getContext(this) as common.UIAbilityContext).terminateSelf();
        })

      BottomButton({
        description: $r('app.string.byodAgree'),
        buttonWidth: '158vp',
        isEnabled: true
      })
        .onClick(() => {
          AlertDialog.show(
            {
              title: $r('app.string.canNotActivate'),
              message: $r('app.string.doNotSupport'),
              autoCancel: true,
              alignment: DialogAlignment.Center,
              gridCount: 4,
              confirm: {
                value: $r('app.string.gotIt'),
                action: () => {
                  (getContext(this) as common.UIAbilityContext).terminateSelf();
                }
              },
              cancel: () => {
                console.info('Closed callbacks')
              }
            }
          )
        })
    }
  }

  build() {
    Column() {
      BaseByodAdminPage({
        topBuilderParam: () => {
          this.topBuilder()
        },
        listTitle: '',
        centerBuilderParam: () => {
          this.centerBuilder()
        },
        bottomBuilderParam: () => {
          this.bottomBuilder()
        }
      })
    }
  }
}
