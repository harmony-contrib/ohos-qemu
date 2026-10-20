import { Driver } from '../common/Driver';
import { Journal, RUN } from '../common/Journal';
import { BusinessError } from '@ohos.base';

@Entry
@Component
struct Index {
  build() {
    Column({space: 16}) {
      Text('SESSION578 ' + RUN.substring(0, 8)).fontColor('#FFFFFF').fontSize(28)
      XComponent({id: 'services578-pip', type: XComponentType.SURFACE, controller: Driver.xController})
        .width(320).height(180).onLoad(() => Journal.record('xcomponent-ready'))
      Button('Main touch').id('services578-touch').onClick(() => Journal.record('touch'))
      Button('Cancel floating ball').id('services578-ball-cancel').onClick(() => {
        Driver.userCancelBall().catch((error: BusinessError) => Journal.fail('ball-user-cancel-error', error));
      })
    }.width('100%').height('100%').backgroundColor('#153B69').justifyContent(FlexAlign.Center)
  }
}
