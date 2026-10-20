import { Journal, RUN, ENDPOINT } from '../common/Journal';
import { Driver } from '../common/Driver';
import common from '@ohos.app.ability.common';
import { BusinessError } from '@ohos.base';
@Entry
@Component
struct Index {
  private surface: XComponentController = new XComponentController();
  build() {
    Column({space: 8}) {
      Text('Pair579 ' + ENDPOINT + ' ' + RUN.substring(0, 12)).fontSize(20)
        // The real CastStreamPlayer requires a producer surface even for its
        // audio item. This creates a normal app surface, never a provider stub.
        XComponent({id: 'paired579-sink-surface', type: XComponentType.SURFACE, controller: this.surface})
          .width('100%').height('70%')
          .onLoad(() => { Driver.surfaceId = this.surface.getXComponentSurfaceId();
            Journal.record('actual-app-surface', JSON.stringify(Driver.surfaceId)); })
      Button('Open actual cast picker').id('paired579-picker').onClick(() => {
        Driver.picker(getContext(this) as common.UIAbilityContext)
          .catch((error: BusinessError) => Journal.fail('picker-ui-error', error));
      })
    }.width('100%').height('100%').backgroundColor('#173F69')
  }
}
