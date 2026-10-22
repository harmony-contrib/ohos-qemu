import { Journal, RUN, CASE } from '../common/Journal';
@Entry
@Component
struct Index {
  build() {
    Column({space: 16}) {
      Text('SERVICES579 ' + CASE + ' ' + RUN.substring(0, 12)).fontColor('#FFFFFF').fontSize(24)
      Button('Caller touch').id('services579-caller-touch').onClick(() => Journal.record('caller-touch'))
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor('#173F69')
  }
}
